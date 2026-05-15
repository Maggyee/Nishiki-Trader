"""Import a small Binance kline sample into Nautilus `ParquetDataCatalog`.

This is a Phase 2 fixture tool, not a live data service. It reads one Binance
spot kline CSV/ZIP, writes the instrument + bars into `data/catalog/`, and can
optionally seed a few deterministic demo `SignalEvent v1` rows so the Phase 2
backtest runner can be smoke-tested end to end against real market bars.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import DuplicateSignalError, SignalStore

BINANCE_SPOT_DAILY_BASE_URL = "https://data.binance.vision/data/spot/daily/klines"

_BINANCE_KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]

_INTERVAL_TO_BAR_STEP = {
    "1m": "1-MINUTE",
    "3m": "3-MINUTE",
    "5m": "5-MINUTE",
    "15m": "15-MINUTE",
    "30m": "30-MINUTE",
    "1h": "1-HOUR",
    "4h": "4-HOUR",
    "1d": "1-DAY",
}


@dataclass(frozen=True)
class BackfillResult:
    catalog_path: str
    raw_path: str
    instrument_id: str
    bar_type: str
    bars_written: int
    first_bar_ts_ns: int
    last_bar_ts_ns: int
    signal_store_path: str | None = None
    demo_signals_written: int = 0
    demo_signal_duplicates: int = 0
    demo_signal_source: str | None = None
    demo_signal_model_version: str | None = None


def run_backfill(
    *,
    raw_path: Path | None,
    download: bool,
    symbol: str,
    interval: str,
    date: str | None,
    raw_output_dir: Path,
    catalog_path: Path,
    max_rows: int | None = None,
    seed_demo_signals: bool = False,
    signal_store_path: Path | None = None,
    signal_source: str = "manual_research",
    signal_model_version: str = "binance-fixture-v1",
    signal_horizon: str = "15m",
    venue_name: str = "BINANCE",
) -> BackfillResult:
    symbol = symbol.upper()
    venue_name = venue_name.upper()
    if download:
        if date is None:
            raise ValueError("--date is required with --download")
        raw_path = download_daily_klines(
            symbol=symbol,
            interval=interval,
            date=date,
            output_dir=raw_output_dir,
        )
    if raw_path is None:
        raise ValueError("provide --raw-path or --download")

    instrument = _binance_spot_instrument(symbol=symbol, venue_name=venue_name)
    bar_type = bar_type_for(instrument, interval)
    bars = load_binance_klines(raw_path, instrument, bar_type, max_rows=max_rows)
    if not bars:
        raise ValueError(f"no bars parsed from {raw_path}")

    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    catalog.write_data([instrument])
    catalog.write_data(bars)

    demo_written = 0
    demo_duplicates = 0
    if seed_demo_signals:
        if signal_store_path is None:
            raise ValueError("signal_store_path is required when seeding demo signals")
        demo_written, demo_duplicates = seed_demo_signals_from_bars(
            signal_store_path=signal_store_path,
            bars=bars,
            symbol=symbol,
            venue_name=venue_name,
            source=signal_source,
            model_version=signal_model_version,
            horizon=signal_horizon,
        )

    return BackfillResult(
        catalog_path=str(catalog_path),
        raw_path=str(raw_path),
        instrument_id=instrument.id.value,
        bar_type=str(bar_type),
        bars_written=len(bars),
        first_bar_ts_ns=int(bars[0].ts_event),
        last_bar_ts_ns=int(bars[-1].ts_event),
        signal_store_path=str(signal_store_path) if signal_store_path else None,
        demo_signals_written=demo_written,
        demo_signal_duplicates=demo_duplicates,
        demo_signal_source=signal_source if seed_demo_signals else None,
        demo_signal_model_version=signal_model_version if seed_demo_signals else None,
    )


def download_daily_klines(
    *,
    symbol: str,
    interval: str,
    date: str,
    output_dir: Path,
) -> Path:
    file_name = f"{symbol}-{interval}-{date}.zip"
    url = f"{BINANCE_SPOT_DAILY_BASE_URL}/{symbol}/{interval}/{file_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / file_name
    if destination.exists():
        return destination
    urllib.request.urlretrieve(url, destination)  # noqa: S310 - public market data URL.
    return destination


def load_binance_klines(
    path: Path,
    instrument: CurrencyPair,
    bar_type: BarType,
    *,
    max_rows: int | None = None,
) -> list[Bar]:
    raw = _read_kline_dataframe(path)
    raw = raw.iloc[:, : len(_BINANCE_KLINE_COLUMNS)].copy()
    raw.columns = _BINANCE_KLINE_COLUMNS[: len(raw.columns)]
    raw["open_time"] = pd.to_numeric(raw["open_time"], errors="coerce")
    raw = raw[raw["open_time"].notna()].copy()
    if raw.empty:
        return []

    raw["open_time"] = raw["open_time"].astype("int64")
    raw = raw.sort_values("open_time", kind="mergesort").drop_duplicates("open_time")
    if max_rows is not None:
        raw = raw.head(max_rows)

    bars_df = pd.DataFrame(
        {
            "open": pd.to_numeric(raw["open"], errors="raise").to_numpy(),
            "high": pd.to_numeric(raw["high"], errors="raise").to_numpy(),
            "low": pd.to_numeric(raw["low"], errors="raise").to_numpy(),
            "close": pd.to_numeric(raw["close"], errors="raise").to_numpy(),
            "volume": pd.to_numeric(raw["volume"], errors="raise").to_numpy(),
        },
        index=pd.to_datetime(raw["open_time"], unit="ms", utc=True),
    )
    bars_df.index.name = "timestamp"
    return BarDataWrangler(bar_type, instrument).process(bars_df)


def _read_kline_dataframe(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise ValueError(f"{path} contains no CSV file")
            with zf.open(sorted(csv_names)[0]) as f:
                return pd.read_csv(f, header=None)
    return pd.read_csv(path, header=None)


def bar_type_for(instrument: CurrencyPair, interval: str) -> BarType:
    step = _INTERVAL_TO_BAR_STEP.get(interval)
    if step is None:
        supported = ", ".join(sorted(_INTERVAL_TO_BAR_STEP))
        raise ValueError(f"unsupported interval {interval!r}; supported: {supported}")
    return BarType.from_str(f"{instrument.id}-{step}-LAST-EXTERNAL")


def seed_demo_signals_from_bars(
    *,
    signal_store_path: Path,
    bars: list[Bar],
    symbol: str,
    venue_name: str,
    source: str,
    model_version: str,
    horizon: str,
) -> tuple[int, int]:
    if len(bars) < 3:
        raise ValueError("need at least 3 bars to seed demo signals")
    store = SignalStore(signal_store_path)
    indexes = sorted({len(bars) // 4, len(bars) // 2, (len(bars) * 3) // 4})
    sides = ["buy", "flat", "sell"]
    written = 0
    duplicates = 0
    for idx, side in zip(indexes, sides, strict=False):
        ts_event = int(bars[idx].ts_event)
        score = {"buy": 0.70, "flat": 0.0, "sell": -0.70}[side]
        event = SignalEvent.model_validate(
            {
                "schema_version": "signal.v1",
                "signal_id": f"{source}:{symbol}:{venue_name}:{model_version}:{ts_event}:{side}",
                "symbol": symbol,
                "venue": venue_name,
                "ts_event": ts_event,
                "horizon": horizon,
                "side": side,
                "score": score,
                "confidence": 0.75,
                "source": source,
                "model_version": model_version,
                "ttl_seconds": 900,
                "features_hash": None,
                "metadata": {
                    "fixture": "binance_klines",
                    "bar_index": idx,
                    "note": "demo signal only; not research alpha",
                },
            }
        )
        try:
            store.write(event)
            written += 1
        except DuplicateSignalError:
            duplicates += 1
    return written, duplicates


def _binance_spot_instrument(*, symbol: str, venue_name: str) -> CurrencyPair:
    if symbol != "BTCUSDT" or venue_name != "BINANCE":
        raise ValueError(
            "only BTCUSDT.BINANCE spot is supported by the Phase 2 fixture importer"
        )
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=Symbol("BTCUSDT"), venue=Venue("BINANCE")),
        raw_symbol=Symbol("BTCUSDT"),
        base_currency=BTC,
        quote_currency=USDT,
        price_precision=2,
        size_precision=6,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.000001"),
        lot_size=None,
        max_quantity=Quantity.from_str("9000.000000"),
        min_quantity=Quantity.from_str("0.000001"),
        max_notional=None,
        min_notional=Money.from_str("10.00000000 USDT"),
        max_price=Price.from_str("1000000.00"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal(0),
        margin_maint=Decimal(0),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Binance spot klines into data/catalog for Phase 2 backtests.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw-path", type=Path, help="Local Binance kline CSV or ZIP")
    source.add_argument(
        "--download",
        action="store_true",
        help="Download one daily public Binance kline ZIP before importing",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--venue", default="BINANCE")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--date", help="YYYY-MM-DD, required with --download")
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=Path("data/raw/binance/spot/daily/klines"),
    )
    parser.add_argument("--catalog-path", type=Path, default=Path("data/catalog"))
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--seed-demo-signals", action="store_true")
    parser.add_argument(
        "--signal-store-path",
        type=Path,
        default=Path("data/bridge/signals.db"),
    )
    parser.add_argument("--signal-source", default="manual_research")
    parser.add_argument("--signal-model-version", default="binance-fixture-v1")
    parser.add_argument("--signal-horizon", default="15m")
    return parser


def _json_ready(result: BackfillResult) -> dict[str, Any]:
    return asdict(result)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_backfill(
            raw_path=args.raw_path,
            download=args.download,
            symbol=args.symbol,
            interval=args.interval,
            date=args.date,
            raw_output_dir=args.raw_output_dir,
            catalog_path=args.catalog_path,
            max_rows=args.max_rows,
            seed_demo_signals=args.seed_demo_signals,
            signal_store_path=args.signal_store_path,
            signal_source=args.signal_source,
            signal_model_version=args.signal_model_version,
            signal_horizon=args.signal_horizon,
            venue_name=args.venue,
        )
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(_json_ready(result), indent=2, sort_keys=True))
    return 0


__all__ = [
    "BackfillResult",
    "bar_type_for",
    "download_daily_klines",
    "load_binance_klines",
    "run_backfill",
    "seed_demo_signals_from_bars",
]


if __name__ == "__main__":
    raise SystemExit(main())

"""Pre-registered taker-flow and funding-positioning Spot research signals."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.ops.backfill_bars import (
    _BINANCE_KLINE_COLUMNS,
    _infer_unix_timestamp_unit,
    _read_kline_dataframe,
)
from apps.strategies_freqtrade.research.multi_asset_rotation_signals import (
    UNIVERSE,
    _transition,
    _within_decision_window,
)

STRATEGY_IDENTITIES = {
    "taker_flow_rotation": (
        "rule_taker_flow_rotation_v1",
        "buyshare7d-ret20-weekly-cash-v1",
    ),
    "flow_exhaustion": (
        "rule_flow_exhaustion_v1",
        "retq10-180-buyshare0.40-vol2x-exit12h-4h-v1",
    ),
    "funding_crowding": (
        "rule_funding_crowding_rotation_v1",
        "ret90-funding7d-z30lt1.5-weekly-cash-v1",
    ),
}

SpotFrames = dict[str, pd.DataFrame]
FundingSeries = dict[str, pd.Series]


def _aligned_field(frames: SpotFrames, field: str) -> pd.DataFrame:
    if set(frames) != set(UNIVERSE):
        raise ValueError(f"spot frames must contain exactly {UNIVERSE}")
    aligned = pd.DataFrame({symbol: frames[symbol][field] for symbol in UNIVERSE})
    if aligned.empty or aligned.isna().any().any():
        raise ValueError(f"aligned {field} is empty or incomplete")
    return aligned


def _timestamps(frames: SpotFrames) -> pd.DataFrame:
    return _aligned_field(frames, "ts_event").astype("int64")


def generate_taker_flow_rotation(
    daily: SpotFrames,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["taker_flow_rotation"]
    closes = _aligned_field(daily, "close")
    quote = _aligned_field(daily, "quote_volume")
    taker = _aligned_field(daily, "taker_buy_quote")
    timestamps = _timestamps(daily)
    buy_share = taker.shift(1).rolling(7, min_periods=7).sum() / quote.shift(1).rolling(
        7, min_periods=7
    ).sum()
    returns = closes.shift(1) / closes.shift(21) - 1.0
    decision_mask = closes.index.weekday == 0
    decision_mask &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    selected: str | None = None
    events: list[SignalEvent] = []
    for ts in closes.index[decision_mask]:
        shares = buy_share.loc[ts]
        rets = returns.loc[ts]
        if shares.isna().any() or rets.isna().any():
            continue
        eligible = [
            symbol
            for symbol in UNIVERSE
            if float(shares[symbol]) > 0.5 and float(rets[symbol]) > 0.0
        ]
        next_asset = max(eligible, key=lambda symbol: float(shares[symbol])) if eligible else None
        events.extend(
            _transition(
                previous=selected,
                selected=next_asset,
                day=ts,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="weekly_taker_flow_rotation",
                metadata={
                    "buy_share_days": 7,
                    "buy_share_floor": 0.5,
                    "return_days": 20,
                    "buy_shares": {
                        symbol: round(float(shares[symbol]), 10) for symbol in UNIVERSE
                    },
                    "returns": {
                        symbol: round(float(rets[symbol]), 10) for symbol in UNIVERSE
                    },
                },
            )
        )
        selected = next_asset
    return events


def generate_flow_exhaustion(
    four_hour: SpotFrames,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    source, model_version = STRATEGY_IDENTITIES["flow_exhaustion"]
    opens = _aligned_field(four_hour, "open")
    closes = _aligned_field(four_hour, "close")
    quote = _aligned_field(four_hour, "quote_volume")
    taker = _aligned_field(four_hour, "taker_buy_quote")
    timestamps = _timestamps(four_hour)
    returns = closes / opens - 1.0
    return_floor = returns.shift(1).rolling(180, min_periods=180).quantile(0.10)
    volume_median = quote.shift(1).rolling(42, min_periods=42).median()
    buy_share = taker / quote
    decision_mask = _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    selected: str | None = None
    held_bars = 0
    events: list[SignalEvent] = []
    for ts in closes.index[decision_mask]:
        if selected is not None:
            held_bars += 1
            recovered = float(buy_share.loc[ts, selected]) >= 0.5
            if held_bars >= 3 or recovered:
                events.extend(
                    _transition(
                        previous=selected,
                        selected=None,
                        day=ts,
                        timestamps=timestamps,
                        source=source,
                        model_version=model_version,
                        trigger="four_hour_flow_exhaustion",
                        metadata={
                            "held_bars": held_bars,
                            "maximum_holding_bars": 3,
                            "flow_recovered": recovered,
                        },
                    )
                )
                selected = None
                held_bars = 0
            continue

        candidates = []
        for symbol in UNIVERSE:
            values = (
                returns.loc[ts, symbol],
                return_floor.loc[ts, symbol],
                volume_median.loc[ts, symbol],
                buy_share.loc[ts, symbol],
            )
            if any(pd.isna(value) for value in values):
                continue
            if (
                float(returns.loc[ts, symbol]) <= float(return_floor.loc[ts, symbol])
                and float(buy_share.loc[ts, symbol]) <= 0.40
                and float(quote.loc[ts, symbol])
                >= 2.0 * float(volume_median.loc[ts, symbol])
            ):
                candidates.append(symbol)
        next_asset = (
            min(candidates, key=lambda symbol: float(returns.loc[ts, symbol]))
            if candidates
            else None
        )
        if next_asset is None:
            continue
        events.extend(
            _transition(
                previous=None,
                selected=next_asset,
                day=ts,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="four_hour_flow_exhaustion",
                metadata={
                    "return_quantile": 0.10,
                    "return_lookback_bars": 180,
                    "buy_share_ceiling": 0.40,
                    "volume_median_bars": 42,
                    "volume_multiple": 2.0,
                    "maximum_holding_bars": 3,
                    "entry_return": round(float(returns.loc[ts, next_asset]), 10),
                    "entry_buy_share": round(float(buy_share.loc[ts, next_asset]), 10),
                },
            )
        )
        selected = next_asset
        held_bars = 0
    return events


def generate_funding_crowding_rotation(
    daily: SpotFrames,
    funding: FundingSeries,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[SignalEvent]:
    if set(funding) != set(UNIVERSE):
        raise ValueError(f"funding must contain exactly {UNIVERSE}")
    source, model_version = STRATEGY_IDENTITIES["funding_crowding"]
    closes = _aligned_field(daily, "close")
    timestamps = _timestamps(daily)
    daily_funding = pd.DataFrame(
        {
            symbol: funding[symbol].resample("1D").mean().reindex(closes.index)
            for symbol in UNIVERSE
        }
    )
    funding_7d = daily_funding.shift(1).rolling(7, min_periods=7).mean()
    funding_mean = daily_funding.shift(1).rolling(30, min_periods=30).mean()
    funding_std = daily_funding.shift(1).rolling(30, min_periods=30).std(ddof=0)
    funding_z = (funding_7d - funding_mean) / funding_std.replace(0.0, np.nan)
    returns = closes.shift(1) / closes.shift(91) - 1.0
    decision_mask = closes.index.weekday == 0
    decision_mask &= _within_decision_window(
        closes.index,
        start_date=start_date,
        end_date=end_date,
    )
    selected: str | None = None
    events: list[SignalEvent] = []
    for ts in closes.index[decision_mask]:
        zscores = funding_z.loc[ts]
        rets = returns.loc[ts]
        if zscores.isna().any() or rets.isna().any():
            continue
        eligible = [
            symbol
            for symbol in UNIVERSE
            if float(rets[symbol]) > 0.0 and float(zscores[symbol]) <= 1.5
        ]
        next_asset = max(eligible, key=lambda symbol: float(rets[symbol])) if eligible else None
        events.extend(
            _transition(
                previous=selected,
                selected=next_asset,
                day=ts,
                timestamps=timestamps,
                source=source,
                model_version=model_version,
                trigger="weekly_funding_crowding_rotation",
                metadata={
                    "return_days": 90,
                    "funding_signal_days": 7,
                    "funding_zscore_days": 30,
                    "funding_zscore_ceiling": 1.5,
                    "funding_zscores": {
                        symbol: round(float(zscores[symbol]), 10) for symbol in UNIVERSE
                    },
                    "returns": {
                        symbol: round(float(rets[symbol]), 10) for symbol in UNIVERSE
                    },
                },
            )
        )
        selected = next_asset
    return events


def load_spot_aggregates(
    directory: Path,
    symbol: str,
    frequency: str,
    *,
    source_interval: str = "1m",
) -> pd.DataFrame:
    paths = sorted(directory.glob(f"{symbol}-{source_interval}-*.zip"))
    if not paths:
        raise FileNotFoundError(
            f"no {symbol} {source_interval} archives in {directory}"
        )
    rows = []
    for path in paths:
        raw = _read_kline_dataframe(path).iloc[:, : len(_BINANCE_KLINE_COLUMNS)].copy()
        raw.columns = _BINANCE_KLINE_COLUMNS[: len(raw.columns)]
        required = {"open_time", "open", "close", "quote_asset_volume", "taker_buy_quote_asset_volume"}
        if not required <= set(raw.columns):
            raise ValueError(f"{path} is missing required kline flow columns")
        open_time = pd.to_numeric(raw["open_time"], errors="raise").astype("int64")
        unit = _infer_unix_timestamp_unit(open_time)
        frame = pd.DataFrame(
            {
                "open": pd.to_numeric(raw["open"], errors="raise").to_numpy(),
                "close": pd.to_numeric(raw["close"], errors="raise").to_numpy(),
                "quote_volume": pd.to_numeric(
                    raw["quote_asset_volume"], errors="raise"
                ).to_numpy(),
                "taker_buy_quote": pd.to_numeric(
                    raw["taker_buy_quote_asset_volume"], errors="raise"
                ).to_numpy(),
                "ts_event": pd.to_datetime(open_time, unit=unit, utc=True)
                .astype("int64")
                .to_numpy(),
            },
            index=pd.to_datetime(open_time, unit=unit, utc=True),
        )
        grouped = frame.resample(frequency, label="left", closed="left").agg(
            {
                "open": "first",
                "close": "last",
                "quote_volume": "sum",
                "taker_buy_quote": "sum",
                "ts_event": "last",
            }
        )
        rows.append(grouped.dropna())
    result = pd.concat(rows).sort_index()
    result = result.loc[~result.index.duplicated(keep="last")]
    if (result["quote_volume"] <= 0.0).any():
        raise ValueError(f"{symbol} has non-positive quote volume aggregates")
    if (
        (result["taker_buy_quote"] < 0.0)
        | (result["taker_buy_quote"] > result["quote_volume"])
    ).any():
        raise ValueError(f"{symbol} has invalid taker-buy quote volume")
    return result


def load_funding_archives(directory: Path, symbol: str) -> pd.Series:
    paths = sorted(directory.glob(f"{symbol}-fundingRate-*.zip"))
    if not paths:
        raise FileNotFoundError(f"no {symbol} funding archives in {directory}")
    rows = []
    for path in paths:
        raw = pd.read_csv(path, compression="zip")
        normalized = {str(column).strip().lower(): column for column in raw.columns}
        timestamp_column = next(
            (normalized[name] for name in ("calc_time", "funding_time") if name in normalized),
            None,
        )
        rate_column = next(
            (
                normalized[name]
                for name in ("last_funding_rate", "funding_rate")
                if name in normalized
            ),
            None,
        )
        if timestamp_column is None or rate_column is None:
            raise ValueError(f"{path} has unsupported funding columns {list(raw.columns)}")
        timestamps = pd.to_numeric(raw[timestamp_column], errors="raise").astype("int64")
        unit = _infer_unix_timestamp_unit(timestamps)
        values = pd.to_numeric(raw[rate_column], errors="raise").astype("float64")
        rows.append(pd.Series(values.to_numpy(), index=pd.to_datetime(timestamps, unit=unit, utc=True)))
    result = pd.concat(rows).sort_index()
    if result.index.duplicated().any() or not np.isfinite(result.to_numpy()).all():
        raise ValueError(f"{symbol} funding contains duplicates or non-finite values")
    return result


GENERATORS: dict[str, Callable[..., list[SignalEvent]]] = {
    "taker_flow_rotation": generate_taker_flow_rotation,
    "flow_exhaustion": generate_flow_exhaustion,
    "funding_crowding": generate_funding_crowding_rotation,
}


def _parse_directory(value: str) -> tuple[str, Path]:
    symbol, separator, directory = value.partition("=")
    symbol = symbol.strip().upper()
    if not separator or symbol not in UNIVERSE or not directory.strip():
        raise argparse.ArgumentTypeError("directory must be SYMBOL=PATH for the locked universe")
    return symbol, Path(directory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(GENERATORS), required=True)
    parser.add_argument("--spot-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--funding-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    spot_dirs = dict(args.spot_dir)
    if set(spot_dirs) != set(UNIVERSE):
        raise SystemExit(f"provide exactly one --spot-dir for each of {UNIVERSE}")
    frequency = "4h" if args.strategy == "flow_exhaustion" else "1D"
    spot = {
        symbol: load_spot_aggregates(spot_dirs[symbol], symbol, frequency)
        for symbol in UNIVERSE
    }
    if args.strategy == "funding_crowding":
        funding_dirs = dict(args.funding_dir)
        if set(funding_dirs) != set(UNIVERSE):
            raise SystemExit(f"provide exactly one --funding-dir for each of {UNIVERSE}")
        funding = {
            symbol: load_funding_archives(funding_dirs[symbol], symbol)
            for symbol in UNIVERSE
        }
        events = generate_funding_crowding_rotation(
            spot,
            funding,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    else:
        events = GENERATORS[args.strategy](
            spot,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    source, model_version = STRATEGY_IDENTITIES[args.strategy]
    print(f"generated {len(events)} signals for {source} / {model_version}")
    if args.dry_run:
        for event in events[:10]:
            print(f"  {event.signal_id} side={event.side}")
        return 0
    written, duplicates = SignalStore(args.signal_store_path).write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

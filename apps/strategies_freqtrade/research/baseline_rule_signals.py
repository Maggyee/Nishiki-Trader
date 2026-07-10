"""Rule-based baseline `SignalEvent v1` generator.

Phase 2 research-to-bridge pipeline smoke. Reads OHLCV bars from a
NautilusTrader `ParquetDataCatalog`, computes an EMA(5)/EMA(20) crossover
with an RSI(14) overbought/oversold filter, and emits one `SignalEvent`
per accepted cross. Writes events through the canonical bridge
(`apps.bridge.store.SignalStore`).

This is not a production strategy. Its purpose is to exercise the full
research → bridge → backtest_runner path end-to-end with non-demo signals
so strategy/runner changes have a reproducible baseline to compare against.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore

DEFAULT_SOURCE = "rule_baseline_v1"
DEFAULT_MODEL_VERSION = "ema5-20+rsi14"


@dataclass(frozen=True)
class RuleParams:
    fast_period: int = 5
    slow_period: int = 20
    rsi_period: int = 14
    rsi_upper: float = 70.0
    rsi_lower: float = 30.0
    ttl_seconds: int = 120

    def __post_init__(self) -> None:
        if self.fast_period >= self.slow_period:
            raise ValueError(
                f"fast_period={self.fast_period} must be < slow_period={self.slow_period}"
            )
        if self.rsi_period < 2:
            raise ValueError(f"rsi_period must be >= 2, got {self.rsi_period}")
        if not 0.0 < self.rsi_lower < self.rsi_upper < 100.0:
            raise ValueError(
                f"need 0 < rsi_lower < rsi_upper < 100, "
                f"got lower={self.rsi_lower} upper={self.rsi_upper}"
            )
        if self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {self.ttl_seconds}")


def generate_rule_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    horizon: str = "1m",
    params: RuleParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    """Return `SignalEvent`s for EMA-cross points that pass the RSI filter.

    `bars` must contain a `close` column and either a `ts_event` column (int
    ns UTC or datetime64) or a `DatetimeIndex` that names `ts_event` after
    normalisation. Output is sorted by `ts_event`.
    """
    rules = params or RuleParams()
    df = _normalize_bar_frame(bars)
    if df.empty:
        return []

    fast = df["close"].ewm(span=rules.fast_period, adjust=False).mean()
    slow = df["close"].ewm(span=rules.slow_period, adjust=False).mean()
    rsi = _rsi(df["close"], period=rules.rsi_period)
    spread = fast - slow
    prev_spread = spread.shift(1)

    signals: list[SignalEvent] = []
    for i in range(len(df)):
        prev = prev_spread.iloc[i]
        curr = spread.iloc[i]
        rsi_now = rsi.iloc[i]
        if pd.isna(prev) or pd.isna(rsi_now):
            continue
        crossed_up = prev <= 0 and curr > 0
        crossed_dn = prev >= 0 and curr < 0
        if not (crossed_up or crossed_dn):
            continue

        classified = _classify(
            crossed_up=crossed_up,
            rsi=float(rsi_now),
            params=rules,
        )
        if classified is None:
            continue
        side, score, confidence = classified

        ts_event = int(df["ts_event"].iloc[i])
        signal_id = _make_signal_id(
            source=source,
            model_version=model_version,
            symbol=symbol,
            venue=venue,
            ts_event_ns=ts_event,
            side=side,
        )
        signals.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": signal_id,
                    "symbol": symbol,
                    "venue": venue,
                    "ts_event": ts_event,
                    "horizon": horizon,
                    "side": side,
                    "score": score,
                    "confidence": confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": rules.ttl_seconds,
                    "features_hash": None,
                    "metadata": {
                        "fast_period": rules.fast_period,
                        "slow_period": rules.slow_period,
                        "rsi_period": rules.rsi_period,
                        "rsi": round(float(rsi_now), 4),
                        "spread": round(float(curr), 6),
                    },
                }
            )
        )
    return signals


def _normalize_bar_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if "ts_event" in bars.columns:
        df = bars.copy()
    elif pd.api.types.is_datetime64_any_dtype(bars.index):
        df = bars.reset_index()
        df = df.rename(columns={bars.index.name or "index": "ts_event"})
    else:
        raise ValueError("bars must have a 'ts_event' column or a DatetimeIndex")

    if (
        pd.api.types.is_datetime64_any_dtype(df["ts_event"])
        or df["ts_event"].dtype == "object"
    ):
        df["ts_event"] = pd.to_datetime(
            df["ts_event"], utc=True, errors="coerce"
        ).astype("int64")

    if "close" not in df.columns:
        raise ValueError(f"bars must contain 'close' column, got {list(df.columns)}")

    df = df.sort_values("ts_event", kind="mergesort").reset_index(drop=True)
    return df


def _rsi(close: pd.Series, *, period: int) -> pd.Series:
    diff = close.diff()
    gain = diff.clip(lower=0.0)
    loss = (-diff).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _classify(
    *, crossed_up: bool, rsi: float, params: RuleParams
) -> tuple[str, float, float] | None:
    """Map a cross + RSI reading to (side, score, confidence) or skip.

    Confidence is a linear function of how far RSI is from the contraindicating
    extreme (overbought for buys, oversold for sells), clamped to [0.5, 1.0]
    over the band width.
    """
    band = params.rsi_upper - params.rsi_lower
    if crossed_up:
        if rsi >= params.rsi_upper:
            return None
        confidence = 0.5 + 0.5 * min(1.0, (params.rsi_upper - rsi) / band)
        return "buy", 0.6, float(confidence)
    if rsi <= params.rsi_lower:
        return None
    confidence = 0.5 + 0.5 * min(1.0, (rsi - params.rsi_lower) / band)
    return "sell", -0.6, float(confidence)


def _make_signal_id(
    *,
    source: str,
    model_version: str,
    symbol: str,
    venue: str,
    ts_event_ns: int,
    side: str,
) -> str:
    return f"{source}:{model_version}:{symbol}:{venue}:{ts_event_ns}:{side}"


def _load_bars_from_catalog(
    catalog_path: Path, bar_type: str
) -> pd.DataFrame:
    from nautilus_trader.model.data import BarType
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    bars = catalog.bars(bar_types=[BarType.from_str(bar_type)])
    if not bars:
        raise SystemExit(f"no bars found in {catalog_path} for bar_type={bar_type}")
    rows = [
        {
            "ts_event": int(b.ts_event),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
        }
        for b in bars
    ]
    return pd.DataFrame(rows)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--horizon", default="1m")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--fast-period", type=int, default=5)
    parser.add_argument("--slow-period", type=int, default=20)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-upper", type=float, default=70.0)
    parser.add_argument("--rsi-lower", type=float, default=30.0)
    parser.add_argument("--ttl-seconds", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    params = RuleParams(
        fast_period=args.fast_period,
        slow_period=args.slow_period,
        rsi_period=args.rsi_period,
        rsi_upper=args.rsi_upper,
        rsi_lower=args.rsi_lower,
        ttl_seconds=args.ttl_seconds,
    )
    bars = _load_bars_from_catalog(args.catalog_path, args.bar_type)
    events = generate_rule_signals(
        bars,
        symbol=args.symbol,
        venue=args.venue,
        horizon=args.horizon,
        params=params,
        source=args.source,
        model_version=args.model_version,
    )

    print(f"generated {len(events)} signals from {len(bars)} bars")
    if args.dry_run:
        for ev in events[:10]:
            print(f"  {ev.signal_id} side={ev.side} conf={ev.confidence:.3f}")
        if len(events) > 10:
            print(f"  ... +{len(events) - 10} more")
        return 0

    store = SignalStore(args.signal_store_path)
    written, skipped = store.write_many(events)
    print(f"wrote {written}, skipped {skipped} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SOURCE",
    "RuleParams",
    "generate_rule_signals",
    "main",
]

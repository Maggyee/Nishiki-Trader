"""Long/flat 15-minute Donchian/ATR research signal generator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    _load_bars_from_catalog,
    _make_signal_id,
    _normalize_bar_frame,
)

DEFAULT_SOURCE = "rule_breakout_v1"
DEFAULT_MODEL_VERSION = "donchian20-10-atr14x0.25-15m"


@dataclass(frozen=True)
class BreakoutRuleParams:
    entry_bars: int = 20
    exit_bars: int = 10
    atr_bars: int = 14
    atr_multiplier: float = 0.25
    timeframe_minutes: int = 15
    ttl_seconds: int = 900

    def __post_init__(self) -> None:
        if min(self.entry_bars, self.exit_bars, self.atr_bars) <= 0:
            raise ValueError("entry_bars, exit_bars and atr_bars must be positive")
        if self.atr_multiplier < 0.0:
            raise ValueError("atr_multiplier must be non-negative")
        if self.timeframe_minutes <= 0 or self.ttl_seconds <= 0:
            raise ValueError("timeframe_minutes and ttl_seconds must be positive")


def resample_ohlcv_15m(
    bars: pd.DataFrame,
    *,
    timeframe_minutes: int = 15,
) -> pd.DataFrame:
    df = _normalize_bar_frame(bars)
    missing = [column for column in ("open", "high", "low") if column not in df]
    if missing:
        raise ValueError(f"bars missing required columns: {missing}")
    for column in ("open", "high", "low"):
        df[column] = pd.to_numeric(df[column], errors="raise").astype(float)
    timestamps = pd.to_datetime(df["ts_event"], unit="ns", utc=True)
    indexed = df.assign(timestamp=timestamps).set_index("timestamp")
    rule = f"{timeframe_minutes}min"
    sampled = indexed.resample(rule, label="left", closed="left", origin="epoch").agg(
        {
            "ts_event": "max",
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return sampled.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def generate_breakout_rule_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    horizon: str = "15m",
    params: BreakoutRuleParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    cfg = params or BreakoutRuleParams()
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    if frame.empty:
        return []

    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(cfg.atr_bars, min_periods=cfg.atr_bars).mean()
    entry_high = frame["high"].shift(1).rolling(
        cfg.entry_bars,
        min_periods=cfg.entry_bars,
    ).max()
    exit_low = frame["low"].shift(1).rolling(
        cfg.exit_bars,
        min_periods=cfg.exit_bars,
    ).min()

    state = "flat"
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if np.isnan(atr.iloc[index]) or np.isnan(entry_high.iloc[index]):
            continue
        close = float(row["close"])
        atr_now = float(atr.iloc[index])
        side: str | None = None
        trigger = ""
        if state == "flat" and close > float(entry_high.iloc[index]) + cfg.atr_multiplier * atr_now:
            state = "long"
            side = "buy"
            trigger = "donchian_entry"
        elif (
            state == "long"
            and not np.isnan(exit_low.iloc[index])
            and close < float(exit_low.iloc[index]) - cfg.atr_multiplier * atr_now
        ):
            state = "flat"
            side = "flat"
            trigger = "donchian_exit"
        if side is None:
            continue

        ts_event = int(row["ts_event"])
        events.append(
            SignalEvent.model_validate(
                {
                    "schema_version": "signal.v1",
                    "signal_id": _make_signal_id(
                        source=source,
                        model_version=model_version,
                        symbol=symbol,
                        venue=venue,
                        ts_event_ns=ts_event,
                        side=side,
                    ),
                    "symbol": symbol,
                    "venue": venue,
                    "ts_event": ts_event,
                    "horizon": horizon,
                    "side": side,
                    "score": 0.75 if side == "buy" else 0.0,
                    "confidence": 0.75,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": None,
                    "metadata": {
                        "algorithm": "donchian_atr_long_flat",
                        "trigger": trigger,
                        "timeframe_minutes": cfg.timeframe_minutes,
                        "entry_bars": cfg.entry_bars,
                        "exit_bars": cfg.exit_bars,
                        "atr_bars": cfg.atr_bars,
                        "atr_multiplier": cfg.atr_multiplier,
                        "atr": round(atr_now, 8),
                        "spot_target": state,
                    },
                }
            )
        )
    return events


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    bars = _load_bars_from_catalog(args.catalog_path, args.bar_type)
    events = generate_breakout_rule_signals(
        bars,
        symbol=args.symbol,
        venue=args.venue,
        source=args.source,
        model_version=args.model_version,
    )
    print(f"generated {len(events)} signals from {len(bars)} bars")
    if args.dry_run:
        for event in events[:10]:
            print(f"  {event.signal_id} side={event.side}")
        return 0

    store = SignalStore(args.signal_store_path)
    written, duplicates = store.write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


__all__ = [
    "BreakoutRuleParams",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SOURCE",
    "generate_breakout_rule_signals",
    "main",
    "resample_ohlcv_15m",
]


if __name__ == "__main__":
    raise SystemExit(main())

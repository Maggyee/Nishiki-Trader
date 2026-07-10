"""Low-turnover one-hour trend-regime research signal generator.

The fixed hypothesis combines EMA(24/96), positive 24-hour momentum, and an
ATR(14) buffer. It emits only long/flat ``SignalEvent v1`` state transitions
and never imports an execution or exchange API.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.breakout_rule_signals import (
    resample_ohlcv_15m,
)
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    _load_bars_from_catalog,
    _make_signal_id,
)

DEFAULT_SOURCE = "rule_trend_regime_v1"
DEFAULT_MODEL_VERSION = "ema24-96-1h-mom24-atr14x0.5-v1"


@dataclass(frozen=True)
class TrendRegimeParams:
    fast_ema_bars: int = 24
    slow_ema_bars: int = 96
    momentum_bars: int = 24
    atr_bars: int = 14
    atr_multiplier: float = 0.5
    timeframe_minutes: int = 60
    ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.fast_ema_bars <= 0 or self.slow_ema_bars <= 0:
            raise ValueError("EMA periods must be positive")
        if self.fast_ema_bars >= self.slow_ema_bars:
            raise ValueError("fast_ema_bars must be less than slow_ema_bars")
        if self.momentum_bars <= 0 or self.atr_bars <= 0:
            raise ValueError("momentum_bars and atr_bars must be positive")
        if self.atr_multiplier < 0.0:
            raise ValueError("atr_multiplier must be non-negative")
        if self.timeframe_minutes <= 0 or self.ttl_seconds <= 0:
            raise ValueError("timeframe_minutes and ttl_seconds must be positive")


def generate_trend_regime_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    horizon: str = "1h",
    params: TrendRegimeParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    cfg = params or TrendRegimeParams()
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    if frame.empty:
        return []

    close = frame["close"].astype(float)
    fast = close.ewm(span=cfg.fast_ema_bars, adjust=False).mean()
    slow = close.ewm(span=cfg.slow_ema_bars, adjust=False).mean()
    momentum = close.pct_change(cfg.momentum_bars)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(cfg.atr_bars, min_periods=cfg.atr_bars).mean()

    state = "flat"
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if np.isnan(momentum.iloc[index]) or np.isnan(atr.iloc[index]):
            continue
        close_now = float(close.iloc[index])
        fast_now = float(fast.iloc[index])
        slow_now = float(slow.iloc[index])
        atr_now = float(atr.iloc[index])
        momentum_now = float(momentum.iloc[index])
        entry = (
            fast_now > slow_now
            and close_now > slow_now + cfg.atr_multiplier * atr_now
            and momentum_now > 0.0
        )
        exit_regime = (
            fast_now < slow_now
            or close_now < slow_now - cfg.atr_multiplier * atr_now
        )
        side: str | None = None
        trigger = ""
        if state == "flat" and entry:
            state = "long"
            side = "buy"
            trigger = "trend_regime_entry"
        elif state == "long" and exit_regime:
            state = "flat"
            side = "flat"
            trigger = "trend_regime_exit"
        if side is None:
            continue

        ts_event = int(row["ts_event"])
        normalized_spread = abs(fast_now - slow_now) / max(atr_now, 1e-12)
        confidence = min(1.0, 0.6 + 0.2 * normalized_spread)
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
                    "score": min(1.0, normalized_spread) if side == "buy" else 0.0,
                    "confidence": confidence,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": None,
                    "metadata": {
                        "algorithm": "ema_momentum_atr_trend_regime_long_flat",
                        "trigger": trigger,
                        "timeframe_minutes": cfg.timeframe_minutes,
                        "fast_ema_bars": cfg.fast_ema_bars,
                        "slow_ema_bars": cfg.slow_ema_bars,
                        "momentum_bars": cfg.momentum_bars,
                        "atr_bars": cfg.atr_bars,
                        "atr_multiplier": cfg.atr_multiplier,
                        "fast_ema": round(fast_now, 8),
                        "slow_ema": round(slow_now, 8),
                        "momentum": round(momentum_now, 10),
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
    events = generate_trend_regime_signals(
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
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SOURCE",
    "TrendRegimeParams",
    "generate_trend_regime_signals",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

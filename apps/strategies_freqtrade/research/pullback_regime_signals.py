"""Causal higher-timeframe risk-on pullback-continuation signal generator.

The fixed candidate uses the previous completed daily bar for regime
permission, then waits for a one-hour pullback and recovery. It emits only
long/flat ``SignalEvent v1`` transitions and never imports an execution or
exchange API.
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

DEFAULT_SOURCE = "rule_pullback_regime_v1"
DEFAULT_MODEL_VERSION = "daily50-200-1h24-pullback-giveback1.25-v1"


@dataclass(frozen=True)
class PullbackRegimeParams:
    daily_fast_ema_days: int = 50
    daily_slow_ema_days: int = 200
    hourly_ema_bars: int = 24
    atr_bars: int = 14
    pullback_arm_hours: int = 24
    max_entry_extension_atr: float = 0.75
    progress_atr: float = 1.0
    giveback_atr: float = 1.25
    structural_stop_atr: float = 1.0
    failure_timeout_hours: int = 72
    timeframe_minutes: int = 60
    ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.daily_fast_ema_days <= 0 or self.daily_slow_ema_days <= 0:
            raise ValueError("daily EMA periods must be positive")
        if self.daily_fast_ema_days >= self.daily_slow_ema_days:
            raise ValueError("daily_fast_ema_days must be less than daily_slow_ema_days")
        if min(
            self.hourly_ema_bars,
            self.atr_bars,
            self.pullback_arm_hours,
            self.failure_timeout_hours,
            self.timeframe_minutes,
            self.ttl_seconds,
        ) <= 0:
            raise ValueError("bar periods, timeouts and TTL must be positive")
        if self.timeframe_minutes != 60:
            raise ValueError("timeframe_minutes must remain fixed at 60")
        if min(
            self.max_entry_extension_atr,
            self.progress_atr,
            self.giveback_atr,
            self.structural_stop_atr,
        ) <= 0.0:
            raise ValueError("ATR thresholds must be positive")


def _indicator_frame(bars: pd.DataFrame, cfg: PullbackRegimeParams) -> pd.DataFrame:
    hourly = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    daily = resample_ohlcv_15m(bars, timeframe_minutes=1440)
    if hourly.empty or daily.empty:
        return hourly

    hourly_close = hourly["close"].astype(float)
    hourly["entry_ema"] = hourly_close.ewm(
        span=cfg.hourly_ema_bars,
        adjust=False,
    ).mean()
    previous_close = hourly_close.shift(1)
    hourly["atr"] = (
        pd.concat(
            [
                hourly["high"] - hourly["low"],
                (hourly["high"] - previous_close).abs(),
                (hourly["low"] - previous_close).abs(),
            ],
            axis=1,
        )
        .max(axis=1)
        .rolling(cfg.atr_bars, min_periods=cfg.atr_bars)
        .mean()
    )
    hourly["previous_high"] = hourly["high"].shift(1)

    daily_close = daily["close"].astype(float)
    daily["daily_fast_ema"] = daily_close.ewm(
        span=cfg.daily_fast_ema_days,
        adjust=False,
    ).mean()
    daily["daily_slow_ema"] = daily_close.ewm(
        span=cfg.daily_slow_ema_days,
        adjust=False,
    ).mean()
    ready = pd.Series(np.arange(len(daily)) >= cfg.daily_slow_ema_days - 1)
    raw_risk_on = (
        ready
        & (daily_close > daily["daily_slow_ema"])
        & (daily["daily_fast_ema"] > daily["daily_slow_ema"])
    )
    daily["risk_on"] = raw_risk_on.shift(1, fill_value=False)
    daily["regime_close"] = daily_close.shift(1)
    daily["regime_fast_ema"] = daily["daily_fast_ema"].shift(1)
    daily["regime_slow_ema"] = daily["daily_slow_ema"].shift(1)
    daily["calendar_day"] = pd.to_datetime(
        daily["ts_event"],
        unit="ns",
        utc=True,
    ).dt.floor("D")

    hourly["calendar_day"] = pd.to_datetime(
        hourly["ts_event"],
        unit="ns",
        utc=True,
    ).dt.floor("D")
    regime = daily.set_index("calendar_day")
    for column in ("risk_on", "regime_close", "regime_fast_ema", "regime_slow_ema"):
        hourly[column] = hourly["calendar_day"].map(regime[column])
    hourly["risk_on"] = hourly["risk_on"].fillna(False).astype(bool)
    return hourly


def generate_pullback_regime_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    horizon: str = "1h",
    params: PullbackRegimeParams | None = None,
    source: str = DEFAULT_SOURCE,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> list[SignalEvent]:
    cfg = params or PullbackRegimeParams()
    frame = _indicator_frame(bars, cfg)
    if frame.empty:
        return []

    state = "flat"
    armed_hours = 0
    entry_price = 0.0
    entry_atr = 0.0
    peak_close = 0.0
    bars_held = 0
    progress_made = False
    events: list[SignalEvent] = []

    for _, row in frame.iterrows():
        if (
            np.isnan(row["atr"])
            or np.isnan(row["previous_high"])
            or np.isnan(row["regime_close"])
        ):
            continue
        close = float(row["close"])
        entry_ema = float(row["entry_ema"])
        atr = float(row["atr"])
        risk_on = bool(row["risk_on"])
        side: str | None = None
        trigger = ""

        if state == "flat":
            if not risk_on:
                armed_hours = 0
            elif close < entry_ema:
                armed_hours = cfg.pullback_arm_hours
            elif armed_hours > 0:
                extension_atr = (close - entry_ema) / atr
                recovered = (
                    close > entry_ema
                    and close > float(row["previous_high"])
                    and extension_atr <= cfg.max_entry_extension_atr
                )
                if recovered:
                    state = "long"
                    side = "buy"
                    trigger = "pullback_recovery_entry"
                    entry_price = close
                    entry_atr = atr
                    peak_close = close
                    bars_held = 0
                    progress_made = False
                    armed_hours = 0
                else:
                    armed_hours -= 1
        else:
            bars_held += 1
            peak_close = max(peak_close, close)
            progress_made = progress_made or (
                peak_close >= entry_price + cfg.progress_atr * entry_atr
            )
            risk_off = not risk_on
            structural_failure = close < entry_ema - cfg.structural_stop_atr * atr
            giveback = progress_made and close <= peak_close - cfg.giveback_atr * atr
            timeout = bars_held >= cfg.failure_timeout_hours and not progress_made
            if risk_off:
                trigger = "daily_risk_off_exit"
            elif structural_failure:
                trigger = "structural_failure_exit"
            elif giveback:
                trigger = "bounded_giveback_exit"
            elif timeout:
                trigger = "failure_timeout_exit"
            if trigger:
                state = "flat"
                side = "flat"
                armed_hours = 0

        if side is None:
            continue

        ts_event = int(row["ts_event"])
        distance_atr = (close - entry_ema) / atr
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
                    "score": min(1.0, max(0.0, 1.0 - abs(distance_atr)))
                    if side == "buy"
                    else 0.0,
                    "confidence": 0.75,
                    "source": source,
                    "model_version": model_version,
                    "ttl_seconds": cfg.ttl_seconds,
                    "features_hash": None,
                    "metadata": {
                        "algorithm": "daily_risk_on_hourly_pullback_continuation_long_flat",
                        "trigger": trigger,
                        "spot_target": state,
                        "timeframe_minutes": cfg.timeframe_minutes,
                        "daily_fast_ema_days": cfg.daily_fast_ema_days,
                        "daily_slow_ema_days": cfg.daily_slow_ema_days,
                        "hourly_ema_bars": cfg.hourly_ema_bars,
                        "atr_bars": cfg.atr_bars,
                        "pullback_arm_hours": cfg.pullback_arm_hours,
                        "max_entry_extension_atr": cfg.max_entry_extension_atr,
                        "progress_atr": cfg.progress_atr,
                        "giveback_atr": cfg.giveback_atr,
                        "structural_stop_atr": cfg.structural_stop_atr,
                        "failure_timeout_hours": cfg.failure_timeout_hours,
                        "regime_close": round(float(row["regime_close"]), 8),
                        "regime_fast_ema": round(float(row["regime_fast_ema"]), 8),
                        "regime_slow_ema": round(float(row["regime_slow_ema"]), 8),
                        "entry_ema": round(entry_ema, 8),
                        "atr": round(atr, 8),
                        "distance_entry_ema_atr": round(distance_atr, 8),
                        "entry_price": round(entry_price, 8) if entry_price else None,
                        "entry_atr": round(entry_atr, 8) if entry_atr else None,
                        "peak_close": round(peak_close, 8) if peak_close else None,
                        "bars_held": bars_held,
                        "progress_made": progress_made,
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
    events = generate_pullback_regime_signals(
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
    "PullbackRegimeParams",
    "generate_pullback_regime_signals",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

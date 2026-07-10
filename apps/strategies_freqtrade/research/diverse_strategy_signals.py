"""Four pre-registered, economically distinct Spot long/flat signal sources."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
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

STRATEGY_IDENTITIES = {
    "mean_reversion": (
        "rule_mean_reversion_v1",
        "z20-rsi2-exitmean-time24h-4h-v1",
    ),
    "vol_squeeze": (
        "rule_vol_squeeze_v1",
        "bb20-kc20x1.5-breakout20-chandelier3-4h-v1",
    ),
    "volume_breakout": (
        "rule_volume_breakout_v1",
        "price20-obv20-volume2x-exit10-4h-v1",
    ),
    "dual_momentum": (
        "rule_dual_momentum_v1",
        "ret20-60-positive-1d-v1",
    ),
}


@dataclass(frozen=True)
class MeanReversionParams:
    lookback_bars: int = 20
    entry_zscore: float = -2.0
    rsi_bars: int = 2
    entry_rsi: float = 10.0
    exit_rsi: float = 70.0
    max_hold_bars: int = 6
    timeframe_minutes: int = 240
    ttl_seconds: int = 14_400

    def __post_init__(self) -> None:
        if min(self.lookback_bars, self.rsi_bars, self.max_hold_bars) <= 0:
            raise ValueError("lookbacks and max_hold_bars must be positive")
        if self.entry_zscore >= 0.0:
            raise ValueError("entry_zscore must be negative")
        if not 0.0 <= self.entry_rsi < self.exit_rsi <= 100.0:
            raise ValueError("RSI thresholds must satisfy 0 <= entry < exit <= 100")
        if self.timeframe_minutes != 240 or self.ttl_seconds != 14_400:
            raise ValueError("mean-reversion timeframe and TTL are fixed at 4h")


@dataclass(frozen=True)
class VolSqueezeParams:
    band_bars: int = 20
    bollinger_std: float = 2.0
    keltner_atr: float = 1.5
    breakout_bars: int = 20
    release_bars: int = 6
    chandelier_atr: float = 3.0
    max_hold_bars: int = 60
    timeframe_minutes: int = 240
    ttl_seconds: int = 14_400

    def __post_init__(self) -> None:
        if min(
            self.band_bars,
            self.breakout_bars,
            self.release_bars,
            self.max_hold_bars,
        ) <= 0:
            raise ValueError("lookbacks and max_hold_bars must be positive")
        if min(self.bollinger_std, self.keltner_atr, self.chandelier_atr) <= 0.0:
            raise ValueError("volatility multipliers must be positive")
        if self.timeframe_minutes != 240 or self.ttl_seconds != 14_400:
            raise ValueError("vol-squeeze timeframe and TTL are fixed at 4h")


@dataclass(frozen=True)
class VolumeBreakoutParams:
    price_breakout_bars: int = 20
    obv_breakout_bars: int = 20
    volume_median_bars: int = 20
    volume_multiplier: float = 2.0
    exit_bars: int = 10
    timeframe_minutes: int = 240
    ttl_seconds: int = 14_400

    def __post_init__(self) -> None:
        if min(
            self.price_breakout_bars,
            self.obv_breakout_bars,
            self.volume_median_bars,
            self.exit_bars,
        ) <= 0:
            raise ValueError("lookbacks must be positive")
        if self.volume_multiplier <= 1.0:
            raise ValueError("volume_multiplier must be greater than one")
        if self.timeframe_minutes != 240 or self.ttl_seconds != 14_400:
            raise ValueError("volume-breakout timeframe and TTL are fixed at 4h")


@dataclass(frozen=True)
class DualMomentumParams:
    fast_return_days: int = 20
    slow_return_days: int = 60
    timeframe_minutes: int = 1440
    ttl_seconds: int = 86_400

    def __post_init__(self) -> None:
        if self.fast_return_days <= 0 or self.slow_return_days <= 0:
            raise ValueError("return horizons must be positive")
        if self.fast_return_days >= self.slow_return_days:
            raise ValueError("fast_return_days must be less than slow_return_days")
        if self.timeframe_minutes != 1440 or self.ttl_seconds != 86_400:
            raise ValueError("dual-momentum timeframe and TTL are fixed at 1d")


def _rsi(close: pd.Series, bars: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(bars, min_periods=bars).mean()
    loss = (-delta.clip(upper=0.0)).rolling(bars, min_periods=bars).mean()
    relative = gain / loss.replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + relative)
    result = result.mask((loss == 0.0) & (gain > 0.0), 100.0)
    return result.mask((loss == 0.0) & (gain == 0.0), 50.0)


def _atr(frame: pd.DataFrame, bars: int) -> pd.Series:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(bars, min_periods=bars).mean()


def _event(
    row: pd.Series,
    *,
    symbol: str,
    venue: str,
    horizon: str,
    side: str,
    source: str,
    model_version: str,
    ttl_seconds: int,
    score: float,
    metadata: dict[str, object],
) -> SignalEvent:
    ts_event = int(row["ts_event"])
    return SignalEvent.model_validate(
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
            "score": min(1.0, max(-1.0, score)),
            "confidence": 0.75,
            "source": source,
            "model_version": model_version,
            "ttl_seconds": ttl_seconds,
            "features_hash": None,
            "metadata": metadata,
        }
    )


def generate_mean_reversion_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    params: MeanReversionParams | None = None,
) -> list[SignalEvent]:
    cfg = params or MeanReversionParams()
    source, model_version = STRATEGY_IDENTITIES["mean_reversion"]
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    close = frame["close"].astype(float)
    mean = close.rolling(cfg.lookback_bars, min_periods=cfg.lookback_bars).mean()
    std = close.rolling(cfg.lookback_bars, min_periods=cfg.lookback_bars).std(ddof=0)
    zscore = (close - mean) / std.replace(0.0, np.nan)
    rsi = _rsi(close, cfg.rsi_bars)
    state = "flat"
    held = 0
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if np.isnan(zscore.iloc[index]) or np.isnan(rsi.iloc[index]):
            continue
        side: str | None = None
        trigger = ""
        if state == "flat" and zscore.iloc[index] <= cfg.entry_zscore and rsi.iloc[index] <= cfg.entry_rsi:
            state = "long"
            held = 0
            side = "buy"
            trigger = "oversold_reversion_entry"
        elif state == "long":
            held += 1
            if close.iloc[index] >= mean.iloc[index]:
                trigger = "mean_reached_exit"
            elif rsi.iloc[index] >= cfg.exit_rsi:
                trigger = "rsi_recovered_exit"
            elif held >= cfg.max_hold_bars:
                trigger = "time_exit"
            if trigger:
                state = "flat"
                side = "flat"
        if side:
            events.append(
                _event(
                    row,
                    symbol=symbol,
                    venue=venue,
                    horizon="4h",
                    side=side,
                    source=source,
                    model_version=model_version,
                    ttl_seconds=cfg.ttl_seconds,
                    score=float(-zscore.iloc[index] / 3.0) if side == "buy" else 0.0,
                    metadata={
                        "algorithm": "oversold_mean_reversion_long_flat",
                        "trigger": trigger,
                        "spot_target": state,
                        "zscore": round(float(zscore.iloc[index]), 8),
                        "rsi": round(float(rsi.iloc[index]), 8),
                        "mean": round(float(mean.iloc[index]), 8),
                        "held_bars": held,
                        **asdict(cfg),
                    },
                )
            )
    return events


def generate_vol_squeeze_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    params: VolSqueezeParams | None = None,
) -> list[SignalEvent]:
    cfg = params or VolSqueezeParams()
    source, model_version = STRATEGY_IDENTITIES["vol_squeeze"]
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    close = frame["close"].astype(float)
    middle = close.rolling(cfg.band_bars, min_periods=cfg.band_bars).mean()
    std = close.rolling(cfg.band_bars, min_periods=cfg.band_bars).std(ddof=0)
    atr = _atr(frame, cfg.band_bars)
    keltner_middle = close.ewm(span=cfg.band_bars, adjust=False).mean()
    squeeze = (
        (middle + cfg.bollinger_std * std < keltner_middle + cfg.keltner_atr * atr)
        & (middle - cfg.bollinger_std * std > keltner_middle - cfg.keltner_atr * atr)
    )
    breakout = frame["high"].shift(1).rolling(
        cfg.breakout_bars,
        min_periods=cfg.breakout_bars,
    ).max()
    state = "flat"
    release_remaining = 0
    held = 0
    peak_high = 0.0
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if np.isnan(atr.iloc[index]) or np.isnan(breakout.iloc[index]):
            continue
        side: str | None = None
        trigger = ""
        if state == "flat":
            if bool(squeeze.iloc[index]):
                release_remaining = cfg.release_bars
            if release_remaining > 0 and close.iloc[index] > breakout.iloc[index]:
                state = "long"
                held = 0
                peak_high = float(row["high"])
                release_remaining = 0
                side = "buy"
                trigger = "squeeze_release_breakout_entry"
            elif release_remaining > 0 and not bool(squeeze.iloc[index]):
                release_remaining -= 1
        else:
            held += 1
            peak_high = max(peak_high, float(row["high"]))
            if close.iloc[index] < peak_high - cfg.chandelier_atr * atr.iloc[index]:
                trigger = "chandelier_exit"
            elif held >= cfg.max_hold_bars:
                trigger = "time_exit"
            if trigger:
                state = "flat"
                side = "flat"
        if side:
            events.append(
                _event(
                    row,
                    symbol=symbol,
                    venue=venue,
                    horizon="4h",
                    side=side,
                    source=source,
                    model_version=model_version,
                    ttl_seconds=cfg.ttl_seconds,
                    score=0.75 if side == "buy" else 0.0,
                    metadata={
                        "algorithm": "volatility_squeeze_release_breakout_long_flat",
                        "trigger": trigger,
                        "spot_target": state,
                        "squeeze_on": bool(squeeze.iloc[index]),
                        "atr": round(float(atr.iloc[index]), 8),
                        "breakout_high": round(float(breakout.iloc[index]), 8),
                        "peak_high": round(peak_high, 8) if peak_high else None,
                        "held_bars": held,
                        **asdict(cfg),
                    },
                )
            )
    return events


def generate_volume_breakout_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    params: VolumeBreakoutParams | None = None,
) -> list[SignalEvent]:
    cfg = params or VolumeBreakoutParams()
    source, model_version = STRATEGY_IDENTITIES["volume_breakout"]
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float)
    direction = np.sign(close.diff()).fillna(0.0)
    obv = (direction * volume).cumsum()
    price_high = frame["high"].shift(1).rolling(
        cfg.price_breakout_bars,
        min_periods=cfg.price_breakout_bars,
    ).max()
    obv_high = obv.shift(1).rolling(
        cfg.obv_breakout_bars,
        min_periods=cfg.obv_breakout_bars,
    ).max()
    volume_median = volume.shift(1).rolling(
        cfg.volume_median_bars,
        min_periods=cfg.volume_median_bars,
    ).median()
    exit_low = frame["low"].shift(1).rolling(
        cfg.exit_bars,
        min_periods=cfg.exit_bars,
    ).min()
    state = "flat"
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if any(
            np.isnan(series.iloc[index])
            for series in (price_high, obv_high, volume_median, exit_low)
        ):
            continue
        side: str | None = None
        trigger = ""
        volume_ratio = volume.iloc[index] / max(volume_median.iloc[index], 1e-12)
        if (
            state == "flat"
            and close.iloc[index] > price_high.iloc[index]
            and obv.iloc[index] > obv_high.iloc[index]
            and volume_ratio >= cfg.volume_multiplier
        ):
            state = "long"
            side = "buy"
            trigger = "price_obv_volume_breakout_entry"
        elif state == "long" and close.iloc[index] < exit_low.iloc[index]:
            state = "flat"
            side = "flat"
            trigger = "donchian_exit"
        if side:
            events.append(
                _event(
                    row,
                    symbol=symbol,
                    venue=venue,
                    horizon="4h",
                    side=side,
                    source=source,
                    model_version=model_version,
                    ttl_seconds=cfg.ttl_seconds,
                    score=min(1.0, volume_ratio / cfg.volume_multiplier - 0.25)
                    if side == "buy"
                    else 0.0,
                    metadata={
                        "algorithm": "price_obv_volume_breakout_long_flat",
                        "trigger": trigger,
                        "spot_target": state,
                        "obv": round(float(obv.iloc[index]), 8),
                        "obv_breakout": round(float(obv_high.iloc[index]), 8),
                        "price_breakout": round(float(price_high.iloc[index]), 8),
                        "volume_ratio": round(float(volume_ratio), 8),
                        **asdict(cfg),
                    },
                )
            )
    return events


def generate_dual_momentum_signals(
    bars: pd.DataFrame,
    *,
    symbol: str,
    venue: str,
    params: DualMomentumParams | None = None,
) -> list[SignalEvent]:
    cfg = params or DualMomentumParams()
    source, model_version = STRATEGY_IDENTITIES["dual_momentum"]
    frame = resample_ohlcv_15m(bars, timeframe_minutes=cfg.timeframe_minutes)
    close = frame["close"].astype(float)
    fast_return = close.pct_change(cfg.fast_return_days)
    slow_return = close.pct_change(cfg.slow_return_days)
    state = "flat"
    events: list[SignalEvent] = []
    for index, row in frame.iterrows():
        if np.isnan(fast_return.iloc[index]) or np.isnan(slow_return.iloc[index]):
            continue
        risk_on = fast_return.iloc[index] > 0.0 and slow_return.iloc[index] > 0.0
        side: str | None = None
        trigger = ""
        if state == "flat" and risk_on:
            state = "long"
            side = "buy"
            trigger = "dual_positive_momentum_entry"
        elif state == "long" and not risk_on:
            state = "flat"
            side = "flat"
            trigger = "momentum_nonpositive_exit"
        if side:
            score = min(1.0, max(0.0, float(min(fast_return.iloc[index], slow_return.iloc[index])) * 5.0))
            events.append(
                _event(
                    row,
                    symbol=symbol,
                    venue=venue,
                    horizon="1d",
                    side=side,
                    source=source,
                    model_version=model_version,
                    ttl_seconds=cfg.ttl_seconds,
                    score=score if side == "buy" else 0.0,
                    metadata={
                        "algorithm": "dual_horizon_absolute_momentum_long_flat",
                        "trigger": trigger,
                        "spot_target": state,
                        "fast_return": round(float(fast_return.iloc[index]), 10),
                        "slow_return": round(float(slow_return.iloc[index]), 10),
                        **asdict(cfg),
                    },
                )
            )
    return events


GENERATORS: dict[str, Callable[..., list[SignalEvent]]] = {
    "mean_reversion": generate_mean_reversion_signals,
    "vol_squeeze": generate_vol_squeeze_signals,
    "volume_breakout": generate_volume_breakout_signals,
    "dual_momentum": generate_dual_momentum_signals,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(GENERATORS), required=True)
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--signal-store-path", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    bars = _load_bars_from_catalog(args.catalog_path, args.bar_type)
    events = GENERATORS[args.strategy](bars, symbol=args.symbol, venue=args.venue)
    source, model_version = STRATEGY_IDENTITIES[args.strategy]
    print(
        f"generated {len(events)} signals from {len(bars)} bars "
        f"for {source} / {model_version}"
    )
    if args.dry_run:
        for event in events[:10]:
            print(f"  {event.signal_id} side={event.side}")
        return 0
    store = SignalStore(args.signal_store_path)
    written, duplicates = store.write_many(events)
    print(f"wrote {written}, skipped {duplicates} duplicates into {args.signal_store_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

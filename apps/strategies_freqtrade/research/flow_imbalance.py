"""Daily research targets for the frozen order-flow rules (v55–v57)."""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_DATASET: str = "um_klines_1d"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Return close-time targets; OI rules use calendar-day holds."""
    if candidate not in {
        "taker_continuation",
        "oi_squeeze",
        "taker_persist_long",
        "deleveraging_rebound",
    }:
        raise ValueError(f"Unknown candidate: {candidate}")
    if candidate == "deleveraging_rebound":
        return _deleveraging_rebound(frames, params)

    prices = frames[PRICE_DATASET]["BTCUSDT"]
    if candidate in {"taker_continuation", "taker_persist_long"}:
        share = prices["taker_buy_volume"] / prices["volume"].where(prices["volume"] > 0.0)
        share = share.replace([np.inf, -np.inf], np.nan)
        baseline = share.shift(1).rolling(params["baseline_days"])
        std = baseline.std(ddof=1)
        z = (share - baseline.mean()) / std.where(std > 0.0)
        if candidate == "taker_continuation":
            weight = (z > params["z_threshold"]).astype(float)
            weight -= (z < -params["z_threshold"]).astype(float)
        else:
            consecutive = (z > params["z_threshold"]).rolling(params["persist_days"]).sum()
            trigger = consecutive == params["persist_days"]
            weight = _hold_long(trigger, params["hold_days"], 1.0)
    else:
        oi = frames["um_metrics_daily"]["BTCUSDT"]["open_interest"]
        panel = pd.concat({"close": prices["close"], "oi": oi}, axis=1).sort_index()
        if not panel.empty:
            panel = panel.asfreq("D")
        lagged = panel.shift(params["lookback_days"])
        changes = (panel / lagged.where(lagged > 0.0) - 1.0).replace([np.inf, -np.inf], np.nan)
        trigger = (
            -np.sign(changes["close"])
            .where(changes["oi"] > params["oi_change_min"], 0.0)
            .fillna(0.0)
        )
        weight = pd.Series(0.0, index=panel.index)
        next_free = 0
        for row, direction in enumerate(trigger.to_numpy()):
            if row >= next_free and direction != 0.0:
                next_free = row + params["hold_days"]
                weight.iloc[row:next_free] = direction

    cap = params.get("max_gross_exposure", 1.0)
    return weight.clip(lower=-cap, upper=cap).to_frame("BTCUSDT")


def _hold_long(trigger: pd.Series, hold_days: int, size: float) -> pd.Series:
    weight = pd.Series(0.0, index=trigger.index)
    next_free = 0
    for row, active in enumerate(trigger.to_numpy()):
        if row >= next_free and active:
            next_free = row + hold_days
            weight.iloc[row:next_free] = size
    return weight


def _deleveraging_rebound(frames: dict, params: dict) -> pd.DataFrame:
    held: dict[str, pd.Series] = {}
    for symbol, prices in frames[PRICE_DATASET].items():
        oi = frames["um_metrics_daily"][symbol]["open_interest"]
        panel = pd.concat({"close": prices["close"], "oi": oi}, axis=1).sort_index()
        if not panel.empty:
            panel = panel.asfreq("D")
        previous = panel.shift(1)
        changes = panel / previous - 1.0
        changes["oi"] = changes["oi"].where(previous["oi"] > 0.0)
        changes = changes.replace([np.inf, -np.inf], np.nan)
        thresholds = (
            changes.shift(1)
            .rolling(params["baseline_days"])
            .quantile(params["quantile"], interpolation="linear")
        )
        trigger = (changes <= thresholds).all(axis=1)
        held[symbol] = _hold_long(trigger, params["hold_days"], params["weight_per_symbol"])

    if not held:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
    weights = pd.DataFrame(held).sort_index().fillna(0.0)
    gross = weights.abs().sum(axis=1)
    scale = (params.get("max_gross_exposure", 1.0) / gross).clip(upper=1.0).fillna(1.0)
    return weights.mul(scale, axis=0)

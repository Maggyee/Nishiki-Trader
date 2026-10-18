"""Daily research targets for the frozen v55 BTC order-flow rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_DATASET: str = "um_klines_1d"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Return close-time BTC targets, with calendar-day holds for squeezes."""
    if candidate not in {"taker_continuation", "oi_squeeze"}:
        raise ValueError(f"Unknown candidate: {candidate}")

    prices = frames[PRICE_DATASET]["BTCUSDT"]
    if candidate == "taker_continuation":
        share = prices["taker_buy_volume"] / prices["volume"].where(prices["volume"] > 0.0)
        share = share.replace([np.inf, -np.inf], np.nan)
        baseline = share.shift(1).rolling(params["baseline_days"])
        std = baseline.std(ddof=1)
        z = (share - baseline.mean()) / std.where(std > 0.0)
        weight = (z > params["z_threshold"]).astype(float)
        weight -= (z < -params["z_threshold"]).astype(float)
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

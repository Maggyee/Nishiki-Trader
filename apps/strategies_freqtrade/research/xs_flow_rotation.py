"""Weekly dollar-neutral targets for the frozen v58 taker-flow rotation."""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_DATASET: str = "spot_klines_1d"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Rank each symbol's trailing flow z-score at the rebalance close."""
    if candidate != "xs_taker_rotation":
        raise ValueError(f"Unknown candidate: {candidate}")

    scores: dict[str, pd.Series] = {}
    for symbol, frame in frames[PRICE_DATASET].items():
        # Roll on each symbol's own observations before aligning the universe.
        totals = frame[["taker_buy_volume", "volume"]].rolling(params["window_days"]).sum()
        share = (totals["taker_buy_volume"] / totals["volume"]).replace([np.inf, -np.inf], np.nan)
        baseline = share.shift(1).rolling(params["baseline_days"])
        std = baseline.std(ddof=1)
        scores[symbol] = (share - baseline.mean()) / std.where(std > 0.0)

    if not scores:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)

    z = pd.DataFrame(scores).sort_index()
    weights = pd.DataFrame(0.0, index=z.index, columns=z.columns)
    legs = params["legs_per_side"]
    rebalances = z.index.weekday == params["rebalance_weekday"]
    for date, row in z.loc[rebalances].iterrows():
        ranked = sorted(row[np.isfinite(row)].items(), key=lambda item: (item[1], item[0]))
        if len(ranked) >= max(params["min_universe"], 2 * legs):
            weights.loc[date, [symbol for symbol, _ in ranked[:legs]]] = -1.0 / (2 * legs)
            weights.loc[date, [symbol for symbol, _ in ranked[-legs:]]] = 1.0 / (2 * legs)
    weights.loc[~rebalances, :] = np.nan
    return weights.ffill().fillna(0.0)

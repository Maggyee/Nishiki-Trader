"""Daily research targets for the frozen v54 trend and inverse-vol rule."""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_DATASET: str = "spot_klines_1d"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Decide at each close, rebalancing only on the configured weekday."""
    if candidate != "tsmom_vol":
        raise ValueError(f"Unknown candidate: {candidate}")

    scores: dict[str, pd.Series] = {}
    vols: dict[str, pd.Series] = {}
    for symbol, frame in frames[PRICE_DATASET].items():
        close = frame["close"].astype(float)
        # Compute before aligning symbols: lookbacks count each symbol's rows.
        signs = [np.sign(close / close.shift(days) - 1.0) for days in params["lookbacks_days"]]
        scores[symbol] = pd.concat(signs, axis=1).mean(axis=1, skipna=False)
        vols[symbol] = np.log(close).diff().rolling(params["vol_window_days"]).std(ddof=1)

    if not scores:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)

    score = pd.DataFrame(scores).sort_index()
    vol = pd.DataFrame(vols).reindex(score.index)
    inverse_vol = (1.0 / vol).where(score.notna() & (vol > 0.0))
    inverse_vol = inverse_vol.replace([np.inf, -np.inf], np.nan)
    total = inverse_vol.sum(axis=1).replace(0.0, np.nan)
    weights = (score * inverse_vol).div(total, axis=0).fillna(0.0)
    gross = weights.abs().sum(axis=1)
    scale = (params["max_gross_exposure"] / gross).clip(upper=1.0).fillna(1.0)
    weights = weights.mul(scale, axis=0)
    weights.loc[weights.index.weekday != params["rebalance_weekday"], :] = np.nan
    return weights.ffill().fillna(0.0)

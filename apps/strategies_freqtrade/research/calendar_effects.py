"""Close-time targets for the frozen v59 turn-of-month window."""

from __future__ import annotations

import pandas as pd

PRICE_DATASET: str = "spot_klines_1d"


def target_weights(
    frames: dict[str, dict[str, pd.DataFrame]], candidate: str, params: dict
) -> pd.DataFrame:
    """Hold equal weights from month-end through the specified return days."""
    if candidate != "turn_of_month":
        raise ValueError(f"Unknown candidate: {candidate}")

    available = {
        symbol: pd.Series(1.0, index=frame.index) for symbol, frame in frames[PRICE_DATASET].items()
    }
    if not available:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz="UTC"), dtype=float)

    present = pd.DataFrame(available).sort_index().fillna(0.0)
    weights = present.div(present.sum(axis=1), axis=0).fillna(0.0)
    in_window = weights.index.is_month_end | (weights.index.day < params["days_after_month_end"])
    weights.loc[~in_window, :] = 0.0
    return weights

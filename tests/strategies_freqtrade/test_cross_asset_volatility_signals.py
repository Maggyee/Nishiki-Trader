from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.cross_asset_volatility_signals import (
    STRATEGY_IDENTITIES,
    VolatilityReliefParams,
    generate_volatility_relief_signals,
)


def _frame(values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "ts_event": [int(value.value) for value in index],
            "available_at": index,
            "vintage_id": ["cboe:test"] * len(index),
            "snapshot_sha256": ["sha256:" + "a" * 64] * len(index),
            "vol_close": values,
        },
        index=index,
    )


@pytest.mark.parametrize("strategy", sorted(STRATEGY_IDENTITIES))
def test_v7_generators_emit_only_state_changes_and_long_flat(strategy: str) -> None:
    events = generate_volatility_relief_signals(
        _frame([20, 21, 22, 23, 24, 19, 18, 17, 16, 15, 25, 26]),
        strategy=strategy,
        start_date="2020-01-01",
        end_date="2020-01-12",
    )
    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["point_in_time"] is True for event in events)
    assert all(event.metadata["index"] == STRATEGY_IDENTITIES[strategy][2] for event in events)
    assert all(event.side != "sell" for event in events)


def test_v7_fold_starts_flat_and_emits_first_eligible_buy() -> None:
    events = generate_volatility_relief_signals(
        _frame([30, 29, 28, 27, 26, 25, 24, 23]),
        strategy="equity_vol_relief",
        start_date="2020-01-07",
        end_date="2020-01-08",
    )
    assert [event.side for event in events] == ["buy"]
    assert events[0].ts_event == int(pd.Timestamp("2020-01-07", tz="UTC").value)


def test_v7_parameters_cannot_be_tuned() -> None:
    with pytest.raises(ValueError, match="five observations"):
        VolatilityReliefParams(change_observations=10)

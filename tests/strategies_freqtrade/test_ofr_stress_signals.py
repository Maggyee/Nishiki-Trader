from __future__ import annotations

import pandas as pd
import pytest

from apps.ops.research_protocol_v20 import IDENTITIES
from apps.strategies_freqtrade.research.ofr_stress_signals import (
    METRIC_COLUMNS,
    StressReliefParams,
    audit_point_in_time_frame,
    generate_ofr_stress_signals,
)


def _frame(values: list[float], candidate: str) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "ts_event": [int(value.value) for value in index],
            "available_at": index,
            "vintage_id": ["ofr:test"] * len(index),
            "snapshot_sha256": ["sha256:" + "a" * 64] * len(index),
            METRIC_COLUMNS[candidate]: values,
        },
        index=index,
    )


@pytest.mark.parametrize("candidate", sorted(IDENTITIES))
def test_v20_generators_emit_only_state_changes_and_long_flat(candidate: str) -> None:
    events = generate_ofr_stress_signals(
        _frame([0, 1, 2, 3, 4, -1, -2, -3, -4, -5, 5, 6], candidate),
        candidate=candidate,
        start_date="2020-01-01",
        end_date="2020-01-12",
    )
    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.side != "sell" for event in events)
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_v20_fold_starts_flat_and_emits_first_eligible_buy() -> None:
    candidate = "credit_stress_relief"
    events = generate_ofr_stress_signals(
        _frame([5, 4, 3, 2, 1, 0, -1, -2], candidate),
        candidate=candidate,
        start_date="2020-01-07",
        end_date="2020-01-08",
    )
    assert [event.side for event in events] == ["buy"]
    assert events[0].ts_event == int(pd.Timestamp("2020-01-07", tz="UTC").value)


def test_v20_parameters_cannot_be_tuned() -> None:
    with pytest.raises(ValueError, match="cannot be tuned"):
        StressReliefParams(change_observations=10)


def test_v20_point_in_time_audit_rejects_lookahead() -> None:
    candidate = "systemic_stress_relief"
    frame = _frame([0, -1, -2], candidate)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="lookahead"):
        audit_point_in_time_frame(frame, METRIC_COLUMNS[candidate])

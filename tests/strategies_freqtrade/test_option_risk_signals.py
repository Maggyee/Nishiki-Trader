from __future__ import annotations

import json

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.option_risk_signals import (
    generate_option_risk_signals,
)


def _frame(values: dict[str, list[float]]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(next(iter(values.values()))), tz="UTC")
    frame = pd.DataFrame(values, index=index)
    frame["available_at"] = index
    frame["snapshot_hashes"] = json.dumps({"source": "sha256:" + "a" * 64})
    frame["vintage_ids"] = json.dumps({"source": "vintage-1"})
    return frame


def test_curve_emits_only_long_flat_state_changes() -> None:
    frame = _frame(
        {
            "vix9d_close": [11, 9, 8, 12, 11],
            "vix_close": [10, 10, 10, 10, 12],
        }
    )

    events = generate_option_risk_signals(frame, candidate="equity_vol_curve")

    assert [event.side for event in events] == ["buy", "flat", "buy"]
    assert events[0].metadata["trigger"] == "vix9d_below_vix"
    assert events[0].metadata["point_in_time"] is True


def test_vvix_relief_uses_exact_five_observation_change() -> None:
    frame = _frame({"vvix_close": [100, 101, 102, 103, 104, 99, 110, 100]})

    events = generate_option_risk_signals(frame, candidate="vol_of_vol_relief")

    assert [event.side for event in events] == ["buy", "flat", "buy"]
    assert events[0].metadata["change_observations"] == 5
    assert events[0].metadata["maximum_change"] == 0.0


def test_candidate_starts_scored_window_flat() -> None:
    frame = _frame(
        {
            "vix9d_close": [9, 9, 9, 11, 9],
            "vix_close": [10, 10, 10, 10, 10],
        }
    )

    events = generate_option_risk_signals(
        frame, candidate="equity_vol_curve", start_date="2020-01-03"
    )

    assert events[0].ts_event == int(pd.Timestamp("2020-01-03", tz="UTC").value)
    assert [event.side for event in events] == ["buy", "flat", "buy"]


def test_curve_rejects_nonpositive_input() -> None:
    frame = _frame({"vix9d_close": [9, 0], "vix_close": [10, 10]})

    with pytest.raises(ValueError, match="finite and positive"):
        generate_option_risk_signals(frame, candidate="equity_vol_curve")

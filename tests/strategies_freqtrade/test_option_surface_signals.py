from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.option_surface_signals import (
    generate_option_surface_signals,
)


def _frame(values: list[float]) -> pd.DataFrame:
    observed = pd.date_range("2019-11-01", periods=len(values), freq="D", tz="UTC")
    available = observed + pd.Timedelta(days=1)
    return pd.DataFrame(
        {
            "available_at": available,
            "observation_date": observed,
            "vintage_id": "fixture-vintage",
            "snapshot_sha256": "sha256:" + "a" * 64,
            "index_value": values,
        },
        index=available,
    )


@pytest.mark.parametrize(
    ("candidate", "values"),
    [
        ("tail_skew_relief", [20.0] * 6 + [10.0] * 6 + [30.0] * 7),
        ("implied_correlation_relief", [20.0] * 6 + [10.0] * 6 + [30.0] * 7),
        ("implied_dispersion_expansion", [20.0] * 6 + [30.0] * 6 + [10.0] * 7),
    ],
)
def test_option_surface_rules_emit_buy_then_flat(candidate: str, values: list[float]) -> None:
    events = generate_option_surface_signals(
        _frame(values),
        candidate=candidate,
        start_date="2019-11-01",
        end_date="2020-12-31",
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_option_surface_rule_rejects_lag_drift() -> None:
    frame = _frame([20.0] * 15)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] - pd.Timedelta(days=2)

    with pytest.raises(ValueError, match="one-day publication lag"):
        generate_option_surface_signals(
            frame,
            candidate="tail_skew_relief",
            start_date="2019-11-01",
        )

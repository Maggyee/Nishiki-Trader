from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.fear_greed_signals import generate_fear_greed_signals


def _frame(labels: list[str]) -> pd.DataFrame:
    observed = pd.date_range("2019-11-01", periods=len(labels), freq="D", tz="UTC")
    available = observed + pd.Timedelta(days=2)
    return pd.DataFrame(
        {
            "available_at": available,
            "observation_date": observed,
            "vintage_id": "fixture-vintage",
            "snapshot_sha256": "sha256:" + "a" * 64,
            "fear_greed_value": [10] * len(labels),
            "value_classification": labels,
        },
        index=available,
    )


@pytest.mark.parametrize(
    ("candidate", "labels"),
    [
        ("extreme_fear_hold", ["Greed"] * 3 + ["Extreme Fear"] * 4 + ["Greed"] * 4),
        ("fear_hold", ["Greed"] * 3 + ["Fear"] * 4 + ["Extreme Greed"] * 4),
        ("non_greed_hold", ["Greed"] * 3 + ["Neutral"] * 4 + ["Extreme Greed"] * 4),
    ],
)
def test_fear_greed_rules_emit_buy_then_flat(candidate: str, labels: list[str]) -> None:
    events = generate_fear_greed_signals(
        _frame(labels),
        candidate=candidate,
        start_date="2019-11-01",
        end_date="2020-12-31",
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_fear_greed_rule_rejects_lag_drift() -> None:
    frame = _frame(["Fear"] * 10)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] - pd.Timedelta(days=1)

    with pytest.raises(ValueError, match="two-day publication lag"):
        generate_fear_greed_signals(frame, candidate="fear_hold", start_date="2019-11-01")

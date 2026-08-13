from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.fx_vol_signals import generate_fx_vol_relief_signals


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
    "candidate",
    ["euro_fx_vol_relief", "yen_fx_vol_relief", "pound_fx_vol_relief"],
)
def test_v32_vol_rules_emit_buy_then_flat(candidate: str) -> None:
    events = generate_fx_vol_relief_signals(
        _frame([20.0] * 6 + [10.0] * 6 + [30.0] * 7),
        candidate=candidate,
        start_date="2019-11-01",
        end_date="2020-12-31",
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_v32_vol_rule_rejects_lag_drift() -> None:
    frame = _frame([20.0] * 15)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] - pd.Timedelta(days=2)

    with pytest.raises(ValueError, match="one-day publication lag"):
        generate_fx_vol_relief_signals(
            frame,
            candidate="euro_fx_vol_relief",
            start_date="2019-11-01",
        )

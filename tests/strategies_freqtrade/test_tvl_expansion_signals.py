from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.tvl_expansion_signals import (
    generate_tvl_expansion_signals,
)


def _frame(values: list[float]) -> pd.DataFrame:
    observed = pd.date_range("2019-11-01", periods=len(values), freq="D", tz="UTC")
    available = observed + pd.Timedelta(days=2)
    return pd.DataFrame(
        {
            "available_at": available,
            "observation_date": observed,
            "vintage_id": "fixture-vintage",
            "snapshot_sha256": "sha256:" + "a" * 64,
            "tvl": values,
        },
        index=available,
    )


@pytest.mark.parametrize(
    "candidate",
    ["all_chains_tvl_expansion", "ethereum_tvl_expansion", "bitcoin_tvl_expansion"],
)
def test_tvl_expansion_rules_emit_buy_then_flat(candidate: str) -> None:
    events = generate_tvl_expansion_signals(
        _frame([100.0] * 6 + [200.0] * 6 + [50.0] * 7),
        candidate=candidate,
        start_date="2019-11-01",
        end_date="2020-12-31",
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_tvl_expansion_rule_rejects_lag_drift() -> None:
    frame = _frame([100.0] * 15)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] - pd.Timedelta(days=1)

    with pytest.raises(ValueError, match="two-day publication lag"):
        generate_tvl_expansion_signals(
            frame,
            candidate="ethereum_tvl_expansion",
            start_date="2019-11-01",
        )

from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.net_liquidity_signals import (
    generate_net_liquidity_signals,
)


def _frame(net_values: list[float]) -> pd.DataFrame:
    observed = pd.date_range("2019-10-02", periods=len(net_values), freq="7D", tz="UTC")
    available = observed + pd.Timedelta(days=7)
    tga = 500_000.0
    rrp = 100.0
    return pd.DataFrame(
        {
            "available_at": available,
            "observation_date": observed,
            "vintage_id": "fixture-vintage",
            "snapshot_sha256": "sha256:" + "a" * 64,
            "walcl_millions": [value + tga + 1000.0 * rrp for value in net_values],
            "wdtgal_millions": tga,
            "rrpontsyd_billions": rrp,
            "net_liquidity_millions": net_values,
        },
        index=available,
    )


def test_net_liquidity_rule_emits_buy_then_flat() -> None:
    values = [1_000_000.0] * 5 + [1_100_000.0] * 5 + [900_000.0] * 6
    events = generate_net_liquidity_signals(
        _frame(values),
        start_date="2019-10-01",
        end_date="2020-12-31",
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["historical_vintage_claim"] is False for event in events)


def test_net_liquidity_rule_rejects_formula_drift() -> None:
    frame = _frame([1_000_000.0] * 12)
    frame.loc[frame.index[0], "net_liquidity_millions"] += 1.0

    with pytest.raises(ValueError, match="formula drifted"):
        generate_net_liquidity_signals(frame, start_date="2019-10-01")


def test_net_liquidity_rule_rejects_lag_drift() -> None:
    frame = _frame([1_000_000.0] * 12)
    frame.loc[frame.index[0], "available_at"] = frame.index[0] - pd.Timedelta(days=6)

    with pytest.raises(ValueError, match="seven-day publication lag"):
        generate_net_liquidity_signals(frame, start_date="2019-10-01")

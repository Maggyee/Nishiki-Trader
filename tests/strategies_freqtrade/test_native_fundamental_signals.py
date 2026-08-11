from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.native_fundamental_signals import (
    generate_native_fundamental_signals,
)


def _frame(column: str, values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2019-11-03", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            column: values,
            "available_at": index,
            "snapshot_sha256": "sha256:" + "a" * 64,
            "vintage_id": "fixture-v1",
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("candidate", "column"),
    [
        ("miner_hashrate_recovery", "hashrate"),
        ("btc_fee_demand", "fee_total_ntv"),
    ],
)
def test_mean_expansion_emits_long_then_flat(candidate: str, column: str) -> None:
    values = [100.0] * 30 + [200.0] * 10 + [10.0] * 20
    events = generate_native_fundamental_signals(_frame(column, values), candidate=candidate)

    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["provider_vintage_claimed"] is False for event in events)


def test_stablecoin_expansion_emits_long_then_flat() -> None:
    values = list(range(100, 141)) + [90.0] * 35
    events = generate_native_fundamental_signals(
        _frame("stablecoin_supply", values), candidate="stablecoin_liquidity_expansion"
    )

    assert [event.side for event in events] == ["buy", "flat"]


def test_generator_rejects_duplicate_factor_day() -> None:
    frame = _frame("hashrate", [100.0] * 40)
    frame = pd.concat([frame, frame.iloc[[-1]]])
    with pytest.raises(ValueError, match="unique"):
        generate_native_fundamental_signals(frame, candidate="miner_hashrate_recovery")

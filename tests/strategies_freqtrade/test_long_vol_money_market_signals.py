from __future__ import annotations

import pandas as pd
import pytest

from apps.ops.research_protocol_v35 import IDENTITIES
from apps.strategies_freqtrade.research.long_vol_money_market_signals import (
    audit_factor_frame,
    generate_long_vol_money_market_signals,
)


def _frame(values: list[float]) -> pd.DataFrame:
    observed = pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC")
    available = observed + pd.Timedelta(days=1)
    return pd.DataFrame(
        {
            "ts_event": [int(value.value) for value in available],
            "available_at": available,
            "observation_date": observed.date,
            "vintage_id": ["cboe:test"] * len(values),
            "snapshot_sha256": ["sha256:" + "a" * 64] * len(values),
            "index_value": values,
        },
        index=available,
    )


@pytest.mark.parametrize("candidate", sorted(IDENTITIES))
def test_v35_generators_emit_only_state_changes_and_long_flat(candidate: str) -> None:
    events = generate_long_vol_money_market_signals(
        _frame([60, 61, 62, 63, 64, 59, 58, 57, 56, 55, 65, 66]),
        candidate=candidate,
        start_date="2020-01-01",
        end_date="2020-01-15",
    )
    assert [event.side for event in events] == ["buy", "flat"]
    assert all(event.metadata["candidate"] == candidate for event in events)
    assert all(event.side != "sell" for event in events)


def test_v35_audit_factor_frame_rejects_lookahead() -> None:
    frame = _frame([60, 59, 58])
    frame.loc[frame.index[0], "available_at"] = frame.index[0] + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="lookahead"):
        audit_factor_frame(frame)

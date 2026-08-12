from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.network_mechanism_signals import generate_network_signals


def _frame(values: list[float], metric: str) -> pd.DataFrame:
    index = pd.date_range("2019-11-03", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            metric: values,
            "available_at": index,
            "snapshot_sha256": "sha256:" + "a" * 64,
            "vintage_id": "fixture",
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("candidate", "metric"),
    [("active_address_expansion", "AdrActCnt"), ("transfer_count_expansion", "TxTfrCnt")],
)
def test_expansion_rules_emit_buy_then_flat(candidate: str, metric: str) -> None:
    events = generate_network_signals(
        _frame([100.0] * 30 + [200.0] * 10 + [10.0] * 20, metric),
        candidate=candidate,
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_mvrv_distress_uses_structural_one_threshold() -> None:
    events = generate_network_signals(
        _frame([1.2, 0.9, 0.8, 1.1], "CapMVRVCur"),
        candidate="mvrv_distress",
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_network_signal_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        generate_network_signals(
            _frame([0.0] * 40, "AdrActCnt"),
            candidate="active_address_expansion",
            start_date="2019-11-03",
        )

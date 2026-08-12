from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.valuation_mechanism_signals import (
    generate_valuation_signals,
)


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


def test_realized_cap_expansion_emits_buy_then_flat() -> None:
    events = generate_valuation_signals(
        _frame([100.0] * 30 + [200.0] * 10 + [10.0] * 20, "CapRealUSD"),
        candidate="realized_cap_expansion",
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_nvt_compression_emits_buy_then_flat() -> None:
    events = generate_valuation_signals(
        _frame([100.0] * 30 + [10.0] * 10 + [200.0] * 20, "NVTAdj"),
        candidate="nvt_compression",
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_sopr_capitulation_uses_smoothed_structural_one_threshold() -> None:
    events = generate_valuation_signals(
        _frame([1.1] * 7 + [0.9] * 7 + [1.1] * 7, "SOPR"),
        candidate="sopr_capitulation",
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_valuation_signal_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        generate_valuation_signals(
            _frame([0.0] * 40, "NVTAdj"),
            candidate="nvt_compression",
            start_date="2019-11-03",
        )

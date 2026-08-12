from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.rate_mechanism_signals import generate_rate_signals


def _frame(values: list[float], metric: str) -> pd.DataFrame:
    index = pd.date_range("2019-11-05", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            metric: values,
            "available_at": index,
            "snapshot_sha256": "sha256:" + "a" * 64,
            "vintage_id": "fixture",
        },
        index=index,
    )


def test_real_yield_relief_emits_buy_then_flat() -> None:
    events = generate_rate_signals(
        _frame([2.0] * 20 + [1.0] * 8 + [3.0] * 15, "DFII10"),
        candidate="real_yield_relief",
        start_date="2019-11-05",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_yield_curve_steepening_emits_buy_then_flat() -> None:
    events = generate_rate_signals(
        _frame([0.0] * 20 + [1.0] * 8 + [-1.0] * 15, "T10Y2Y"),
        candidate="yield_curve_steepening",
        start_date="2019-11-05",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_treasury_volatility_relief_uses_absolute_changes() -> None:
    quiet = [1.0 + index * 0.001 for index in range(10)]
    volatile = [1.01 + ((-1) ** index) * 0.5 for index in range(20)]
    events = generate_rate_signals(
        _frame([1.0 + ((-1) ** index) * 0.5 for index in range(25)] + quiet + volatile, "DGS10"),
        candidate="treasury_volatility_relief",
        start_date="2019-11-05",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_rate_signal_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        generate_rate_signals(
            _frame([float("nan")] * 40, "DFII10"),
            candidate="real_yield_relief",
            start_date="2019-11-05",
        )

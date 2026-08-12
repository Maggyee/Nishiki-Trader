from __future__ import annotations

import pandas as pd
import pytest

from apps.strategies_freqtrade.research.treasury_rate_signals import (
    generate_treasury_rate_signals,
)


def _frame(values: list[float], metric: str) -> pd.DataFrame:
    index = pd.date_range("2019-11-03", periods=len(values), freq="D", tz="UTC")
    return pd.DataFrame(
        {metric: values, "available_at": index, "snapshot_sha256": "sha256:" + "a" * 64, "vintage_id": "fixture"},
        index=index,
    )


@pytest.mark.parametrize(
    ("candidate", "metric", "values"),
    [
        ("real_yield_relief", "real_10y", [2.0] * 20 + [1.0] * 8 + [3.0] * 15),
        ("yield_curve_steepening", "nominal_10y_minus_2y", [0.0] * 20 + [1.0] * 8 + [-1.0] * 15),
    ],
)
def test_directional_rate_rules_emit_buy_then_flat(
    candidate: str, metric: str, values: list[float]
) -> None:
    events = generate_treasury_rate_signals(
        _frame(values, metric), candidate=candidate, start_date="2019-11-03", end_date="2020-12-31"
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_treasury_volatility_relief_uses_absolute_changes() -> None:
    volatile = [1.0 + ((-1) ** index) * 0.5 for index in range(25)]
    quiet = [1.0 + index * 0.001 for index in range(10)]
    events = generate_treasury_rate_signals(
        _frame(volatile + quiet + volatile[:20], "nominal_10y"),
        candidate="treasury_volatility_relief",
        start_date="2019-11-03",
        end_date="2020-12-31",
    )
    assert [event.side for event in events] == ["buy", "flat"]


def test_treasury_signal_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        generate_treasury_rate_signals(
            _frame([float("nan")] * 40, "real_10y"),
            candidate="real_yield_relief",
            start_date="2019-11-03",
        )

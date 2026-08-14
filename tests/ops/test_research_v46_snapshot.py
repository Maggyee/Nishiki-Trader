from __future__ import annotations

from apps.ops.research_v46_snapshot import (
    collect_and_qualify_all,
    compute_factors,
)


def test_compute_factors_v46_generates_three_series() -> None:
    rows = []
    for i in range(100):
        rows.append({
            "date": f"2020-01-{i+1:02d}" if i < 30 else f"2020-02-{i-29:02d}",
            "premium_open": 0.0001,
            "premium_high": 0.0002,
            "premium_low": -0.0001,
            "premium_close": 0.0001 - (i % 10) * 0.00005,
        })
    factors = compute_factors(rows)
    assert "btc_prem_diff5_negative" in factors
    assert "btc_prem_diff5_loose" in factors
    assert "btc_prem_diff5_minhold2" in factors
    assert len(factors["btc_prem_diff5_negative"]) == 100


def test_collect_and_qualify_all_structure_v46() -> None:
    assert callable(collect_and_qualify_all)

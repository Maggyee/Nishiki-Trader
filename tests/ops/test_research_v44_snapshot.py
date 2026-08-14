from __future__ import annotations

from apps.ops.research_v44_snapshot import (
    collect_and_qualify_all,
    compute_factors,
)


def test_compute_factors_v44_generates_three_series() -> None:
    rows = []
    for i in range(100):
        rows.append({
            "date": f"2020-01-{i+1:02d}" if i < 30 else f"2020-02-{i-29:02d}",
            "open": 10000.0 + i * 10,
            "high": 10100.0 + i * 10,
            "low": 9900.0 + i * 10,
            "close": 10050.0 + i * 10,
            "volume": 1000.0 + (i % 5) * 100,
        })
    factors = compute_factors(rows)
    assert "btc_trend_pullback_rsi20" in factors
    assert "btc_trend_pullback_rsi15" in factors
    assert "btc_trend_pullback_rsi10" in factors
    assert len(factors["btc_trend_pullback_rsi20"]) == 100


def test_collect_and_qualify_all_structure_v44() -> None:
    assert callable(collect_and_qualify_all)

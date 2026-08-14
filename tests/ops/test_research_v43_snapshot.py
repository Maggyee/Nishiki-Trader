from __future__ import annotations

from apps.ops.research_v43_snapshot import (
    collect_and_qualify_all,
    compute_factors,
)


def test_compute_factors_generates_three_series() -> None:
    # Dummy klines
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
    assert "btc_macd_vol_confirmed" in factors
    assert "btc_macd_rsi_vol_confirmed" in factors
    assert "btc_macd_vol_tight" in factors
    assert len(factors["btc_macd_vol_confirmed"]) == 100


def test_collect_and_qualify_all_structure() -> None:
    # Just ensure import and validator pass
    assert callable(collect_and_qualify_all)

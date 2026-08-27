"""Offline tests for the cross-sectional harness and the v52 contract."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.ops import research_protocol_v52 as contract
from apps.ops.research_xs_portfolio import (
    _rank_metric,
    _select_legs,
    apply_gates,
    permutation_p_value,
    run_portfolio,
    universe_coverage_errors,
)

SYMBOLS = [f"S{i:02d}USDT" for i in range(11)] + ["BTCUSDT"]


def _growth_frame(start: str = "2019-12-01", end: str = "2020-03-31") -> pd.DataFrame:
    """12 symbols with strictly ordered constant daily growth (S00 lowest)."""
    dates = pd.date_range(start, end, freq="D", tz="UTC")
    data = {}
    for i, symbol in enumerate(SYMBOLS):
        rate = -0.004 + 0.0008 * i
        data[symbol] = 100.0 * np.cumprod(np.full(len(dates), 1.0 + rate))
    return pd.DataFrame(data, index=dates)


def test_contract_is_valid_and_fingerprint_stable() -> None:
    assert contract.validate_contract() == []
    assert contract.contract_sha256() == contract.contract_sha256()
    assert len(contract.SYMBOL_POOL) == 22
    assert contract.WINDOWS["development"][1] < contract.WINDOWS["confirmation"][0]


def test_rank_and_selection_follow_frozen_rules() -> None:
    closes = _growth_frame()
    pos = 40  # a date with full 30d lookback
    mom = _rank_metric(closes, pos, "xs_mom_30d", 30)
    assert mom.idxmax() == "BTCUSDT" and mom.idxmin() == "S00USDT"
    legs = _select_legs(mom, "xs_mom_30d", 3)
    assert legs["BTCUSDT"] == 1 and legs["S00USDT"] == -1
    assert sum(1 for s in legs.values() if s == 1) == 3
    assert sum(1 for s in legs.values() if s == -1) == 3
    rev = _select_legs(_rank_metric(closes, pos, "xs_rev_7d", 7), "xs_rev_7d", 3)
    assert rev["S00USDT"] == 1 and rev["BTCUSDT"] == -1  # reversal longs the losers
    vol = _rank_metric(closes, pos, "xs_lowvol_30d", 30)
    assert vol.notna().all()


def test_rank_metric_ignores_future_data() -> None:
    closes = _growth_frame()
    pos = 40
    before = _rank_metric(closes, pos, "xs_mom_30d", 30)
    mutated = closes.copy()
    mutated.iloc[pos + 1 :] = mutated.iloc[pos + 1 :] * 5.0
    after = _rank_metric(mutated, pos, "xs_mom_30d", 30)
    pd.testing.assert_series_equal(before, after)


def test_portfolio_costs_match_fill_count_for_static_composition() -> None:
    closes = _growth_frame()
    result = run_portfolio(closes, contract, "xs_mom_30d", "2020-01-01", "2020-03-31")
    # constant growth ordering -> composition never changes: 6 entry + 6 exit fills
    expected_base_fees = 12 * 100.0 * 0.0012
    assert result["closed_leg_positions"] == 6
    assert result["base_net_pnl"] == pytest.approx(
        result["gross_net_pnl"] - expected_base_fees, abs=1e-9
    )
    assert result["stress_net_pnl"] == pytest.approx(
        result["gross_net_pnl"] - 12 * 100.0 * 0.0015, abs=1e-9
    )
    # long winners, short losers on a monotonic-growth frame is profitable gross
    assert result["gross_net_pnl"] > 0
    assert result["net_exposure_fraction"] == pytest.approx(0.0, abs=1e-9)
    repeat = run_portfolio(closes, contract, "xs_mom_30d", "2020-01-01", "2020-03-31")
    assert repeat == result


def test_delisting_forces_close_and_failsafe_flattens_small_universe() -> None:
    closes = _growth_frame()
    cut = pd.Timestamp("2020-02-15", tz="UTC")
    # S00 is a held short leg for momentum; its archive ends mid-window
    closes.loc[closes.index > cut, "S00USDT"] = np.nan
    result = run_portfolio(closes, contract, "xs_mom_30d", "2020-01-01", "2020-03-31")
    full = run_portfolio(_growth_frame(), contract, "xs_mom_30d", "2020-01-01", "2020-03-31")
    # the held S00 leg is force-closed at its last available close, and after
    # the delist eligible = 11 < min_universe 12 -> the whole book goes flat
    assert result["closed_leg_positions"] == 6
    assert result["gross_net_pnl"] < full["gross_net_pnl"]
    assert result["mean_holding_days"] < full["mean_holding_days"]
    # flat book after mid-February: gross accrues nothing in March
    march = run_portfolio(closes, contract, "xs_mom_30d", "2020-01-01", "2020-02-14")
    assert result["gross_net_pnl"] == pytest.approx(march["gross_net_pnl"], rel=0.2)


def test_permutation_p_value_is_deterministic_and_bounded() -> None:
    rng = np.random.default_rng(9)
    dates = pd.date_range("2019-12-01", "2020-06-30", freq="D", tz="UTC")
    data = {symbol: 100.0 * np.cumprod(1.0 + rng.normal(0, 0.02, len(dates))) for symbol in SYMBOLS}
    closes = pd.DataFrame(data, index=dates)
    p1 = permutation_p_value(
        closes, contract, "xs_mom_30d", "2020-01-01", "2020-06-30", 1.0, n_trials=300, seed=5
    )
    p2 = permutation_p_value(
        closes, contract, "xs_mom_30d", "2020-01-01", "2020-06-30", 1.0, n_trials=300, seed=5
    )
    assert p1 == p2
    assert 0.0 < p1 <= 1.0
    lucky = permutation_p_value(
        closes, contract, "xs_mom_30d", "2020-01-01", "2020-06-30", 1e9, n_trials=300, seed=5
    )
    assert lucky == pytest.approx(1 / 301)


def test_universe_coverage_errors_flag_gaps_and_minimum() -> None:
    closes = _growth_frame()
    gappy = closes.copy()
    gappy.loc[gappy.index[50] : gappy.index[52], "S03USDT"] = np.nan  # interior gap
    universe, errors = universe_coverage_errors(gappy, contract, "2019-12-01", "2020-03-31")
    assert "S03USDT" not in universe
    assert any("below minimum" in e for e in errors)  # 11 < 12


def test_apply_gates_requires_all_checks() -> None:
    candidate = {
        "base_net_pnl": 50.0,
        "stress_net_pnl": 40.0,
        "positive_years": 2,
        "positive_months": 20,
        "closed_leg_positions": 120,
        "leave_best_leg_base_net_pnl": 5.0,
        "net_exposure_fraction": 0.0,
    }
    gates = contract.GATES_V2["confirmation"]
    good = apply_gates(gates, candidate, btc_bh_pnl_100usdt=80.0, p_value=0.02)
    assert good["pass_gates"] is True
    assert good["benchmark_floor"] == pytest.approx(0.0)
    bad = apply_gates(gates, dict(candidate, positive_months=10), 80.0, 0.02)
    assert bad["checks"]["months_breadth"] is False and bad["pass_gates"] is False

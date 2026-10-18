from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.research import gates, replay

GATES = {
    "base_net_pnl_gt": 0.0,
    "stress_net_pnl_gt": 0.0,
    "positive_years_fraction_at_least": 0.6667,
    "months_breadth_rule": "adaptive_null_median",
    "closed_positions_at_least": 1,
    "leave_best_base_net_pnl_gt": 0.0,
    "benchmark_relative": True,
    "p_value_max": 0.10,
}


def _days(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="D", tz="UTC")


def test_weight_decided_at_close_earns_next_day_and_pays_costs() -> None:
    days = _days(4)
    closes = pd.DataFrame({"A": [100.0, 110.0, 121.0, 121.0]}, index=days)
    weights = pd.DataFrame({"A": [0.0, 1.0, 0.0, 0.0]}, index=days)

    result = replay.run(
        weights,
        closes,
        start="2020-01-02",
        end="2020-01-04",
        notional=1000.0,
        costs_bps={"base": 10.0, "stress": 20.0},
    )

    # Day 2's decision earns day 3's +10%; entry and exit cost 10 bps each.
    assert result["gross_net_pnl"] == pytest.approx(100.0)
    assert result["base_net_pnl"] == pytest.approx(98.0)
    assert result["stress_net_pnl"] == pytest.approx(96.0)
    assert result["closed_positions"] == 1
    assert result["leave_best_base_net_pnl"] == pytest.approx(0.0)


def test_episodes_sum_to_base_pnl_through_flips_and_resizes() -> None:
    rng = np.random.default_rng(1)
    held = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], size=(200, 3))
    returns = rng.normal(0.0, 0.02, size=(200, 3))

    episodes = replay._episodes(held, returns, 1000.0, 0.0012)

    assert sum(episodes) == pytest.approx(replay.daily_pnl(held, returns, 1000.0, 0.0012).sum())


def test_book_open_before_window_pays_entry_and_is_closed_at_end() -> None:
    days = _days(5)
    closes = pd.DataFrame({"A": [100.0, 100.0, 100.0, 100.0, 100.0]}, index=days)
    weights = pd.DataFrame({"A": [1.0] * 5}, index=days)

    result = replay.run(
        weights,
        closes,
        start="2020-01-03",
        end="2020-01-05",
        notional=1000.0,
        costs_bps={"base": 10.0, "stress": 10.0},
    )

    assert result["base_net_pnl"] == pytest.approx(-2.0)
    assert result["time_in_market"] == 1.0


def test_null_rejects_noise_and_accepts_perfect_timing() -> None:
    days = _days(730)
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0, 0.03, size=(730, 2))
    noise = rng.choice([-1.0, 1.0], size=(730, 2)) * 0.5
    perfect = np.sign(returns) * 0.5

    def p_value(held: np.ndarray) -> float:
        observed = replay.daily_pnl(held, returns, 1000.0, 0.0).sum()
        return gates.shift_null(
            held,
            returns,
            days,
            observed_base=observed,
            notional=1000.0,
            cost=0.0,
            trials=500,
            seed=3,
        )["p_value"]

    assert p_value(noise) > 0.10
    assert p_value(perfect) < 0.01


def test_gates_read_two_of_three_years_and_compare_to_benchmark() -> None:
    result = {
        "base_net_pnl": 50.0,
        "stress_net_pnl": 40.0,
        "positive_years": 2,
        "years_total": 3,
        "positive_months": 20,
        "closed_positions": 5,
        "leave_best_base_net_pnl": 10.0,
        "benchmark_pnl": 60.0,
    }
    null = {"p_value": 0.05, "null_months_positive_median": 18.0}

    verdict = gates.apply_gates(GATES, result, null)

    assert verdict["years_needed"] == 2
    assert verdict["checks"]["years_breadth"]
    assert not verdict["checks"]["benchmark_relative"]
    assert not verdict["pass"]

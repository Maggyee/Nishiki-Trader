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

    assert sum(episodes) == pytest.approx(replay.bar_pnl(held, returns, 1000.0, 0.0012).sum())


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
        observed = replay.bar_pnl(held, returns, 1000.0, 0.0).sum()
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


def test_funding_is_paid_by_longs_and_received_by_shorts() -> None:
    days = _days(3)
    closes = pd.DataFrame({"L": [100.0] * 3, "S": [100.0] * 3}, index=days)
    weights = pd.DataFrame({"L": [0.5] * 3, "S": [-0.5] * 3}, index=days)
    settlements = days + pd.Timedelta(hours=8)  # one settlement inside each holding day
    funding = pd.DataFrame({"L": [0.001] * 3, "S": [0.001] * 3}, index=settlements)

    def pnl(asset: str) -> float:
        return replay.run(
            weights[[asset]],
            closes[[asset]],
            start="2020-01-02",
            end="2020-01-03",
            notional=1000.0,
            costs_bps={"base": 0.0, "stress": 0.0},
            funding=funding,
        )["base_net_pnl"]

    assert pnl("L") == pytest.approx(-1.0)  # 2 days x 0.5 x 1000 x 0.1%
    assert pnl("S") == pytest.approx(1.0)


def test_daily_funding_assigns_midnight_to_previous_day_and_sums_settlements() -> None:
    days = _days(3)
    closes = pd.DataFrame({"A": 100.0}, index=days)
    weights = pd.DataFrame({"A": 1.0}, index=days)
    funding = pd.DataFrame(
        {"A": [0.0001, 0.0002, 0.0003, 0.0004]},
        index=pd.to_datetime(
            ["2020-01-02 00:00", "2020-01-02 08:00", "2020-01-02 16:00", "2020-01-03 00:00"],
            utc=True,
        ),
    )
    index, held, returns = replay.window_arrays(
        weights, closes, "2020-01-01", "2020-01-03", funding
    )
    pd.testing.assert_index_equal(index, days)
    np.testing.assert_allclose(returns[:, 0], [-0.0001, -0.0009, 0.0])
    np.testing.assert_array_equal(held[:, 0], [0.0, 1.0, 1.0])


def test_hourly_funding_settlement_at_eight_belongs_to_seven_oclock_bar() -> None:
    index = pd.date_range("2020-01-01", periods=24, freq="h", tz="UTC")
    closes = pd.DataFrame({"A": 100.0}, index=index)
    funding = pd.DataFrame({"A": [0.001]}, index=index[[8]])
    _, _, returns = replay.window_arrays(
        closes * 0.0 + 1.0, closes, "2020-01-01", "2020-01-01", funding, bar="1h"
    )
    expected = np.zeros(24)
    expected[7] = -0.001
    np.testing.assert_array_equal(returns[:, 0], expected)


@pytest.mark.parametrize("lag", [0, 1])
def test_minute_decisions_earn_the_next_bar_plus_execution_lag(lag: int) -> None:
    index = pd.date_range("2020-01-01 23:58", periods=7, freq="min", tz="UTC")
    closes = pd.DataFrame({"A": [100, 110, 132, 171.6, 171.6, 171.6, 171.6]}, index=index)
    weights = pd.DataFrame({"A": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=index)
    bars, held, returns = replay.window_arrays(
        weights, closes, "2020-01-01", "2020-01-02", bar="1min", lag=lag
    )
    pd.testing.assert_index_equal(bars, index)
    expected = np.zeros(7)
    expected[1 + lag] = 1.0
    np.testing.assert_array_equal(held[:, 0], expected)
    result = replay.run(
        weights,
        closes,
        start="2020-01-01",
        end="2020-01-02",
        notional=1000.0,
        costs_bps={"base": 0.0, "stress": 0.0},
        bar="1min",
        lag=lag,
    )
    assert result["base_net_pnl"] == pytest.approx(1000.0 * returns[1 + lag, 0])
    assert result["bars"] == 7
    assert result["days"] == 2
    assert result["active_days"] == 1
    assert "base_pnl_sha256" in result
    assert "daily_base_pnl_sha256" not in result


def test_end_date_includes_all_minutes_and_counts_distinct_active_dates() -> None:
    index = pd.date_range("2019-12-31 23:59", periods=1442, freq="min", tz="UTC")
    closes = pd.DataFrame({"A": 100.0}, index=index)
    weights = pd.DataFrame({"A": 1.0}, index=index)
    result = replay.run(
        weights,
        closes,
        start="2020-01-01",
        end="2020-01-01",
        notional=1000.0,
        costs_bps={"base": 10.0, "stress": 10.0},
        bar="1min",
    )
    assert result["bars"] == 1440
    assert result["days"] == result["active_days"] == 1
    assert result["base_net_pnl"] == pytest.approx(-2.0)
    result = replay.run(
        weights,
        closes,
        start="2019-12-31",
        end="2020-01-02",
        notional=1000.0,
        costs_bps={"base": 0.0, "stress": 0.0},
        bar="1min",
    )
    assert result["days"] == 3
    assert result["active_days"] == 2  # The lone Dec 31 bar is flat before the first decision.
    flat = replay.run(
        weights * 0.0,
        closes,
        start="2020-01-01",
        end="2020-01-01",
        notional=1000.0,
        costs_bps={"base": 0.0, "stress": 0.0},
        bar="1min",
    )
    assert flat["active_days"] == 0


def test_intraday_missing_bar_uses_last_close_and_rejects_negative_lag() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="min", tz="UTC")
    closes = pd.DataFrame({"A": [100, 110, 121]}, index=index[[0, 2, 3]])
    weights = pd.DataFrame({"A": 1.0}, index=closes.index)
    bars, held, returns = replay.window_arrays(
        weights, closes, "2020-01-01", "2020-01-01", bar="1min"
    )
    pd.testing.assert_index_equal(bars, index)
    np.testing.assert_allclose(returns[:, 0], [0.0, 0.0, 0.1, 0.1])
    np.testing.assert_array_equal(held[:, 0], [0.0, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match="nonnegative"):
        replay.window_arrays(weights, closes, "2020-01-01", "2020-01-01", bar="1min", lag=-1)


def _old_null(held, returns, days, *, observed_base, notional, cost, trials, seed):
    # Frozen reference loop from the daily harness, before per-asset reduction.
    rng = np.random.default_rng(seed)
    n_days, n_assets = held.shape
    month_codes = days.tz_localize(None).to_period("M").asi8
    month_starts = np.flatnonzero(np.r_[True, np.diff(month_codes) != 0])
    totals = np.empty(trials)
    positive_months = np.empty(trials)
    rows = np.arange(n_days)[:, None]
    for trial in range(trials):
        shifts = rng.integers(1, n_days, size=n_assets)
        shifted = held[(rows - shifts[None, :]) % n_days, np.arange(n_assets)]
        pnl = replay.bar_pnl(shifted, returns, notional, cost)
        totals[trial] = pnl.sum()
        positive_months[trial] = (np.add.reduceat(pnl, month_starts) > 0).sum()
    return {
        "p_value": (1 + int((totals >= observed_base).sum())) / (trials + 1),
        "null_months_positive_median": float(np.median(positive_months)),
        "null_base_mean": float(totals.mean()),
        "null_base_p90": float(np.quantile(totals, 0.9)),
    }


@pytest.mark.parametrize("seed", [3, 42, 20261018])
def test_daily_null_p_values_and_months_match_original_algorithm(seed: int) -> None:
    rng = np.random.default_rng(15)
    days = _days(730)
    held = rng.choice([-0.25, 0.0, 0.25], size=(730, 4))
    returns = rng.normal(0.0, 0.03, size=held.shape)
    args = {
        "observed_base": replay.bar_pnl(held, returns, 1000.0, 0.0012).sum(),
        "notional": 1000.0,
        "cost": 0.0012,
        "trials": 200,
        "seed": seed,
    }
    expected = _old_null(held, returns, days, **args)
    actual = gates.shift_null(held, returns, days, **args)
    assert actual["p_value"] == expected["p_value"]
    assert actual["null_months_positive_median"] == expected["null_months_positive_median"]
    assert actual["null_base_mean"] == pytest.approx(expected["null_base_mean"], abs=1e-9)
    assert actual["null_base_p90"] == pytest.approx(expected["null_base_p90"], abs=1e-9)


def test_day_shift_unit_only_draws_whole_days(monkeypatch) -> None:
    days = pd.date_range("2020-01-01", periods=72, freq="h", tz="UTC")
    held = np.ones((72, 2)) * 0.5
    shifts = []
    original = np.roll

    def record(array, shift):
        shifts.append(int(shift))
        return original(array, shift)

    monkeypatch.setattr(gates.np, "roll", record)
    gates.shift_null(
        held,
        held * 0.01,
        days,
        observed_base=0.0,
        notional=1000.0,
        cost=0.0012,
        trials=10,
        seed=9,
        shift_unit=24,
    )
    assert len(shifts) == 20
    assert set(shifts) == {24, 48}
    with pytest.raises(ValueError, match="two shift units"):
        gates.shift_null(
            held[:24],
            held[:24],
            days[:24],
            observed_base=0.0,
            notional=1000.0,
            cost=0.0,
            trials=1,
            seed=9,
            shift_unit=24,
        )


@pytest.mark.parametrize("floor", [None, 2, 3])
def test_active_days_gate_is_opt_in(floor: int | None) -> None:
    result = {
        "base_net_pnl": 50.0,
        "stress_net_pnl": 40.0,
        "positive_years": 2,
        "years_total": 3,
        "positive_months": 20,
        "closed_positions": 5,
        "leave_best_base_net_pnl": 10.0,
        "benchmark_pnl": 30.0,
    }
    spec = dict(GATES)
    if floor is not None:
        spec["active_days_at_least"] = floor
        result["active_days"] = 2
    verdict = gates.apply_gates(
        spec, result, {"p_value": 0.05, "null_months_positive_median": 18.0}
    )
    assert ("active_days_floor" in verdict["checks"]) == (floor is not None)
    assert verdict["pass"] == (floor != 3)

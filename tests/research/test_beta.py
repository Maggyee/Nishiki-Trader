from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.research import beta


def _closes(**columns: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(next(iter(columns.values()))), tz="UTC")
    return pd.DataFrame(columns, index=index)


def test_buy_and_hold_reserves_fees_and_follows_price() -> None:
    closes = _closes(A=[100.0, 110.0, 99.0])
    hold = pd.DataFrame({"A": [1.0]}, index=closes.index[:1])

    result = beta.simulate(hold, closes, cost=0.001, start="2020-01-01", end="2020-01-03")

    invested = 10_000.0 / 1.001  # entry fee comes out of the buy, cash ends at 0
    expected = [invested, invested * 1.1, invested * 0.99 * (1 - 0.001)]
    assert result["equity"].tolist() == pytest.approx(expected)
    assert result["trades"] == 1


def test_full_rotation_never_leaves_negative_cash() -> None:
    closes = _closes(A=[100.0, 100.0], B=[50.0, 50.0])
    weights = pd.DataFrame({"A": [1.0, 0.0], "B": [0.0, 1.0]}, index=closes.index)

    result = beta.simulate(weights, closes, cost=0.002, start="2020-01-01", end="2020-01-02")

    # Day 2 sells A and buys B: both legs pay fees out of the same equity.
    day1 = 10_000.0 / 1.002
    day2_invested = day1 * (1 - 0.002) / (1 + 0.002)  # sell fee + buy fee
    assert result["equity"].iloc[1] == pytest.approx(day2_invested * (1 - 0.002), rel=1e-9)


def test_window_must_be_fully_covered() -> None:
    closes = _closes(A=[100.0, 100.0, 100.0])
    hold = pd.DataFrame({"A": [1.0]}, index=closes.index[:1])
    with pytest.raises(ValueError, match="cover"):
        beta.simulate(hold, closes, cost=0.0, start="2019-12-31", end="2020-01-03")
    with pytest.raises(ValueError, match="cover"):
        beta.simulate(hold, closes, cost=0.0, start="2020-01-01", end="2020-01-04")
    pair = pd.DataFrame({"A": [0.5], "B": [0.5]}, index=closes.index[:1])
    for gappy in (
        closes.assign(B=[np.nan, 50.0, 50.0]),  # listed late
        closes.assign(B=[50.0, 55.0, np.nan]),  # ends early
        closes.assign(B=50.0).drop(closes.index[1]),  # missing middle day
    ):
        with pytest.raises(ValueError, match="cover"):
            beta.simulate(pair, gappy, cost=0.0, start="2020-01-01", end="2020-01-03")


def test_units_drift_until_the_target_changes() -> None:
    closes = _closes(A=[100.0, 200.0, 200.0, 200.0], B=[100.0, 100.0, 100.0, 100.0])
    weights = pd.DataFrame(
        {"A": [0.5, 0.5, 0.0, 0.0], "B": [0.5, 0.5, 0.5, 0.5]}, index=closes.index
    )

    result = beta.simulate(weights, closes, cost=0.0, start="2020-01-01", end="2020-01-04")

    # Day 2: A doubled and is not rebalanced (15,000). Day 3: A sold, B resized to
    # half of equity, half in cash.
    assert result["equity"].tolist() == pytest.approx([10_000.0, 15_000.0, 15_000.0, 15_000.0])
    assert result["trades"] == 4
    assert result["time_in_market"] == 1.0


def test_rejects_shorts_and_leverage() -> None:
    closes = _closes(A=[100.0, 100.0])
    for bad in (-0.1, 1.5):
        with pytest.raises(ValueError, match="long/flat"):
            beta.simulate(
                pd.DataFrame({"A": [bad]}, index=closes.index[:1]),
                closes,
                cost=0.0,
                start="2020-01-01",
                end="2020-01-02",
            )


def test_metrics_cagr_drawdown_and_calendar_years() -> None:
    index = pd.DatetimeIndex(["2020-06-30", "2020-12-31", "2021-06-30", "2021-12-31"], tz="UTC")
    equity = pd.Series([12_000.0, 15_000.0, 7_500.0, 9_000.0], index=index)

    m = beta.metrics(equity)

    assert m["max_drawdown"] == pytest.approx(0.5)
    assert m["yearly_return"] == pytest.approx({2020: 0.5, 2021: -0.4})
    years = (index[-1] - index[0]).days / 365.25
    assert m["cagr"] == pytest.approx(0.9 ** (1 / years) - 1)


def test_admission_criteria() -> None:
    bench = {"max_drawdown": 0.75, "cagr": 0.40, "cagr_over_max_drawdown": 0.40 / 0.75,
             "yearly_return": {2022: -0.70}}  # fmt: skip
    good = {"max_drawdown": 0.45, "cagr": 0.30, "cagr_over_max_drawdown": 0.30 / 0.45,
            "yearly_return": {2022: -0.20}}  # fmt: skip

    assert beta.admit(good, bench, stress_final=20_000.0)["admitted"]
    worse = good | {"max_drawdown": 0.55, "cagr_over_max_drawdown": 0.30 / 0.55}
    assert not beta.admit(worse, bench, 20_000.0)["checks"]["drawdown_at_most_two_thirds"]
    timid = good | {"cagr": 0.15, "cagr_over_max_drawdown": 0.15 / 0.10, "max_drawdown": 0.10}
    assert not beta.admit(timid, bench, 20_000.0)["checks"]["cagr_at_least_half"]
    bad_2022 = good | {"yearly_return": {2022: -0.36}}
    assert not beta.admit(bad_2022, bench, 20_000.0)["checks"]["loss_2022_at_most_half"]
    assert not beta.admit(good, bench, stress_final=9_000.0)["admitted"]


def test_weekly_reset_stops_partial_exposure_from_drifting() -> None:
    closes = _closes(A=[100.0, 200.0, 200.0, 200.0, 200.0, 100.0, 100.0])
    half = pd.DataFrame({"A": [0.5]}, index=closes.index[:1])
    args = {"cost": 0.0, "start": "2020-01-01", "end": "2020-01-07"}
    assert closes.index[4].weekday() == 6  # 2020-01-05 is a Sunday

    drift = beta.simulate(half, closes, **args)
    weekly = beta.simulate(half, closes, rebalance_weekday=6, **args)

    # A doubles on day 2: 10,000 of A and 5,000 cash. Unreset, A is 2/3 of the book
    # when it halves (-> 10,000); reset to half on Sunday it holds 7,500 (-> 11,250).
    assert drift["equity"].iloc[-1] == pytest.approx(10_000.0)
    assert weekly["equity"].iloc[-1] == pytest.approx(11_250.0)
    assert (drift["trades"], weekly["trades"]) == (1, 2)

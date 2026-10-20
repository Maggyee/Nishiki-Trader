"""Synthetic close-time, baseline and hold checks for the v60 mechanism."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research import intraday_flow

DAY = 1440
MINUTE = pd.Timedelta(minutes=1)
PARAMS = {
    "return_window_minutes": 60,
    "oi_window_minutes": 60,
    "oi_max_staleness_minutes": 10,
    "baseline_days": 1,
    "quantile": 0.005,
    "min_baseline_fraction": 0.5,
    "hold_minutes": 240,
    "weight_per_symbol": 0.1,
}


def _frames(shocks: tuple[int, ...] = (), periods: int = 2 * DAY) -> dict:
    index = pd.date_range("2024-01-01", periods=periods, freq="min", tz="UTC")
    levels = np.full(periods, 100.0)
    # Sixty -.5 returns in the prior day fix both 0.5% quantiles at -.5.
    levels[120:180] = 50.0
    levels[list(shocks)] = 50.0
    return {
        "spot_klines_1m": {"BTCUSDT": pd.DataFrame({"close": levels.copy()}, index=index)},
        "um_metrics_5m": {
            "BTCUSDT": pd.DataFrame({"open_interest": levels.copy()}, index=index + MINUTE)
        },
    }


def _weights(frames: dict, **params) -> pd.DataFrame:
    return intraday_flow.target_weights(frames, "cascade_rebound", PARAMS | params)


@pytest.mark.parametrize("reenter", [False, True])
def test_four_hour_hold_ignores_retriggers_then_can_reenter(reenter: bool) -> None:
    start = DAY + 120
    shocks = (start, start + 40, start + 240) if reenter else (start, start + 40)
    frames = _frames(shocks)
    weights = _weights(frames)
    expected = np.zeros(2 * DAY)
    expected[start : start + (480 if reenter else 240)] = 0.1
    np.testing.assert_array_equal(weights["BTCUSDT"], expected)
    assert intraday_flow.PRICE_DATASET == "spot_klines_1m"
    assert PARAMS["hold_minutes"] == 240


@pytest.mark.parametrize(("offset", "expected"), [(1, 0.1), (2, 0.0)])
def test_oi_observation_at_decision_close_is_used_but_later_one_is_not(offset, expected):
    frames = _frames()
    prices = frames["spot_klines_1m"]["BTCUSDT"]
    t = prices.index[DAY + 120]
    prices.loc[t, "close"] = 50.0
    frames["um_metrics_5m"]["BTCUSDT"].loc[t + offset * MINUTE, "open_interest"] = 50.0
    assert _weights(frames).loc[t, "BTCUSDT"] == expected


@pytest.mark.parametrize("endpoint", ["current", "previous"])
@pytest.mark.parametrize(("age", "expected"), [(10, 0.1), (11, 0.0)])
def test_asof_staleness_is_checked_at_both_endpoints_and_boundary_is_inclusive(
    endpoint, age, expected
):
    frames = _frames()
    prices = frames["spot_klines_1m"]["BTCUSDT"]
    t = prices.index[DAY + 120]
    prices.loc[t, "close"] = 50.0
    metrics = frames["um_metrics_5m"]["BTCUSDT"]
    metrics.loc[t + MINUTE, "open_interest"] = 50.0
    query = t + MINUTE - (60 * MINUTE if endpoint == "previous" else pd.Timedelta(0))
    last = query - age * MINUTE
    metrics.loc[last, "open_interest"] = 100.0 if endpoint == "previous" else 50.0
    frames["um_metrics_5m"]["BTCUSDT"] = metrics.drop(
        metrics.index[(metrics.index > last) & (metrics.index <= query)]
    )
    assert _weights(frames).loc[t, "BTCUSDT"] == expected


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan])
@pytest.mark.parametrize("endpoint", ["current", "previous"])
def test_asof_missing_or_nonpositive_last_value_does_not_fall_back(value, endpoint):
    frames = _frames()
    prices = frames["spot_klines_1m"]["BTCUSDT"]
    t = prices.index[DAY + 120]
    prices.loc[t, "close"] = 50.0
    metrics = frames["um_metrics_5m"]["BTCUSDT"]
    metrics.loc[t + MINUTE, "open_interest"] = 50.0
    query = t + MINUTE - (60 * MINUTE if endpoint == "previous" else pd.Timedelta(0))
    metrics.loc[query - MINUTE, "open_interest"] = 100.0 if endpoint == "previous" else 50.0
    metrics.loc[query, "open_interest"] = value
    assert _weights(frames).loc[t, "BTCUSDT"] == 0.0


@pytest.mark.parametrize(("missing_offset", "expected"), [(60, 0.0), (30, 0.1), (0, 0.0)])
def test_return_lookback_uses_grid_endpoints_without_filling_missing_minutes(
    missing_offset, expected
):
    row = DAY + 120
    frames = _frames((row,))
    prices = frames["spot_klines_1m"]["BTCUSDT"]
    t = prices.index[row]
    frames["spot_klines_1m"]["BTCUSDT"] = prices.drop(t - missing_offset * MINUTE)
    weights = _weights(frames)
    pd.testing.assert_index_equal(weights.index, prices.index)
    assert weights.loc[t, "BTCUSDT"] == expected


def test_day_thresholds_exclude_all_of_the_current_day() -> None:
    frames = _frames((DAY + 400,))
    for symbols in frames.values():
        frame = symbols["BTCUSDT"]
        frame.iloc[DAY + 10 : DAY + 70, 0] = 25.0
    weights = _weights(frames)["BTCUSDT"]
    assert weights.iloc[DAY + 10] == 0.1
    assert weights.iloc[DAY + 250] == 0.0
    # Today's -.75 crash cannot lower today's prior-day threshold of -.5.
    assert weights.iloc[DAY + 400] == 0.1


def test_baseline_excludes_rows_older_than_its_calendar_window() -> None:
    frames = _frames(periods=3 * DAY)
    row = 2 * DAY + 120
    for symbols in frames.values():
        frame = symbols["BTCUSDT"]
        frame.iloc[2 * DAY :, 0] = np.arange(DAY) + 101.0
        frame.iloc[row, 0] = frame.iloc[row - 60, 0] * 0.75
    weights = _weights(frames)["BTCUSDT"]
    assert (weights.iloc[2 * DAY : row] == 0.0).all()
    # Day two's threshold is zero; day one's -.5 tail is outside the baseline.
    assert weights.iloc[row] == 0.1


@pytest.mark.parametrize(("level", "expected"), [(50.0, 0.1), (62.5, 0.1), (75.0, 0.0)])
def test_daily_quantile_is_linear_and_trigger_comparison_includes_equality(level, expected):
    index = pd.date_range("2024-01-01 22:55", periods=70, freq="min", tz="UTC")
    levels = np.full(70, 100.0)
    levels[60:65] = [50.0, 75.0, 100.0, 125.0, 150.0]
    levels[65] = level
    frames = {
        "spot_klines_1m": {"BTCUSDT": pd.DataFrame({"close": levels}, index=index)},
        "um_metrics_5m": {"BTCUSDT": pd.DataFrame({"open_interest": levels}, index=index + MINUTE)},
    }
    # Five finite prior-day values: [-.5, -.25, 0, .25, .5]; q=.125 is -.375.
    weights = _weights(frames, quantile=0.125, min_baseline_fraction=5 / DAY)
    assert weights.iloc[65, 0] == expected
    assert (weights.iloc[:65] == 0.0).all().all()


@pytest.mark.parametrize(("count", "expected"), [(1380, 0.1), (1381, 0.0)])
def test_minimum_baseline_counts_use_calendar_days_and_include_exact_boundary(count, expected):
    row = DAY + 120
    weights = _weights(_frames((row,)), min_baseline_fraction=count / DAY)
    assert weights.iloc[row, 0] == expected


@pytest.mark.parametrize("missing_series", ["close", "open_interest"])
def test_each_series_must_independently_meet_minimum_finite_baseline(missing_series):
    row = DAY + 120
    frames = _frames((row,))
    dataset = "spot_klines_1m" if missing_series == "close" else "um_metrics_5m"
    frames[dataset]["BTCUSDT"].iloc[300, 0] = np.nan
    # One missing endpoint invalidates both that row and the row sixty minutes later.
    assert _weights(frames, min_baseline_fraction=1379 / DAY).iloc[row, 0] == 0.0


def test_frozen_baseline_allows_partial_history_only_after_finite_count_reaches_half() -> None:
    frames = _frames(periods=17 * DAY)
    for symbols in frames.values():
        symbols["BTCUSDT"].iloc[:, 0] = 100.0
    weights = _weights(frames, baseline_days=30)
    assert (weights.iloc[: 16 * DAY] == 0.0).all().all()
    assert (weights.iloc[16 * DAY :] == 0.1).all().all()


def test_symbols_have_independent_triggers_and_holds() -> None:
    btc = _frames((DAY + 120,))
    eth = _frames((DAY + 400,))
    combined = {
        dataset: {"BTCUSDT": btc[dataset]["BTCUSDT"], "ETHUSDT": eth[dataset]["BTCUSDT"]}
        for dataset in btc
    }
    weights = _weights(combined)
    pd.testing.assert_series_equal(weights["BTCUSDT"], _weights(btc)["BTCUSDT"])
    pd.testing.assert_series_equal(weights["ETHUSDT"], _weights(eth)["BTCUSDT"].rename("ETHUSDT"))
    assert weights.iloc[DAY + 120].tolist() == [0.1, 0.0]
    assert weights.iloc[DAY + 400].tolist() == [0.0, 0.1]


def test_output_union_grid_is_float_flat_outside_symbol_history_and_gross_is_capped() -> None:
    row = DAY + 120
    base = _frames((row,))
    frames = {
        dataset: {f"COIN{i}": symbols["BTCUSDT"].copy() for i in range(10)}
        for dataset, symbols in base.items()
    }
    prices = frames["spot_klines_1m"]["COIN0"]
    frames["spot_klines_1m"]["COIN0"] = prices.iloc[30 : row + 100].drop(prices.index[row + 50])
    weights = _weights(frames)
    pd.testing.assert_index_equal(weights.index, prices.index)
    assert weights.columns.tolist() == list(frames["spot_klines_1m"])
    assert weights.loc[prices.index[row + 50], "COIN0"] == 0.1  # The hold crosses a missing bar.
    assert (weights["COIN0"].iloc[row + 100 :] == 0.0).all()
    assert not weights.isna().any().any()
    assert weights.dtypes.eq("float64").all()
    assert (weights >= 0.0).all().all()
    assert (weights.abs().sum(axis=1) <= 1.0 + 1e-12).all()
    assert weights.iloc[row].sum() == pytest.approx(1.0)


def test_future_changes_and_truncation_cannot_change_past_targets() -> None:
    frames = _frames((DAY + 120, DAY + 400))
    originals = {
        dataset: {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
        for dataset, symbols in frames.items()
    }
    weights = _weights(frames)
    t = weights.index[DAY + 150]
    changed = {
        dataset: {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
        for dataset, symbols in frames.items()
    }
    truncated = {}
    for dataset, symbols in changed.items():
        frame = symbols["BTCUSDT"]
        cutoff = t if dataset == "spot_klines_1m" else t + MINUTE
        future = frame.index > cutoff
        frame.loc[future, :] *= np.arange(2.0, int(future.sum()) + 2.0)[:, None]
        truncated[dataset] = {"BTCUSDT": frames[dataset]["BTCUSDT"].loc[:cutoff]}
    pd.testing.assert_frame_equal(weights.loc[:t], _weights(changed).loc[:t])
    pd.testing.assert_frame_equal(weights.loc[:t], _weights(truncated))
    for dataset, symbols in frames.items():
        pd.testing.assert_frame_equal(symbols["BTCUSDT"], originals[dataset]["BTCUSDT"])


@pytest.mark.parametrize("missing_symbol", [False, True])
def test_missing_metrics_suppress_all_triggers(missing_symbol: bool) -> None:
    frames = _frames((DAY + 120,))
    if missing_symbol:
        frames["um_metrics_5m"].clear()
    else:
        frames["um_metrics_5m"]["BTCUSDT"] = frames["um_metrics_5m"]["BTCUSDT"].iloc[:0]
    assert (_weights(frames) == 0.0).all().all()


@pytest.mark.parametrize("empty_universe", [False, True])
def test_empty_history_stays_utc_and_float(empty_universe: bool) -> None:
    frames = _frames(periods=0)
    if empty_universe:
        frames["spot_klines_1m"].clear()
    weights = _weights(frames)
    assert weights.empty
    assert str(weights.index.tz) == "UTC"
    assert weights.dtypes.eq("float64").all()


def test_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        intraday_flow.target_weights({}, "unknown", {})

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


LAGGARD_PARAMS = {
    "return_window_minutes": 60,
    "baseline_days": 1,
    "quantile": 0.995,
    "min_baseline_fraction": 0.5,
    "legs": 3,
    "min_universe": 6,
    "gross_weight": 1.0,
    "hold_minutes": 240,
}


def _laggard_frames(surges: tuple[int, ...] = (), periods: int = 2 * DAY) -> dict:
    index = pd.date_range("2024-01-01", periods=periods, freq="min", tz="UTC")
    # Deliberately neither alphabetical nor BTC-first, to exercise tie ordering.
    symbols = (
        "XRPUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "ADAUSDT",
        "LTCUSDT",
        "LINKUSDT",
        "TRXUSDT",
        "ETCUSDT",
        "XLMUSDT",
    )
    prices = {
        symbol: pd.DataFrame({"close": np.full(periods, 100.0)}, index=index) for symbol in symbols
    }
    # Sixty +100% returns set the prior-day upper 0.5% tail to +100%.
    prices["BTCUSDT"].iloc[120:180, 0] = 200.0
    prices["BTCUSDT"].iloc[list(surges), 0] = 200.0
    return {"spot_klines_1m": prices}


def _laggard_weights(frames: dict, **params) -> pd.DataFrame:
    return intraday_flow.target_weights(frames, "laggard_catchup", LAGGARD_PARAMS | params)


@pytest.mark.parametrize("reenter", [False, True])
def test_laggard_legs_stay_fixed_for_four_hours_and_retriggers_are_ignored(reenter):
    row = DAY + 120
    surges = (row, row + 40, row + 240) if reenter else (row, row + 40)
    frames = _laggard_frames(surges)
    prices = frames["spot_klines_1m"]
    first = ["ETHUSDT", "BNBUSDT", "ADAUSDT"]
    later = ["XRPUSDT", "LTCUSDT", "LINKUSDT"]
    for symbol, level in zip(first, [70.0, 80.0, 90.0], strict=True):
        prices[symbol].iloc[row, 0] = level
    for symbol, level in zip(later, [60.0, 70.0, 80.0], strict=True):
        prices[symbol].iloc[[row + 40, row + 240], 0] = level
    weights = _laggard_weights(frames)
    expected = pd.DataFrame(0.0, index=weights.index, columns=weights.columns)
    expected.loc[weights.index[row : row + 240], first] = 1 / 3
    if reenter:
        expected.loc[weights.index[row + 240 : row + 480], later] = 1 / 3
    pd.testing.assert_frame_equal(weights, expected)


def test_laggard_upper_threshold_uses_only_previous_days() -> None:
    frames = _laggard_frames((DAY + 400,))
    frames["spot_klines_1m"]["BTCUSDT"].iloc[DAY + 10 : DAY + 70, 0] = 400.0
    gross = _laggard_weights(frames).sum(axis=1)
    assert gross.iloc[DAY + 10] == 1.0
    assert gross.iloc[DAY + 250] == 0.0
    # Today's +300% surge cannot raise today's prior-day threshold of +100%.
    assert gross.iloc[DAY + 400] == 1.0


def test_laggard_baseline_discards_days_outside_calendar_window() -> None:
    row = 2 * DAY
    frames = _laggard_frames((row,), periods=3 * DAY)
    frames["spot_klines_1m"]["BTCUSDT"].iloc[row, 0] = 150.0
    # Day two's returns are all zero; day one's +100% tail is no longer included.
    assert _laggard_weights(frames).iloc[row].sum() == 1.0


@pytest.mark.parametrize(("level", "expected"), [(125.0, 0.0), (137.5, 1.0), (150.0, 1.0)])
def test_laggard_upper_quantile_is_linear_and_equality_triggers(level, expected):
    frames = _laggard_frames(periods=70)
    prices = frames["spot_klines_1m"]
    index = pd.date_range("2024-01-01 22:55", periods=70, freq="min", tz="UTC")
    for frame in prices.values():
        frame.index = index
    prices["BTCUSDT"].iloc[60:65, 0] = [50.0, 75.0, 100.0, 125.0, 150.0]
    prices["BTCUSDT"].iloc[65, 0] = level
    # Five prior-day values [-.5, -.25, 0, .25, .5], whose q=.875 is .375.
    weights = _laggard_weights(frames, quantile=0.875, min_baseline_fraction=5 / DAY)
    assert weights.iloc[65].sum() == expected
    assert (weights.iloc[:65] == 0.0).all().all()


@pytest.mark.parametrize(("count", "expected"), [(1380, 1.0), (1381, 0.0)])
def test_laggard_minimum_baseline_finite_count_includes_exact_boundary(count, expected):
    row = DAY + 120
    weights = _laggard_weights(_laggard_frames((row,)), min_baseline_fraction=count / DAY)
    assert weights.iloc[row].sum() == expected


def test_laggard_baseline_count_uses_only_finite_btc_returns() -> None:
    row = DAY + 120
    frames = _laggard_frames((row,))
    frames["spot_klines_1m"]["BTCUSDT"].iloc[300, 0] = np.nan
    # One missing close removes two returns, leaving 1378 finite baseline rows.
    assert _laggard_weights(frames, min_baseline_fraction=1379 / DAY).iloc[row].sum() == 0.0


def test_laggard_does_not_require_altcoin_baseline_histories() -> None:
    row = DAY + 120
    frames = _laggard_frames((row,))
    for symbol, frame in frames["spot_klines_1m"].items():
        if symbol != "BTCUSDT":
            frames["spot_klines_1m"][symbol] = frame.iloc[DAY:]
    assert _laggard_weights(frames).iloc[row].sum() == 1.0


def test_laggard_frozen_baseline_waits_for_half_of_thirty_days_of_finite_returns() -> None:
    frames = _laggard_frames(periods=17 * DAY)
    frames["spot_klines_1m"]["BTCUSDT"].iloc[:, 0] = 100.0
    gross = _laggard_weights(frames, baseline_days=30).sum(axis=1)
    assert (gross.iloc[: 16 * DAY] == 0.0).all()
    assert (gross.iloc[16 * DAY :] == 1.0).all()


def test_laggard_rank_ties_use_symbol_names_independent_of_input_order() -> None:
    row = DAY + 120
    frames = _laggard_frames((row,))
    prices = frames["spot_klines_1m"]
    for symbol, level in {
        "ADAUSDT": 70.0,
        "XRPUSDT": 80.0,
        "ETHUSDT": 80.0,
        "BNBUSDT": 80.0,
    }.items():
        prices[symbol].iloc[row, 0] = level
    weights = _laggard_weights(frames)
    assert set(weights.columns[weights.iloc[row] > 0.0]) == {"ADAUSDT", "BNBUSDT", "ETHUSDT"}
    reversed_frames = {"spot_klines_1m": dict(reversed(list(prices.items())))}
    pd.testing.assert_frame_equal(
        weights.sort_index(axis=1), _laggard_weights(reversed_frames).sort_index(axis=1)
    )


@pytest.mark.parametrize(("valid_alts", "expected"), [(5, 0.0), (6, 1.0)])
def test_laggard_requires_minimum_finite_non_btc_universe(valid_alts, expected):
    row = DAY + 120
    frames = _laggard_frames((row,))
    alts = [symbol for symbol in frames["spot_klines_1m"] if symbol != "BTCUSDT"]
    for symbol in alts[valid_alts:]:
        frames["spot_klines_1m"][symbol].iloc[row, 0] = np.inf
    assert _laggard_weights(frames).iloc[row].sum() == expected


def test_laggard_insufficient_universe_does_not_start_a_hold_and_next_row_can_trigger() -> None:
    row = DAY + 120
    frames = _laggard_frames((row, row + 1))
    for symbol in ["ADAUSDT", "BNBUSDT", "ETHUSDT", "XRPUSDT"]:
        frames["spot_klines_1m"][symbol].iloc[row, 0] = np.nan
    weights = _laggard_weights(frames)
    assert weights.iloc[row].sum() == 0.0
    assert (weights.iloc[row + 1 : row + 241].sum(axis=1) == 1.0).all()
    assert weights.iloc[row + 241].sum() == 0.0


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ADAUSDT"])
@pytest.mark.parametrize("missing_offset", [0, 30, 60])
def test_laggard_missing_minutes_invalidate_only_return_endpoints(symbol, missing_offset):
    row = DAY + 120
    frames = _laggard_frames((row,))
    prices = frames["spot_klines_1m"]
    prices["ADAUSDT"].iloc[row, 0] = 50.0
    index = prices["BTCUSDT"].index
    prices[symbol] = prices[symbol].drop(index[row - missing_offset])
    weights = _laggard_weights(frames)
    pd.testing.assert_index_equal(weights.index, index)
    invalid_endpoint = missing_offset in (0, 60)
    if symbol == "BTCUSDT" and invalid_endpoint:
        assert weights.iloc[row].sum() == 0.0
    else:
        assert weights.iloc[row].sum() == 1.0
        assert weights.iloc[row]["ADAUSDT"] == (0.0 if invalid_endpoint else 1 / 3)


def test_laggard_nonfinite_current_btc_return_does_not_trigger() -> None:
    row = DAY + 120
    frames = _laggard_frames((row,))
    frames["spot_klines_1m"]["BTCUSDT"].iloc[row, 0] = np.inf
    assert _laggard_weights(frames).iloc[row].sum() == 0.0


def test_laggard_output_uses_btc_grid_and_holds_legs_even_when_their_prices_disappear() -> None:
    row = DAY + 120
    frames = _laggard_frames((row,))
    prices = frames["spot_klines_1m"]
    index = prices["BTCUSDT"].index
    prices["BTCUSDT"] = prices["BTCUSDT"].drop(index[row + 20])
    prices["ADAUSDT"] = prices["ADAUSDT"].iloc[: row + 1]
    extra = pd.DatetimeIndex([index[0] - MINUTE, index[-1] + MINUTE])
    prices["ETHUSDT"] = prices["ETHUSDT"].reindex(index.union(extra), fill_value=100.0)
    prices["XLMUSDT"] = prices["XLMUSDT"].iloc[:0]
    weights = _laggard_weights(frames)
    pd.testing.assert_index_equal(weights.index, index)
    assert weights.columns.tolist() == list(prices)
    assert weights.dtypes.eq("float64").all()
    assert not weights.isna().any().any()
    assert (weights >= 0.0).all().all()
    assert (weights["BTCUSDT"] == 0.0).all()
    assert (weights["XLMUSDT"] == 0.0).all()
    assert (weights["ADAUSDT"].iloc[row : row + 240] == 1 / 3).all()
    assert (weights.sum(axis=1) <= 1.0).all()
    assert weights.iloc[row + 240].sum() == 0.0


@pytest.mark.parametrize("cutoff", [DAY + 119, DAY + 160, 2 * DAY + 100])
def test_laggard_future_perturbations_and_truncation_leave_past_targets_unchanged(cutoff):
    frames = _laggard_frames((DAY + 120, DAY + 400, 2 * DAY + 120), periods=3 * DAY)
    originals = {
        symbol: frame.copy(deep=True) for symbol, frame in frames["spot_klines_1m"].items()
    }
    weights = _laggard_weights(frames)
    t = weights.index[cutoff]
    changed = {"spot_klines_1m": {}}
    truncated = {"spot_klines_1m": {}}
    for number, (symbol, frame) in enumerate(frames["spot_klines_1m"].items()):
        altered = frame.copy(deep=True)
        future = altered.index > t
        altered.loc[future, "close"] *= (
            1.0 + (number + 1) * np.arange(1, int(future.sum()) + 1) / 1000
        )
        changed["spot_klines_1m"][symbol] = altered
        truncated["spot_klines_1m"][symbol] = frame.loc[:t]
    pd.testing.assert_frame_equal(weights.loc[:t], _laggard_weights(changed).loc[:t])
    pd.testing.assert_frame_equal(weights.loc[:t], _laggard_weights(truncated))
    for symbol, frame in frames["spot_klines_1m"].items():
        pd.testing.assert_frame_equal(frame, originals[symbol])


def test_laggard_empty_btc_history_returns_empty_utc_grid_with_all_columns() -> None:
    frames = _laggard_frames()
    frames["spot_klines_1m"]["BTCUSDT"] = frames["spot_klines_1m"]["BTCUSDT"].iloc[:0]
    weights = _laggard_weights(frames)
    assert weights.empty
    assert str(weights.index.tz) == "UTC"
    assert weights.columns.tolist() == list(frames["spot_klines_1m"])
    assert weights.dtypes.eq("float64").all()

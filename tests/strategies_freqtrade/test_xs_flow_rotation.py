"""Synthetic flow rankings, weekly targets and causality checks for v58."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research import xs_flow_rotation

PARAMS = {
    "window_days": 1,
    "baseline_days": 3,
    "legs_per_side": 3,
    "min_universe": 6,
    "rebalance_weekday": 6,
}


def _flow(shares: list[float] | np.ndarray, index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"volume": 100.0, "taker_buy_volume": np.array(shares) * 100}, index=index)


def _weights(symbols: dict[str, pd.DataFrame], **params) -> pd.DataFrame:
    return xs_flow_rotation.target_weights(
        {xs_flow_rotation.PRICE_DATASET: symbols}, "xs_taker_rotation", PARAMS | params
    )


def test_ranking_uses_current_z_and_breaks_ties_by_symbol_name() -> None:
    index = pd.date_range("2024-01-04", periods=4, tz="UTC")
    # Prior mean=.5 and sample std=.25: today's z values are -2, -1, 0, 0, 1, 2.
    today = {"F": 1.0, "D": 0.5, "A": 0.0, "C": 0.5, "B": 0.25, "E": 0.75}
    symbols = {symbol: _flow([0.25, 0.5, 0.75, share], index) for symbol, share in today.items()}
    weights = _weights(symbols)

    assert xs_flow_rotation.PRICE_DATASET == "spot_klines_1d"
    assert (weights.iloc[:3] == 0.0).all().all()
    assert weights.iloc[-1].sort_index().tolist() == pytest.approx([-1 / 6] * 3 + [1 / 6] * 3)
    # All tied still selects disjoint legs, independent of input dictionary order.
    tied = {symbol: _flow([0.25, 0.5, 0.75, 0.75], index) for symbol in today}
    expected = _weights(tied).sort_index(axis=1)
    assert expected.iloc[-1].tolist() == pytest.approx([-1 / 6] * 3 + [1 / 6] * 3)
    pd.testing.assert_frame_equal(
        expected, _weights(dict(reversed(list(tied.items())))).sort_index(axis=1)
    )


@pytest.mark.parametrize("min_universe", [6, 7])
def test_minimum_universe_excludes_undefined_and_zero_std_z(min_universe: int) -> None:
    index = pd.date_range("2024-01-04", periods=4, tz="UTC")
    symbols = {symbol: _flow([0.25, 0.5, 0.75, 1.0], index) for symbol in "ABCDEF"}
    if min_universe == 6:
        symbols["F"] = _flow([0.5] * 4, index)
    symbols["MISSING"] = _flow([0.25, np.nan, 0.75, 0.9], index)
    symbols["ZERO_VOLUME"] = _flow([0.25, 0.5, 0.75, 0.9], index)
    symbols["ZERO_VOLUME"].loc[index[-1], "volume"] = 0.0
    assert (_weights(symbols, min_universe=min_universe) == 0.0).all().all()


def test_share_is_ratio_of_window_sums_with_full_previous_baseline() -> None:
    index = pd.date_range("2024-01-04", periods=4, tz="UTC")
    # X's window shares are .5, .1, .1; Y's are .5, .9, 1.0.
    # Averaging the daily ratios instead would give X a zero-variance baseline.
    symbols = {
        "X": pd.DataFrame({"volume": [1, 1, 9, 1], "taker_buy_volume": [0, 1, 0, 1]}, index=index),
        "Y": pd.DataFrame({"volume": [1, 1, 9, 1], "taker_buy_volume": [1, 0, 9, 1]}, index=index),
    }
    weights = _weights(symbols, window_days=2, baseline_days=2, legs_per_side=1, min_universe=2)
    assert weights["X"].tolist() == [0.0] * 3 + [-0.5]
    assert weights["Y"].tolist() == [0.0] * 3 + [0.5]


def test_frozen_windows_need_seven_rows_then_ninety_prior_shares() -> None:
    index = pd.date_range(end="2024-01-07", periods=97, tz="UTC")
    symbols = {symbol: _flow(np.resize([0.25, 0.75], 97), index) for symbol in "ABCDEF"}
    weights = _weights(symbols, window_days=7, baseline_days=90)
    assert (weights.iloc[:96] == 0.0).all().all()
    assert weights.iloc[-1].abs().sum() == pytest.approx(1.0)


def test_weekly_targets_carry_until_rebalance_and_invalid_rebalance_resets_to_flat() -> None:
    index = pd.date_range("2024-01-01", periods=23, tz="UTC")
    shares = [0.4, 0.5, 0.6, 0.4, 0.5, 0.6, 0.9]
    shares += [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.1]
    shares += [0.2, 0.4, 0.6, 0.4, 0.5, 0.6, 0.9, 0.9, 0.1]
    symbols = {"A": _flow(shares, index), "B": _flow(1.0 - np.array(shares), index)}
    symbols["B"].loc[index[20], "volume"] = 0.0
    weights = _weights(symbols, legs_per_side=1, min_universe=2)

    pd.testing.assert_index_equal(weights.index, index)
    assert weights["A"].tolist() == [0.0] * 6 + [0.5] * 7 + [-0.5] * 7 + [0.0] * 3
    assert weights["B"].tolist() == (-weights["A"]).tolist()


def test_rolling_windows_use_each_symbols_rows_before_union_alignment() -> None:
    index = pd.date_range("2024-01-01", periods=7, tz="UTC")
    symbols = {
        "A": _flow([0.25, 0.5, 0.75, 1.0], index[::2]),
        "B": _flow([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3], index),
    }
    weights = _weights(symbols, legs_per_side=1, min_universe=2)
    pd.testing.assert_index_equal(weights.index, index)
    assert weights.iloc[-1].tolist() == [0.5, -0.5]


def test_missing_rebalance_row_cannot_use_an_earlier_score() -> None:
    index = pd.date_range("2024-01-01", periods=7, tz="UTC")
    symbols = {
        "A": _flow([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], index),
        "B": _flow([0.9, 0.8, 0.7, 0.6, 0.5, 0.4], index[:-1]),
    }
    assert (_weights(symbols, legs_per_side=1, min_universe=2) == 0.0).all().all()


def test_future_changes_and_truncation_cannot_change_past_targets() -> None:
    index = pd.date_range("2024-01-01", periods=120, tz="UTC")
    rng = np.random.default_rng(58)
    symbols = {symbol: _flow(rng.uniform(0.1, 0.9, 120), index) for symbol in "ABCDEFGH"}
    originals = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    weights = _weights(symbols, window_days=7, baseline_days=10)
    cutoff = index[73]
    changed = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    for frame in changed.values():
        frame.loc[frame.index > cutoff, "volume"] *= np.arange(2.0, 48.0)
        frame.loc[frame.index > cutoff, "taker_buy_volume"] = rng.uniform(0.0, 1e4, 46)
    pd.testing.assert_frame_equal(
        weights.loc[:cutoff], _weights(changed, window_days=7, baseline_days=10).loc[:cutoff]
    )
    truncated = {symbol: frame.loc[:cutoff] for symbol, frame in symbols.items()}
    pd.testing.assert_frame_equal(
        weights.loc[:cutoff], _weights(truncated, window_days=7, baseline_days=10)
    )
    assert not weights.isna().any().any()
    assert weights.dtypes.eq("float64").all()
    assert (weights.sum(axis=1).abs() < 1e-12).all()
    assert (weights.abs().sum(axis=1) <= 1.0 + 1e-12).all()
    assert weights.abs().to_numpy().sum() > 0.0
    for symbol, original in originals.items():
        pd.testing.assert_frame_equal(symbols[symbol], original)


@pytest.mark.parametrize("empty_universe", [False, True])
def test_empty_history_stays_utc_and_float(empty_universe: bool) -> None:
    index = pd.DatetimeIndex([], tz="UTC")
    symbols = {} if empty_universe else {"BTCUSDT": _flow([], index)}
    weights = _weights(symbols)
    assert weights.empty
    assert str(weights.index.tz) == "UTC"
    assert weights.dtypes.eq("float64").all()


def test_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        xs_flow_rotation.target_weights({}, "unknown", PARAMS)

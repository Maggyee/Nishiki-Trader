"""Synthetic close-time and allocation checks for the v54 mechanism."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research import trend_vol

PARAMS = {
    "lookbacks_days": [1, 2, 3],
    "vol_window_days": 3,
    "rebalance_weekday": 6,
    "max_gross_exposure": 1.0,
}


def _prices(log_returns: list[float] | np.ndarray, index: pd.DatetimeIndex) -> pd.DataFrame:
    close = 100.0 * np.exp(np.r_[0.0, np.cumsum(log_returns)])
    return pd.DataFrame({"close": close}, index=index)


def _weights(symbols: dict[str, pd.DataFrame], **params) -> pd.DataFrame:
    return trend_vol.target_weights(
        {trend_vol.PRICE_DATASET: symbols}, "tsmom_vol", PARAMS | params
    )


def test_weekly_rebalance_carries_targets_and_starts_flat() -> None:
    index = pd.date_range("2024-01-01", periods=21, tz="UTC")
    close = [
        100,
        101,
        103,
        106,
        110,
        115,
        121,
        100,
        90,
        80,
        70,
        60,
        50,
        40,
        60,
        65,
        70,
        80,
        90,
        100,
        120,
    ]
    weights = _weights({"BTCUSDT": pd.DataFrame({"close": close}, index=index)})

    assert trend_vol.PRICE_DATASET == "spot_klines_1d"
    pd.testing.assert_index_equal(weights.index, index)
    assert weights["BTCUSDT"].tolist() == [0.0] * 6 + [1.0] * 7 + [-1.0] * 7 + [1.0]
    assert weights["BTCUSDT"].dtype == float


@pytest.mark.parametrize("cap", [1.0, 0.4])
def test_inverse_vol_allocation_excludes_invalid_symbols_and_caps_gross(cap: float) -> None:
    index = pd.date_range("2024-01-01", periods=7, tz="UTC")
    returns = np.array([0.01, 0.03, 0.01, 0.03, 0.01, 0.03])
    symbols = {
        "BTCUSDT": _prices(returns, index),
        "ETHUSDT": _prices(-2.0 * returns, index),
        "FLAT": pd.DataFrame({"close": 100.0}, index=index),
        "NEW": pd.DataFrame({"close": [100.0, 110.0]}, index=index[-2:]),
    }
    weights = _weights(symbols, max_gross_exposure=cap)

    assert weights.iloc[-1].tolist() == pytest.approx([2.0 * cap / 3.0, -cap / 3.0, 0, 0])
    assert (weights.abs().sum(axis=1) <= cap + 1e-12).all()
    assert not weights.isna().any().any()


@pytest.mark.parametrize(
    ("close", "expected"),
    [([100, 110, 105, 108], 1.0 / 3.0), ([100, 110, 120, 110], 0.0)],
)
def test_score_averages_signs_including_zero(close: list[float], expected: float) -> None:
    index = pd.date_range("2024-01-04", periods=4, tz="UTC")
    weights = _weights({"BTCUSDT": pd.DataFrame({"close": close}, index=index)})
    assert weights.iloc[-1, 0] == pytest.approx(expected)


def test_zero_score_still_counts_in_inverse_vol_denominator() -> None:
    index = pd.date_range("2024-01-04", periods=4, tz="UTC")
    symbols = {
        "BTCUSDT": pd.DataFrame({"close": [100, 110, 120, 110]}, index=index),
        "ETHUSDT": _prices([0.01, 0.02, 0.03], index),
    }
    weights = _weights(symbols)
    btc_vol = np.std(np.log(np.array([1.1, 120 / 110, 110 / 120])), ddof=1)
    eth_vol = np.std([0.01, 0.02, 0.03], ddof=1)
    assert weights.iloc[-1, 0] == 0.0
    assert weights.iloc[-1, 1] == pytest.approx((1 / eth_vol) / (1 / btc_vol + 1 / eth_vol))


@pytest.mark.parametrize(
    ("params", "periods", "first_active"),
    [
        ({"lookbacks_days": [20, 60, 120], "vol_window_days": 30}, 140, 125),
        ({"lookbacks_days": [1], "vol_window_days": 8}, 21, 13),
    ],
)
def test_both_full_trend_and_vol_history_are_required(
    params: dict, periods: int, first_active: int
) -> None:
    index = pd.date_range("2024-01-01", periods=periods, tz="UTC")
    prices = _prices(np.resize([0.01, 0.02], periods - 1), index)
    weights = _weights({"BTCUSDT": prices}, **params)
    assert (weights.iloc[:first_active] == 0.0).all().all()
    assert weights.iloc[first_active, 0] == 1.0


def test_missing_days_use_symbol_row_offsets_before_alignment() -> None:
    index = pd.date_range("2024-01-01", periods=7, tz="UTC")
    symbols = {
        "BTCUSDT": pd.DataFrame({"close": [100, 110, 120, 130]}, index=index[::2]),
        "FLAT": pd.DataFrame({"close": 100.0}, index=index),
    }
    weights = _weights(symbols)
    pd.testing.assert_index_equal(weights.index, index)
    assert weights.iloc[-1].tolist() == [1.0, 0.0]


def test_symbol_missing_on_rebalance_day_is_invalid() -> None:
    index = pd.date_range("2024-01-01", periods=7, tz="UTC")
    prices = _prices([0.01, 0.02, 0.03, 0.01, 0.02, 0.03], index)
    weights = _weights({"BTCUSDT": prices.iloc[:-1], "ETHUSDT": prices})
    assert weights.iloc[-1].tolist() == [0.0, 1.0]


def test_future_changes_and_truncation_cannot_change_past_targets() -> None:
    index = pd.date_range("2024-01-01", periods=80, tz="UTC")
    rng = np.random.default_rng(54)
    symbols = {symbol: _prices(rng.normal(0, 0.03, 79), index) for symbol in ["BTC", "ETH"]}
    originals = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    weights = _weights(symbols)
    cutoff = index[43]
    changed = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    for frame in changed.values():
        frame.loc[frame.index > cutoff, "close"] *= np.linspace(0.01, 100.0, 36)

    pd.testing.assert_frame_equal(weights.loc[:cutoff], _weights(changed).loc[:cutoff])
    truncated = {symbol: frame.loc[:cutoff] for symbol, frame in symbols.items()}
    pd.testing.assert_frame_equal(weights.loc[:cutoff], _weights(truncated))
    for symbol, original in originals.items():
        pd.testing.assert_frame_equal(symbols[symbol], original)


def test_empty_history_stays_utc_and_float() -> None:
    prices = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], tz="UTC"))
    weights = _weights({"BTCUSDT": prices})
    assert weights.empty
    assert str(weights.index.tz) == "UTC"
    assert weights["BTCUSDT"].dtype == float


def test_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        trend_vol.target_weights({}, "unknown", PARAMS)


def test_sma_filter_holds_only_above_the_average_without_look_ahead() -> None:
    index = pd.date_range("2020-01-01", periods=6, freq="D", tz="UTC")
    a = pd.DataFrame({"close": [10.0, 10.0, 10.0, 13.0, 9.0, 12.0]}, index=index)
    b = pd.DataFrame({"close": [5.0, 6.0, 7.0]}, index=index[3:])
    params = {"sma_days": 3, "weight_per_symbol": 0.5}
    frames = {trend_vol.PRICE_DATASET: {"A": a, "B": b}}

    weights = trend_vol.target_weights(frames, "sma_filter", params)

    # A: SMA3 is NaN, NaN, 10, 11, 10.67, 11.33 -> above on rows 3 and 5 only.
    assert weights["A"].tolist() == [0.0, 0.0, 0.0, 0.5, 0.0, 0.5]
    # B starts on row 3; its first SMA3 exists on row 5 (6 < 7 is above).
    assert weights["B"].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 0.5]
    a.loc[index[5], "close"] = 1.0
    changed = trend_vol.target_weights(frames, "sma_filter", params)
    pd.testing.assert_frame_equal(changed.iloc[:5], weights.iloc[:5])

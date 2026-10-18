"""Synthetic month boundaries, availability and causality checks for v59."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.strategies_freqtrade.research import calendar_effects


def _prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"close": 100.0}, index=index)


def _weights(symbols: dict[str, pd.DataFrame], days_after_month_end: int = 3) -> pd.DataFrame:
    return calendar_effects.target_weights(
        {calendar_effects.PRICE_DATASET: symbols},
        "turn_of_month",
        {"days_after_month_end": days_after_month_end},
    )


@pytest.mark.parametrize("start", ["2023-12-29", "2024-02-27"])
def test_window_enters_at_month_end_for_the_first_three_return_days(start: str) -> None:
    index = pd.date_range(start, periods=7, tz="UTC")
    weights = _weights({"BTCUSDT": _prices(index), "ETHUSDT": _prices(index)})
    assert calendar_effects.PRICE_DATASET == "spot_klines_1d"
    pd.testing.assert_index_equal(weights.index, index)
    # Dec 31 / Feb 29 and days 1,2 are target rows; day 3 is the exit close.
    assert weights["BTCUSDT"].tolist() == [0.0, 0.0, 0.5, 0.5, 0.5, 0.0, 0.0]
    assert weights["ETHUSDT"].tolist() == weights["BTCUSDT"].tolist()


@pytest.mark.parametrize(
    ("days", "expected"),
    [(1, [1.0, 0.0, 0.0, 0.0, 0.0]), (4, [1.0, 1.0, 1.0, 1.0, 0.0])],
)
def test_window_length_counts_return_days(days: int, expected: list[float]) -> None:
    index = pd.date_range("2024-04-30", periods=5, tz="UTC")
    assert _weights({"BTCUSDT": _prices(index)}, days)["BTCUSDT"].tolist() == expected


def test_equal_weights_use_rows_present_today_without_forward_fill() -> None:
    index = pd.date_range("2023-12-31", periods=4, tz="UTC")
    symbols = {
        "BTCUSDT": _prices(index[:3]),
        "ETHUSDT": _prices(index[[0, 2, 3]]),
        "NEW": _prices(index[[2]]),
        "EMPTY": _prices(pd.DatetimeIndex([], tz="UTC")),
    }
    # Availability is defined by a row's presence, independently of its close value.
    symbols["NEW"].loc[:, "close"] = np.nan
    weights = _weights(symbols)
    pd.testing.assert_index_equal(weights.index, index)
    np.testing.assert_allclose(
        weights.to_numpy(),
        [[0.5, 0.5, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [1 / 3, 1 / 3, 1 / 3, 0.0], [0.0] * 4],
    )
    assert not weights.isna().any().any()
    assert weights.dtypes.eq("float64").all()
    assert (weights.abs().sum(axis=1) <= 1.0).all()


def test_future_values_rows_and_truncation_cannot_change_past_targets() -> None:
    index = pd.date_range("2023-12-20", periods=100, tz="UTC")
    symbols = {"BTCUSDT": _prices(index), "ETHUSDT": _prices(index[::2])}
    originals = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    weights = _weights(symbols)
    cutoff = index[43]
    changed = {symbol: frame.copy(deep=True) for symbol, frame in symbols.items()}
    for symbol, frame in changed.items():
        future = frame.index[frame.index > cutoff]
        frame.loc[future, "close"] *= np.arange(1.0, len(future) + 1.0)
        changed[symbol] = frame.drop(future[::2])
    pd.testing.assert_frame_equal(
        weights.loc[:cutoff], _weights(changed).loc[:cutoff], check_freq=False
    )
    truncated = {symbol: frame.loc[:cutoff] for symbol, frame in symbols.items()}
    pd.testing.assert_frame_equal(weights.loc[:cutoff], _weights(truncated))
    for symbol, original in originals.items():
        pd.testing.assert_frame_equal(symbols[symbol], original)


@pytest.mark.parametrize("empty_universe", [False, True])
def test_empty_history_stays_utc_and_float(empty_universe: bool) -> None:
    symbols = {} if empty_universe else {"BTCUSDT": _prices(pd.DatetimeIndex([], tz="UTC"))}
    weights = _weights(symbols)
    assert weights.empty
    assert str(weights.index.tz) == "UTC"
    assert weights.dtypes.eq("float64").all()


def test_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError, match="Unknown candidate"):
        calendar_effects.target_weights({}, "unknown", {})

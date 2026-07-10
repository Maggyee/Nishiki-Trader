from __future__ import annotations

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.multi_asset_rotation_signals import (
    UNIVERSE,
    generate_market_breadth_from_daily,
    generate_relative_value_from_daily,
    generate_xs_momentum_from_daily,
)


def _timestamps(index: pd.DatetimeIndex) -> pd.DataFrame:
    values = (index + pd.Timedelta(hours=23, minutes=59)).astype("int64")
    return pd.DataFrame({symbol: values for symbol in UNIVERSE}, index=index)


def _assert_deterministic(generator, closes: pd.DataFrame) -> list:
    timestamps = _timestamps(closes.index)
    first = generator(closes, timestamps)
    second = generator(closes, timestamps)
    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]
    assert first
    assert {event.side for event in first} <= {"buy", "flat"}
    assert all(event.side != "sell" for event in first)
    return first


def test_monthly_cross_sectional_momentum_selects_positive_leader() -> None:
    index = pd.date_range("2024-01-01", periods=180, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = pd.DataFrame(
        {
            "BTCUSDT": 100.0 * np.power(1.001, step),
            "ETHUSDT": 100.0 * np.power(1.002, step),
            "SOLUSDT": 100.0 * np.power(0.999, step),
        },
        index=index,
    )

    events = _assert_deterministic(generate_xs_momentum_from_daily, closes)

    assert events[0].symbol == "ETHUSDT"
    assert events[0].side == "buy"
    assert events[0].metadata["cash_if_top_nonpositive"] is True


def test_fold_window_reinitializes_target_state_without_losing_warmup() -> None:
    index = pd.date_range("2024-01-01", periods=240, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = pd.DataFrame(
        {
            "BTCUSDT": 100.0 * np.power(1.001, step),
            "ETHUSDT": 100.0 * np.power(1.002, step),
            "SOLUSDT": 100.0 * np.power(0.999, step),
        },
        index=index,
    )
    timestamps = _timestamps(index)

    events = generate_xs_momentum_from_daily(
        closes,
        timestamps,
        start_date="2024-08-01",
        end_date="2024-08-31",
    )

    assert [(event.symbol, event.side) for event in events] == [("ETHUSDT", "buy")]
    assert events[0].metadata["selection_day"].startswith("2024-08-01")


def test_market_breadth_enters_and_exits_btc_only() -> None:
    index = pd.date_range("2024-01-01", periods=260, freq="1D", tz="UTC")
    up = np.linspace(100.0, 180.0, 140)
    down = np.linspace(180.0, 60.0, 120)
    path = np.concatenate([up, down])
    closes = pd.DataFrame(
        {
            "BTCUSDT": path,
            "ETHUSDT": path * 0.8,
            "SOLUSDT": path * 0.2,
        },
        index=index,
    )

    events = _assert_deterministic(generate_market_breadth_from_daily, closes)

    assert [event.side for event in events] == ["buy", "flat"]
    assert {event.symbol for event in events} == {"BTCUSDT"}
    assert events[0].metadata["breadth_required"] == 2


def test_weekly_relative_value_rotates_eth_btc_and_cash_without_overlap() -> None:
    index = pd.date_range("2024-01-01", periods=240, freq="1D", tz="UTC")
    step = np.arange(len(index))
    btc = 40_000.0 * np.power(1.0005, step)
    ratio = 0.05 * (1.0 + 0.12 * np.sin(step / 8.0))
    closes = pd.DataFrame(
        {
            "BTCUSDT": btc,
            "ETHUSDT": btc * ratio,
            "SOLUSDT": 100.0 * np.power(1.0002, step),
        },
        index=index,
    )

    events = _assert_deterministic(generate_relative_value_from_daily, closes)

    assert {event.symbol for event in events} == {"BTCUSDT", "ETHUSDT"}
    held: str | None = None
    for event in events:
        if event.side == "flat":
            assert held == event.symbol
            held = None
        else:
            assert held is None
            held = event.symbol
        assert pd.Timestamp(event.ts_event, unit="ns", tz="UTC").weekday() == 0

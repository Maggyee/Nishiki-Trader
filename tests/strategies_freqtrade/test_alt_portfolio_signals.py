from __future__ import annotations

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.alt_portfolio_signals import (
    ALT_UNIVERSE,
    generate_diversified_momentum,
    generate_low_vol_rotation,
)


def _frames(index: pd.DatetimeIndex, closes: dict[str, np.ndarray]):
    return {
        symbol: pd.DataFrame(
            {
                "close": closes[symbol],
                "ts_event": (index + pd.Timedelta(hours=23, minutes=59)).astype(
                    "int64"
                ),
            },
            index=index,
        )
        for symbol in ALT_UNIVERSE
    }


def test_diversified_momentum_can_hold_multiple_positive_assets() -> None:
    index = pd.date_range("2023-01-01", periods=220, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = {
        "BNBUSDT": 100.0 * np.power(1.001, step),
        "XRPUSDT": 1.0 * np.power(0.999, step),
        "ADAUSDT": 1.0 * np.power(1.002, step),
    }

    events = generate_diversified_momentum(_frames(index, closes))

    first_buys = {event.symbol for event in events if event.side == "buy"}
    assert first_buys == {"BNBUSDT", "ADAUSDT"}
    assert all(event.metadata["maximum_concurrent_assets"] == 3 for event in events)
    assert {event.side for event in events} <= {"buy", "flat"}


def test_low_vol_rotation_selects_least_volatile_positive_trend() -> None:
    index = pd.date_range("2023-01-01", periods=220, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = {
        "BNBUSDT": 100.0 * np.power(1.001, step),
        "XRPUSDT": np.power(1.002, step) * (1.0 + 0.05 * np.sin(step)),
        "ADAUSDT": np.power(0.999, step),
    }

    first = generate_low_vol_rotation(_frames(index, closes))
    second = generate_low_vol_rotation(_frames(index, closes))

    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]
    assert first[0].symbol == "BNBUSDT"
    assert first[0].side == "buy"

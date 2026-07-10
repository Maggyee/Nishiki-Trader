from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.flow_positioning_signals import (
    generate_flow_exhaustion,
    generate_funding_crowding_rotation,
    generate_taker_flow_rotation,
    load_funding_archives,
    load_spot_aggregates,
)
from apps.strategies_freqtrade.research.multi_asset_rotation_signals import UNIVERSE


def _frames(
    index: pd.DatetimeIndex,
    closes: dict[str, np.ndarray],
    buy_shares: dict[str, np.ndarray],
    quote: dict[str, np.ndarray] | None = None,
) -> dict[str, pd.DataFrame]:
    frequency = index[1] - index[0]
    quote = quote or {symbol: np.full(len(index), 100.0) for symbol in UNIVERSE}
    return {
        symbol: pd.DataFrame(
            {
                "open": np.concatenate(([closes[symbol][0]], closes[symbol][:-1])),
                "close": closes[symbol],
                "quote_volume": quote[symbol],
                "taker_buy_quote": quote[symbol] * buy_shares[symbol],
                "ts_event": (index + frequency - pd.Timedelta(minutes=1)).astype("int64"),
            },
            index=index,
        )
        for symbol in UNIVERSE
    }


def test_weekly_taker_flow_selects_positive_highest_buy_share() -> None:
    index = pd.date_range("2024-01-01", periods=120, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = {
        "BTCUSDT": 100.0 * np.power(1.001, step),
        "ETHUSDT": 100.0 * np.power(1.002, step),
        "SOLUSDT": 100.0 * np.power(0.999, step),
    }
    shares = {
        "BTCUSDT": np.full(len(index), 0.51),
        "ETHUSDT": np.full(len(index), 0.55),
        "SOLUSDT": np.full(len(index), 0.60),
    }

    events = generate_taker_flow_rotation(_frames(index, closes, shares))

    assert [(event.symbol, event.side) for event in events] == [("ETHUSDT", "buy")]
    assert events[0].metadata["buy_share_floor"] == 0.5


def test_four_hour_flow_exhaustion_enters_one_asset_and_exits_after_twelve_hours() -> None:
    index = pd.date_range("2024-01-01", periods=220, freq="4h", tz="UTC")
    closes = {symbol: np.full(len(index), 100.0) for symbol in UNIVERSE}
    shares = {symbol: np.full(len(index), 0.50) for symbol in UNIVERSE}
    quote = {symbol: np.full(len(index), 100.0) for symbol in UNIVERSE}
    frames = _frames(index, closes, shares, quote)
    entry = 190
    frames["BTCUSDT"].loc[index[entry], "open"] = 100.0
    frames["BTCUSDT"].loc[index[entry], "close"] = 90.0
    frames["BTCUSDT"].loc[index[entry], "quote_volume"] = 300.0
    frames["BTCUSDT"].loc[index[entry], "taker_buy_quote"] = 90.0
    frames["BTCUSDT"].loc[index[entry + 1 : entry + 3], "taker_buy_quote"] = 30.0

    events = generate_flow_exhaustion(
        frames,
        start_date=str(index[entry].date()),
        end_date=str(index[entry + 3].date()),
    )

    assert [(event.symbol, event.side) for event in events] == [
        ("BTCUSDT", "buy"),
        ("BTCUSDT", "flat"),
    ]
    assert events[1].metadata["held_bars"] == 3


def test_funding_crowding_excludes_highest_return_when_funding_is_extreme() -> None:
    index = pd.date_range("2024-01-01", periods=141, freq="1D", tz="UTC")
    step = np.arange(len(index))
    closes = {
        "BTCUSDT": 100.0 * np.power(1.001, step),
        "ETHUSDT": 100.0 * np.power(1.002, step),
        "SOLUSDT": 100.0 * np.power(1.003, step),
    }
    shares = {symbol: np.full(len(index), 0.5) for symbol in UNIVERSE}
    funding = {
        "BTCUSDT": pd.Series(np.sin(step / 5.0) * 0.0001, index=index),
        "ETHUSDT": pd.Series(np.cos(step / 7.0) * 0.0001, index=index),
        "SOLUSDT": pd.Series(np.where(step >= 134, 0.01, 0.0), index=index),
    }

    events = generate_funding_crowding_rotation(
        _frames(index, closes, shares),
        funding,
        start_date="2024-05-20",
        end_date="2024-05-20",
    )

    assert [(event.symbol, event.side) for event in events] == [("ETHUSDT", "buy")]
    assert events[0].metadata["funding_zscores"]["SOLUSDT"] > 1.5


def test_raw_archive_loaders_preserve_flow_and_funding_columns(tmp_path) -> None:
    spot = tmp_path / "BTCUSDT-1m-2024-01.zip"
    with zipfile.ZipFile(spot, "w") as archive:
        archive.writestr(
            "BTCUSDT-1m-2024-01.csv",
            "1704067200000,100,101,99,100.5,1,1704067259999,1000,10,0.6,600,0\n"
            "1704067260000,100.5,102,100,101,1,1704067319999,1200,11,0.7,700,0\n",
        )
    funding = tmp_path / "BTCUSDT-fundingRate-2024-01.zip"
    with zipfile.ZipFile(funding, "w") as archive:
        archive.writestr(
            "BTCUSDT-fundingRate-2024-01.csv",
            "calc_time,funding_interval_hours,last_funding_rate\n"
            "1704067200000,8,0.0001\n1704096000000,8,-0.0001\n",
        )

    daily = load_spot_aggregates(tmp_path, "BTCUSDT", "1D")
    rates = load_funding_archives(tmp_path, "BTCUSDT")

    assert len(daily) == 1
    assert daily.iloc[0]["quote_volume"] == 2200.0
    assert daily.iloc[0]["taker_buy_quote"] == 1300.0
    assert rates.tolist() == [0.0001, -0.0001]

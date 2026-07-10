from __future__ import annotations

import pandas as pd

from apps.strategies_freqtrade.research.diverse_strategy_signals import (
    DualMomentumParams,
    MeanReversionParams,
    VolSqueezeParams,
    VolumeBreakoutParams,
    generate_dual_momentum_signals,
    generate_mean_reversion_signals,
    generate_vol_squeeze_signals,
    generate_volume_breakout_signals,
)


def _bucket_bars(
    closes: list[float],
    *,
    bucket_minutes: int,
    volumes: list[float] | None = None,
    spread: float = 0.1,
) -> pd.DataFrame:
    volumes = volumes or [1.0] * len(closes)
    rows = []
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    for bucket, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        for minute in range(bucket_minutes):
            timestamp = start + pd.Timedelta(minutes=bucket * bucket_minutes + minute)
            rows.append(
                {
                    "ts_event": int(timestamp.value),
                    "open": close,
                    "high": close + spread,
                    "low": close - spread,
                    "close": close,
                    "volume": volume / bucket_minutes,
                }
            )
    return pd.DataFrame(rows)


def _assert_reproducible_long_flat(first, second) -> None:
    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]
    assert first
    assert {event.side for event in first} <= {"buy", "flat"}
    assert all(event.side != "sell" for event in first)


def test_mean_reversion_emits_oversold_entry_and_mean_exit() -> None:
    bars = _bucket_bars([100, 100, 100, 90, 100], bucket_minutes=240)
    params = MeanReversionParams(
        lookback_bars=3,
        entry_zscore=-1.0,
        rsi_bars=2,
        entry_rsi=10.0,
        exit_rsi=60.0,
        max_hold_bars=3,
    )
    first = generate_mean_reversion_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )
    second = generate_mean_reversion_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )

    _assert_reproducible_long_flat(first, second)
    assert [event.metadata["trigger"] for event in first] == [
        "oversold_reversion_entry",
        "mean_reached_exit",
    ]


def test_vol_squeeze_emits_breakout_and_chandelier_exit() -> None:
    bars = _bucket_bars(
        [100, 100, 100, 100, 103, 104, 95],
        bucket_minutes=240,
        spread=1.0,
    )
    params = VolSqueezeParams(
        band_bars=3,
        bollinger_std=2.0,
        keltner_atr=1.5,
        breakout_bars=3,
        release_bars=3,
        chandelier_atr=1.0,
        max_hold_bars=5,
    )
    first = generate_vol_squeeze_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )
    second = generate_vol_squeeze_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )

    _assert_reproducible_long_flat(first, second)
    assert [event.metadata["trigger"] for event in first] == [
        "squeeze_release_breakout_entry",
        "chandelier_exit",
    ]


def test_volume_breakout_requires_price_obv_and_volume_then_donchian_exit() -> None:
    bars = _bucket_bars(
        [100, 100, 100, 101, 102, 90],
        bucket_minutes=240,
        volumes=[1, 1, 1, 3, 1, 1],
    )
    params = VolumeBreakoutParams(
        price_breakout_bars=3,
        obv_breakout_bars=3,
        volume_median_bars=3,
        volume_multiplier=2.0,
        exit_bars=2,
    )
    first = generate_volume_breakout_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )
    second = generate_volume_breakout_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )

    _assert_reproducible_long_flat(first, second)
    assert [event.metadata["trigger"] for event in first] == [
        "price_obv_volume_breakout_entry",
        "donchian_exit",
    ]


def test_dual_momentum_emits_daily_state_transitions() -> None:
    bars = _bucket_bars(
        [100, 101, 102, 104, 105, 90],
        bucket_minutes=1440,
    )
    params = DualMomentumParams(fast_return_days=2, slow_return_days=3)
    first = generate_dual_momentum_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )
    second = generate_dual_momentum_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )

    _assert_reproducible_long_flat(first, second)
    assert [event.metadata["trigger"] for event in first] == [
        "dual_positive_momentum_entry",
        "momentum_nonpositive_exit",
    ]
    assert all(event.horizon == "1d" and event.ttl_seconds == 86_400 for event in first)

from __future__ import annotations

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.breakout_rule_signals import (
    BreakoutRuleParams,
    generate_breakout_rule_signals,
    resample_ohlcv_15m,
)
from apps.strategies_freqtrade.research.freqai_linear_walkforward_signals import (
    WalkForwardLinearParams,
    generate_walkforward_linear_signals,
)


def _hourly_bars(days: int = 100) -> pd.DataFrame:
    count = days * 24
    index = np.arange(count)
    returns = 0.004 * np.sin(index / 11.0) + 0.001 * np.cos(index / 5.0)
    close = 50_000 * np.cumprod(1.0 + returns)
    timestamps = pd.date_range("2024-01-01", periods=count, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "ts_event": timestamps.astype("int64"),
            "open": close,
            "high": close + 20,
            "low": close - 20,
            "close": close,
            "volume": 10 + np.sin(index / 7.0),
        }
    )


def test_walkforward_is_deterministic_long_flat_and_purged():
    bars = _hourly_bars()
    params = WalkForwardLinearParams(
        training_window_days=60,
        horizon_bars=1,
        min_train_rows=100,
        emit_every_bars=1,
        prediction_threshold=0.00001,
        score_scale=0.01,
        confidence_scale=0.01,
    )
    first = generate_walkforward_linear_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )
    second = generate_walkforward_linear_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=params,
    )

    assert first
    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]
    assert {event.side for event in first} <= {"buy", "flat"}
    for event in first:
        prediction_month = pd.Timestamp(f"{event.metadata['prediction_month']}-01", tz="UTC")
        train_until = pd.Timestamp(event.metadata["train_until"])
        assert train_until < prediction_month
        assert event.features_hash and event.features_hash.startswith("sha256:")


def _minute_bars_from_15m_closes(closes: list[float]) -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    for bucket, close in enumerate(closes):
        for minute in range(15):
            ts = start + pd.Timedelta(minutes=bucket * 15 + minute)
            rows.append(
                {
                    "ts_event": int(ts.value),
                    "open": close,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "close": close,
                    "volume": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_breakout_resamples_and_emits_transition_only_long_flat():
    bars = _minute_bars_from_15m_closes([100, 100, 100, 101, 102, 103, 99, 98, 97])
    sampled = resample_ohlcv_15m(bars)
    assert len(sampled) == 9
    events = generate_breakout_rule_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        params=BreakoutRuleParams(
            entry_bars=2,
            exit_bars=2,
            atr_bars=2,
            atr_multiplier=0.0,
        ),
    )

    assert [event.side for event in events] == ["buy", "flat"]
    assert [event.metadata["trigger"] for event in events] == [
        "donchian_entry",
        "donchian_exit",
    ]
    assert all(event.side != "sell" for event in events)

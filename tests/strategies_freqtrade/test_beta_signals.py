from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from apps.strategies_freqtrade import beta_signals

DAY_MS = 86_400_000


def _klines(closes: list[float], first_day: str) -> list[list]:
    start = int(pd.Timestamp(first_day, tz="UTC").value // 1_000_000)
    return [
        [start + i * DAY_MS, "0", "0", "0", str(c), "0", start + (i + 1) * DAY_MS - 1]
        for i, c in enumerate(closes)
    ]


def _fake_api(btc: list[float], eth: list[float], first_day: str):
    rows = {"BTCUSDT": _klines(btc, first_day), "ETHUSDT": _klines(eth, first_day)}
    return lambda url: rows["BTCUSDT" if "BTCUSDT" in url else "ETHUSDT"]


def test_signals_for_the_last_closed_day_match_the_backtest_encoding() -> None:
    rising = [100.0 + i for i in range(251)]  # 2026-01-01 .. 2026-09-08, last is still open
    falling = [500.0 - i for i in range(251)]
    now = datetime(2026, 9, 8, 0, 5, tzinfo=UTC)

    events = beta_signals.build_signals(now, get=_fake_api(rising, falling, "2026-01-01"))

    by_symbol = {event.symbol: event for event in events}
    assert by_symbol["BTCUSDT"].side == "buy"
    assert by_symbol["ETHUSDT"].side == "flat"
    btc = by_symbol["BTCUSDT"]
    assert btc.signal_id == "rule_beta_sma200_v1:btc-eth-sma200-v1:BTCUSDT:2026-09-07"
    assert btc.ts_event == pd.Timestamp("2026-09-08", tz="UTC").value
    assert btc.metadata == {"weight": 0.5, "adr": "019", "producer": "beta_signals"}
    assert (btc.source, btc.model_version, btc.ttl_seconds) == (
        "rule_beta_sma200_v1",
        "btc-eth-sma200-v1",
        2 * 86_400,
    )


def test_open_candle_is_dropped() -> None:
    now = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)
    closes = beta_signals.closed_daily_closes(
        "BTCUSDT", now=now, get=lambda url: _klines([1.0, 2.0, 3.0], "2026-01-01")
    )
    assert list(closes) == [1.0, 2.0]


@pytest.mark.parametrize(
    ("now", "days"),
    [
        (datetime(2026, 9, 9, 0, 5, tzinfo=UTC), 251),  # stale: 09-08 close missing
        (datetime(2026, 9, 8, 0, 5, tzinfo=UTC), 150),  # too little history for SMA200
    ],
)
def test_refuses_stale_or_short_history(now: datetime, days: int) -> None:
    last_candle = pd.Timestamp("2026-09-07", tz="UTC")  # its close is the last close
    first = (last_candle - pd.Timedelta(days=days - 1)).date()
    api = _fake_api([100.0] * days, [100.0] * days, first.isoformat())
    with pytest.raises(ValueError, match="closed days"):
        beta_signals.build_signals(now, get=api)

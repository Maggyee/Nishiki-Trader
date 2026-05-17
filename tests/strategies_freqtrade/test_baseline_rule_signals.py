"""Tests for `apps.strategies_freqtrade.research.baseline_rule_signals`.

Covers:
- Cross-up bar produces a `buy` SignalEvent; cross-down produces `sell`.
- RSI filter suppresses crosses in overbought / oversold territory.
- Deterministic output: identical bars in → identical SignalEvent list out.
- Generated events validate as `SignalEvent v1` end-to-end and write through
  `SignalStore` without collision when run twice (duplicates raise).
- `RuleParams` rejects invalid configurations (fast >= slow, RSI band edges).
- Module imports no trading or HTTP API.
"""

from __future__ import annotations

import io
import sys
import tokenize

import numpy as np
import pandas as pd
import pytest

from apps.bridge.store import DuplicateSignalError, SignalStore
from apps.strategies_freqtrade.research.baseline_rule_signals import (
    DEFAULT_MODEL_VERSION,
    DEFAULT_SOURCE,
    RuleParams,
    generate_rule_signals,
)

BASE_TS_NS = 1_704_067_200_000_000_000  # 2024-01-01T00:00:00Z
ONE_MIN_NS = 60_000_000_000


def _bars(closes: list[float]) -> pd.DataFrame:
    """Build an OHLC frame whose `close` series drives EMA-cross detection."""
    return pd.DataFrame(
        {
            "ts_event": [BASE_TS_NS + i * ONE_MIN_NS for i in range(len(closes))],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [10.0] * len(closes),
        }
    )


def _down_then_up(rampdown: int = 30, rampup: int = 30) -> pd.DataFrame:
    # Slowly slide close DOWN then sharply pull it UP so EMA(5) crosses EMA(20)
    # to the upside near the start of the ramp-up phase.
    down = list(np.linspace(50_000, 49_500, rampdown))
    up = list(np.linspace(49_500, 51_500, rampup))
    return _bars(down + up)


def _up_then_down(rampup: int = 30, rampdown: int = 30) -> pd.DataFrame:
    up = list(np.linspace(50_000, 50_500, rampup))
    down = list(np.linspace(50_500, 48_500, rampdown))
    return _bars(up + down)


def test_cross_up_produces_buy_signal():
    bars = _down_then_up()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    buys = [e for e in events if e.side == "buy"]
    assert buys, f"expected at least one buy, got {[(e.side, e.signal_id) for e in events]}"
    for buy in buys:
        assert buy.score == pytest.approx(0.6)
        assert 0.5 <= buy.confidence <= 1.0
        assert buy.source == DEFAULT_SOURCE
        assert buy.model_version == DEFAULT_MODEL_VERSION
        assert buy.symbol == "BTCUSDT"
        assert buy.venue == "BINANCE"


def test_cross_down_produces_sell_signal():
    bars = _up_then_down()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    sells = [e for e in events if e.side == "sell"]
    assert sells
    for sell in sells:
        assert sell.score == pytest.approx(-0.6)
        assert 0.5 <= sell.confidence <= 1.0


def test_no_signals_when_close_is_flat():
    bars = _bars([50_000.0] * 50)
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert events == []


def test_deterministic_repeat_runs_produce_equal_lists():
    bars = _down_then_up()
    a = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    b = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert [e.signal_id for e in a] == [e.signal_id for e in b]
    assert [(e.side, e.score, e.confidence, e.ts_event) for e in a] == [
        (e.side, e.score, e.confidence, e.ts_event) for e in b
    ]


def test_signal_ids_are_unique_and_carry_source_metadata():
    bars = _down_then_up()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    ids = [e.signal_id for e in events]
    assert len(ids) == len(set(ids))
    for ev in events:
        assert ev.signal_id.startswith(f"{DEFAULT_SOURCE}:{DEFAULT_MODEL_VERSION}:")
        assert str(ev.ts_event) in ev.signal_id


def test_rsi_oversold_blocks_cross_down():
    # An aggressively-high `rsi_lower` makes the oversold band cover the
    # entire mid-RSI region, so every cross-down sits inside it and must be
    # filtered out.
    bars = _up_then_down()
    rules = RuleParams(rsi_lower=60.0, rsi_upper=70.0)
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE", params=rules)
    assert all(e.side != "sell" for e in events), (
        f"expected RSI filter to suppress sell in oversold band, got {[e.side for e in events]}"
    )


def test_metadata_contains_indicator_params_and_values():
    bars = _down_then_up()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert events
    md = events[0].metadata
    assert md["fast_period"] == 5
    assert md["slow_period"] == 20
    assert md["rsi_period"] == 14
    assert isinstance(md["rsi"], float)
    assert isinstance(md["spread"], float)


def test_ttl_seconds_propagates_from_params():
    bars = _down_then_up()
    rules = RuleParams(ttl_seconds=600)
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE", params=rules)
    assert events
    assert all(e.ttl_seconds == 600 for e in events)


def test_horizon_propagates():
    bars = _down_then_up()
    events = generate_rule_signals(
        bars, symbol="BTCUSDT", venue="BINANCE", horizon="5m"
    )
    assert events
    assert all(e.horizon == "5m" for e in events)


def test_accepts_datetime_index_in_place_of_ts_event_column():
    bars = _down_then_up()
    df = bars.set_index(
        pd.to_datetime(bars["ts_event"], utc=True, unit="ns").rename("ts_event")
    ).drop(columns=["ts_event"])
    events = generate_rule_signals(df, symbol="BTCUSDT", venue="BINANCE")
    assert events
    assert all(int(e.ts_event) >= BASE_TS_NS for e in events)


def test_empty_bars_returns_empty():
    bars = _bars([])
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert events == []


def test_signals_can_be_written_to_signal_store(tmp_path):
    bars = _down_then_up()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert events
    store = SignalStore(tmp_path / "signals.db")
    for ev in events:
        store.write(ev)
    rows = list(store.replay())
    assert len(rows) == len(events)
    assert {r.signal_id for r in rows} == {e.signal_id for e in events}


def test_signal_store_rejects_duplicate_on_re_run(tmp_path):
    bars = _down_then_up()
    events = generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")
    assert events
    store = SignalStore(tmp_path / "signals.db")
    for ev in events:
        store.write(ev)
    with pytest.raises(DuplicateSignalError):
        store.write(events[0])


def test_missing_close_column_rejected():
    bars = _down_then_up().drop(columns=["close"])
    with pytest.raises(ValueError, match="close"):
        generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")


def test_bars_without_ts_event_or_datetime_index_rejected():
    bars = _down_then_up().drop(columns=["ts_event"]).reset_index(drop=True)
    with pytest.raises(ValueError, match="ts_event"):
        generate_rule_signals(bars, symbol="BTCUSDT", venue="BINANCE")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fast_period": 20, "slow_period": 5},
        {"fast_period": 10, "slow_period": 10},
        {"rsi_period": 1},
        {"rsi_lower": 30.0, "rsi_upper": 30.0},
        {"rsi_lower": -1.0, "rsi_upper": 70.0},
        {"rsi_lower": 30.0, "rsi_upper": 101.0},
        {"ttl_seconds": 0},
    ],
)
def test_rule_params_rejects_invalid_configurations(kwargs):
    base = {
        "fast_period": 5,
        "slow_period": 20,
        "rsi_period": 14,
        "rsi_upper": 70.0,
        "rsi_lower": 30.0,
        "ttl_seconds": 120,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        RuleParams(**base)


def _strip_comments_and_strings(source: str) -> str:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return " ".join(
        tok.string
        for tok in tokens
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_module_has_no_trading_api_calls():
    from apps.strategies_freqtrade.research import baseline_rule_signals

    with open(baseline_rule_signals.__file__, encoding="utf-8") as f:
        text = f.read()
    code = _strip_comments_and_strings(text)
    for forbidden in (
        "freqtrade",
        "requests.",
        "httpx.",
        "ccxt.",
        "binance",
        "submit_order",
        "ExecutionEngine",
        "RiskEngine",
    ):
        assert forbidden not in code, (
            f"forbidden token {forbidden!r} found in baseline_rule_signals.py — "
            "research layer must not touch trading or network APIs"
        )


@pytest.mark.parametrize(
    "module",
    ["freqtrade", "httpx", "requests", "ccxt"],
)
def test_research_module_does_not_import_network_modules(module):
    assert module not in sys.modules or sys.modules[module] is None, (
        f"{module} unexpectedly imported by baseline_rule_signals"
    )

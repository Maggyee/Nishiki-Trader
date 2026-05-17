"""Tests for `apps.strategies_freqtrade.research.freqai_linear_signals`."""

from __future__ import annotations

import io
import sys
import tokenize

import numpy as np
import pandas as pd
import pytest

from apps.bridge.store import DuplicateSignalError, SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    DEFAULT_MODEL_VERSION,
    DEFAULT_SOURCE,
    FEATURE_COLUMNS,
    LinearFreqaiParams,
    generate_freqai_linear_signals,
)

BASE_TS_NS = 1_704_067_200_000_000_000  # 2024-01-01T00:00:00Z
ONE_MIN_NS = 60_000_000_000


def _bars(count: int = 240) -> pd.DataFrame:
    # Deterministic oscillating return stream. It is deliberately synthetic:
    # these tests validate bridge semantics and determinism, not alpha.
    idx = np.arange(count)
    returns = 0.0006 * np.sin(idx / 7.0) + 0.0002 * np.cos(idx / 3.0)
    close = 50_000 * np.cumprod(1.0 + returns)
    return pd.DataFrame(
        {
            "ts_event": [BASE_TS_NS + i * ONE_MIN_NS for i in range(count)],
            "open": close,
            "high": close + 15,
            "low": close - 15,
            "close": close,
            "volume": 10.0 + 2.0 * np.sin(idx / 5.0),
        }
    )


def _params(**overrides: object) -> LinearFreqaiParams:
    base = {
        "horizon_bars": 5,
        "min_train_rows": 80,
        "emit_every_bars": 5,
        "prediction_threshold": 0.0,
        "score_scale": 0.003,
        "confidence_scale": 0.003,
        "ridge_alpha": 0.0001,
        "ttl_seconds": 300,
    }
    base.update(overrides)
    return LinearFreqaiParams(**base)


def test_generates_valid_freqai_signal_events():
    bars = _bars()
    train_until = BASE_TS_NS + 140 * ONE_MIN_NS
    events = generate_freqai_linear_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=train_until,
        params=_params(),
    )

    assert events
    for ev in events:
        assert ev.source == DEFAULT_SOURCE
        assert ev.model_version == DEFAULT_MODEL_VERSION
        assert ev.ts_event > train_until
        assert ev.side in {"buy", "sell"}
        assert -1.0 <= ev.score <= 1.0
        assert 0.5 <= ev.confidence <= 1.0
        assert ev.features_hash is not None
        assert ev.features_hash.startswith("sha256:")
        assert ev.metadata["algorithm"] == "ridge_linear_momentum"
        assert ev.metadata["train_rows"] >= 80


def test_deterministic_repeat_runs_produce_equal_lists():
    bars = _bars()
    train_until = BASE_TS_NS + 140 * ONE_MIN_NS
    a = generate_freqai_linear_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=train_until,
        params=_params(),
    )
    b = generate_freqai_linear_signals(
        bars,
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=train_until,
        params=_params(),
    )

    assert [e.signal_id for e in a] == [e.signal_id for e in b]
    assert [(e.side, e.score, e.confidence, e.features_hash) for e in a] == [
        (e.side, e.score, e.confidence, e.features_hash) for e in b
    ]


def test_signal_ids_are_unique_and_include_source_metadata():
    events = generate_freqai_linear_signals(
        _bars(),
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
        params=_params(),
    )
    ids = [e.signal_id for e in events]
    assert len(ids) == len(set(ids))
    for ev in events:
        assert ev.signal_id.startswith(f"{DEFAULT_SOURCE}:{DEFAULT_MODEL_VERSION}:")
        assert str(ev.ts_event) in ev.signal_id


def test_high_threshold_can_filter_all_predictions():
    events = generate_freqai_linear_signals(
        _bars(),
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
        params=_params(prediction_threshold=0.5, confidence_scale=0.6),
    )
    assert events == []


def test_empty_bars_returns_empty():
    events = generate_freqai_linear_signals(
        _bars(0),
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS,
        params=_params(),
    )
    assert events == []


def test_missing_required_columns_rejected():
    with pytest.raises(ValueError, match="volume"):
        generate_freqai_linear_signals(
            _bars().drop(columns=["volume"]),
            symbol="BTCUSDT",
            venue="BINANCE",
            train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
            params=_params(),
        )


def test_bars_without_ts_event_or_datetime_index_rejected():
    with pytest.raises(ValueError, match="ts_event"):
        generate_freqai_linear_signals(
            _bars().drop(columns=["ts_event"]).reset_index(drop=True),
            symbol="BTCUSDT",
            venue="BINANCE",
            train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
            params=_params(),
        )


def test_accepts_datetime_index_in_place_of_ts_event_column():
    bars = _bars()
    df = bars.set_index(
        pd.to_datetime(bars["ts_event"], utc=True, unit="ns").rename("ts_event")
    ).drop(columns=["ts_event"])
    events = generate_freqai_linear_signals(
        df,
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
        params=_params(),
    )
    assert events


def test_insufficient_training_rows_rejected():
    with pytest.raises(ValueError, match="not enough training rows"):
        generate_freqai_linear_signals(
            _bars(120),
            symbol="BTCUSDT",
            venue="BINANCE",
            train_until_ns=BASE_TS_NS + 40 * ONE_MIN_NS,
            params=_params(min_train_rows=80),
        )


def test_signals_can_be_written_to_signal_store(tmp_path):
    events = generate_freqai_linear_signals(
        _bars(),
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
        params=_params(),
    )
    assert events
    store = SignalStore(tmp_path / "signals.db")
    for ev in events:
        store.write(ev)
    rows = store.replay(source=DEFAULT_SOURCE, model_version=DEFAULT_MODEL_VERSION)
    assert {r.signal_id for r in rows} == {e.signal_id for e in events}


def test_signal_store_rejects_duplicate_on_re_run(tmp_path):
    events = generate_freqai_linear_signals(
        _bars(),
        symbol="BTCUSDT",
        venue="BINANCE",
        train_until_ns=BASE_TS_NS + 140 * ONE_MIN_NS,
        params=_params(),
    )
    assert events
    store = SignalStore(tmp_path / "signals.db")
    store.write(events[0])
    with pytest.raises(DuplicateSignalError):
        store.write(events[0])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizon_bars": 0},
        {"min_train_rows": len(FEATURE_COLUMNS)},
        {"emit_every_bars": 0},
        {"prediction_threshold": -0.1},
        {"score_scale": 0.0},
        {"confidence_scale": 0.0001, "prediction_threshold": 0.0001},
        {"ridge_alpha": -0.1},
        {"ttl_seconds": 0},
    ],
)
def test_params_reject_invalid_configurations(kwargs):
    with pytest.raises(ValueError):
        _params(**kwargs)


def _strip_comments_and_strings(source: str) -> str:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return " ".join(
        tok.string
        for tok in tokens
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_module_has_no_trading_api_calls():
    from apps.strategies_freqtrade.research import freqai_linear_signals

    with open(freqai_linear_signals.__file__, encoding="utf-8") as f:
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
            f"forbidden token {forbidden!r} found in freqai_linear_signals.py"
        )


@pytest.mark.parametrize(
    "module",
    ["freqtrade", "httpx", "requests", "ccxt"],
)
def test_research_module_does_not_import_network_modules(module):
    assert module not in sys.modules or sys.modules[module] is None, (
        f"{module} unexpectedly imported by freqai_linear_signals"
    )

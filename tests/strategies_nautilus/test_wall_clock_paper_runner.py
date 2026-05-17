"""Tests for ADR-008 §6.1 Phase 3a wall-clock paper runtime."""

from __future__ import annotations

import inspect
import json
import queue
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.bridge.validators import Authorization
from apps.strategies_nautilus.baseline_strategy import BaselineStrategyConfig
from apps.strategies_nautilus.runners import paper_runner, wall_clock_bar_feed
from apps.strategies_nautilus.runners.paper_runner import (
    PaperRunnerConfig,
    _wall_clock_refresh_signals,
    run_paper_session,
)
from apps.strategies_nautilus.runners.wall_clock_bar_feed import (
    BarSample,
    BinancePublicBarFeed,
)

BASE_TS_NS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z
ONE_MIN_NS = 60_000_000_000


class FakeBarFeed:
    """Synchronous BarFeed test double with controllable inputs."""

    def __init__(self) -> None:
        self._queue: queue.Queue[BarSample] = queue.Queue()
        self.reconnect_count = 0
        self.duplicate_bars_dropped = 0
        self.endpoint = "fake://wall-clock"
        self.stream_name = "btcusdt@kline_1m"
        self.source_name = "fake_feed"
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def next_bar(self, timeout: float) -> BarSample | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def push(self, bar: BarSample) -> None:
        self._queue.put(bar)

    def push_duplicate(self) -> None:
        self.duplicate_bars_dropped += 1

    def trigger_reconnect(self) -> None:
        self.reconnect_count += 1


@pytest.fixture
def btcusdt_instrument():
    return TestInstrumentProvider.btcusdt_binance()


@pytest.fixture
def bar_type(btcusdt_instrument):
    return BarType.from_str(f"{btcusdt_instrument.id}-1-MINUTE-LAST-EXTERNAL")


def _sample(ts_ns: int, close: float = 100.0) -> BarSample:
    return BarSample(
        ts_event=ts_ns,
        ts_init=ts_ns,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
    )


def _instrument_catalog(tmp_path: Path, btcusdt_instrument) -> Path:
    path = tmp_path / "catalog"
    path.mkdir()
    ParquetDataCatalog(str(path.resolve())).write_data([btcusdt_instrument])
    return path


def _signal_event(signal_id: str, ts_event: int) -> SignalEvent:
    return SignalEvent.model_validate(
        {
            "schema_version": "signal.v1",
            "signal_id": signal_id,
            "symbol": "BTCUSDT",
            "venue": "BINANCE",
            "ts_event": ts_event,
            "horizon": "15m",
            "side": "buy",
            "score": 0.7,
            "confidence": 0.7,
            "source": "freqai_v1",
            "model_version": "2026-05-14",
            "ttl_seconds": 9000,
            "features_hash": None,
            "metadata": {"test": "wall_clock"},
        }
    )


def _wall_clock_config(
    *,
    tmp_path: Path,
    catalog_path: Path,
    bar_type,
    signal_store_path: Path,
    max_bars: int | None = 3,
    max_duration_seconds: int | None = None,
    signal_poll_interval_seconds: int = 1,
    heartbeat_interval_seconds: int = 60,
) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        output_root=tmp_path / "paper",
        catalog_path=catalog_path,
        instrument_id="BTCUSDT.BINANCE",
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        baseline_config=BaselineStrategyConfig(
            venue="BINANCE",
            auth=Authorization(
                allowed_sources=frozenset({"freqai_v1"}),
                allowed_model_versions=frozenset({"2026-05-14"}),
            ),
            min_confidence=0.5,
            max_position_pct=0.05,
        ),
        trade_size=Decimal("1"),
        starting_balance=Money(1_000, USDT),
        base_currency=USDT,
        signal_filter={"source": "freqai_v1", "model_version": "2026-05-14"},
        git_commit="0" * 40,
        git_dirty=False,
        machine_id="pytest",
        data_mode="wall_clock",
        max_bars=max_bars,
        max_duration_seconds=max_duration_seconds,
        max_signal_lag_seconds=900,
        signal_poll_interval_seconds=signal_poll_interval_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        ws_symbol="BTCUSDT",
        operator="pytest",
    )


def test_wall_clock_sources_have_no_credential_or_live_tokens():
    """ADR-008 §7.1 / §7.2 item 1: runner & feed read no exchange secrets."""
    runner_src = inspect.getsource(paper_runner)
    feed_src = inspect.getsource(wall_clock_bar_feed)
    forbidden = (
        "os.environ",
        "getenv",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
        "submit_order",
        "LiveExec",
        "LiveData",
        "BinanceLive",
    )
    combined = runner_src + "\n----\n" + feed_src
    for token in forbidden:
        assert token not in combined, f"forbidden token {token!r} appears in source"


def test_binance_public_bar_feed_dedupes_by_ts_event_ns():
    """ADR-008 §7.2 item 3: duplicate bars (WS retransmission) are dropped."""
    feed = BinancePublicBarFeed(symbol="BTCUSDT")
    raw = json.dumps(
        {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "k": {
                    "t": 1000,
                    "T": 60000,
                    "i": "1m",
                    "o": "100",
                    "c": "100",
                    "h": "100",
                    "l": "100",
                    "v": "10",
                    "x": True,
                },
            },
        }
    ).encode()
    feed._handle_message(raw)
    feed._handle_message(raw)  # same ts_event, must be dropped
    feed._handle_message(raw)  # again
    assert feed._queue.qsize() == 1
    assert feed.duplicate_bars_dropped == 2


def test_binance_public_bar_feed_ignores_unclosed_klines():
    """Phase 3a contract: only consume closed (k.x == true) klines."""
    feed = BinancePublicBarFeed(symbol="BTCUSDT")
    raw = json.dumps(
        {
            "data": {
                "e": "kline",
                "k": {
                    "t": 1000,
                    "T": 60000,
                    "i": "1m",
                    "o": "100",
                    "c": "100",
                    "h": "100",
                    "l": "100",
                    "v": "10",
                    "x": False,
                },
            },
        }
    ).encode()
    feed._handle_message(raw)
    assert feed._queue.qsize() == 0
    assert feed.duplicate_bars_dropped == 0


def test_binance_public_bar_feed_rejects_non_kline_payloads():
    feed = BinancePublicBarFeed(symbol="BTCUSDT")
    raw = json.dumps({"data": {"e": "trade", "p": "100", "q": "1"}}).encode()
    feed._handle_message(raw)
    feed._handle_message(b"not-json")
    feed._handle_message(json.dumps({"data": None}).encode())
    assert feed._queue.qsize() == 0


def test_wall_clock_paper_session_writes_bundle_when_max_bars_reached(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)  # create empty store
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=2,
    )
    feed = FakeBarFeed()
    feed.push(_sample(BASE_TS_NS))
    feed.push(_sample(BASE_TS_NS + ONE_MIN_NS, close=101.0))
    feed.push(_sample(BASE_TS_NS + 2 * ONE_MIN_NS, close=102.0))

    result = run_paper_session(config, bar_feed=feed)

    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    runtime = manifest["runtime"]
    assert manifest["kind"] == "paper"
    assert runtime["data_mode"] == "wall_clock"
    assert runtime["bar_source"] == "fake_feed"
    assert runtime["ws_endpoint"] == "fake://wall-clock"
    assert runtime["ws_stream"] == "btcusdt@kline_1m"
    assert runtime["shutdown_reason"] == "max_bars"
    assert runtime["bar_count"] == 2
    assert runtime["first_processed_ns"] == BASE_TS_NS
    assert runtime["processed_until_ns"] == BASE_TS_NS + ONE_MIN_NS
    assert runtime["credentials_loaded"] is False
    assert manifest["totals"]["iterations"] == 2


def test_wall_clock_paper_session_propagates_reconnect_count(
    tmp_path, btcusdt_instrument, bar_type
):
    """ADR-008 §7.2 item 2 (structural): reconnect counter lands in manifest."""
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=1,
    )
    feed = FakeBarFeed()
    feed.trigger_reconnect()
    feed.trigger_reconnect()
    feed.trigger_reconnect()
    feed.push(_sample(BASE_TS_NS))

    result = run_paper_session(config, bar_feed=feed)
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["runtime"]["ws_reconnect_count"] == 3


def test_wall_clock_paper_session_propagates_duplicate_drop_count(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=1,
    )
    feed = FakeBarFeed()
    feed.push_duplicate()
    feed.push_duplicate()
    feed.push(_sample(BASE_TS_NS))

    result = run_paper_session(config, bar_feed=feed)
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["runtime"]["duplicate_bars_dropped"] == 2


def test_wall_clock_paper_session_consumes_signals_inside_bar_window(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    store = SignalStore(signal_store_path)
    store.write(_signal_event("paper-1", BASE_TS_NS + 30 * 1_000_000_000))
    store.write(_signal_event("paper-2", BASE_TS_NS + 90 * 1_000_000_000))
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=2,
    )
    feed = FakeBarFeed()
    feed.push(_sample(BASE_TS_NS + ONE_MIN_NS))
    feed.push(_sample(BASE_TS_NS + 2 * ONE_MIN_NS, close=101.0))

    result = run_paper_session(config, bar_feed=feed)
    lineage = pd.read_parquet(result.output_dir / "signal_lineage.parquet")
    assert set(lineage["signal_id"]) == {"paper-1", "paper-2"}
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["signal_source"]["row_count"] == 2


def test_wall_clock_refresh_signals_pulls_new_rows_above_cursor(tmp_path):
    signal_store_path = tmp_path / "signals.db"
    store = SignalStore(signal_store_path)
    store.write(_signal_event("paper-1", BASE_TS_NS + ONE_MIN_NS))
    base_filter = {"source": "freqai_v1", "model_version": "2026-05-14"}
    signals = sorted(
        store.replay(**base_filter),
        key=lambda s: (int(s.ts_event), s.signal_id),
    )
    assert {s.signal_id for s in signals} == {"paper-1"}
    last_ts = signals[-1].ts_event

    # Add a new signal after the cursor; refresh should pick it up.
    store.write(_signal_event("paper-2", BASE_TS_NS + 2 * ONE_MIN_NS))
    signals, signal_idx, last_ts = _wall_clock_refresh_signals(
        signal_store=store,
        base_filter=base_filter,
        last_signal_ts=last_ts,
        signals=signals,
        signal_idx=0,
    )
    assert {s.signal_id for s in signals} == {"paper-1", "paper-2"}
    assert signal_idx == 0
    assert last_ts == BASE_TS_NS + 2 * ONE_MIN_NS

    # No new rows -> idempotent, no duplicates.
    signals, signal_idx, last_ts2 = _wall_clock_refresh_signals(
        signal_store=store,
        base_filter=base_filter,
        last_signal_ts=last_ts,
        signals=signals,
        signal_idx=0,
    )
    assert len(signals) == 2
    assert last_ts2 == last_ts


def test_wall_clock_paper_session_emits_heartbeats_per_event_time_interval(
    tmp_path, btcusdt_instrument, bar_type
):
    """ADR-008 §7.2 item 4 structural: one heartbeat per heartbeat_interval."""
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=4,
        heartbeat_interval_seconds=120,
    )
    feed = FakeBarFeed()
    # bars at +0, +60s, +120s, +180s; heartbeat_interval=120s -> first beat at 0s, next at >=120s, so 2 beats
    for i in range(4):
        feed.push(_sample(BASE_TS_NS + i * ONE_MIN_NS, close=100.0 + i))

    result = run_paper_session(config, bar_feed=feed)
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    runtime = manifest["runtime"]
    assert runtime["heartbeat_count"] == 2
    heartbeat_lines = (
        result.output_dir / "logs" / "heartbeat.jsonl"
    ).read_text().splitlines()
    assert len(heartbeat_lines) == 2


def test_wall_clock_config_rejects_missing_stop_condition(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    with pytest.raises(ValueError, match="wall_clock data_mode requires"):
        _wall_clock_config(
            tmp_path=tmp_path,
            catalog_path=catalog_path,
            bar_type=bar_type,
            signal_store_path=signal_store_path,
            max_bars=None,
            max_duration_seconds=None,
        )


def test_wall_clock_paper_session_writes_shutdown_reason_on_stop_event(
    tmp_path, btcusdt_instrument, bar_type
):
    import threading

    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=100,
        signal_poll_interval_seconds=1,
    )
    feed = FakeBarFeed()
    feed.push(_sample(BASE_TS_NS))
    stop_event = threading.Event()
    stop_event.set()  # already set: first iteration of loop will break

    result = run_paper_session(config, bar_feed=feed, stop_event=stop_event)
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["runtime"]["shutdown_reason"] == "sigterm"
    # The single pushed bar should still be in the queue (we exited before reading)
    assert manifest["runtime"]["bar_count"] == 0


def test_wall_clock_paper_session_writes_shutdown_reason_on_max_duration(
    tmp_path, btcusdt_instrument, bar_type
):
    catalog_path = _instrument_catalog(tmp_path, btcusdt_instrument)
    signal_store_path = tmp_path / "signals.db"
    SignalStore(signal_store_path)
    config = _wall_clock_config(
        tmp_path=tmp_path,
        catalog_path=catalog_path,
        bar_type=bar_type,
        signal_store_path=signal_store_path,
        max_bars=None,
        max_duration_seconds=1,
        signal_poll_interval_seconds=1,
    )
    feed = FakeBarFeed()  # never push anything; runner should idle out at max_duration

    result = run_paper_session(config, bar_feed=feed)
    manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
    assert manifest["runtime"]["shutdown_reason"] == "max_duration"
    assert manifest["runtime"]["bar_count"] == 0

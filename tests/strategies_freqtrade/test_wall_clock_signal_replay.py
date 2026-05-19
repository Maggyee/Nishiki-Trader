"""Tests for the wall-clock SignalStore restamp helper."""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore
from apps.strategies_freqtrade.research.freqai_linear_signals import (
    DEFAULT_MODEL_VERSION,
    DEFAULT_SOURCE,
)
from apps.strategies_freqtrade.research.wall_clock_signal_replay import (
    WallClockReplayConfig,
    build_wall_clock_replay_events,
    main,
    write_wall_clock_replay,
)

BASE_NS = 1_704_067_200_000_000_000
START_NS = 1_779_840_000_000_000_000  # 2026-05-20T00:00:00Z
ONE_MIN_NS = 60_000_000_000


def _event(
    signal_id: str,
    ts_event: int,
    *,
    confidence: float = 0.7,
    side: str = "buy",
    metadata: dict | None = None,
) -> SignalEvent:
    return SignalEvent(
        signal_id=signal_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        ts_event=ts_event,
        horizon="15m",
        side=side,
        score=0.4 if side == "buy" else -0.4,
        confidence=confidence,
        source=DEFAULT_SOURCE,
        model_version=DEFAULT_MODEL_VERSION,
        ttl_seconds=900,
        features_hash="sha256:test",
        metadata=metadata or {"algorithm": "ridge_linear_momentum"},
    )


def test_build_wall_clock_replay_restamps_selected_events():
    source_events = [
        _event("low-confidence", BASE_NS, confidence=0.51),
        _event("sell", BASE_NS + ONE_MIN_NS, side="sell"),
        _event("buy-a", BASE_NS + 2 * ONE_MIN_NS, side="buy"),
        _event("buy-b", BASE_NS + 3 * ONE_MIN_NS, side="buy"),
    ]
    config = WallClockReplayConfig(
        start_ns=START_NS,
        interval_seconds=60,
        max_signals=2,
        min_confidence=0.55,
        side="buy",
        ttl_seconds=600,
    )

    replayed, eligible_count = build_wall_clock_replay_events(source_events, config)

    assert eligible_count == 2
    assert [event.ts_event for event in replayed] == [
        START_NS,
        START_NS + ONE_MIN_NS,
    ]
    assert [event.side for event in replayed] == ["buy", "buy"]
    assert all(event.source == DEFAULT_SOURCE for event in replayed)
    assert all(event.model_version == DEFAULT_MODEL_VERSION for event in replayed)
    assert all(event.ttl_seconds == 600 for event in replayed)
    assert replayed[0].signal_id.startswith(
        f"{DEFAULT_SOURCE}:{DEFAULT_MODEL_VERSION}:wall_clock_replay:"
    )
    marker = replayed[0].metadata["wall_clock_replay"]
    assert marker["kind"] == "historical_signal_restamp"
    assert marker["original_signal_id"] == "buy-a"
    assert marker["original_ts_event"] == BASE_NS + 2 * ONE_MIN_NS


def test_write_wall_clock_replay_skips_existing_replay_rows(tmp_path: Path):
    db_path = tmp_path / "signals.db"
    store = SignalStore(db_path)
    store.write(_event("hist-a", BASE_NS), now_ns=0)
    store.write(
        _event(
            "already-replayed",
            BASE_NS + ONE_MIN_NS,
            metadata={"wall_clock_replay": {"original_signal_id": "hist-a"}},
        ),
        now_ns=0,
    )
    config = WallClockReplayConfig(
        input_store_path=db_path,
        output_store_path=db_path,
        start_ns=START_NS,
        max_signals=10,
    )

    summary, replayed = write_wall_clock_replay(config)

    assert summary.input_count == 2
    assert summary.eligible_count == 1
    assert summary.generated_count == 1
    assert summary.written_count == 1
    assert summary.skipped_duplicates == 0
    assert replayed[0].metadata["wall_clock_replay"]["original_signal_id"] == "hist-a"

    rows = SignalStore(db_path).replay(
        source=DEFAULT_SOURCE,
        model_version=DEFAULT_MODEL_VERSION,
    )
    assert len(rows) == 3
    assert sum("wall_clock_replay" in event.metadata for event in rows) == 2


def test_write_wall_clock_replay_dry_run_does_not_write(tmp_path: Path):
    input_path = tmp_path / "input.db"
    output_path = tmp_path / "output.db"
    SignalStore(input_path).write(_event("hist-a", BASE_NS), now_ns=0)
    config = WallClockReplayConfig(
        input_store_path=input_path,
        output_store_path=output_path,
        start_ns=START_NS,
        max_signals=1,
    )

    summary, replayed = write_wall_clock_replay(config, dry_run=True)

    assert summary.generated_count == 1
    assert summary.written_count == 0
    assert replayed
    assert not output_path.exists()


def test_cli_dry_run_prints_summary_without_writing(tmp_path: Path, capsys):
    db_path = tmp_path / "signals.db"
    SignalStore(db_path).write(_event("hist-a", BASE_NS), now_ns=0)

    rc = main(
        [
            "--input-store-path",
            str(db_path),
            "--output-store-path",
            str(db_path),
            "--start-at",
            str(START_NS),
            "--max-signals",
            "1",
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert '"generated_count": 1' in out
    assert '"written_count": 0' in out
    rows = SignalStore(db_path).replay(
        source=DEFAULT_SOURCE,
        model_version=DEFAULT_MODEL_VERSION,
    )
    assert [event.signal_id for event in rows] == ["hist-a"]


def _strip_comments_and_strings(source: str) -> str:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return " ".join(
        tok.string
        for tok in tokens
        if tok.type not in (tokenize.COMMENT, tokenize.STRING)
    )


def test_module_has_no_trading_or_network_api_calls():
    from apps.strategies_freqtrade.research import wall_clock_signal_replay

    with open(wall_clock_signal_replay.__file__, encoding="utf-8") as f:
        text = f.read()
    code = _strip_comments_and_strings(text)
    for forbidden in (
        "requests",
        "httpx",
        "ccxt",
        "submit_order",
        "ExecutionEngine",
        "RiskEngine",
        "BINANCE_TESTNET_API",
    ):
        assert forbidden not in code, (
            f"forbidden token {forbidden!r} found in wall_clock_signal_replay.py"
        )


def test_replay_module_does_not_import_network_modules():
    for module in ("httpx", "requests", "ccxt"):
        assert module not in sys.modules or sys.modules[module] is None

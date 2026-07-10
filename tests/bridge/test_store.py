from __future__ import annotations

import json

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import DuplicateSignalError, UnknownSignalError


def test_write_and_read(store, signal_event):
    store.write(signal_event)
    row = store.get(signal_event.signal_id)
    assert row is not None
    assert row["signal_id"] == signal_event.signal_id
    assert row["status"] == "pending"
    assert row["ts_event"] == signal_event.ts_event
    raw = json.loads(row["raw_json"])
    assert raw["schema_version"] == "signal.v1"
    assert raw["score"] == pytest.approx(signal_event.score)


def test_duplicate_signal_id_rejected(store, signal_event):
    store.write(signal_event)
    with pytest.raises(DuplicateSignalError):
        store.write(signal_event)
    rows = store.list_by_status("pending")
    assert len(rows) == 1


def test_write_many_commits_batch_and_counts_duplicates(store, make_payload):
    events = [
        SignalEvent.model_validate(make_payload(signal_id=f"batch-{index}"))
        for index in range(3)
    ]
    written, duplicates = store.write_many([*events, events[0]], now_ns=123)

    assert (written, duplicates) == (3, 1)
    assert [event.signal_id for event in store.replay()] == [
        "batch-0",
        "batch-1",
        "batch-2",
    ]
    assert {row["created_at"] for row in store.list_by_status("pending")} == {123}


def test_mark_consumed_transitions(store, signal_event):
    store.write(signal_event)
    store.mark(signal_event.signal_id, "consumed")
    row = store.get(signal_event.signal_id)
    assert row["status"] == "consumed"
    assert row["consumed_at"] is not None


def test_mark_rejected_records_reason(store, signal_event):
    store.write(signal_event)
    store.mark(signal_event.signal_id, "rejected", reason="ttl_expired")
    row = store.get(signal_event.signal_id)
    assert row["status"] == "rejected"
    assert row["reason"] == "ttl_expired"


def test_mark_unknown_signal_raises(store):
    with pytest.raises(UnknownSignalError):
        store.mark("missing", "consumed")


def test_replay_is_deterministic(store, make_payload):
    events = [
        SignalEvent.model_validate(make_payload(signal_id=f"id-{i}", ts_event=1_778_760_000_000_000_000 + i))
        for i in range(5)
    ]
    for ev in events:
        store.write(ev)
    first = store.replay()
    second = store.replay()
    assert [e.signal_id for e in first] == [f"id-{i}" for i in range(5)]
    assert first == second


def test_replay_filters_by_source_and_model(store, make_payload):
    store.write(SignalEvent.model_validate(make_payload(signal_id="a", source="freqai_v1")))
    store.write(
        SignalEvent.model_validate(
            make_payload(signal_id="b", source="manual_research", model_version="2026-05-14")
        )
    )
    out = store.replay(source="freqai_v1")
    assert [e.signal_id for e in out] == ["a"]


def test_wal_journal_mode_enabled(store):
    import sqlite3

    conn = sqlite3.connect(store.path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_agent_advice_cannot_enter_signals_table(store, make_payload):
    # AgentAdvice would be a different schema; trying to coerce it into SignalEvent must fail,
    # so it never reaches the signals table.
    from pydantic import ValidationError as PydanticValidationError

    advice_payload = {
        "schema_version": "agent.advice.v1",
        "advice": "consider reducing exposure to BTC",
    }
    with pytest.raises(PydanticValidationError):
        SignalEvent.model_validate(advice_payload)
    assert store.list_by_status("pending") == []

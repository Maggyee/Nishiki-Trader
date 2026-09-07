"""Postgres integration tests, isolated by the explicit pg_conn_info fixture."""

from __future__ import annotations

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import (
    DuplicateSignalError,
    PostgresSignalStore,
    UnknownSignalError,
)

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_store(pg_conn_info) -> PostgresSignalStore:
    return PostgresSignalStore(pg_conn_info)


def test_pg_write_and_read(pg_store: PostgresSignalStore, signal_event: SignalEvent) -> None:
    pg_store.write(signal_event)
    row = pg_store.get(signal_event.signal_id)
    assert row is not None
    assert row["signal_id"] == signal_event.signal_id
    assert row["status"] == "pending"
    assert row["ts_event"] == signal_event.ts_event
    assert row["source"] == signal_event.source
    assert row["model_version"] == signal_event.model_version


def test_pg_duplicate_signal_id_rejected(
    pg_store: PostgresSignalStore, signal_event: SignalEvent
) -> None:
    pg_store.write(signal_event)
    with pytest.raises(DuplicateSignalError):
        pg_store.write(signal_event)


def test_pg_mark_unknown_signal_raises(pg_store: PostgresSignalStore) -> None:
    with pytest.raises(UnknownSignalError):
        pg_store.mark("not-a-signal", "consumed")


def test_pg_mark_consumed_sets_consumed_at(
    pg_store: PostgresSignalStore, signal_event: SignalEvent
) -> None:
    pg_store.write(signal_event)
    pg_store.mark(signal_event.signal_id, "consumed", now_ns=1_700_000_000_000_000_000)
    row = pg_store.get(signal_event.signal_id)
    assert row is not None
    assert row["status"] == "consumed"
    assert row["consumed_at"] == 1_700_000_000_000_000_000


def test_pg_replay_filters_by_source_and_window(
    pg_store: PostgresSignalStore, make_payload
) -> None:
    base_ts = 1_700_000_000_000_000_000
    early = SignalEvent.model_validate(
        make_payload(
            signal_id="freqai_v1:A",
            ts_event=base_ts,
        )
    )
    middle = SignalEvent.model_validate(
        make_payload(
            signal_id="freqai_v1:B",
            ts_event=base_ts + 60_000_000_000,
        )
    )
    later = SignalEvent.model_validate(
        make_payload(
            signal_id="freqai_v1:C",
            ts_event=base_ts + 120_000_000_000,
        )
    )
    other_source = SignalEvent.model_validate(
        make_payload(
            signal_id="rule_v1:Z",
            ts_event=base_ts + 30_000_000_000,
            source="rule_v1",
            model_version="rule-2026-05",
        )
    )
    for ev in (early, middle, later, other_source):
        pg_store.write(ev)

    out = pg_store.replay(
        source="freqai_v1",
        since_ns=base_ts,
        until_ns=base_ts + 90_000_000_000,
    )
    assert [ev.signal_id for ev in out] == ["freqai_v1:A", "freqai_v1:B"]


def test_pg_list_by_status_orders_by_ts_event(
    pg_store: PostgresSignalStore, make_payload
) -> None:
    base_ts = 1_700_000_000_000_000_000
    late = SignalEvent.model_validate(
        make_payload(signal_id="freqai_v1:later", ts_event=base_ts + 60_000_000_000)
    )
    early = SignalEvent.model_validate(
        make_payload(signal_id="freqai_v1:earlier", ts_event=base_ts)
    )
    pg_store.write(late)
    pg_store.write(early)
    rows = pg_store.list_by_status("pending")
    assert [r["signal_id"] for r in rows] == ["freqai_v1:earlier", "freqai_v1:later"]


def test_pg_round_trip_preserves_signal_event_payload(
    pg_store: PostgresSignalStore, signal_event: SignalEvent
) -> None:
    pg_store.write(signal_event)
    out = pg_store.replay(source=signal_event.source)
    assert len(out) == 1
    assert out[0].model_dump() == signal_event.model_dump()

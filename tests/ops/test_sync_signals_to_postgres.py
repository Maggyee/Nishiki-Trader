"""Sync integration tests use an explicit test DB and a disposable schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import PostgresSignalStore, SignalStore
from apps.ops import sync_signals_to_postgres

pytestmark = pytest.mark.postgres


@pytest.fixture
def sqlite_with_three(tmp_path: Path, make_payload) -> Path:
    db = tmp_path / "signals.db"
    store = SignalStore(db)
    for offset_ns, sid, source in (
        (0, "freqai_v1:A", "freqai_v1"),
        (60_000_000_000, "freqai_v1:B", "freqai_v1"),
        (120_000_000_000, "rule_v1:Z", "rule_v1"),
    ):
        store.write(
            SignalEvent.model_validate(
                make_payload(
                    signal_id=sid,
                    ts_event=1_700_000_000_000_000_000 + offset_ns,
                    source=source,
                    model_version="rule-2026-05" if source == "rule_v1" else "2026-05-14",
                )
            ),
            now_ns=1_700_000_000_000_000_000 + offset_ns,
        )
    return db


def test_dry_run_does_not_write(
    sqlite_with_three: Path, pg_conn_info
) -> None:
    counts = sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=True,
        sources=None,
        since_ns=None,
    )
    assert counts == {
        "read": 3,
        "written": 0,
        "skipped_duplicate": 0,
        "skipped_filter": 0,
        "errored": 0,
    }
    pg = PostgresSignalStore(pg_conn_info)
    assert pg.get("freqai_v1:A") is None


def test_full_sync_round_trips(
    sqlite_with_three: Path, pg_conn_info
) -> None:
    counts = sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=False,
        sources=None,
        since_ns=None,
    )
    assert counts["read"] == 3
    assert counts["written"] == 3
    assert counts["skipped_duplicate"] == 0
    assert counts["errored"] == 0

    pg = PostgresSignalStore(pg_conn_info)
    for sid in ("freqai_v1:A", "freqai_v1:B", "rule_v1:Z"):
        row = pg.get(sid)
        assert row is not None
        assert row["status"] == "pending"


def test_rerun_is_idempotent(
    sqlite_with_three: Path, pg_conn_info
) -> None:
    sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=False,
        sources=None,
        since_ns=None,
    )
    counts = sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=False,
        sources=None,
        since_ns=None,
    )
    assert counts["read"] == 3
    assert counts["written"] == 0
    assert counts["skipped_duplicate"] == 3
    assert counts["errored"] == 0


def test_filter_by_source(
    sqlite_with_three: Path, pg_conn_info
) -> None:
    counts = sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=False,
        sources=["freqai_v1"],
        since_ns=None,
    )
    assert counts["read"] == 3
    assert counts["written"] == 2
    assert counts["skipped_filter"] == 1
    assert counts["errored"] == 0
    pg = PostgresSignalStore(pg_conn_info)
    assert pg.get("rule_v1:Z") is None
    assert pg.get("freqai_v1:B") is not None


def test_filter_by_since_ns(
    sqlite_with_three: Path, pg_conn_info
) -> None:
    cutoff = 1_700_000_000_000_000_000 + 90_000_000_000  # between B (60s) and Z (120s)
    counts = sync_signals_to_postgres.sync(
        sqlite_path=sqlite_with_three,
        pg_conn=pg_conn_info,
        dry_run=False,
        sources=None,
        since_ns=cutoff,
    )
    assert counts["read"] == 3
    assert counts["written"] == 1
    assert counts["skipped_filter"] == 2
    pg = PostgresSignalStore(pg_conn_info)
    assert pg.get("rule_v1:Z") is not None
    assert pg.get("freqai_v1:A") is None

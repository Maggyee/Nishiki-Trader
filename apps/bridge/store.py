from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from apps.bridge.signal_event import SignalEvent

DEFAULT_DB_PATH = Path("data/bridge/signals.db")

Status = Literal["pending", "consumed", "rejected", "expired"]

_VALID_STATUSES: frozenset[Status] = frozenset({"pending", "consumed", "rejected", "expired"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id      TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    venue          TEXT NOT NULL,
    ts_event       INTEGER NOT NULL,
    horizon        TEXT NOT NULL,
    side           TEXT NOT NULL,
    score          REAL NOT NULL,
    confidence     REAL NOT NULL,
    source         TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    ttl_seconds    INTEGER NOT NULL,
    raw_json       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    reason         TEXT,
    created_at     INTEGER NOT NULL,
    consumed_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_signals_ts_event ON signals(ts_event);
CREATE INDEX IF NOT EXISTS idx_signals_source_model
    ON signals(source, model_version);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
"""


class DuplicateSignalError(Exception):
    pass


class UnknownSignalError(Exception):
    pass


class SignalStore:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def write(self, event: SignalEvent, *, now_ns: int | None = None) -> None:
        created_at = time.time_ns() if now_ns is None else now_ns
        payload = event.model_dump_json()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO signals (
                        signal_id, schema_version, symbol, venue, ts_event,
                        horizon, side, score, confidence, source, model_version,
                        ttl_seconds, raw_json, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        event.signal_id,
                        event.schema_version,
                        event.symbol,
                        event.venue,
                        event.ts_event,
                        event.horizon,
                        event.side,
                        event.score,
                        event.confidence,
                        event.source,
                        event.model_version,
                        event.ttl_seconds,
                        payload,
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateSignalError(event.signal_id) from exc

    def mark(
        self,
        signal_id: str,
        status: Status,
        *,
        reason: str | None = None,
        now_ns: int | None = None,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        consumed_at = (time.time_ns() if now_ns is None else now_ns) if status == "consumed" else None
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE signals SET status = ?, reason = ?, consumed_at = COALESCE(?, consumed_at) "
                "WHERE signal_id = ?",
                (status, reason, consumed_at, signal_id),
            )
            if cur.rowcount == 0:
                raise UnknownSignalError(signal_id)

    def get(self, signal_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
            return cur.fetchone()

    def list_by_status(self, status: Status) -> list[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM signals WHERE status = ? ORDER BY ts_event ASC",
                (status,),
            )
            return list(cur.fetchall())

    def replay(
        self,
        *,
        source: str | None = None,
        model_version: str | None = None,
        since_ns: int | None = None,
        until_ns: int | None = None,
    ) -> list[SignalEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if model_version is not None:
            clauses.append("model_version = ?")
            params.append(model_version)
        if since_ns is not None:
            clauses.append("ts_event >= ?")
            params.append(since_ns)
        if until_ns is not None:
            clauses.append("ts_event <= ?")
            params.append(until_ns)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT raw_json FROM signals" + where + " ORDER BY ts_event ASC, signal_id ASC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [SignalEvent.model_validate_json(row["raw_json"]) for row in rows]


# ---------------------------------------------------------------------------
# Postgres backend (Phase 3 entry, service-only — SQLite is still the default
# bridge backend; see ADR-001 §6 2026-05-21 修订第二段).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostgresConnInfo:
    """Connection settings for ``PostgresSignalStore``.

    Schema lives in ``infra/postgres/init.sql`` (table ``signal_events``).
    The default credentials match ``infra/docker-compose.yml``'s
    ``trader-postgres`` service on ``127.0.0.1:5433``; they are dev-only and
    safe to commit because the port is loopback.
    """

    host: str = "127.0.0.1"
    port: int = 5433
    dbname: str = "trader"
    user: str = "trader"
    password: str = "trader_local_pg"

    def to_conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password}"
        )


class PostgresSignalStore:
    """Drop-in alternative to ``SignalStore`` backed by ``signal_events``.

    Method surface mirrors ``SignalStore`` so callers can be wired to either
    backend by configuration. SQLite remains the default; this class is for
    future Phase 2+ adoption once SignalStore-level volume forces the move.
    """

    def __init__(self, conn_info: PostgresConnInfo | None = None) -> None:
        if conn_info is None:
            conn_info = PostgresConnInfo()
        self.conn_info = conn_info

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        import psycopg

        conn = psycopg.connect(self.conn_info.to_conninfo(), autocommit=True)
        try:
            yield conn
        finally:
            conn.close()

    def write(self, event: SignalEvent, *, now_ns: int | None = None) -> None:
        import psycopg

        created_at = time.time_ns() if now_ns is None else now_ns
        payload = event.model_dump_json()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO signal_events (
                        signal_id, schema_version, symbol, venue, ts_event,
                        horizon, side, score, confidence, source, model_version,
                        ttl_seconds, raw_json, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    """,
                    (
                        event.signal_id,
                        event.schema_version,
                        event.symbol,
                        event.venue,
                        event.ts_event,
                        event.horizon,
                        event.side,
                        event.score,
                        event.confidence,
                        event.source,
                        event.model_version,
                        event.ttl_seconds,
                        payload,
                        created_at,
                    ),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise DuplicateSignalError(event.signal_id) from exc

    def mark(
        self,
        signal_id: str,
        status: Status,
        *,
        reason: str | None = None,
        now_ns: int | None = None,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        consumed_at = (
            (time.time_ns() if now_ns is None else now_ns) if status == "consumed" else None
        )
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE signal_events SET status = %s, reason = %s, "
                "consumed_at = COALESCE(%s, consumed_at) WHERE signal_id = %s",
                (status, reason, consumed_at, signal_id),
            )
            if cur.rowcount == 0:
                raise UnknownSignalError(signal_id)

    def get(self, signal_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM signal_events WHERE signal_id = %s",
                (signal_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            columns = [desc.name for desc in cur.description]
            return dict(zip(columns, row, strict=True))

    def list_by_status(self, status: Status) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM signal_events WHERE status = %s ORDER BY ts_event ASC",
                (status,),
            )
            rows = cur.fetchall()
            columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def replay(
        self,
        *,
        source: str | None = None,
        model_version: str | None = None,
        since_ns: int | None = None,
        until_ns: int | None = None,
    ) -> list[SignalEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if source is not None:
            clauses.append("source = %s")
            params.append(source)
        if model_version is not None:
            clauses.append("model_version = %s")
            params.append(model_version)
        if since_ns is not None:
            clauses.append("ts_event >= %s")
            params.append(since_ns)
        if until_ns is not None:
            clauses.append("ts_event <= %s")
            params.append(until_ns)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT raw_json FROM signal_events"
            + where
            + " ORDER BY ts_event ASC, signal_id ASC"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [SignalEvent.model_validate_json(row[0]) for row in rows]


__all__ = [
    "DEFAULT_DB_PATH",
    "DuplicateSignalError",
    "PostgresConnInfo",
    "PostgresSignalStore",
    "SignalStore",
    "Status",
    "UnknownSignalError",
]

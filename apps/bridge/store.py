from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

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

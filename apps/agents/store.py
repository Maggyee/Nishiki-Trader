from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from apps.agents.advice import (
    AdviceStatus,
    AgentAdvice,
    AgentAdviceReview,
    ReviewDecision,
)

DEFAULT_ADVICE_DB_PATH = Path("data/agents/advice.db")

_VALID_STATUSES: frozenset[AdviceStatus] = frozenset({"recorded", "reviewed", "archived"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_advice (
    advice_id      TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    agent_name     TEXT NOT NULL,
    created_at_ns  INTEGER NOT NULL,
    advice_type    TEXT NOT NULL,
    summary        TEXT NOT NULL,
    confidence     REAL NOT NULL,
    raw_json       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'recorded',
    review_decision TEXT,
    reviewed_by    TEXT,
    reviewed_at_ns INTEGER,
    review_note    TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_advice_created_at ON agent_advice(created_at_ns);
CREATE INDEX IF NOT EXISTS idx_agent_advice_agent_type
    ON agent_advice(agent_name, advice_type);
CREATE INDEX IF NOT EXISTS idx_agent_advice_status ON agent_advice(status);
"""


class DuplicateAdviceError(Exception):
    pass


class UnknownAdviceError(Exception):
    pass


class AgentAdviceStore:
    def __init__(self, path: Path | str = DEFAULT_ADVICE_DB_PATH) -> None:
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

    def write(self, advice: AgentAdvice) -> None:
        payload = advice.model_dump_json()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO agent_advice (
                        advice_id, schema_version, agent_name, created_at_ns,
                        advice_type, summary, confidence, raw_json, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recorded')
                    """,
                    (
                        advice.advice_id,
                        advice.schema_version,
                        advice.agent_name,
                        advice.created_at_ns,
                        advice.advice_type,
                        advice.summary,
                        advice.confidence,
                        payload,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateAdviceError(advice.advice_id) from exc

    def get(self, advice_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM agent_advice WHERE advice_id = ?", (advice_id,))
            return cur.fetchone()

    def list(
        self,
        *,
        agent_name: str | None = None,
        advice_type: str | None = None,
        status: AdviceStatus | None = None,
        since_ns: int | None = None,
        until_ns: int | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        if status is not None and status not in _VALID_STATUSES:
            raise ValueError(f"invalid status {status!r}")
        if limit <= 0:
            raise ValueError("limit must be positive")

        clauses: list[str] = []
        params: list[Any] = []
        if agent_name is not None:
            clauses.append("agent_name = ?")
            params.append(agent_name)
        if advice_type is not None:
            clauses.append("advice_type = ?")
            params.append(advice_type)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if since_ns is not None:
            clauses.append("created_at_ns >= ?")
            params.append(since_ns)
        if until_ns is not None:
            clauses.append("created_at_ns <= ?")
            params.append(until_ns)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM agent_advice"
            + where
            + " ORDER BY created_at_ns ASC, advice_id ASC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return list(cur.fetchall())

    def replay(
        self,
        *,
        agent_name: str | None = None,
        advice_type: str | None = None,
        status: AdviceStatus | None = None,
        since_ns: int | None = None,
        until_ns: int | None = None,
        limit: int = 100,
    ) -> list[AgentAdvice]:
        rows = self.list(
            agent_name=agent_name,
            advice_type=advice_type,
            status=status,
            since_ns=since_ns,
            until_ns=until_ns,
            limit=limit,
        )
        return [AgentAdvice.model_validate_json(row["raw_json"]) for row in rows]

    def review(
        self,
        advice_id: str,
        decision: ReviewDecision,
        *,
        reviewed_by: str,
        note: str | None = None,
        now_ns: int | None = None,
    ) -> AgentAdviceReview:
        reviewed_at = time.time_ns() if now_ns is None else now_ns
        review = AgentAdviceReview(
            advice_id=advice_id,
            decision=decision,
            reviewed_by=reviewed_by,
            reviewed_at_ns=reviewed_at,
            note=note,
        )
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE agent_advice
                SET status = 'reviewed',
                    review_decision = ?,
                    reviewed_by = ?,
                    reviewed_at_ns = ?,
                    review_note = ?
                WHERE advice_id = ?
                """,
                (
                    review.decision,
                    review.reviewed_by,
                    review.reviewed_at_ns,
                    review.note,
                    advice_id,
                ),
            )
            if cur.rowcount == 0:
                raise UnknownAdviceError(advice_id)
        return review

    def archive(self, advice_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE agent_advice SET status = 'archived' WHERE advice_id = ?",
                (advice_id,),
            )
            if cur.rowcount == 0:
                raise UnknownAdviceError(advice_id)

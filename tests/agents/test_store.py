from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps.agents.advice import AgentAdvice
from apps.agents.store import AgentAdviceStore, DuplicateAdviceError, UnknownAdviceError

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _advice(advice_id: str = "a1", **overrides: object) -> AgentAdvice:
    payload: dict[str, object] = {
        "schema_version": "agent.advice.v1",
        "advice_id": advice_id,
        "agent_name": "review_agent",
        "created_at_ns": REFERENCE_TS_NS,
        "advice_type": "journal",
        "summary": "testnet evidence is operational",
        "confidence": 0.8,
        "payload": {"content": "review note"},
        "tags": ("testnet",),
        "source_refs": (),
    }
    payload.update(overrides)
    return AgentAdvice.model_validate(payload)


def test_write_and_get(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")
    advice = _advice()

    store.write(advice)
    row = store.get(advice.advice_id)

    assert row is not None
    assert row["advice_id"] == "a1"
    assert row["status"] == "recorded"
    assert row["schema_version"] == "agent.advice.v1"
    raw = json.loads(row["raw_json"])
    assert raw["schema_version"] == "agent.advice.v1"


def test_duplicate_advice_id_rejected(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")
    advice = _advice()

    store.write(advice)
    with pytest.raises(DuplicateAdviceError):
        store.write(advice)

    assert len(store.list()) == 1


def test_replay_filters_by_agent_type_and_window(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")
    store.write(_advice("a1", advice_type="journal", created_at_ns=REFERENCE_TS_NS))
    store.write(
        _advice(
            "a2",
            agent_name="data_agent",
            advice_type="anomaly_note",
            created_at_ns=REFERENCE_TS_NS + 10,
        )
    )

    assert [a.advice_id for a in store.replay(agent_name="review_agent")] == ["a1"]
    assert [a.advice_id for a in store.replay(advice_type="anomaly_note")] == ["a2"]
    assert [a.advice_id for a in store.replay(since_ns=REFERENCE_TS_NS + 1)] == ["a2"]


def test_review_records_human_decision(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")
    store.write(_advice())

    review = store.review(
        "a1",
        "accepted",
        reviewed_by="nishiki",
        note="Useful for retro.",
        now_ns=REFERENCE_TS_NS + 1,
    )
    row = store.get("a1")

    assert review.decision == "accepted"
    assert row is not None
    assert row["status"] == "reviewed"
    assert row["review_decision"] == "accepted"
    assert row["reviewed_by"] == "nishiki"
    assert row["review_note"] == "Useful for retro."


def test_unknown_review_raises(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")

    with pytest.raises(UnknownAdviceError):
        store.review("missing", "ignored", reviewed_by="nishiki", now_ns=REFERENCE_TS_NS)


def test_wal_journal_mode_enabled(tmp_path: Path) -> None:
    store = AgentAdviceStore(tmp_path / "advice.db")
    conn = sqlite3.connect(store.path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"

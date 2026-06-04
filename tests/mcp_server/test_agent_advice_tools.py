from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.agents.store import AgentAdviceStore
from apps.bridge.store import SignalStore
from apps.mcp_server.agent_advice_tools import (
    ALLOWED_AGENT_ADVICE_TOOLS,
    AgentAdviceToolContext,
    query_agent_advice,
    write_agent_advice,
    write_journal,
)

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _context(tmp_path: Path) -> AgentAdviceToolContext:
    return AgentAdviceToolContext(
        advice_db_path=tmp_path / "advice.db",
        audit_log_path=tmp_path / "mcp_tool_audit.jsonl",
        caller="pytest",
    )


def _advice_payload(advice_id: str = "a1") -> dict[str, object]:
    return {
        "schema_version": "agent.advice.v1",
        "advice_id": advice_id,
        "agent_name": "review_agent",
        "created_at_ns": REFERENCE_TS_NS,
        "advice_type": "journal",
        "summary": "testnet evidence is operational",
        "confidence": 0.8,
        "payload": {"content": "review note"},
        "tags": ["testnet"],
        "source_refs": [],
    }


def test_allowed_tool_surface_is_agent_advice_only() -> None:
    assert {
        "query_agent_advice",
        "write_agent_advice",
        "write_journal",
    } == ALLOWED_AGENT_ADVICE_TOOLS


def test_write_agent_advice_records_row_and_audit(tmp_path: Path) -> None:
    ctx = _context(tmp_path)

    result = write_agent_advice(context=ctx, advice=_advice_payload())

    assert result == {
        "advice_id": "a1",
        "schema_version": "agent.advice.v1",
        "status": "recorded",
    }
    row = AgentAdviceStore(ctx.advice_db_path).get("a1")
    assert row is not None
    assert row["schema_version"] == "agent.advice.v1"
    audit_rows = _audit_rows(ctx.audit_log_path)
    assert audit_rows[-1]["tool_name"] == "write_agent_advice"
    assert audit_rows[-1]["caller"] == "pytest"
    assert audit_rows[-1]["parameters"]["advice_id"] == "a1"


def test_context_accepts_string_paths(tmp_path: Path) -> None:
    ctx = AgentAdviceToolContext(
        advice_db_path=str(tmp_path / "advice.db"),
        audit_log_path=str(tmp_path / "mcp_tool_audit.jsonl"),
    )

    write_agent_advice(context=ctx, advice=_advice_payload())

    assert isinstance(ctx.advice_db_path, Path)
    assert isinstance(ctx.audit_log_path, Path)
    assert ctx.advice_db_path.exists()
    assert ctx.audit_log_path.exists()


def test_query_agent_advice_filters_and_audits(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    write_agent_advice(context=ctx, advice=_advice_payload("a1"))
    write_agent_advice(
        context=ctx,
        advice={
            **_advice_payload("a2"),
            "agent_name": "data_agent",
            "advice_type": "anomaly_note",
            "created_at_ns": REFERENCE_TS_NS + 1,
        },
    )

    rows = query_agent_advice(context=ctx, agent_name="data_agent", limit=10)

    assert [row["advice_id"] for row in rows] == ["a2"]
    audit_rows = _audit_rows(ctx.audit_log_path)
    assert audit_rows[-1]["tool_name"] == "query_agent_advice"
    assert audit_rows[-1]["result"]["row_count"] == 1


def test_write_journal_uses_agent_advice_schema(tmp_path: Path) -> None:
    ctx = _context(tmp_path)

    result = write_journal(
        context=ctx,
        agent_name="review_agent",
        advice_id="journal-1",
        created_at_ns=REFERENCE_TS_NS,
        content="BTCUSDT testnet evidence is operational, not alpha.",
        tags=("testnet", "retro"),
        source_refs=("docs/project-status.md",),
    )

    assert result["advice_id"] == "journal-1"
    stored = AgentAdviceStore(ctx.advice_db_path).replay()[0]
    assert stored.advice_type == "journal"
    assert stored.payload == {
        "content": "BTCUSDT testnet evidence is operational, not alpha."
    }
    audit_tool_names = [row["tool_name"] for row in _audit_rows(ctx.audit_log_path)]
    assert audit_tool_names == ["write_agent_advice", "write_journal"]


def test_execution_directives_are_rejected_before_write(tmp_path: Path) -> None:
    ctx = _context(tmp_path)

    with pytest.raises(PydanticValidationError):
        write_agent_advice(
            context=ctx,
            advice={**_advice_payload(), "payload": {"order_type": "market"}},
        )

    assert AgentAdviceStore(ctx.advice_db_path).replay() == []
    assert not ctx.audit_log_path.exists()


def test_agent_advice_tools_do_not_touch_signal_store(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    signal_store = SignalStore(tmp_path / "signals.db")

    write_agent_advice(context=ctx, advice=_advice_payload())

    assert signal_store.list_by_status("pending") == []


def _audit_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

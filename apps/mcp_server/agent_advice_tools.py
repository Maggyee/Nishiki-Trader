from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from apps.agents.advice import AdviceStatus, AgentAdvice
from apps.agents.store import DEFAULT_ADVICE_DB_PATH, AgentAdviceStore

DEFAULT_MCP_AUDIT_LOG_PATH = Path("data/agents/mcp_tool_audit.jsonl")

AgentAdviceToolName = Literal[
    "query_agent_advice",
    "write_agent_advice",
    "write_journal",
]

ALLOWED_AGENT_ADVICE_TOOLS: frozenset[str] = frozenset(
    {
        "query_agent_advice",
        "write_agent_advice",
        "write_journal",
    }
)


@dataclass(frozen=True)
class AgentAdviceToolContext:
    """Local context for Phase 4 MCP-facing AgentAdvice tools.

    This is not a running MCP server. It is the safe callable layer future MCP
    handlers can wrap without gaining access to SignalStore or exchange APIs.
    """

    advice_db_path: Path | str = DEFAULT_ADVICE_DB_PATH
    audit_log_path: Path | str = DEFAULT_MCP_AUDIT_LOG_PATH
    caller: str = "local_mcp"

    def __post_init__(self) -> None:
        object.__setattr__(self, "advice_db_path", Path(self.advice_db_path))
        object.__setattr__(self, "audit_log_path", Path(self.audit_log_path))


def query_agent_advice(
    *,
    context: AgentAdviceToolContext | None = None,
    agent_name: str | None = None,
    advice_type: str | None = None,
    status: AdviceStatus | None = None,
    since_ns: int | None = None,
    until_ns: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ctx = _context(context)
    store = AgentAdviceStore(ctx.advice_db_path)
    advice_rows = store.replay(
        agent_name=agent_name,
        advice_type=advice_type,
        status=status,
        since_ns=since_ns,
        until_ns=until_ns,
        limit=limit,
    )
    result = [advice.model_dump(mode="json") for advice in advice_rows]
    _append_audit(
        ctx,
        tool_name="query_agent_advice",
        parameters={
            "agent_name": agent_name,
            "advice_type": advice_type,
            "status": status,
            "since_ns": since_ns,
            "until_ns": until_ns,
            "limit": limit,
        },
        result={"row_count": len(result)},
    )
    return result


def write_agent_advice(
    *,
    advice: AgentAdvice | dict[str, Any],
    context: AgentAdviceToolContext | None = None,
) -> dict[str, Any]:
    ctx = _context(context)
    validated = advice if isinstance(advice, AgentAdvice) else AgentAdvice.model_validate(advice)
    AgentAdviceStore(ctx.advice_db_path).write(validated)
    result = {
        "advice_id": validated.advice_id,
        "schema_version": validated.schema_version,
        "status": "recorded",
    }
    _append_audit(
        ctx,
        tool_name="write_agent_advice",
        parameters={
            "advice_id": validated.advice_id,
            "agent_name": validated.agent_name,
            "advice_type": validated.advice_type,
        },
        result=result,
    )
    return result


def write_journal(
    *,
    agent_name: str,
    content: str,
    advice_id: str,
    created_at_ns: int,
    confidence: float = 1.0,
    summary: str | None = None,
    tags: tuple[str, ...] = (),
    source_refs: tuple[str, ...] = (),
    context: AgentAdviceToolContext | None = None,
) -> dict[str, Any]:
    advice = AgentAdvice(
        schema_version="agent.advice.v1",
        advice_id=advice_id,
        agent_name=agent_name,
        created_at_ns=created_at_ns,
        advice_type="journal",
        summary=summary or _summarize_content(content),
        confidence=confidence,
        payload={"content": content},
        tags=tags,
        source_refs=source_refs,
    )
    result = write_agent_advice(advice=advice, context=context)
    ctx = _context(context)
    _append_audit(
        ctx,
        tool_name="write_journal",
        parameters={
            "advice_id": advice.advice_id,
            "agent_name": advice.agent_name,
            "tag_count": len(advice.tags),
            "source_ref_count": len(advice.source_refs),
        },
        result=result,
    )
    return result


def _context(context: AgentAdviceToolContext | None) -> AgentAdviceToolContext:
    return AgentAdviceToolContext() if context is None else context


def _append_audit(
    context: AgentAdviceToolContext,
    *,
    tool_name: AgentAdviceToolName,
    parameters: dict[str, Any],
    result: dict[str, Any],
) -> None:
    if tool_name not in ALLOWED_AGENT_ADVICE_TOOLS:
        raise ValueError(f"tool_name={tool_name!r} is not an AgentAdvice MCP tool")
    path = context.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_ns": time.time_ns(),
        "caller": context.caller,
        "tool_name": tool_name,
        "parameters": parameters,
        "result": result,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _summarize_content(content: str) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= 160:
        return normalized
    return normalized[:157] + "..."

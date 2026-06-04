from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.agents.advice import AgentAdvice
from apps.agents.store import (
    DEFAULT_ADVICE_DB_PATH,
    AgentAdviceStore,
    DuplicateAdviceError,
)

DEFAULT_PROJECT_STATUS_PATH = Path("docs/project-status.md")
DEFAULT_AGENT_NAME = "review_agent"
ADVICE_TYPE = "project_review"

_CURRENT_PHASE_RE = re.compile(r"^- \*\*Current phase\*\*:\s*(?P<value>.+)$", re.MULTILINE)
_CURRENT_OBJECTIVE_RE = re.compile(
    r"^- \*\*Current objective\*\*:\s*(?P<value>.+)$",
    re.MULTILINE,
)
_STRICT_STREAK_RE = re.compile(r"current_qualified_streak_days\s*=\s*(?P<value>\d+/\d+)")
_CLEAN_CANARY_RE = re.compile(
    r"\b(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty)\s+clean\b[^\n]*(?:testnet\s+)?canaries\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


@dataclass(frozen=True)
class ReviewAgentInput:
    project_status_path: Path = DEFAULT_PROJECT_STATUS_PATH
    evidence_paths: tuple[Path, ...] = ()
    agent_name: str = DEFAULT_AGENT_NAME
    created_at_ns: int | None = None
    advice_id: str | None = None


@dataclass(frozen=True)
class ReviewAgentResult:
    advice: AgentAdvice
    wrote: bool
    duplicate: bool = False


def build_project_review_advice(input_data: ReviewAgentInput) -> AgentAdvice:
    created_at_ns = time.time_ns() if input_data.created_at_ns is None else input_data.created_at_ns
    status_text = _read_text(input_data.project_status_path)
    evidence_texts = {path: _read_text(path) for path in input_data.evidence_paths}

    phase = _extract_first(_CURRENT_PHASE_RE, status_text) or "unknown"
    objective = _extract_first(_CURRENT_OBJECTIVE_RE, status_text) or "unknown"
    strict_streak = _extract_strict_streak(status_text, evidence_texts.values())
    clean_canary_count = _extract_clean_canary_count(status_text, evidence_texts.values())
    live_blocked = _detect_live_blocked(status_text)
    dashboard_snapshot_ready = _detect_dashboard_snapshot_ready(status_text)

    observations = [
        f"Current phase: {phase}",
        f"Strict testnet continuity streak: {strict_streak or 'unknown'}",
        f"Clean sidecar-backed canary count: {clean_canary_count or 'unknown'}",
    ]
    if live_blocked:
        observations.append("Live trading remains blocked by ADR-001/ADR-008 gates.")

    recommended_next_actions = _recommended_next_actions(
        phase=phase,
        live_blocked=live_blocked,
        strict_streak=strict_streak,
        dashboard_snapshot_ready=dashboard_snapshot_ready,
    )
    payload: dict[str, Any] = {
        "phase": phase,
        "objective": objective,
        "observations": observations,
        "recommended_next_actions": recommended_next_actions,
        "dashboard_snapshot_ready": dashboard_snapshot_ready,
        "live_path_allowed": False,
        "signal_event_write_allowed": False,
        "source_policy_mutation_allowed": False,
    }
    source_refs = (str(input_data.project_status_path),) + tuple(
        str(path) for path in input_data.evidence_paths
    )
    advice_id = input_data.advice_id or _make_advice_id(
        agent_name=input_data.agent_name,
        created_at_ns=created_at_ns,
        payload=payload,
    )
    summary = _summary(phase=phase, strict_streak=strict_streak, live_blocked=live_blocked)
    return AgentAdvice(
        schema_version="agent.advice.v1",
        advice_id=advice_id,
        agent_name=input_data.agent_name,
        created_at_ns=created_at_ns,
        advice_type=ADVICE_TYPE,
        summary=summary,
        confidence=1.0,
        payload=payload,
        tags=("phase4", "review", "mock_llm"),
        source_refs=source_refs,
    )


def run_review_agent(
    input_data: ReviewAgentInput,
    *,
    store: AgentAdviceStore,
    dry_run: bool = False,
) -> ReviewAgentResult:
    advice = build_project_review_advice(input_data)
    if dry_run:
        return ReviewAgentResult(advice=advice, wrote=False)
    try:
        store.write(advice)
    except DuplicateAdviceError:
        return ReviewAgentResult(advice=advice, wrote=False, duplicate=True)
    return ReviewAgentResult(advice=advice, wrote=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group("value").strip() if match else None


def _extract_strict_streak(status_text: str, evidence_texts: Iterable[str]) -> str | None:
    for text in (status_text, *tuple(evidence_texts)):
        match = _STRICT_STREAK_RE.search(text)
        if match:
            return match.group("value")
    return None


def _extract_clean_canary_count(
    status_text: str,
    evidence_texts: Iterable[str],
) -> int | None:
    for text in (status_text, *tuple(evidence_texts)):
        match = _CLEAN_CANARY_RE.search(text)
        if match:
            raw = match.group("count").lower()
            return int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
    return None


def _detect_live_blocked(status_text: str) -> bool:
    lowered = status_text.lower()
    return "no live trading" in lowered or "live trading still blocked" in lowered


def _detect_dashboard_snapshot_ready(status_text: str) -> bool:
    lowered = status_text.lower()
    return "dashboard.snapshot.v1" in lowered or "apps.ops.dashboard_snapshot" in lowered


def _recommended_next_actions(
    *,
    phase: str,
    live_blocked: bool,
    strict_streak: str | None,
    dashboard_snapshot_ready: bool,
) -> list[str]:
    actions = [
        "Continue Phase 4 with AgentAdvice-only review/report tooling.",
        "Keep LLM and MCP outputs outside SignalEvent and SourcePolicy mutation paths.",
    ]
    if phase.lower().startswith("phase 4"):
        if dashboard_snapshot_ready:
            actions.append(
                "Use dashboard.snapshot.v1 as the read-only surface for future dashboard/frontend work."
            )
        else:
            actions.append(
                "Before Phase 5, add read-only report surfaces suitable for dashboard use."
            )
    if strict_streak and not strict_streak.endswith("/0"):
        actions.append("Treat testnet continuity as paused evidence unless the operator resumes it.")
    if live_blocked:
        actions.append("Do not open live-risk work until the separate live ADR gate exists.")
    return actions


def _summary(*, phase: str, strict_streak: str | None, live_blocked: bool) -> str:
    blocked = "live blocked" if live_blocked else "live status unknown"
    streak = strict_streak or "unknown streak"
    return f"{phase}; testnet continuity {streak}; {blocked}."


def _make_advice_id(*, agent_name: str, created_at_ns: int, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"{agent_name}:{ADVICE_TYPE}:{created_at_ns}:{digest}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review-agent",
        description="Deterministic Phase 4 review agent that writes only AgentAdvice",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_ADVICE_DB_PATH),
        help=f"SQLite AgentAdvice DB path (default: {DEFAULT_ADVICE_DB_PATH})",
    )
    parser.add_argument(
        "--project-status-path",
        default=str(DEFAULT_PROJECT_STATUS_PATH),
    )
    parser.add_argument(
        "--evidence-path",
        action="append",
        default=[],
        help="Optional evidence markdown path to reference and summarize.",
    )
    parser.add_argument("--agent-name", default=DEFAULT_AGENT_NAME)
    parser.add_argument("--created-at-ns", type=int, default=None)
    parser.add_argument("--advice-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_data = ReviewAgentInput(
        project_status_path=Path(args.project_status_path),
        evidence_paths=tuple(Path(path) for path in args.evidence_path),
        agent_name=args.agent_name,
        created_at_ns=args.created_at_ns,
        advice_id=args.advice_id,
    )
    result = run_review_agent(
        input_data,
        store=AgentAdviceStore(args.db),
        dry_run=args.dry_run,
    )
    out = result.advice.model_dump(mode="json")
    out["_write_result"] = {
        "wrote": result.wrote,
        "duplicate": result.duplicate,
        "dry_run": args.dry_run,
    }
    sys.stdout.write(json.dumps(out, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

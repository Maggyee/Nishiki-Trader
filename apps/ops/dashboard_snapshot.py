from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from apps.agents.store import DEFAULT_ADVICE_DB_PATH
from apps.strategies_nautilus.runners.report_paper_bundle import (
    load_paper_bundle_report,
)
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    load_testnet_bundle_report,
)

DEFAULT_PROJECT_STATUS_PATH = Path("docs/project-status.md")
SNAPSHOT_SCHEMA_VERSION = "dashboard.snapshot.v1"

_STATUS_FIELD_RE = re.compile(
    r"^- \*\*(?P<key>Last updated|Current phase|Current objective)\*\*:\s*(?P<value>.+)$",
    re.MULTILINE,
)
_HEADING_RE_TEMPLATE = r"^## {heading}\s*$"
_NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s+(?P<value>.+)$")
_BULLET_ITEM_RE = re.compile(r"^- (?P<value>.+)$")
_STRICT_STREAK_RE = re.compile(
    r"(?:current_qualified_streak_days\s*=\s*|strict streak remains\s+)"
    r"(?P<value>\d+/\d+)",
    re.IGNORECASE,
)


def build_dashboard_snapshot(
    *,
    project_status_path: Path = DEFAULT_PROJECT_STATUS_PATH,
    agent_advice_db_path: Path = DEFAULT_ADVICE_DB_PATH,
    paper_bundle_dirs: Sequence[Path] = (),
    testnet_bundle_dirs: Sequence[Path] = (),
    advice_limit: int = 20,
    generated_at_ns: int | None = None,
) -> dict[str, Any]:
    if advice_limit <= 0:
        raise ValueError("advice_limit must be positive")

    boundaries = {
        "live_path_allowed": False,
        "signal_event_write_allowed": False,
        "source_policy_mutation_allowed": False,
        "exchange_api_access_allowed": False,
    }
    project_status = _project_status_snapshot(project_status_path)
    agent_advice = _agent_advice_snapshot(agent_advice_db_path, limit=advice_limit)
    paper_bundles = [
        _compact_paper_report(load_paper_bundle_report(path))
        for path in paper_bundle_dirs
    ]
    testnet_bundles = [
        _compact_testnet_report(load_testnet_bundle_report(path))
        for path in testnet_bundle_dirs
    ]
    ops_status = _ops_status_snapshot(
        project_status=project_status,
        boundaries=boundaries,
        agent_advice=agent_advice,
        paper_bundles=paper_bundles,
        testnet_bundles=testnet_bundles,
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at_ns": time.time_ns() if generated_at_ns is None else generated_at_ns,
        "boundaries": boundaries,
        "project_status": project_status,
        "agent_advice": agent_advice,
        "paper_bundles": paper_bundles,
        "testnet_bundles": testnet_bundles,
        "ops_status": ops_status,
        "operator_checklist": _operator_checklist(
            project_status=project_status,
            boundaries=boundaries,
            agent_advice=agent_advice,
            ops_status=ops_status,
        ),
    }


def render_markdown_snapshot(snapshot: dict[str, Any]) -> str:
    status = snapshot["project_status"]
    advice = snapshot["agent_advice"]
    boundaries = snapshot["boundaries"]
    lines = [
        "# Dashboard Snapshot",
        "",
        f"- schema_version: `{snapshot['schema_version']}`",
        f"- generated_at_ns: `{snapshot['generated_at_ns']}`",
        f"- current_phase: {status.get('current_phase') or 'unknown'}",
        f"- ops_state: `{snapshot.get('ops_status', {}).get('state', 'unknown')}`",
        f"- live_trading_blocked: {str(status.get('live_trading_blocked')).lower()}",
        (
            "- boundaries: "
            f"live_path_allowed={str(boundaries['live_path_allowed']).lower()}, "
            "signal_event_write_allowed="
            f"{str(boundaries['signal_event_write_allowed']).lower()}, "
            "source_policy_mutation_allowed="
            f"{str(boundaries['source_policy_mutation_allowed']).lower()}"
        ),
        "",
        "## Operator Next Steps",
        "",
    ]
    for item in status.get("sections", {}).get("next_steps", []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Blocked / Deferred",
            "",
        ]
    )
    for item in status.get("sections", {}).get("blocked_deferred", []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## AgentAdvice",
            "",
        ]
    )
    lines.extend(
        [
            f"- db_exists: {str(advice['db_exists']).lower()}",
            f"- total: {advice['total']}",
            f"- by_status: `{json.dumps(advice['by_status'], sort_keys=True)}`",
            f"- by_type: `{json.dumps(advice['by_type'], sort_keys=True)}`",
            "",
            "| created_at_ns | advice_id | agent | type | status | summary |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for item in advice["latest"]:
        lines.append(
            "| "
            f"{item['created_at_ns']} | "
            f"`{item['advice_id']}` | "
            f"{item['agent_name']} | "
            f"{item['advice_type']} | "
            f"{item['status']} | "
            f"{_markdown_cell(item['summary'])} |"
        )

    if snapshot["paper_bundles"]:
        lines.extend(
            [
                "",
                "## Paper Bundles",
                "",
                "| run_id | source/model | signals | fills | recommendation | blockers |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for report in snapshot["paper_bundles"]:
            lines.append(
                "| "
                f"`{report['run_id']}` | "
                f"{report['source'] or 'unknown'} / {report['model_version'] or 'unknown'} | "
                f"{report['signal_rows']} | "
                f"{report['fills']} | "
                f"{report['recommendation']} | "
                f"{_join_or_none(report['review_blockers'])} |"
            )

    if snapshot["testnet_bundles"]:
        lines.extend(
            [
                "",
                "## Testnet Bundles",
                "",
                "| run_id | clean | heartbeats | alerts | fills | pnl | recommendation | blockers |",
                "|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for report in snapshot["testnet_bundles"]:
            lines.append(
                "| "
                f"`{report['run_id']}` | "
                f"{str(report['clean_for_retro']).lower()} | "
                f"{report['heartbeat_count']} | "
                f"{report['alert_count']} | "
                f"{report['fills']} | "
                f"{report['realized_pnl_total']:.8g} | "
                f"{report['recommendation']} | "
                f"{_join_or_none(report['review_blockers'])} |"
            )

    return "\n".join(lines)


def _project_status_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "last_updated": None,
            "current_phase": None,
            "current_objective": None,
            "live_trading_blocked": True,
            "strict_continuity": None,
            "sections": {
                "immediate_focus": [],
                "next_steps": [],
                "blocked_deferred": [],
                "latest_verification": [],
            },
        }

    text = path.read_text(encoding="utf-8")
    fields = {
        _normalize_status_key(match.group("key")): match.group("value").strip()
        for match in _STATUS_FIELD_RE.finditer(text)
    }
    lowered = text.lower()
    return {
        "path": str(path),
        "exists": True,
        "last_updated": fields.get("last_updated"),
        "current_phase": fields.get("current_phase"),
        "current_objective": fields.get("current_objective"),
        "live_trading_blocked": (
            "no live trading" in lowered
            or "live trading still blocked" in lowered
        ),
        "strict_continuity": _strict_streak(text),
        "sections": {
            "immediate_focus": _current_focus_items(text),
            "next_steps": _numbered_section_items(text, "Next Steps"),
            "blocked_deferred": _bullet_section_items(text, "Blocked / Deferred"),
            "latest_verification": _latest_verification_items(text),
        },
    }


def _agent_advice_snapshot(path: Path, *, limit: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "db_path": str(path),
        "db_exists": path.exists(),
        "total": 0,
        "by_status": {},
        "by_type": {},
        "by_agent": {},
        "latest": [],
    }
    if not path.exists():
        return base

    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            base["total"] = int(
                conn.execute("SELECT COUNT(*) AS count FROM agent_advice").fetchone()[
                    "count"
                ]
            )
            base["by_status"] = _count_rows(
                conn,
                "SELECT status AS key, COUNT(*) AS count FROM agent_advice GROUP BY status",
            )
            base["by_type"] = _count_rows(
                conn,
                "SELECT advice_type AS key, COUNT(*) AS count FROM agent_advice GROUP BY advice_type",
            )
            base["by_agent"] = _count_rows(
                conn,
                "SELECT agent_name AS key, COUNT(*) AS count FROM agent_advice GROUP BY agent_name",
            )
            latest = conn.execute(
                """
                SELECT
                    advice_id,
                    agent_name,
                    created_at_ns,
                    advice_type,
                    summary,
                    confidence,
                    status,
                    review_decision
                FROM agent_advice
                ORDER BY created_at_ns DESC, advice_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        base["error"] = str(exc)
        return base

    base["latest"] = [
        {
            "advice_id": row["advice_id"],
            "agent_name": row["agent_name"],
            "created_at_ns": int(row["created_at_ns"]),
            "advice_type": row["advice_type"],
            "summary": row["summary"],
            "confidence": float(row["confidence"]),
            "status": row["status"],
            "review_decision": row["review_decision"],
        }
        for row in latest
    ]
    return base


def _compact_paper_report(report: Any) -> dict[str, Any]:
    return {
        "bundle_dir": report.bundle_dir,
        "run_id": report.run_id,
        "kind": report.kind,
        "git_dirty": report.git_dirty,
        "source": report.source,
        "model_version": report.model_version,
        "signal_rows": report.signal_rows,
        "accepted_signals": report.accepted_signals,
        "fills": int(report.totals["fills"]),
        "positions": int(report.totals["positions"]),
        "pnl_total_by_currency": report.pnl_total_by_currency,
        "max_drawdown_pct_by_currency": report.max_drawdown_pct_by_currency,
        "eligible_for_review": report.eligible_for_review,
        "review_blockers": report.review_blockers,
        "promotion_blockers": report.promotion_blockers,
        "recommendation": report.recommendation,
    }


def _compact_testnet_report(report: Any) -> dict[str, Any]:
    return {
        "bundle_dir": report.bundle_dir,
        "run_id": report.run_id,
        "kind": report.kind,
        "git_dirty": report.git_dirty,
        "source": report.source,
        "model_version": report.model_version,
        "clean_for_retro": report.clean_for_retro,
        "elapsed_seconds": report.elapsed_seconds,
        "heartbeat_count": report.heartbeat_count,
        "alert_count": report.alert_count,
        "orders": report.order_count,
        "fills": report.fill_count,
        "positions": report.position_count,
        "final_position_sides": report.final_position_sides,
        "realized_pnl_total": report.realized_pnl_total,
        "max_ws_reconnect_count": report.max_ws_reconnect_count,
        "max_exchange_error_count": report.max_exchange_error_count,
        "review_blockers": report.review_blockers,
        "recommendation": report.recommendation,
    }


def _ops_status_snapshot(
    *,
    project_status: dict[str, Any],
    boundaries: dict[str, bool],
    agent_advice: dict[str, Any],
    paper_bundles: list[dict[str, Any]],
    testnet_bundles: list[dict[str, Any]],
) -> dict[str, Any]:
    boundary_open_count = sum(1 for value in boundaries.values() if value)
    paper_blockers = sum(len(bundle.get("review_blockers") or []) for bundle in paper_bundles)
    testnet_blockers = sum(
        len(bundle.get("review_blockers") or []) for bundle in testnet_bundles
    )
    promotion_blockers = sum(
        len(bundle.get("promotion_blockers") or []) for bundle in paper_bundles
    )
    recorded_advice = int(agent_advice.get("by_status", {}).get("recorded", 0))
    live_blocked = bool(project_status.get("live_trading_blocked", True))
    strict_continuity = project_status.get("strict_continuity")

    if boundary_open_count:
        state = "breach"
        headline = "A dashboard or agent boundary is open."
    elif paper_blockers or testnet_blockers or promotion_blockers:
        state = "attention"
        headline = "Review blockers exist in attached evidence."
    elif not live_blocked:
        state = "attention"
        headline = "Live gate state is not explicitly blocked."
    else:
        state = "guarded"
        headline = "Read-only operations are guarded; live trading remains blocked."

    return {
        "state": state,
        "headline": headline,
        "live_gate": "blocked" if live_blocked else "unknown",
        "strict_continuity": strict_continuity,
        "counts": {
            "boundary_open_count": boundary_open_count,
            "recorded_advice": recorded_advice,
            "paper_bundle_count": len(paper_bundles),
            "testnet_bundle_count": len(testnet_bundles),
            "paper_review_blockers": paper_blockers,
            "paper_promotion_blockers": promotion_blockers,
            "testnet_review_blockers": testnet_blockers,
        },
        "summary": _ops_summary_lines(
            live_blocked=live_blocked,
            boundary_open_count=boundary_open_count,
            strict_continuity=strict_continuity,
            recorded_advice=recorded_advice,
            paper_blockers=paper_blockers,
            testnet_blockers=testnet_blockers,
            promotion_blockers=promotion_blockers,
        ),
    }


def _ops_summary_lines(
    *,
    live_blocked: bool,
    boundary_open_count: int,
    strict_continuity: str | None,
    recorded_advice: int,
    paper_blockers: int,
    testnet_blockers: int,
    promotion_blockers: int,
) -> list[str]:
    lines = [
        "Live trading is blocked by ADR gates."
        if live_blocked
        else "Live trading gate is not explicitly blocked in project status.",
        (
            "All dashboard/agent mutation boundaries are closed."
            if boundary_open_count == 0
            else f"{boundary_open_count} dashboard/agent boundary flags are open."
        ),
    ]
    if strict_continuity:
        lines.append(f"Strict testnet continuity remains {strict_continuity}.")
    if recorded_advice:
        lines.append(f"{recorded_advice} AgentAdvice rows still await human review.")
    if paper_blockers or testnet_blockers or promotion_blockers:
        lines.append(
            "Attached evidence has blockers: "
            f"paper_review={paper_blockers}, "
            f"paper_promotion={promotion_blockers}, "
            f"testnet_review={testnet_blockers}."
        )
    return lines


def _operator_checklist(
    *,
    project_status: dict[str, Any],
    boundaries: dict[str, bool],
    agent_advice: dict[str, Any],
    ops_status: dict[str, Any],
) -> list[dict[str, str]]:
    boundary_open_count = int(ops_status["counts"]["boundary_open_count"])
    recorded_advice = int(agent_advice.get("by_status", {}).get("recorded", 0))
    strict_continuity = project_status.get("strict_continuity") or "unknown"
    return [
        {
            "label": "Refresh dashboard snapshot",
            "status": "manual",
            "detail": "Run apps.ops.dashboard_snapshot before operational review.",
        },
        {
            "label": "Keep trading mutations closed",
            "status": "ok" if boundary_open_count == 0 and not any(boundaries.values()) else "breach",
            "detail": "Frontend must not expose order, SignalEvent, SourcePolicy, or exchange writes.",
        },
        {
            "label": "Review AgentAdvice queue",
            "status": "warn" if recorded_advice else "ok",
            "detail": (
                f"{recorded_advice} recorded rows need review."
                if recorded_advice
                else "No recorded AgentAdvice rows in the snapshot."
            ),
        },
        {
            "label": "Respect paused continuity",
            "status": "blocked",
            "detail": f"Strict continuity is {strict_continuity}; do not claim live readiness.",
        },
        {
            "label": "Use promotion review for policy changes",
            "status": "manual",
            "detail": "SourcePolicy changes must go through promotion_review, not the dashboard.",
        },
    ]


def _count_rows(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {
        str(row["key"]): int(row["count"])
        for row in conn.execute(sql).fetchall()
        if row["key"] is not None
    }


def _normalize_status_key(value: str) -> str:
    return value.lower().replace(" ", "_")


def _strict_streak(text: str) -> str | None:
    match = _STRICT_STREAK_RE.search(text)
    return match.group("value") if match else None


def _current_focus_items(text: str) -> list[str]:
    block = _heading_block(text, "Current Focus")
    if not block:
        return []
    after_label = block.split("Immediate focus:", maxsplit=1)[-1]
    return _numbered_items(after_label)


def _numbered_section_items(text: str, heading: str) -> list[str]:
    return _numbered_items(_heading_block(text, heading))


def _bullet_section_items(text: str, heading: str) -> list[str]:
    return _bullet_items(_heading_block(text, heading))


def _latest_verification_items(text: str, *, limit: int = 8) -> list[str]:
    block = _heading_block(text, "Latest Verification")
    items = _bullet_items(block)
    return items[:limit]


def _heading_block(text: str, heading: str) -> str:
    heading_re = re.compile(
        _HEADING_RE_TEMPLATE.format(heading=re.escape(heading)),
        re.MULTILINE,
    )
    match = heading_re.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _numbered_items(text: str) -> list[str]:
    return [
        _strip_markdown(match.group("value"))
        for line in text.splitlines()
        if (match := _NUMBERED_ITEM_RE.match(line.strip()))
    ]


def _bullet_items(text: str) -> list[str]:
    return [
        _strip_markdown(match.group("value"))
        for line in text.splitlines()
        if (match := _BULLET_ITEM_RE.match(line.strip()))
    ]


def _strip_markdown(value: str) -> str:
    return re.sub(r"\*\*|`", "", value).strip()


def _join_or_none(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard-snapshot",
        description="Emit a read-only Phase 5 operations dashboard snapshot.",
    )
    parser.add_argument(
        "--project-status-path",
        default=str(DEFAULT_PROJECT_STATUS_PATH),
    )
    parser.add_argument(
        "--agent-advice-db",
        default=str(DEFAULT_ADVICE_DB_PATH),
    )
    parser.add_argument("--paper-bundle", action="append", default=[])
    parser.add_argument("--testnet-bundle", action="append", default=[])
    parser.add_argument("--advice-limit", type=int, default=20)
    parser.add_argument("--markdown", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    snapshot = build_dashboard_snapshot(
        project_status_path=Path(args.project_status_path),
        agent_advice_db_path=Path(args.agent_advice_db),
        paper_bundle_dirs=tuple(Path(path) for path in args.paper_bundle),
        testnet_bundle_dirs=tuple(Path(path) for path in args.testnet_bundle),
        advice_limit=args.advice_limit,
    )
    if args.markdown:
        sys.stdout.write(render_markdown_snapshot(snapshot) + "\n")
    else:
        sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SNAPSHOT_SCHEMA_VERSION",
    "build_dashboard_snapshot",
    "render_markdown_snapshot",
]

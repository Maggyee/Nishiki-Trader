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

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at_ns": time.time_ns() if generated_at_ns is None else generated_at_ns,
        "boundaries": {
            "live_path_allowed": False,
            "signal_event_write_allowed": False,
            "source_policy_mutation_allowed": False,
            "exchange_api_access_allowed": False,
        },
        "project_status": _project_status_snapshot(project_status_path),
        "agent_advice": _agent_advice_snapshot(agent_advice_db_path, limit=advice_limit),
        "paper_bundles": [
            _compact_paper_report(load_paper_bundle_report(path))
            for path in paper_bundle_dirs
        ],
        "testnet_bundles": [
            _compact_testnet_report(load_testnet_bundle_report(path))
            for path in testnet_bundle_dirs
        ],
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
        "## AgentAdvice",
        "",
        f"- db_exists: {str(advice['db_exists']).lower()}",
        f"- total: {advice['total']}",
        f"- by_status: `{json.dumps(advice['by_status'], sort_keys=True)}`",
        f"- by_type: `{json.dumps(advice['by_type'], sort_keys=True)}`",
        "",
        "| created_at_ns | advice_id | agent | type | status | summary |",
        "|---:|---|---|---|---|---|",
    ]
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


def _count_rows(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {
        str(row["key"]): int(row["count"])
        for row in conn.execute(sql).fetchall()
        if row["key"] is not None
    }


def _normalize_status_key(value: str) -> str:
    return value.lower().replace(" ", "_")


def _join_or_none(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard-snapshot",
        description="Emit a read-only Phase 4 dashboard snapshot.",
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

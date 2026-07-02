from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from apps.agents.store import DEFAULT_ADVICE_DB_PATH
from apps.strategies_nautilus.runners.report_paper_bundle import (
    load_paper_bundle_report,
)
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    load_testnet_bundle_report,
)

DEFAULT_PROJECT_STATUS_PATH = Path("docs/project-status.md")
DEFAULT_GRAFANA_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_OBSERVABILITY_TEXTFILE_DIR = Path("data/observability/textfile")
DEFAULT_OBSERVABILITY_STALE_AFTER_SECONDS = 120.0
DEFAULT_SNAPSHOT_WARNING_AFTER_SECONDS = 15 * 60.0
DEFAULT_SNAPSHOT_STALE_AFTER_SECONDS = 60 * 60.0
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
_PROM_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NaN|\+Inf|-Inf)\s*$"
)
_PROM_LABEL_RE = re.compile(r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"\\])*)"')
_SOURCE_REFERENCE_LINKS = (
    {
        "group": "docs",
        "label": "Project status",
        "kind": "status",
        "path": "docs/project-status.md",
        "detail": "Current phase, focus, blockers, next steps, and verification.",
    },
    {
        "group": "docs",
        "label": "Phase 5 dashboard ADR",
        "kind": "adr",
        "path": "docs/decisions/012-phase5-readonly-dashboard.md",
        "detail": "Read-only frontend boundary and verification standard.",
    },
    {
        "group": "docs",
        "label": "AgentAdvice audit ADR",
        "kind": "adr",
        "path": "docs/decisions/009-agent-advice-audit.md",
        "detail": "Agent output audit store and no-order-path boundary.",
    },
    {
        "group": "evidence",
        "label": "Testnet canary evidence",
        "kind": "progress",
        "path": "docs/progress/phase-3-testnet-canary-evidence.md",
        "detail": "Clean and non-clean Phase 3 canary evidence ledger.",
    },
    {
        "group": "evidence",
        "label": "Paused continuity plan",
        "kind": "progress",
        "path": "docs/progress/phase-3-testnet-continuity-plan.md",
        "detail": "Paused 14-day strict-continuity procedure and resume command.",
    },
    {
        "group": "ops",
        "label": "First testnet canary runbook",
        "kind": "runbook",
        "path": "docs/runbook-first-testnet-canary.md",
        "detail": "Operator steps for controlled testnet canary evidence collection.",
    },
    {
        "group": "docs",
        "label": "Phase 6 live-risk ADR",
        "kind": "adr",
        "path": "docs/decisions/013-phase6-live-risk-gate.md",
        "detail": "Passive live-readiness and startup-refusal gate requirements.",
    },
    {
        "group": "ops",
        "label": "First live day runbook",
        "kind": "runbook",
        "path": "docs/runbook-first-live-day.md",
        "detail": "Draft first live day checklist and manual fallback boundary.",
    },
)
_GRAFANA_REFERENCE_LINKS = (
    {
        "group": "grafana",
        "label": "Signals overview",
        "kind": "dashboard",
        "grafana_path": "/d/signals-overview/signals-overview",
        "path": "infra/grafana/dashboards/signals-overview.json",
        "detail": "Read-only signal distribution dashboard backed by provisioned Grafana.",
    },
    {
        "group": "grafana",
        "label": "Current testnet canary",
        "kind": "dashboard",
        "grafana_path": "/d/canary-current/canary-current",
        "path": "infra/grafana/dashboards/canary-current.json",
        "detail": "Read-only heartbeat, alert, and runtime panels for the active canary.",
    },
)


def build_dashboard_snapshot(
    *,
    project_status_path: Path = DEFAULT_PROJECT_STATUS_PATH,
    agent_advice_db_path: Path = DEFAULT_ADVICE_DB_PATH,
    paper_bundle_dirs: Sequence[Path] = (),
    testnet_bundle_dirs: Sequence[Path] = (),
    phase6_live_readiness_report_path: Path | None = None,
    phase6_live_startup_guard_report_path: Path | None = None,
    advice_limit: int = 20,
    grafana_base_url: str | None = DEFAULT_GRAFANA_BASE_URL,
    repo_browser_base_url: str | None = None,
    observability_textfile_dir: Path | None = DEFAULT_OBSERVABILITY_TEXTFILE_DIR,
    observability_limit: int = 5,
    snapshot_warning_after_seconds: float = DEFAULT_SNAPSHOT_WARNING_AFTER_SECONDS,
    snapshot_stale_after_seconds: float = DEFAULT_SNAPSHOT_STALE_AFTER_SECONDS,
    generated_at_ns: int | None = None,
) -> dict[str, Any]:
    if advice_limit <= 0:
        raise ValueError("advice_limit must be positive")
    if observability_limit <= 0:
        raise ValueError("observability_limit must be positive")
    _validate_snapshot_freshness_thresholds(
        warning_after_seconds=snapshot_warning_after_seconds,
        stale_after_seconds=snapshot_stale_after_seconds,
    )

    generated_ns = time.time_ns() if generated_at_ns is None else generated_at_ns
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
    signal_summary = _signal_summary_snapshot(
        paper_bundles=paper_bundles,
        testnet_bundles=testnet_bundles,
        generated_at_ns=generated_ns,
        grafana_base_url=grafana_base_url,
        repo_browser_base_url=repo_browser_base_url,
    )
    ops_status = _ops_status_snapshot(
        project_status=project_status,
        boundaries=boundaries,
        agent_advice=agent_advice,
        paper_bundles=paper_bundles,
        testnet_bundles=testnet_bundles,
    )
    phase6 = _phase6_snapshot(
        live_readiness_report_path=phase6_live_readiness_report_path,
        live_startup_guard_report_path=phase6_live_startup_guard_report_path,
    )
    snapshot_inputs = _snapshot_inputs(
        project_status_path=project_status_path,
        agent_advice_db_path=agent_advice_db_path,
        paper_bundle_dirs=paper_bundle_dirs,
        testnet_bundle_dirs=testnet_bundle_dirs,
        phase6_live_readiness_report_path=phase6_live_readiness_report_path,
        phase6_live_startup_guard_report_path=phase6_live_startup_guard_report_path,
        observability_textfile_dir=observability_textfile_dir,
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at_ns": generated_ns,
        "snapshot_freshness": _snapshot_freshness_policy(
            generated_ns,
            warning_after_seconds=snapshot_warning_after_seconds,
            stale_after_seconds=snapshot_stale_after_seconds,
        ),
        "snapshot_inputs": snapshot_inputs,
        "boundaries": boundaries,
        "project_status": project_status,
        "agent_advice": agent_advice,
        "paper_bundles": paper_bundles,
        "testnet_bundles": testnet_bundles,
        "signal_summary": signal_summary,
        "phase6": phase6,
        "ops_status": ops_status,
        "observability": _observability_snapshot(
            observability_textfile_dir,
            generated_at_ns=generated_ns,
            limit=observability_limit,
        ),
        "reference_links": _reference_links(
            grafana_base_url=grafana_base_url,
            repo_browser_base_url=repo_browser_base_url,
        ),
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
        "- snapshot_stale_after_seconds: "
        f"`{snapshot.get('snapshot_freshness', {}).get('stale_after_seconds', 'unknown')}`",
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
    ]
    phase6 = snapshot.get("phase6") or {}
    lines.extend(["", "## Phase 6 Gates", ""])
    for report in phase6.get("reports", []):
        lines.append(
            "- "
            f"{report.get('label')}: "
            f"status=`{report.get('status')}`, "
            f"blockers={_join_or_none(report.get('blockers') or [])}, "
            f"path=`{report.get('path') or 'not attached'}`"
        )
        for item in report.get("evidence") or []:
            lines.append(
                "  - evidence: "
                f"{item.get('label')} status=`{item.get('status')}`, "
                f"sha256=`{item.get('sha256') or item.get('expected_sha256') or 'none'}`"
            )

    lines.extend(["", "## Operator Next Steps", ""])
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

    snapshot_inputs = snapshot.get("snapshot_inputs") or {}
    input_items = snapshot_inputs.get("items") or []
    if input_items:
        lines.extend(
            [
                "",
                "## Snapshot Inputs",
                "",
                "| label | category | attached | exists | path |",
                "|---|---|---:|---:|---|",
            ]
        )
        for item in input_items:
            lines.append(
                "| "
                f"{_markdown_cell(str(item.get('label') or 'unknown'))} | "
                f"`{_markdown_cell(str(item.get('category') or 'unknown'))}` | "
                f"{_format_optional_bool(item.get('attached'))} | "
                f"{_format_optional_bool(item.get('exists'))} | "
                f"`{_markdown_cell(str(item.get('path') or 'n/a'))}` |"
            )

    observability = snapshot.get("observability") or {}
    if observability:
        lines.extend(
            [
                "",
                "## Observability Textfiles",
                "",
                f"- textfile_dir: `{observability.get('textfile_dir') or 'disabled'}`",
                f"- exists: {str(observability.get('exists')).lower()}",
                f"- file_count: {observability.get('file_count', 0)}",
                "",
                "| run_id | state | heartbeat_age_s | ws | open orders | open positions | alerts | data_lag_s |",
                "|---|---|---:|---|---:|---:|---:|---:|",
            ]
        )
        for run in observability.get("runs", []):
            data_lag = run.get("last_bar_age_seconds")
            lines.append(
                "| "
                f"`{run.get('run_id') or 'unknown'}` | "
                f"{run.get('state') or 'unknown'} | "
                f"{_format_optional_float(run.get('heartbeat_age_seconds'))} | "
                f"{_format_optional_bool(run.get('ws_connected'))} | "
                f"{_format_optional_int(run.get('open_orders'))} | "
                f"{_format_optional_int(run.get('open_positions'))} | "
                f"{_format_optional_int(run.get('alert_total'))} | "
                f"{_format_optional_float(data_lag)} |"
            )

    signal_summary = snapshot.get("signal_summary") or {}
    if signal_summary:
        freshness = signal_summary.get("freshness") or {}
        lines.extend(
            [
                "",
                "## Signal Summary",
                "",
                f"- bundle_count: {signal_summary.get('bundle_count', 0)}",
                f"- signal_rows: {signal_summary.get('signal_rows', 0)}",
                f"- accepted_signals: {signal_summary.get('accepted_signals', 0)}",
                f"- skipped_signals: {signal_summary.get('skipped_signals', 0)}",
                f"- rejection_signals: {signal_summary.get('rejection_signals', 0)}",
                "- latest_signal_age_seconds: "
                f"{_format_optional_float(freshness.get('latest_signal_age_seconds'))}",
                "",
                "| kind | run_id | source/model | signals | accepted | skipped | rejections | latest age s | top rejection reasons |",
                "|---|---|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for run in signal_summary.get("runs", []):
            source_model = (
                f"{run.get('source') or 'unknown'} / "
                f"{run.get('model_version') or 'unknown'}"
            )
            lines.append(
                "| "
                f"{run.get('kind') or 'unknown'} | "
                f"`{run.get('run_id') or 'unknown'}` | "
                f"{_markdown_cell(source_model)} | "
                f"{_format_optional_int(run.get('signal_rows'))} | "
                f"{_format_optional_int(run.get('accepted_signals'))} | "
                f"{_format_optional_int(run.get('skipped_signals'))} | "
                f"{_format_optional_int(run.get('rejection_signals'))} | "
                f"{_format_optional_float(run.get('latest_signal_age_seconds'))} | "
                f"{_join_reason_counts(run.get('top_rejection_reasons') or [])} |"
            )

    reference_links = snapshot.get("reference_links") or []
    if reference_links:
        lines.extend(
            [
                "",
                "## Reference Links",
                "",
                "| group | label | target | source path |",
                "|---|---|---|---|",
            ]
        )
        for link in reference_links:
            href = link.get("href")
            label = _markdown_cell(str(link.get("label") or "unknown"))
            target = f"[{label}]({href})" if href else "local path only"
            lines.append(
                "| "
                f"{_markdown_cell(str(link.get('group') or 'unknown'))} | "
                f"{label} | "
                f"{target} | "
                f"`{_markdown_cell(str(link.get('path') or ''))}` |"
            )

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


def _validate_snapshot_freshness_thresholds(
    *,
    warning_after_seconds: float,
    stale_after_seconds: float,
) -> None:
    if warning_after_seconds <= 0:
        raise ValueError("snapshot_warning_after_seconds must be positive")
    if stale_after_seconds <= 0:
        raise ValueError("snapshot_stale_after_seconds must be positive")
    if stale_after_seconds <= warning_after_seconds:
        raise ValueError(
            "snapshot_stale_after_seconds must be greater than "
            "snapshot_warning_after_seconds"
        )


def _snapshot_freshness_policy(
    generated_at_ns: int,
    *,
    warning_after_seconds: float,
    stale_after_seconds: float,
) -> dict[str, Any]:
    return {
        "generated_at_ns": generated_at_ns,
        "state_at_generation": "fresh",
        "warning_after_seconds": float(warning_after_seconds),
        "stale_after_seconds": float(stale_after_seconds),
        "evaluated_by": "dashboard_reader",
    }


def _snapshot_inputs(
    *,
    project_status_path: Path,
    agent_advice_db_path: Path,
    paper_bundle_dirs: Sequence[Path],
    testnet_bundle_dirs: Sequence[Path],
    phase6_live_readiness_report_path: Path | None,
    phase6_live_startup_guard_report_path: Path | None,
    observability_textfile_dir: Path | None,
) -> dict[str, Any]:
    items = [
        _input_item(
            label="Project status",
            category="project_status",
            kind="file",
            path=project_status_path,
            required=True,
            attached=True,
        ),
        _input_item(
            label="AgentAdvice database",
            category="agent_advice",
            kind="sqlite",
            path=agent_advice_db_path,
            required=False,
            attached=True,
        ),
        *[
            _input_item(
                label=f"Paper bundle {index}",
                category="paper_bundle",
                kind="directory",
                path=path,
                required=False,
                attached=True,
            )
            for index, path in enumerate(paper_bundle_dirs, start=1)
        ],
        *[
            _input_item(
                label=f"Testnet bundle {index}",
                category="testnet_bundle",
                kind="directory",
                path=path,
                required=False,
                attached=True,
            )
            for index, path in enumerate(testnet_bundle_dirs, start=1)
        ],
        _input_item(
            label="Phase 6 live readiness report",
            category="phase6_live_readiness",
            kind="json",
            path=phase6_live_readiness_report_path,
            required=False,
            attached=phase6_live_readiness_report_path is not None,
        ),
        _input_item(
            label="Phase 6 live startup guard report",
            category="phase6_live_startup_guard",
            kind="json",
            path=phase6_live_startup_guard_report_path,
            required=False,
            attached=phase6_live_startup_guard_report_path is not None,
        ),
        _input_item(
            label="Observability textfile directory",
            category="observability_textfiles",
            kind="directory",
            path=observability_textfile_dir,
            required=False,
            attached=observability_textfile_dir is not None,
        ),
    ]
    attached_items = [item for item in items if item["attached"]]
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "attached": len(attached_items),
            "existing": sum(1 for item in attached_items if item["exists"]),
            "missing_attached": sum(
                1 for item in attached_items if not item["exists"]
            ),
            "required_missing": sum(
                1 for item in items if item["required"] and not item["exists"]
            ),
        },
        "boundaries": {
            "reads_only": True,
            "loads_exchange_credentials": False,
            "starts_runtime": False,
            "writes_signal_event": False,
            "mutates_source_policy": False,
            "places_orders": False,
        },
    }


def _input_item(
    *,
    label: str,
    category: str,
    kind: str,
    path: Path | None,
    required: bool,
    attached: bool,
) -> dict[str, Any]:
    return {
        "label": label,
        "category": category,
        "kind": kind,
        "path": str(path) if path is not None else None,
        "required": required,
        "attached": attached,
        "exists": bool(path.exists()) if path is not None else False,
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
        "first_signal_ts_event_ns": getattr(report, "first_signal_ts_event_ns", None),
        "last_signal_ts_event_ns": getattr(report, "last_signal_ts_event_ns", None),
        "accepted_signals": report.accepted_signals,
        "skipped_signals": report.skipped_signals,
        "dry_run_signals": report.dry_run_signals,
        "expired_signals": report.expired_signals,
        "unauthorized_signals": report.unauthorized_signals,
        "signal_lag_signals": report.signal_lag_signals,
        "kill_switch_signals": report.kill_switch_signals,
        "data_gap_signals": report.data_gap_signals,
        "decision_counts": report.decision_counts,
        "reason_counts": report.reason_counts,
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
        "lineage_rows": report.lineage_rows,
        "first_signal_ts_event_ns": getattr(report, "first_signal_ts_event_ns", None),
        "last_signal_ts_event_ns": getattr(report, "last_signal_ts_event_ns", None),
        "accepted_signals": _accepted_signal_count(
            signal_rows=report.lineage_rows,
            decision_counts=report.decision_counts,
        ),
        "skipped_signals": int(report.decision_counts.get("skip", 0)),
        "lineage_rows_with_order_ids": report.lineage_rows_with_order_ids,
        "lineage_rows_with_fill_ids": report.lineage_rows_with_fill_ids,
        "lineage_rows_with_position_id": report.lineage_rows_with_position_id,
        "decision_counts": report.decision_counts,
        "reason_counts": report.reason_counts,
        "final_position_sides": report.final_position_sides,
        "realized_pnl_total": report.realized_pnl_total,
        "max_ws_reconnect_count": report.max_ws_reconnect_count,
        "max_exchange_error_count": report.max_exchange_error_count,
        "review_blockers": report.review_blockers,
        "recommendation": report.recommendation,
    }


def _signal_summary_snapshot(
    *,
    paper_bundles: Sequence[dict[str, Any]],
    testnet_bundles: Sequence[dict[str, Any]],
    generated_at_ns: int,
    grafana_base_url: str | None,
    repo_browser_base_url: str | None,
) -> dict[str, Any]:
    runs = [
        _signal_run_summary(bundle, generated_at_ns=generated_at_ns)
        for bundle in (*paper_bundles, *testnet_bundles)
    ]
    source_model: dict[tuple[str, str], dict[str, Any]] = {}
    reason_counts: dict[str, int] = {}
    by_kind: dict[str, dict[str, int]] = {}

    for run in runs:
        key = (
            str(run.get("source") or "unknown"),
            str(run.get("model_version") or "unknown"),
        )
        source_row = source_model.setdefault(
            key,
            {
                "source": key[0],
                "model_version": key[1],
                "bundle_count": 0,
                "signal_rows": 0,
                "accepted_signals": 0,
                "skipped_signals": 0,
                "rejection_signals": 0,
                "kinds": {},
                "first_signal_ts_event_ns": None,
                "last_signal_ts_event_ns": None,
                "latest_signal_age_seconds": None,
                "latest_signal_run_id": None,
                "latest_signal_kind": None,
                "top_rejection_reasons": [],
                "evidence_links": [],
            },
        )
        kind = str(run.get("kind") or "unknown")
        first_ts = _optional_int(run.get("first_signal_ts_event_ns"))
        last_ts = _optional_int(run.get("last_signal_ts_event_ns"))
        source_row["bundle_count"] += 1
        source_row["signal_rows"] += int(run.get("signal_rows") or 0)
        source_row["accepted_signals"] += int(run.get("accepted_signals") or 0)
        source_row["skipped_signals"] += int(run.get("skipped_signals") or 0)
        source_row["rejection_signals"] += int(run.get("rejection_signals") or 0)
        source_row["kinds"][kind] = int(source_row["kinds"].get(kind, 0)) + 1
        source_row["first_signal_ts_event_ns"] = _min_optional_int(
            _optional_int(source_row.get("first_signal_ts_event_ns")),
            first_ts,
        )
        current_last = _optional_int(source_row.get("last_signal_ts_event_ns"))
        source_row["last_signal_ts_event_ns"] = _max_optional_int(
            current_last,
            last_ts,
        )
        if last_ts is not None and (current_last is None or last_ts > current_last):
            source_row["latest_signal_run_id"] = run.get("run_id")
            source_row["latest_signal_kind"] = run.get("kind")

        kind_row = by_kind.setdefault(
            kind,
            {
                "bundle_count": 0,
                "signal_rows": 0,
                "accepted_signals": 0,
                "skipped_signals": 0,
                "rejection_signals": 0,
            },
        )
        kind_row["bundle_count"] += 1
        kind_row["signal_rows"] += int(run.get("signal_rows") or 0)
        kind_row["accepted_signals"] += int(run.get("accepted_signals") or 0)
        kind_row["skipped_signals"] += int(run.get("skipped_signals") or 0)
        kind_row["rejection_signals"] += int(run.get("rejection_signals") or 0)

        for reason, count in (run.get("rejection_reason_counts") or {}).items():
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + int(count)

    for row in source_model.values():
        source_reasons: dict[str, int] = {}
        matching_runs = []
        for run in runs:
            if run.get("source") != row["source"]:
                continue
            if run.get("model_version") != row["model_version"]:
                continue
            matching_runs.append(run)
            for reason, count in (run.get("rejection_reason_counts") or {}).items():
                source_reasons[str(reason)] = source_reasons.get(str(reason), 0) + int(count)
        row["top_rejection_reasons"] = _top_reason_counts(source_reasons)
        row["latest_signal_age_seconds"] = _signal_age_seconds(
            generated_at_ns,
            _optional_int(row.get("last_signal_ts_event_ns")),
        )
        row["evidence_links"] = _signal_source_evidence_links(
            row,
            matching_runs,
            grafana_base_url=grafana_base_url,
            repo_browser_base_url=repo_browser_base_url,
        )

    return {
        "bundle_count": len(runs),
        "signal_rows": sum(int(run.get("signal_rows") or 0) for run in runs),
        "accepted_signals": sum(int(run.get("accepted_signals") or 0) for run in runs),
        "skipped_signals": sum(int(run.get("skipped_signals") or 0) for run in runs),
        "rejection_signals": sum(int(run.get("rejection_signals") or 0) for run in runs),
        "freshness": _latest_signal_freshness(runs),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_source_model": sorted(
            source_model.values(),
            key=lambda item: (
                -int(item.get("signal_rows") or 0),
                str(item.get("source") or ""),
                str(item.get("model_version") or ""),
            ),
        ),
        "runs": runs,
    }


def _signal_run_summary(
    bundle: dict[str, Any],
    *,
    generated_at_ns: int,
) -> dict[str, Any]:
    decision_counts = {
        str(key): int(value)
        for key, value in (bundle.get("decision_counts") or {}).items()
    }
    reason_counts = {
        str(key): int(value)
        for key, value in (bundle.get("reason_counts") or {}).items()
    }
    signal_rows = int(bundle.get("signal_rows") or bundle.get("lineage_rows") or 0)
    accepted = int(
        bundle.get("accepted_signals")
        if bundle.get("accepted_signals") is not None
        else _accepted_signal_count(
            signal_rows=signal_rows,
            decision_counts=decision_counts,
        )
    )
    skipped = int(
        bundle.get("skipped_signals")
        if bundle.get("skipped_signals") is not None
        else decision_counts.get("skip", 0)
    )
    rejection_reason_counts = _rejection_reason_counts(reason_counts)
    first_signal_ts_event_ns = _optional_int(bundle.get("first_signal_ts_event_ns"))
    last_signal_ts_event_ns = _optional_int(bundle.get("last_signal_ts_event_ns"))
    return {
        "kind": bundle.get("kind"),
        "run_id": bundle.get("run_id"),
        "bundle_dir": bundle.get("bundle_dir"),
        "source": bundle.get("source"),
        "model_version": bundle.get("model_version"),
        "first_signal_ts_event_ns": first_signal_ts_event_ns,
        "last_signal_ts_event_ns": last_signal_ts_event_ns,
        "latest_signal_age_seconds": _signal_age_seconds(
            generated_at_ns,
            last_signal_ts_event_ns,
        ),
        "signal_rows": signal_rows,
        "accepted_signals": accepted,
        "skipped_signals": skipped,
        "rejection_signals": sum(rejection_reason_counts.values()),
        "decision_counts": decision_counts,
        "rejection_reason_counts": rejection_reason_counts,
        "top_rejection_reasons": _top_reason_counts(rejection_reason_counts),
    }


def _signal_source_evidence_links(
    row: dict[str, Any],
    runs: Sequence[dict[str, Any]],
    *,
    grafana_base_url: str | None,
    repo_browser_base_url: str | None,
) -> list[dict[str, str | None]]:
    links: list[dict[str, str | None]] = []
    source = str(row.get("source") or "")
    model_version = str(row.get("model_version") or "")
    grafana_base = _optional_base_url(grafana_base_url)
    if grafana_base and source:
        params = [f"var-source={quote(source, safe='')}"]
        if model_version:
            params.append(f"var-model_version={quote(model_version, safe='')}")
        first_ts = _optional_int(row.get("first_signal_ts_event_ns"))
        last_ts = _optional_int(row.get("last_signal_ts_event_ns"))
        if first_ts is not None and last_ts is not None:
            params.extend(
                [
                    f"from={max(0, first_ts - 3_600_000_000_000) // 1_000_000}",
                    f"to={(last_ts + 3_600_000_000_000) // 1_000_000}",
                ]
            )
        links.append(
            {
                "group": "grafana",
                "label": "Signals overview",
                "kind": "dashboard",
                "path": "infra/grafana/dashboards/signals-overview.json",
                "detail": (
                    "Read-only Grafana source/model drill-down for this "
                    "source/model row."
                ),
                "href": f"{grafana_base}/d/signals-overview/signals-overview?{'&'.join(params)}",
            }
        )

    seen_bundle_dirs: set[str] = set()
    sorted_runs = sorted(
        runs,
        key=lambda run: _optional_int(run.get("last_signal_ts_event_ns")) or -1,
        reverse=True,
    )
    for run in sorted_runs:
        bundle_dir = run.get("bundle_dir")
        if not bundle_dir:
            continue
        bundle_path = str(bundle_dir)
        if bundle_path in seen_bundle_dirs:
            continue
        seen_bundle_dirs.add(bundle_path)
        kind = str(run.get("kind") or "bundle")
        run_id = str(run.get("run_id") or "unknown")
        links.append(
            {
                "group": "evidence",
                "label": f"{kind} bundle {run_id}",
                "kind": "bundle",
                "path": bundle_path,
                "detail": "Attached passive bundle source for this source/model row.",
                "href": None,
            }
        )
        if len(seen_bundle_dirs) >= 2:
            break

    if any(run.get("kind") == "testnet" for run in runs):
        repo_base = _optional_base_url(repo_browser_base_url)
        path = "docs/progress/phase-3-testnet-canary-evidence.md"
        links.append(
            {
                "group": "evidence",
                "label": "Testnet canary evidence",
                "kind": "progress",
                "path": path,
                "detail": "Clean and non-clean Phase 3 canary evidence ledger.",
                "href": f"{repo_base}/{path}" if repo_base else None,
            }
        )
    return links


def _latest_signal_freshness(runs: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_ts: int | None = None
    for run in runs:
        run_ts = _optional_int(run.get("last_signal_ts_event_ns"))
        if run_ts is None:
            continue
        if latest_ts is None or run_ts > latest_ts:
            latest = run
            latest_ts = run_ts
    if latest is None or latest_ts is None:
        return None
    return {
        "latest_signal_ts_event_ns": latest_ts,
        "latest_signal_age_seconds": latest.get("latest_signal_age_seconds"),
        "latest_signal_run_id": latest.get("run_id"),
        "latest_signal_kind": latest.get("kind"),
        "latest_signal_source": latest.get("source"),
        "latest_signal_model_version": latest.get("model_version"),
    }


def _signal_age_seconds(generated_at_ns: int, ts_event_ns: int | None) -> float | None:
    if ts_event_ns is None:
        return None
    return _age_seconds(generated_at_ns / 1_000_000_000, ts_event_ns / 1_000_000_000)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _min_optional_int(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _max_optional_int(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _accepted_signal_count(
    *,
    signal_rows: int,
    decision_counts: dict[str, int],
) -> int:
    return max(signal_rows - int(decision_counts.get("skip", 0)), 0)


def _rejection_reason_counts(reason_counts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for reason, count in reason_counts.items():
        category = _rejection_reason_category(reason)
        if category is None:
            continue
        out[category] = out.get(category, 0) + int(count)
    return dict(sorted(out.items()))


def _rejection_reason_category(reason: str) -> str | None:
    if reason.startswith("expired:"):
        return "expired"
    if reason.startswith("reject_unauthorized"):
        return "unauthorized"
    if reason.startswith("reject_low_confidence"):
        return "low_confidence"
    if reason.startswith("reject_"):
        return "reject_other"
    if reason.startswith("signal_lag"):
        return "signal_lag"
    if reason.startswith("kill_switch"):
        return "kill_switch"
    if reason.startswith("data_gap"):
        return "data_gap"
    return None


def _top_reason_counts(reason_counts: dict[str, int], *, limit: int = 3) -> list[dict[str, int | str]]:
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            reason_counts.items(),
            key=lambda item: (-int(item[1]), str(item[0])),
        )[:limit]
    ]


def _observability_snapshot(
    textfile_dir: Path | None,
    *,
    generated_at_ns: int,
    limit: int,
) -> dict[str, Any]:
    if textfile_dir is None:
        return {
            "textfile_dir": None,
            "exists": False,
            "file_count": 0,
            "stale_after_seconds": DEFAULT_OBSERVABILITY_STALE_AFTER_SECONDS,
            "counts": _observability_counts([]),
            "latest": None,
            "runs": [],
        }

    if not textfile_dir.exists():
        return {
            "textfile_dir": str(textfile_dir),
            "exists": False,
            "file_count": 0,
            "stale_after_seconds": DEFAULT_OBSERVABILITY_STALE_AFTER_SECONDS,
            "counts": _observability_counts([]),
            "latest": None,
            "runs": [],
        }

    paths = sorted(path for path in textfile_dir.glob("*.prom") if path.is_file())
    runs = [
        _textfile_run_snapshot(path, generated_at_ns=generated_at_ns)
        for path in paths
    ]
    runs.sort(
        key=lambda run: (
            run.get("heartbeat_timestamp_seconds") or 0.0,
            run.get("file_mtime_ns") or 0,
        ),
        reverse=True,
    )
    limited = runs[:limit]
    return {
        "textfile_dir": str(textfile_dir),
        "exists": True,
        "file_count": len(paths),
        "stale_after_seconds": DEFAULT_OBSERVABILITY_STALE_AFTER_SECONDS,
        "counts": _observability_counts(runs),
        "latest": limited[0] if limited else None,
        "runs": limited,
    }


def _textfile_run_snapshot(path: Path, *, generated_at_ns: int) -> dict[str, Any]:
    metrics, parse_errors = _parse_prometheus_textfile(path)
    heartbeat_ts = _metric_value(metrics, "trader_canary_heartbeat_timestamp_seconds")
    last_bar_ts = _metric_value(metrics, "trader_canary_last_bar_timestamp_seconds")
    last_signal_ts = _metric_value(metrics, "trader_canary_last_signal_timestamp_seconds")
    labels = (
        _metric_labels(metrics, "trader_canary_info")
        or _metric_labels(metrics, "trader_canary_heartbeat_timestamp_seconds")
        or {}
    )
    fallback_kind, fallback_run_id = _kind_run_from_prom_filename(path)
    ws_connected_value = _metric_value(metrics, "trader_canary_ws_connected")
    alerts = _alert_counts(metrics)
    generated_seconds = generated_at_ns / 1_000_000_000

    heartbeat_age = _age_seconds(generated_seconds, heartbeat_ts)
    last_bar_age = _age_seconds(generated_seconds, last_bar_ts)
    last_signal_age = _age_seconds(generated_seconds, last_signal_ts)
    state, reason = _observability_run_state(
        heartbeat_age_seconds=heartbeat_age,
        ws_connected=_bool_metric(ws_connected_value),
        alert_total=sum(alerts.values()),
        parse_errors=parse_errors,
    )

    return {
        "path": str(path),
        "file_mtime_ns": path.stat().st_mtime_ns,
        "kind": labels.get("kind") or fallback_kind,
        "run_id": labels.get("run_id") or fallback_run_id,
        "state": state,
        "state_reason": reason,
        "parse_errors": parse_errors[:3],
        "heartbeat_timestamp_seconds": heartbeat_ts,
        "heartbeat_age_seconds": heartbeat_age,
        "ws_connected": _bool_metric(ws_connected_value),
        "ws_reconnect_total": _optional_int_metric(
            _metric_value(metrics, "trader_canary_ws_reconnect_total")
        ),
        "exchange_error_total": _optional_int_metric(
            _metric_value(metrics, "trader_canary_exchange_error_total")
        ),
        "open_orders": _optional_int_metric(
            _metric_value(metrics, "trader_canary_open_orders")
        ),
        "open_positions": _optional_int_metric(
            _metric_value(metrics, "trader_canary_open_positions")
        ),
        "daily_pnl_usdt": _metric_value(metrics, "trader_canary_daily_pnl_usdt"),
        "account_total_usdt": _metric_value(metrics, "trader_canary_account_total_usdt"),
        "last_bar_timestamp_seconds": last_bar_ts,
        "last_bar_age_seconds": last_bar_age,
        "last_signal_timestamp_seconds": last_signal_ts,
        "last_signal_age_seconds": last_signal_age,
        "alert_total": sum(alerts.values()),
        "alerts_by_kind": alerts,
    }


def _parse_prometheus_textfile(
    path: Path,
) -> tuple[dict[str, list[tuple[dict[str, str], float]]], list[str]]:
    metrics: dict[str, list[tuple[dict[str, str], float]]] = {}
    parse_errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {}, [f"read_failed:{exc.__class__.__name__}"]

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _PROM_SAMPLE_RE.match(stripped)
        if not match:
            parse_errors.append(f"line_{lineno}:unparseable")
            continue
        value = _parse_prom_float(match.group("value"))
        if value is None:
            parse_errors.append(f"line_{lineno}:non_finite")
            continue
        labels = _parse_prom_labels(match.group("labels") or "")
        metrics.setdefault(match.group("name"), []).append((labels, value))
    return metrics, parse_errors


def _parse_prom_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_prom_labels(value: str) -> dict[str, str]:
    return {
        match.group("key"): _unescape_prom_label(match.group("value"))
        for match in _PROM_LABEL_RE.finditer(value)
    }


def _unescape_prom_label(value: str) -> str:
    return (
        value.replace(r"\n", "\n")
        .replace(r"\"", '"')
        .replace(r"\\", "\\")
    )


def _metric_value(
    metrics: dict[str, list[tuple[dict[str, str], float]]],
    name: str,
) -> float | None:
    values = metrics.get(name) or []
    return values[0][1] if values else None


def _metric_labels(
    metrics: dict[str, list[tuple[dict[str, str], float]]],
    name: str,
) -> dict[str, str] | None:
    values = metrics.get(name) or []
    return values[0][0] if values else None


def _alert_counts(
    metrics: dict[str, list[tuple[dict[str, str], float]]],
) -> dict[str, int]:
    alerts: dict[str, int] = {}
    for labels, value in metrics.get("trader_canary_alert_total") or []:
        alert = labels.get("alert") or "unknown"
        alerts[alert] = alerts.get(alert, 0) + int(value)
    return alerts


def _kind_run_from_prom_filename(path: Path) -> tuple[str | None, str | None]:
    kind, sep, run_id = path.stem.partition("-")
    return (kind or None, run_id or None) if sep else (None, path.stem or None)


def _age_seconds(generated_seconds: float, timestamp_seconds: float | None) -> float | None:
    if timestamp_seconds is None:
        return None
    return max(0.0, generated_seconds - timestamp_seconds)


def _bool_metric(value: float | None) -> bool | None:
    if value is None:
        return None
    return value >= 0.5


def _optional_int_metric(value: float | None) -> int | None:
    return None if value is None else int(value)


def _observability_run_state(
    *,
    heartbeat_age_seconds: float | None,
    ws_connected: bool | None,
    alert_total: int,
    parse_errors: Sequence[str],
) -> tuple[str, str]:
    if parse_errors:
        return "attention", "parse_errors_present"
    if heartbeat_age_seconds is None:
        return "unknown", "heartbeat_missing"
    if heartbeat_age_seconds > DEFAULT_OBSERVABILITY_STALE_AFTER_SECONDS:
        return "stale", "heartbeat_age_exceeds_threshold"
    if ws_connected is False:
        return "disconnected", "ws_disconnected"
    if alert_total > 0:
        return "attention", "alerts_present"
    return "healthy", "latest_sample_within_threshold"


def _observability_counts(runs: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "run_count": len(runs),
        "connected_count": sum(1 for run in runs if run.get("ws_connected") is True),
        "stale_count": sum(1 for run in runs if run.get("state") == "stale"),
        "attention_count": sum(
            1
            for run in runs
            if run.get("state") in {"attention", "disconnected", "unknown"}
        ),
        "open_orders": sum(int(run.get("open_orders") or 0) for run in runs),
        "open_positions": sum(int(run.get("open_positions") or 0) for run in runs),
        "alert_total": sum(int(run.get("alert_total") or 0) for run in runs),
        "parse_error_count": sum(len(run.get("parse_errors") or []) for run in runs),
    }


def _phase6_snapshot(
    *,
    live_readiness_report_path: Path | None,
    live_startup_guard_report_path: Path | None,
) -> dict[str, Any]:
    readiness = _phase6_report_snapshot(
        label="Live readiness",
        path=live_readiness_report_path,
        expected_schema="phase6.live_readiness.v1",
        gate_field="readiness_gate_met",
        authorization_field="live_trading_allowed",
    )
    startup_guard = _phase6_report_snapshot(
        label="Live startup guard",
        path=live_startup_guard_report_path,
        expected_schema="phase6.live_startup_guard.v1",
        gate_field="startup_allowed",
        authorization_field="live_trading_authorized",
    )
    reports = [readiness, startup_guard]
    blocker_count = sum(len(report.get("blockers") or []) for report in reports)
    missing_count = sum(1 for report in reports if report.get("status") == "missing")
    invalid_count = sum(1 for report in reports if report.get("status") == "invalid")
    passed_count = sum(1 for report in reports if report.get("status") == "ok")
    return {
        "state": "review" if passed_count == len(reports) else "blocked",
        "reports": reports,
        "counts": {
            "attached_report_count": sum(1 for report in reports if report.get("attached")),
            "passed_report_count": passed_count,
            "missing_report_count": missing_count,
            "invalid_report_count": invalid_count,
            "blocker_count": blocker_count,
        },
        "summary": _phase6_summary_lines(reports),
        "boundaries": {
            "loads_exchange_credentials": False,
            "starts_runtime": False,
            "mutates_source_policy": False,
            "writes_signal_event": False,
            "places_orders": False,
            "authorizes_live_trading": False,
        },
    }


def _phase6_report_snapshot(
    *,
    label: str,
    path: Path | None,
    expected_schema: str,
    gate_field: str,
    authorization_field: str,
) -> dict[str, Any]:
    if path is None:
        return {
            "label": label,
            "path": None,
            "attached": False,
            "exists": False,
            "schema_version": None,
            "status": "missing",
            "gate_field": gate_field,
            "gate_met": False,
            "authorization_field": authorization_field,
            "authorizes_live_trading": False,
            "source": None,
            "model_version": None,
            "recommendation": None,
            "blockers": [f"{gate_field}_report_not_attached"],
            "checks": [],
            "evidence": [],
        }
    if not path.exists():
        return {
            "label": label,
            "path": str(path),
            "attached": True,
            "exists": False,
            "schema_version": None,
            "status": "missing",
            "gate_field": gate_field,
            "gate_met": False,
            "authorization_field": authorization_field,
            "authorizes_live_trading": False,
            "source": None,
            "model_version": None,
            "recommendation": None,
            "blockers": [f"{gate_field}_report_not_found"],
            "checks": [],
            "evidence": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "label": label,
            "path": str(path),
            "attached": True,
            "exists": True,
            "schema_version": None,
            "status": "invalid",
            "gate_field": gate_field,
            "gate_met": False,
            "authorization_field": authorization_field,
            "authorizes_live_trading": False,
            "source": None,
            "model_version": None,
            "recommendation": None,
            "blockers": [f"invalid_json:{exc.__class__.__name__}"],
            "checks": [],
            "evidence": [],
        }

    blockers = [str(item) for item in payload.get("blockers") or []]
    schema_version = payload.get("schema_version")
    gate_met = payload.get(gate_field) is True
    authorizes_live_trading = payload.get(authorization_field) is True
    raw_checks = payload.get("checks")
    checks = _compact_phase6_checks(raw_checks or [])
    evidence = _phase6_report_evidence(payload=payload, expected_schema=expected_schema)
    if schema_version != expected_schema:
        blockers.append(f"unexpected_schema_version:{schema_version}")
    if authorizes_live_trading:
        blockers.append(f"{authorization_field}_must_remain_false")
    if gate_met:
        blockers.extend(_phase6_check_blockers(raw_checks))
        blockers.extend(
            f"evidence:{item['label']}"
            for item in evidence
            if item.get("status") != "ok"
        )
    status = "ok" if gate_met and not blockers else "blocked"
    return {
        "label": label,
        "path": str(path),
        "attached": True,
        "exists": True,
        "schema_version": schema_version,
        "status": status,
        "gate_field": gate_field,
        "gate_met": gate_met,
        "authorization_field": authorization_field,
        "authorizes_live_trading": authorizes_live_trading,
        "source": payload.get("source"),
        "model_version": payload.get("model_version"),
        "recommendation": payload.get("recommendation"),
        "blockers": sorted(dict.fromkeys(blockers)),
        "checks": checks,
        "evidence": evidence,
    }


def _phase6_report_evidence(
    *,
    payload: dict[str, Any],
    expected_schema: str,
) -> list[dict[str, str | None]]:
    if expected_schema == "phase6.live_readiness.v1":
        return [
            _artifact_evidence_item(
                payload.get("project_status"),
                label="Project status artifact",
            ),
            _artifact_evidence_item(
                payload.get("live_risk_adr"),
                label="Readiness live-risk ADR artifact",
            ),
            _continuity_artifacts_evidence_item(
                payload.get("continuity_artifacts"),
                label="Continuity bundle artifacts",
            ),
            _promotion_review_evidence_item(
                payload.get("live_promotion_review"),
                label="Promotion review artifact",
            )
        ]
    if expected_schema != "phase6.live_startup_guard.v1":
        return []

    evidence = payload.get("evidence") if isinstance(payload, dict) else None
    evidence = evidence if isinstance(evidence, dict) else {}
    live_risk_adr_gate = evidence.get("live_risk_adr")
    readiness_gate = evidence.get("live_readiness_report")
    readiness_gate = readiness_gate if isinstance(readiness_gate, dict) else {}
    startup_promotion_gate = evidence.get("live_promotion_review")
    first_live_day_runbook_gate = evidence.get("first_live_day_runbook")
    readiness_promotion_gate = readiness_gate.get("live_promotion_review")
    readiness_promotion_gate = (
        readiness_promotion_gate if isinstance(readiness_promotion_gate, dict) else {}
    )
    readiness_sha = _optional_str(readiness_promotion_gate.get("sha256"))
    expected_sha = _optional_str(
        readiness_gate.get("expected_live_promotion_review_sha256")
    )
    sha_matches = bool(readiness_sha and expected_sha and readiness_sha == expected_sha)
    return [
        _accepted_artifact_evidence_item(
            live_risk_adr_gate,
            label="Live-risk ADR artifact",
        ),
        _artifact_evidence_item(
            readiness_gate,
            label="Readiness report artifact",
        ),
        _readiness_live_risk_adr_match_item(readiness_gate),
        _startup_continuity_artifact_verification_item(readiness_gate),
        _promotion_review_evidence_item(
            startup_promotion_gate,
            label="Startup promotion review artifact",
        ),
        {
            "label": "Readiness promotion SHA-256 match",
            "status": "ok" if sha_matches else "blocked",
            "detail": (
                "Readiness report and startup artifact fingerprints match."
                if sha_matches
                else "Readiness report fingerprint does not match the startup artifact."
            ),
            "path": None,
            "sha256": readiness_sha,
            "expected_sha256": expected_sha,
        },
        _accepted_artifact_evidence_item(
            first_live_day_runbook_gate,
            label="First live day runbook artifact",
        ),
        _readiness_freshness_evidence_item(readiness_gate),
        _readiness_git_evidence_item(readiness_gate),
        _readiness_project_status_match_item(readiness_gate),
    ]


def _artifact_evidence_item(
    gate: Any,
    *,
    label: str,
) -> dict[str, str | None]:
    if not isinstance(gate, dict):
        return {
            "label": label,
            "status": "missing",
            "detail": "Artifact evidence is not recorded in this report.",
            "path": None,
            "sha256": None,
        }
    sha256 = _optional_str(gate.get("sha256"))
    path = _optional_str(gate.get("path"))
    status = "ok" if sha256 else "blocked"
    return {
        "label": label,
        "status": status,
        "detail": (
            "Artifact fingerprint is recorded."
            if status == "ok"
            else "Artifact fingerprint is not recorded."
        ),
        "path": path,
        "sha256": sha256,
    }


def _accepted_artifact_evidence_item(
    gate: Any,
    *,
    label: str,
) -> dict[str, str | None]:
    if not isinstance(gate, dict):
        return {
            "label": label,
            "status": "missing",
            "detail": "Artifact evidence is not recorded in this report.",
            "path": None,
            "sha256": None,
        }
    sha256 = _optional_str(gate.get("sha256"))
    path = _optional_str(gate.get("path"))
    accepted = gate.get("accepted") is True
    blocker = _optional_str(gate.get("blocker"))
    document_status = _optional_str(gate.get("status"))
    status = "ok" if accepted and sha256 else "blocked"
    if status == "ok":
        detail = "Artifact is accepted and fingerprinted."
    elif not sha256:
        detail = "Artifact fingerprint is not recorded."
    else:
        detail = blocker or (
            f"Artifact status is {document_status}."
            if document_status
            else "Artifact is not accepted."
        )
    return {
        "label": label,
        "status": status,
        "detail": detail,
        "path": path,
        "sha256": sha256,
    }


def _continuity_artifacts_evidence_item(
    artifacts: Any,
    *,
    label: str,
) -> dict[str, str | None]:
    if not isinstance(artifacts, list) or not artifacts:
        return {
            "label": label,
            "status": "missing",
            "detail": "Continuity bundle artifact fingerprints are not recorded.",
            "path": None,
            "sha256": None,
        }
    missing = [
        item
        for item in artifacts
        if not isinstance(item, dict) or not _optional_str(item.get("sha256"))
    ]
    first_path = next(
        (
            _optional_str(item.get("manifest_path"))
            for item in artifacts
            if isinstance(item, dict) and item.get("manifest_path")
        ),
        None,
    )
    status = "ok" if not missing else "blocked"
    return {
        "label": label,
        "status": status,
        "detail": (
            f"{len(artifacts)} continuity bundle manifest fingerprints recorded."
            if status == "ok"
            else "One or more continuity bundle fingerprints are missing."
        ),
        "path": first_path,
        "sha256": _optional_str(artifacts[0].get("sha256"))
        if isinstance(artifacts[0], dict)
        else None,
    }


def _readiness_live_risk_adr_match_item(
    readiness_gate: Any,
) -> dict[str, str | None]:
    if not isinstance(readiness_gate, dict):
        return {
            "label": "Readiness live-risk ADR SHA-256 match",
            "status": "missing",
            "detail": "Readiness report gate evidence is not recorded.",
            "path": None,
            "sha256": None,
            "expected_sha256": None,
        }

    live_risk_adr = readiness_gate.get("live_risk_adr")
    live_risk_adr = live_risk_adr if isinstance(live_risk_adr, dict) else {}
    readiness_sha = _optional_str(live_risk_adr.get("sha256"))
    expected_sha = _optional_str(readiness_gate.get("expected_live_risk_adr_sha256"))
    sha_matches = bool(readiness_sha and expected_sha and readiness_sha == expected_sha)
    return {
        "label": "Readiness live-risk ADR SHA-256 match",
        "status": "ok" if sha_matches else "blocked",
        "detail": (
            "Readiness report and startup ADR artifact fingerprints match."
            if sha_matches
            else "Readiness report ADR fingerprint does not match the startup artifact."
        ),
        "path": _optional_str(live_risk_adr.get("path")),
        "sha256": readiness_sha,
        "expected_sha256": expected_sha,
    }


def _startup_continuity_artifact_verification_item(
    readiness_gate: Any,
) -> dict[str, str | None]:
    if not isinstance(readiness_gate, dict):
        return {
            "label": "Startup continuity artifact verification",
            "status": "missing",
            "detail": "Readiness report gate evidence is not recorded.",
            "path": None,
            "sha256": None,
        }

    artifacts = readiness_gate.get("continuity_artifacts")
    problems = readiness_gate.get("continuity_artifact_problems")
    first_path = None
    first_sha256 = None
    if isinstance(artifacts, list):
        first_path = next(
            (
                _optional_str(item.get("manifest_path"))
                for item in artifacts
                if isinstance(item, dict) and item.get("manifest_path")
            ),
            None,
        )
        first_sha256 = (
            _optional_str(artifacts[0].get("sha256"))
            if artifacts and isinstance(artifacts[0], dict)
            else None
        )
    if not isinstance(problems, list):
        return {
            "label": "Startup continuity artifact verification",
            "status": "missing",
            "detail": "Startup guard did not record continuity artifact verification.",
            "path": first_path,
            "sha256": first_sha256,
        }
    if problems:
        return {
            "label": "Startup continuity artifact verification",
            "status": "blocked",
            "detail": "Startup guard reported: " + _join_or_none(problems),
            "path": first_path,
            "sha256": first_sha256,
        }
    if not isinstance(artifacts, list) or not artifacts:
        return {
            "label": "Startup continuity artifact verification",
            "status": "blocked",
            "detail": "Startup guard did not record continuity artifact inputs.",
            "path": None,
            "sha256": None,
        }
    return {
        "label": "Startup continuity artifact verification",
        "status": "ok",
        "detail": f"{len(artifacts)} continuity bundle manifest bytes verified.",
        "path": first_path,
        "sha256": first_sha256,
    }


def _readiness_freshness_evidence_item(
    readiness_gate: Any,
) -> dict[str, str | None]:
    if not isinstance(readiness_gate, dict):
        return {
            "label": "Readiness freshness window",
            "status": "missing",
            "detail": "Readiness report gate evidence is not recorded.",
            "path": None,
            "sha256": None,
        }

    freshness = readiness_gate.get("freshness")
    if not isinstance(freshness, dict):
        return {
            "label": "Readiness freshness window",
            "status": "missing",
            "detail": "Startup guard did not record readiness freshness evidence.",
            "path": _optional_str(readiness_gate.get("path")),
            "sha256": _optional_str(readiness_gate.get("sha256")),
        }

    problems = freshness.get("problems")
    problems = problems if isinstance(problems, list) else []
    fresh = freshness.get("fresh") is True and not problems
    age = _optional_str(freshness.get("age_seconds"))
    max_age = _optional_str(freshness.get("max_age_seconds"))
    return {
        "label": "Readiness freshness window",
        "status": "ok" if fresh else "blocked",
        "detail": (
            f"Readiness report age {age}s is within max {max_age}s."
            if fresh
            else "Startup guard reported: " + _join_or_none(problems)
        ),
        "path": _optional_str(readiness_gate.get("path")),
        "sha256": _optional_str(readiness_gate.get("sha256")),
    }


def _readiness_git_evidence_item(
    readiness_gate: Any,
) -> dict[str, str | None]:
    if not isinstance(readiness_gate, dict):
        return {
            "label": "Readiness git commit match",
            "status": "missing",
            "detail": "Readiness report gate evidence is not recorded.",
            "path": None,
            "sha256": None,
        }

    readiness_git = readiness_gate.get("readiness_git")
    if not isinstance(readiness_git, dict):
        return {
            "label": "Readiness git commit match",
            "status": "missing",
            "detail": "Startup guard did not record readiness git evidence.",
            "path": _optional_str(readiness_gate.get("path")),
            "sha256": None,
        }

    readiness_commit = _optional_str(readiness_git.get("commit"))
    expected_commit = _optional_str(readiness_gate.get("expected_git_commit"))
    readiness_dirty = readiness_git.get("dirty")
    if readiness_dirty is not False:
        return {
            "label": "Readiness git commit match",
            "status": "blocked",
            "detail": "Readiness report git evidence is dirty.",
            "path": _optional_str(readiness_gate.get("path")),
            "sha256": None,
        }
    if not readiness_commit or not expected_commit:
        return {
            "label": "Readiness git commit match",
            "status": "blocked",
            "detail": "Startup guard did not record both git commits.",
            "path": _optional_str(readiness_gate.get("path")),
            "sha256": None,
        }
    if readiness_commit != expected_commit:
        return {
            "label": "Readiness git commit match",
            "status": "blocked",
            "detail": "Readiness report git commit does not match startup preflight.",
            "path": _optional_str(readiness_gate.get("path")),
            "sha256": None,
        }
    return {
        "label": "Readiness git commit match",
        "status": "ok",
        "detail": "Readiness report git commit matches startup preflight and is clean.",
        "path": _optional_str(readiness_gate.get("path")),
        "sha256": None,
    }


def _readiness_project_status_match_item(
    readiness_gate: Any,
) -> dict[str, str | None]:
    label = "Readiness project-status SHA-256 match"
    if not isinstance(readiness_gate, dict):
        return {
            "label": label,
            "status": "missing",
            "detail": "Readiness report gate evidence is not recorded.",
            "path": None,
            "sha256": None,
            "expected_sha256": None,
        }

    project_status = readiness_gate.get("project_status")
    project_status = project_status if isinstance(project_status, dict) else {}
    readiness_sha = _optional_str(project_status.get("sha256"))
    expected_sha = _optional_str(
        readiness_gate.get("expected_project_status_sha256")
    )
    sha_matches = bool(readiness_sha and expected_sha and readiness_sha == expected_sha)
    return {
        "label": label,
        "status": "ok" if sha_matches else "blocked",
        "detail": (
            "Readiness report and startup project-status artifact fingerprints match."
            if sha_matches
            else "Readiness report project-status fingerprint does not match the startup artifact."
        ),
        "path": _optional_str(project_status.get("path")),
        "sha256": readiness_sha,
        "expected_sha256": expected_sha,
    }


def _promotion_review_evidence_item(
    gate: Any,
    *,
    label: str,
) -> dict[str, str | None]:
    if not isinstance(gate, dict):
        return {
            "label": label,
            "status": "missing",
            "detail": "Promotion review evidence is not recorded in this artifact.",
            "path": None,
            "sha256": None,
        }
    accepted = gate.get("accepted") is True
    sha256 = _optional_str(gate.get("sha256"))
    path = _optional_str(gate.get("path"))
    blocker = _optional_str(gate.get("blocker"))
    status = "ok" if accepted and sha256 else "blocked"
    return {
        "label": label,
        "status": status,
        "detail": (
            "Promotion review artifact is accepted and fingerprinted."
            if status == "ok"
            else blocker or "Promotion review artifact is missing its fingerprint."
        ),
        "path": path,
        "sha256": sha256,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _compact_phase6_checks(checks: Sequence[Any]) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        compact.append(
            {
                "name": str(check.get("name") or "unknown"),
                "status": str(check.get("status") or "unknown"),
                "detail": str(check.get("detail") or ""),
            }
        )
    return compact[:8]


def _phase6_check_blockers(checks: Any) -> list[str]:
    if not isinstance(checks, list):
        return []
    blockers: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "unknown")
        if status == "ok":
            continue
        blockers.append(f"check:{check.get('name') or 'unknown'}")
    return blockers


def _phase6_summary_lines(reports: Sequence[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for report in reports:
        status = str(report.get("status") or "unknown")
        label = str(report.get("label") or "Phase 6 report")
        blockers = report.get("blockers") or []
        if status == "ok":
            lines.append(f"{label} artifact passes its passive gate.")
        elif status == "missing":
            if report.get("attached"):
                lines.append(f"{label} artifact path is missing.")
            else:
                lines.append(f"{label} artifact is not attached.")
        elif status == "invalid":
            lines.append(f"{label} artifact is invalid.")
        else:
            lines.append(f"{label} remains blocked: {_join_or_none(blockers)}.")
    return lines


def _reference_links(
    *,
    grafana_base_url: str | None,
    repo_browser_base_url: str | None,
) -> list[dict[str, str | None]]:
    repo_base = _optional_base_url(repo_browser_base_url)
    links: list[dict[str, str | None]] = []
    for item in _SOURCE_REFERENCE_LINKS:
        path = item["path"]
        links.append(
            {
                **item,
                "href": f"{repo_base}/{path}" if repo_base else None,
            }
        )

    grafana_base = _optional_base_url(grafana_base_url)
    for item in _GRAFANA_REFERENCE_LINKS:
        grafana_path = item["grafana_path"]
        links.append(
            {
                "group": item["group"],
                "label": item["label"],
                "kind": item["kind"],
                "path": item["path"],
                "detail": item["detail"],
                "href": f"{grafana_base}{grafana_path}" if grafana_base else None,
            }
        )
    return links


def _optional_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip().rstrip("/")
    return stripped or None


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


def _join_reason_counts(values: Sequence[dict[str, Any]]) -> str:
    if not values:
        return "none"
    return ", ".join(
        f"{_markdown_cell(str(value.get('reason') or 'unknown'))}={int(value.get('count') or 0)}"
        for value in values
    )


def _format_optional_float(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, float | int) else "n/a"


def _format_optional_int(value: Any) -> str:
    return str(value) if isinstance(value, int) else "n/a"


def _format_optional_bool(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return "n/a"


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
    parser.add_argument(
        "--phase6-live-readiness-report",
        default=None,
        help="Optional saved phase6.live_readiness.v1 JSON artifact to summarize.",
    )
    parser.add_argument(
        "--phase6-live-startup-guard-report",
        default=None,
        help="Optional saved phase6.live_startup_guard.v1 JSON artifact to summarize.",
    )
    parser.add_argument("--advice-limit", type=int, default=20)
    parser.add_argument(
        "--observability-textfile-dir",
        default=str(DEFAULT_OBSERVABILITY_TEXTFILE_DIR),
        help=(
            "Directory containing Prometheus textfile collector .prom files. "
            "Pass an empty string to disable this read-only summary."
        ),
    )
    parser.add_argument("--observability-limit", type=int, default=5)
    parser.add_argument(
        "--snapshot-warning-after-seconds",
        type=float,
        default=DEFAULT_SNAPSHOT_WARNING_AFTER_SECONDS,
        help="Snapshot age in seconds after which dashboard readers should show aging.",
    )
    parser.add_argument(
        "--snapshot-stale-after-seconds",
        type=float,
        default=DEFAULT_SNAPSHOT_STALE_AFTER_SECONDS,
        help="Snapshot age in seconds after which dashboard readers should show stale.",
    )
    parser.add_argument(
        "--grafana-base-url",
        default=DEFAULT_GRAFANA_BASE_URL,
        help=(
            "Base URL for read-only Grafana dashboard links. "
            "Pass an empty string to emit only local dashboard definition paths."
        ),
    )
    parser.add_argument(
        "--repo-browser-base-url",
        default=None,
        help=(
            "Optional repository browser base URL, for example "
            "https://github.com/Maggyee/Nishiki-Trader/blob/main."
        ),
    )
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
        phase6_live_readiness_report_path=(
            Path(args.phase6_live_readiness_report)
            if args.phase6_live_readiness_report
            else None
        ),
        phase6_live_startup_guard_report_path=(
            Path(args.phase6_live_startup_guard_report)
            if args.phase6_live_startup_guard_report
            else None
        ),
        advice_limit=args.advice_limit,
        grafana_base_url=args.grafana_base_url,
        repo_browser_base_url=args.repo_browser_base_url,
        observability_textfile_dir=(
            Path(args.observability_textfile_dir)
            if args.observability_textfile_dir
            else None
        ),
        observability_limit=args.observability_limit,
        snapshot_warning_after_seconds=args.snapshot_warning_after_seconds,
        snapshot_stale_after_seconds=args.snapshot_stale_after_seconds,
    )
    if args.markdown:
        sys.stdout.write(render_markdown_snapshot(snapshot) + "\n")
    else:
        sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_GRAFANA_BASE_URL",
    "DEFAULT_OBSERVABILITY_TEXTFILE_DIR",
    "SNAPSHOT_SCHEMA_VERSION",
    "build_dashboard_snapshot",
    "render_markdown_snapshot",
]

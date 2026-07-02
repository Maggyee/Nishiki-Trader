from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.agents.advice import AgentAdvice
from apps.agents.store import AgentAdviceStore
from apps.ops import dashboard_snapshot

REFERENCE_TS_NS = 1_778_760_000_000_000_000
PAPER_FIRST_SIGNAL_TS_NS = REFERENCE_TS_NS - 600_000_000_000
PAPER_LAST_SIGNAL_TS_NS = REFERENCE_TS_NS - 300_000_000_000
TESTNET_FIRST_SIGNAL_TS_NS = REFERENCE_TS_NS - 120_000_000_000
TESTNET_LAST_SIGNAL_TS_NS = REFERENCE_TS_NS - 60_000_000_000


def _write_status(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Project Status",
                "- **Last updated**: 2026-06-04 (snapshot test)",
                "- **Current phase**: Phase 4 entry (agent research foundation)",
                "- **Current objective**: Keep agent output out of the order path.",
                "",
                "Strict continuity remains current_qualified_streak_days=0/14.",
                "No live trading without a separate live-risk ADR.",
                "",
                "## Current Focus",
                "",
                "Immediate focus:",
                "",
                "1. Keep agents out of the order path.",
                "2. Review all recorded AgentAdvice rows.",
                "",
                "## Next Steps",
                "",
                "1. Expand the dashboard with read-only operations panels.",
                "2. Keep frontend mutations closed.",
                "",
                "## Blocked / Deferred",
                "",
                "- No live trading.",
                "- No frontend write actions.",
                "",
                "## Latest Verification",
                "",
                "On 2026-06-04, after snapshot test:",
                "",
                "- `pytest tests/ops/test_dashboard_snapshot.py` -> passed.",
            ]
        ),
        encoding="utf-8",
    )


def _advice(
    advice_id: str,
    *,
    created_at_ns: int,
    advice_type: str = "journal",
) -> AgentAdvice:
    return AgentAdvice(
        schema_version="agent.advice.v1",
        advice_id=advice_id,
        agent_name="review_agent",
        created_at_ns=created_at_ns,
        advice_type=advice_type,
        summary=f"{advice_type} summary",
        confidence=0.9,
        payload={"content": "read-only observation"},
        tags=("phase4",),
        source_refs=("docs/project-status.md",),
    )


def test_snapshot_reads_project_status_and_agent_advice(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    db = tmp_path / "advice.db"
    store = AgentAdviceStore(db)
    store.write(_advice("advice-1", created_at_ns=REFERENCE_TS_NS))
    store.write(
        _advice(
            "advice-2",
            created_at_ns=REFERENCE_TS_NS + 1,
            advice_type="project_review",
        )
    )
    store.review(
        "advice-1",
        "accepted",
        reviewed_by="nishiki",
        now_ns=REFERENCE_TS_NS + 2,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=db,
        advice_limit=10,
        generated_at_ns=REFERENCE_TS_NS + 3,
    )

    assert snapshot["schema_version"] == "dashboard.snapshot.v1"
    assert snapshot["generated_at_ns"] == REFERENCE_TS_NS + 3
    assert snapshot["snapshot_freshness"] == {
        "generated_at_ns": REFERENCE_TS_NS + 3,
        "state_at_generation": "fresh",
        "warning_after_seconds": 900.0,
        "stale_after_seconds": 3600.0,
        "evaluated_by": "dashboard_reader",
    }
    assert snapshot["snapshot_inputs"]["boundaries"] == {
        "reads_only": True,
        "loads_exchange_credentials": False,
        "starts_runtime": False,
        "writes_signal_event": False,
        "mutates_source_policy": False,
        "places_orders": False,
    }
    input_items = {
        item["category"]: item
        for item in snapshot["snapshot_inputs"]["items"]
        if item["category"] in {"project_status", "agent_advice"}
    }
    assert input_items["project_status"] == {
        "label": "Project status",
        "category": "project_status",
        "kind": "file",
        "path": str(status_path),
        "required": True,
        "attached": True,
        "exists": True,
    }
    assert input_items["agent_advice"] == {
        "label": "AgentAdvice database",
        "category": "agent_advice",
        "kind": "sqlite",
        "path": str(db),
        "required": False,
        "attached": True,
        "exists": True,
    }
    assert snapshot["boundaries"] == {
        "live_path_allowed": False,
        "signal_event_write_allowed": False,
        "source_policy_mutation_allowed": False,
        "exchange_api_access_allowed": False,
    }
    assert snapshot["project_status"]["path"] == str(status_path)
    assert snapshot["project_status"]["exists"] is True
    assert snapshot["project_status"]["last_updated"] == "2026-06-04 (snapshot test)"
    assert snapshot["project_status"]["current_phase"] == (
        "Phase 4 entry (agent research foundation)"
    )
    assert snapshot["project_status"]["current_objective"] == (
        "Keep agent output out of the order path."
    )
    assert snapshot["project_status"]["live_trading_blocked"] is True
    assert snapshot["project_status"]["strict_continuity"] == "0/14"
    assert snapshot["project_status"]["sections"]["next_steps"] == [
        "Expand the dashboard with read-only operations panels.",
        "Keep frontend mutations closed.",
    ]
    assert snapshot["project_status"]["sections"]["blocked_deferred"] == [
        "No live trading.",
        "No frontend write actions.",
    ]
    assert snapshot["project_status"]["sections"]["latest_verification"] == [
        "pytest tests/ops/test_dashboard_snapshot.py -> passed."
    ]
    assert snapshot["ops_status"]["state"] == "guarded"
    assert snapshot["ops_status"]["strict_continuity"] == "0/14"
    assert snapshot["operator_checklist"][1]["status"] == "ok"
    assert snapshot["agent_advice"]["total"] == 2
    assert snapshot["agent_advice"]["by_status"] == {"recorded": 1, "reviewed": 1}
    assert snapshot["agent_advice"]["by_type"] == {
        "journal": 1,
        "project_review": 1,
    }
    assert [item["advice_id"] for item in snapshot["agent_advice"]["latest"]] == [
        "advice-2",
        "advice-1",
    ]
    assert snapshot["agent_advice"]["latest"][1]["review_decision"] == "accepted"


def test_snapshot_freshness_thresholds_can_be_configured(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        snapshot_warning_after_seconds=30.5,
        snapshot_stale_after_seconds=120,
        generated_at_ns=REFERENCE_TS_NS,
    )
    markdown = dashboard_snapshot.render_markdown_snapshot(snapshot)

    assert snapshot["snapshot_freshness"] == {
        "generated_at_ns": REFERENCE_TS_NS,
        "state_at_generation": "fresh",
        "warning_after_seconds": 30.5,
        "stale_after_seconds": 120.0,
        "evaluated_by": "dashboard_reader",
    }
    assert "snapshot_stale_after_seconds: `120.0`" in markdown


@pytest.mark.parametrize(
    ("warning_after_seconds", "stale_after_seconds", "message"),
    [
        (0, 60, "snapshot_warning_after_seconds must be positive"),
        (60, 0, "snapshot_stale_after_seconds must be positive"),
        (60, 60, "snapshot_stale_after_seconds must be greater"),
        (90, 60, "snapshot_stale_after_seconds must be greater"),
    ],
)
def test_snapshot_freshness_thresholds_reject_invalid_values(
    tmp_path: Path,
    warning_after_seconds: float,
    stale_after_seconds: float,
    message: str,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    with pytest.raises(ValueError, match=message):
        dashboard_snapshot.build_dashboard_snapshot(
            project_status_path=status_path,
            agent_advice_db_path=tmp_path / "missing.db",
            snapshot_warning_after_seconds=warning_after_seconds,
            snapshot_stale_after_seconds=stale_after_seconds,
            generated_at_ns=REFERENCE_TS_NS,
        )


def test_snapshot_missing_advice_db_is_empty(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert snapshot["agent_advice"]["db_exists"] is False
    assert snapshot["agent_advice"]["total"] == 0
    assert snapshot["agent_advice"]["latest"] == []


def test_markdown_snapshot_renders_boundary_and_advice(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    db = tmp_path / "advice.db"
    AgentAdviceStore(db).write(_advice("advice-1", created_at_ns=REFERENCE_TS_NS))
    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=db,
        generated_at_ns=REFERENCE_TS_NS,
    )

    out = dashboard_snapshot.render_markdown_snapshot(snapshot)

    assert "# Dashboard Snapshot" in out
    assert "ops_state: `guarded`" in out
    assert "snapshot_stale_after_seconds: `3600.0`" in out
    assert "Expand the dashboard with read-only operations panels." in out
    assert "signal_event_write_allowed=false" in out
    assert "## Reference Links" in out
    assert "Signals overview" in out
    assert "`advice-1`" in out
    assert "## Phase 6 Gates" in out
    assert "Live readiness" in out


def test_snapshot_includes_source_neutral_reference_links(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        grafana_base_url="http://grafana.local",
        repo_browser_base_url="https://github.com/example/trader/blob/main/",
        generated_at_ns=REFERENCE_TS_NS,
    )

    links = {item["label"]: item for item in snapshot["reference_links"]}
    assert links["Project status"] == {
        "group": "docs",
        "label": "Project status",
        "kind": "status",
        "path": "docs/project-status.md",
        "detail": "Current phase, focus, blockers, next steps, and verification.",
        "href": "https://github.com/example/trader/blob/main/docs/project-status.md",
    }
    assert links["Signals overview"]["href"] == (
        "http://grafana.local/d/signals-overview/signals-overview"
    )
    assert links["Signals overview"]["path"] == (
        "infra/grafana/dashboards/signals-overview.json"
    )
    assert links["Current testnet canary"]["kind"] == "dashboard"
    assert links["Phase 6 live-risk ADR"]["href"] == (
        "https://github.com/example/trader/blob/main/"
        "docs/decisions/013-phase6-live-risk-gate.md"
    )
    assert links["First live day runbook"]["kind"] == "runbook"


def test_snapshot_can_emit_local_reference_paths_without_urls(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        grafana_base_url="",
        generated_at_ns=REFERENCE_TS_NS,
    )

    links = {item["label"]: item for item in snapshot["reference_links"]}
    assert links["Project status"]["href"] is None
    assert links["Signals overview"]["href"] is None
    assert links["Signals overview"]["path"] == (
        "infra/grafana/dashboards/signals-overview.json"
    )


def test_snapshot_summarizes_missing_phase6_reports_by_default(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        generated_at_ns=REFERENCE_TS_NS,
    )

    phase6 = snapshot["phase6"]
    assert phase6["state"] == "blocked"
    assert phase6["counts"] == {
        "attached_report_count": 0,
        "passed_report_count": 0,
        "missing_report_count": 2,
        "invalid_report_count": 0,
        "blocker_count": 2,
    }
    assert [report["status"] for report in phase6["reports"]] == [
        "missing",
        "missing",
    ]
    assert phase6["boundaries"]["authorizes_live_trading"] is False


def test_snapshot_summarizes_phase6_gate_artifacts(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    readiness_path = tmp_path / "live-readiness.json"
    guard_path = tmp_path / "live-startup-guard.json"
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "readiness_gate_met": False,
                "live_trading_allowed": False,
                "recommendation": "remain_blocked_before_phase6_live_canary",
                "blockers": ["live_risk_adr_not_accepted"],
                "project_status": {
                    "path": "docs/project-status.md",
                    "sha256": "e" * 64,
                },
                "live_risk_adr": {
                    "path": "docs/decisions/013-phase6-live-risk-gate.md",
                    "sha256": "f" * 64,
                    "accepted": False,
                },
                "continuity_artifacts": [
                    {
                        "bundle_dir": "data/testnet/run-1",
                        "manifest_path": "data/testnet/run-1/run_manifest.json",
                        "sha256": "g" * 64,
                    }
                ],
                "live_promotion_review": {
                    "accepted": False,
                    "blocker": "live_canary_promotion_review_required",
                    "path": None,
                },
                "checks": [
                    {
                        "name": "live_risk_adr",
                        "status": "blocked",
                        "detail": "ADR-013 is Draft.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": False,
                "live_trading_authorized": False,
                "recommendation": "refuse_live_startup",
                "blockers": ["first_live_day_runbook_not_accepted"],
                "evidence": {
                    "live_risk_adr": {
                        "path": "docs/decisions/013-phase6-live-risk-gate.md",
                        "sha256": "c" * 64,
                        "accepted": False,
                    },
                    "live_readiness_report": {
                        "path": str(readiness_path),
                        "sha256": "b" * 64,
                        "freshness": {
                            "fresh": True,
                            "problems": [],
                            "age_seconds": 60.0,
                            "max_age_seconds": 86400.0,
                        },
                        "readiness_git": {
                            "commit": "a" * 40,
                            "dirty": False,
                        },
                        "expected_git_commit": "a" * 40,
                        "expected_git_dirty": False,
                        "project_status": {
                            "path": "docs/project-status.md",
                            "sha256": "e" * 64,
                        },
                        "expected_project_status_sha256": "e" * 64,
                        "live_risk_adr": {
                            "path": "docs/decisions/013-phase6-live-risk-gate.md",
                            "sha256": "c" * 64,
                        },
                        "expected_live_risk_adr_sha256": "c" * 64,
                        "continuity_artifacts": [
                            {
                                "bundle_dir": "data/testnet/run-1",
                                "manifest_path": (
                                    "data/testnet/run-1/run_manifest.json"
                                ),
                                "sha256": "g" * 64,
                            }
                        ],
                        "continuity_artifact_problems": [],
                        "live_promotion_review": {
                            "accepted": False,
                            "path": None,
                        },
                        "expected_live_promotion_review_sha256": None,
                    },
                    "live_promotion_review": {
                        "accepted": False,
                        "blocker": "live_promotion_review_not_found",
                        "path": "missing-live-review.md",
                    },
                    "first_live_day_runbook": {
                        "path": "docs/runbook-first-live-day.md",
                        "sha256": "d" * 64,
                        "accepted": False,
                    },
                },
                "checks": [
                    {
                        "name": "first_live_day_runbook",
                        "status": "blocked",
                        "detail": "Runbook is Draft.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_readiness_report_path=readiness_path,
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )
    markdown = dashboard_snapshot.render_markdown_snapshot(snapshot)

    phase6 = snapshot["phase6"]
    assert phase6["state"] == "blocked"
    assert phase6["counts"]["attached_report_count"] == 2
    assert phase6["counts"]["blocker_count"] == 2
    assert phase6["reports"][0]["label"] == "Live readiness"
    assert phase6["reports"][0]["status"] == "blocked"
    assert phase6["reports"][0]["blockers"] == ["live_risk_adr_not_accepted"]
    assert phase6["reports"][0]["evidence"] == [
        {
            "label": "Project status artifact",
            "status": "ok",
            "detail": "Artifact fingerprint is recorded.",
            "path": "docs/project-status.md",
            "sha256": "e" * 64,
        },
        {
            "label": "Readiness live-risk ADR artifact",
            "status": "ok",
            "detail": "Artifact fingerprint is recorded.",
            "path": "docs/decisions/013-phase6-live-risk-gate.md",
            "sha256": "f" * 64,
        },
        {
            "label": "Continuity bundle artifacts",
            "status": "ok",
            "detail": "1 continuity bundle manifest fingerprints recorded.",
            "path": "data/testnet/run-1/run_manifest.json",
            "sha256": "g" * 64,
        },
        {
            "label": "Promotion review artifact",
            "status": "blocked",
            "detail": "live_canary_promotion_review_required",
            "path": None,
            "sha256": None,
        }
    ]
    assert phase6["reports"][1]["label"] == "Live startup guard"
    assert phase6["reports"][1]["status"] == "blocked"
    assert phase6["reports"][1]["checks"][0]["name"] == "first_live_day_runbook"
    assert phase6["reports"][1]["evidence"][0]["label"] == (
        "Live-risk ADR artifact"
    )
    assert phase6["reports"][1]["evidence"][0]["status"] == "blocked"
    assert phase6["reports"][1]["evidence"][0]["detail"] == (
        "Artifact is not accepted."
    )
    assert phase6["reports"][1]["evidence"][0]["sha256"] == "c" * 64
    assert phase6["reports"][1]["evidence"][1]["label"] == (
        "Readiness report artifact"
    )
    assert phase6["reports"][1]["evidence"][1]["sha256"] == "b" * 64
    assert phase6["reports"][1]["evidence"][2]["label"] == (
        "Readiness live-risk ADR SHA-256 match"
    )
    assert phase6["reports"][1]["evidence"][2]["status"] == "ok"
    assert phase6["reports"][1]["evidence"][2]["sha256"] == "c" * 64
    assert phase6["reports"][1]["evidence"][3]["label"] == (
        "Startup continuity artifact verification"
    )
    assert phase6["reports"][1]["evidence"][3]["status"] == "ok"
    assert phase6["reports"][1]["evidence"][3]["sha256"] == "g" * 64
    assert phase6["reports"][1]["evidence"][4]["label"] == (
        "Startup promotion review artifact"
    )
    assert phase6["reports"][1]["evidence"][5]["label"] == (
        "Readiness promotion SHA-256 match"
    )
    assert phase6["reports"][1]["evidence"][6]["label"] == (
        "First live day runbook artifact"
    )
    assert phase6["reports"][1]["evidence"][6]["status"] == "blocked"
    assert phase6["reports"][1]["evidence"][6]["detail"] == (
        "Artifact is not accepted."
    )
    assert phase6["reports"][1]["evidence"][6]["sha256"] == "d" * 64
    assert phase6["reports"][1]["evidence"][7] == {
        "label": "Readiness freshness window",
        "status": "ok",
        "detail": "Readiness report age 60.0s is within max 86400.0s.",
        "path": str(readiness_path),
        "sha256": "b" * 64,
    }
    assert phase6["reports"][1]["evidence"][8] == {
        "label": "Readiness git commit match",
        "status": "ok",
        "detail": (
            "Readiness report git commit matches startup preflight and is clean."
        ),
        "path": str(readiness_path),
        "sha256": None,
    }
    assert phase6["reports"][1]["evidence"][9] == {
        "label": "Readiness project-status SHA-256 match",
        "status": "ok",
        "detail": (
            "Readiness report and startup project-status artifact fingerprints match."
        ),
        "path": "docs/project-status.md",
        "sha256": "e" * 64,
        "expected_sha256": "e" * 64,
    }
    assert "## Phase 6 Gates" in markdown
    assert "evidence: Promotion review artifact" in markdown
    assert "first_live_day_runbook_not_accepted" in markdown


def test_snapshot_blocks_phase6_readiness_without_promotion_fingerprint(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    readiness_path = tmp_path / "old-live-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "recommendation": "ready_for_manual_live_go_no_go_review",
                "blockers": [],
                "project_status": {
                    "path": "docs/project-status.md",
                    "sha256": "b" * 64,
                },
                "live_risk_adr": {
                    "path": "docs/decisions/013-phase6-live-risk-gate.md",
                    "sha256": "c" * 64,
                    "accepted": True,
                },
                "continuity_artifacts": [
                    {
                        "bundle_dir": "data/testnet/run-1",
                        "manifest_path": "data/testnet/run-1/run_manifest.json",
                        "sha256": "d" * 64,
                    }
                ],
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_readiness_report_path=readiness_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = snapshot["phase6"]["reports"][0]
    assert readiness["status"] == "blocked"
    assert "evidence:Promotion review artifact" in readiness["blockers"]
    assert readiness["evidence"] == [
        {
            "label": "Project status artifact",
            "status": "ok",
            "detail": "Artifact fingerprint is recorded.",
            "path": "docs/project-status.md",
            "sha256": "b" * 64,
        },
        {
            "label": "Readiness live-risk ADR artifact",
            "status": "ok",
            "detail": "Artifact fingerprint is recorded.",
            "path": "docs/decisions/013-phase6-live-risk-gate.md",
            "sha256": "c" * 64,
        },
        {
            "label": "Continuity bundle artifacts",
            "status": "ok",
            "detail": "1 continuity bundle manifest fingerprints recorded.",
            "path": "data/testnet/run-1/run_manifest.json",
            "sha256": "d" * 64,
        },
        {
            "label": "Promotion review artifact",
            "status": "missing",
            "detail": "Promotion review evidence is not recorded in this artifact.",
            "path": None,
            "sha256": None,
        }
    ]
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_readiness_without_source_document_fingerprints(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    readiness_path = tmp_path / "old-live-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "recommendation": "ready_for_manual_live_go_no_go_review",
                "blockers": [],
                "project_status": {"path": "docs/project-status.md"},
                "live_risk_adr": {
                    "path": "docs/decisions/013-phase6-live-risk-gate.md",
                    "accepted": True,
                },
                "live_promotion_review": {
                    "accepted": True,
                    "path": "live-promotion.md",
                    "sha256": "a" * 64,
                },
                "continuity_artifacts": [
                    {
                        "bundle_dir": "data/testnet/run-1",
                        "manifest_path": "data/testnet/run-1/run_manifest.json",
                        "sha256": "b" * 64,
                    }
                ],
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_readiness_report_path=readiness_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = snapshot["phase6"]["reports"][0]
    assert readiness["status"] == "blocked"
    assert "evidence:Project status artifact" in readiness["blockers"]
    assert "evidence:Readiness live-risk ADR artifact" in readiness["blockers"]
    assert readiness["evidence"][0] == {
        "label": "Project status artifact",
        "status": "blocked",
        "detail": "Artifact fingerprint is not recorded.",
        "path": "docs/project-status.md",
        "sha256": None,
    }
    assert readiness["evidence"][1] == {
        "label": "Readiness live-risk ADR artifact",
        "status": "blocked",
        "detail": "Artifact fingerprint is not recorded.",
        "path": "docs/decisions/013-phase6-live-risk-gate.md",
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_readiness_without_continuity_fingerprints(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    readiness_path = tmp_path / "old-live-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "recommendation": "ready_for_manual_live_go_no_go_review",
                "blockers": [],
                "project_status": {
                    "path": "docs/project-status.md",
                    "sha256": "b" * 64,
                },
                "live_risk_adr": {
                    "path": "docs/decisions/013-phase6-live-risk-gate.md",
                    "sha256": "c" * 64,
                    "accepted": True,
                },
                "live_promotion_review": {
                    "accepted": True,
                    "path": "live-promotion.md",
                    "sha256": "a" * 64,
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_readiness_report_path=readiness_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = snapshot["phase6"]["reports"][0]
    assert readiness["status"] == "blocked"
    assert "evidence:Continuity bundle artifacts" in readiness["blockers"]
    assert readiness["evidence"][2] == {
        "label": "Continuity bundle artifacts",
        "status": "missing",
        "detail": "Continuity bundle artifact fingerprints are not recorded.",
        "path": None,
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_readiness_with_blocked_internal_check(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    readiness_path = tmp_path / "inconsistent-live-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "recommendation": "ready_for_manual_live_go_no_go_review",
                "blockers": [],
                "project_status": {
                    "path": "docs/project-status.md",
                    "sha256": "b" * 64,
                },
                "live_risk_adr": {
                    "path": "docs/decisions/013-phase6-live-risk-gate.md",
                    "sha256": "c" * 64,
                    "accepted": True,
                },
                "continuity_artifacts": [
                    {
                        "bundle_dir": "data/testnet/run-1",
                        "manifest_path": "data/testnet/run-1/run_manifest.json",
                        "sha256": "d" * 64,
                    }
                ],
                "live_promotion_review": {
                    "accepted": True,
                    "path": "live-promotion.md",
                    "sha256": "a" * 64,
                },
                "checks": [
                    {
                        "name": "capital_ladder",
                        "status": "blocked",
                        "detail": "Starting capital is outside range.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_readiness_report_path=readiness_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = snapshot["phase6"]["reports"][0]
    assert readiness["status"] == "blocked"
    assert "check:capital_ladder" in readiness["blockers"]
    assert readiness["checks"] == [
        {
            "name": "capital_ladder",
            "status": "blocked",
            "detail": "Starting capital is outside range.",
        }
    ]
    assert snapshot["phase6"]["state"] == "blocked"


def _write_passing_startup_guard_report_with_readiness_git(
    path: Path,
    *,
    readiness_git: dict[str, object],
    expected_git_commit: str = "b" * 40,
    readiness_project_status_sha256: str = "f" * 64,
    expected_project_status_sha256: str = "f" * 64,
    live_risk_adr_accepted: bool = True,
    first_live_day_runbook_accepted: bool = True,
    checks: list[dict[str, str]] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                        "sha256": "b" * 64,
                        "accepted": live_risk_adr_accepted,
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "sha256": "c" * 64,
                        "freshness": {
                            "fresh": True,
                            "problems": [],
                            "age_seconds": 60.0,
                            "max_age_seconds": 86400.0,
                        },
                        "readiness_git": readiness_git,
                        "expected_git_commit": expected_git_commit,
                        "expected_git_dirty": False,
                        "project_status": {
                            "path": "docs/project-status.md",
                            "sha256": readiness_project_status_sha256,
                        },
                        "expected_project_status_sha256": (
                            expected_project_status_sha256
                        ),
                        "live_risk_adr": {
                            "path": "013-phase6-live-risk-gate.md",
                            "sha256": "b" * 64,
                        },
                        "expected_live_risk_adr_sha256": "b" * 64,
                        "continuity_artifacts": [
                            {
                                "bundle_dir": "data/testnet/run-1",
                                "manifest_path": (
                                    "data/testnet/run-1/run_manifest.json"
                                ),
                                "sha256": "d" * 64,
                            }
                        ],
                        "continuity_artifact_problems": [],
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                        "sha256": "e" * 64,
                        "accepted": first_live_day_runbook_accepted,
                        "blocker": (
                            ""
                            if first_live_day_runbook_accepted
                            else "first_live_day_runbook_not_accepted"
                        ),
                    },
                },
                "checks": checks or [],
            }
        ),
        encoding="utf-8",
    )


def test_snapshot_blocks_phase6_startup_with_different_readiness_git_commit(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "d" * 40,
            "dirty": False,
        },
        expected_git_commit="b" * 40,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Readiness git commit match" in startup_guard["blockers"]
    assert startup_guard["evidence"][8] == {
        "label": "Readiness git commit match",
        "status": "blocked",
        "detail": (
            "Readiness report git commit does not match startup preflight."
        ),
        "path": "live-readiness.json",
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_dirty_readiness_git(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "b" * 40,
            "dirty": True,
        },
        expected_git_commit="b" * 40,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Readiness git commit match" in startup_guard["blockers"]
    assert startup_guard["evidence"][8] == {
        "label": "Readiness git commit match",
        "status": "blocked",
        "detail": "Readiness report git evidence is dirty.",
        "path": "live-readiness.json",
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_different_readiness_project_status(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "b" * 40,
            "dirty": False,
        },
        expected_git_commit="b" * 40,
        readiness_project_status_sha256="d" * 64,
        expected_project_status_sha256="f" * 64,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert (
        "evidence:Readiness project-status SHA-256 match"
        in startup_guard["blockers"]
    )
    assert startup_guard["evidence"][9] == {
        "label": "Readiness project-status SHA-256 match",
        "status": "blocked",
        "detail": (
            "Readiness report project-status fingerprint does not match the startup artifact."
        ),
        "path": "docs/project-status.md",
        "sha256": "d" * 64,
        "expected_sha256": "f" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_unaccepted_live_risk_adr_artifact(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "b" * 40,
            "dirty": False,
        },
        expected_git_commit="b" * 40,
        live_risk_adr_accepted=False,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Live-risk ADR artifact" in startup_guard["blockers"]
    assert startup_guard["evidence"][0] == {
        "label": "Live-risk ADR artifact",
        "status": "blocked",
        "detail": "Artifact is not accepted.",
        "path": "013-phase6-live-risk-gate.md",
        "sha256": "b" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_unaccepted_first_live_day_runbook(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "b" * 40,
            "dirty": False,
        },
        expected_git_commit="b" * 40,
        first_live_day_runbook_accepted=False,
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:First live day runbook artifact" in startup_guard["blockers"]
    assert startup_guard["evidence"][6] == {
        "label": "First live day runbook artifact",
        "status": "blocked",
        "detail": "first_live_day_runbook_not_accepted",
        "path": "runbook-first-live-day.md",
        "sha256": "e" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_blocked_internal_check(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    _write_passing_startup_guard_report_with_readiness_git(
        guard_path,
        readiness_git={
            "commit": "b" * 40,
            "dirty": False,
        },
        expected_git_commit="b" * 40,
        checks=[
            {
                "name": "source_policy",
                "status": "blocked",
                "detail": "SourcePolicy is outside live-canary bounds.",
            }
        ],
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "check:source_policy" in startup_guard["blockers"]
    assert startup_guard["checks"] == [
        {
            "name": "source_policy",
            "status": "blocked",
            "detail": "SourcePolicy is outside live-canary bounds.",
        }
    ]
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_without_readiness_artifact_fingerprint(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "old-live-startup-guard.json"
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                        "sha256": "b" * 64,
                        "accepted": True,
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                        "sha256": "c" * 64,
                        "accepted": True,
                    },
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Readiness report artifact" in startup_guard["blockers"]
    assert startup_guard["evidence"][1] == {
        "label": "Readiness report artifact",
        "status": "blocked",
        "detail": "Artifact fingerprint is not recorded.",
        "path": "live-readiness.json",
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_without_operator_document_fingerprints(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "old-live-startup-guard.json"
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "sha256": "b" * 64,
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                    },
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Live-risk ADR artifact" in startup_guard["blockers"]
    assert "evidence:First live day runbook artifact" in startup_guard["blockers"]
    assert startup_guard["evidence"][0] == {
        "label": "Live-risk ADR artifact",
        "status": "blocked",
        "detail": "Artifact fingerprint is not recorded.",
        "path": "013-phase6-live-risk-gate.md",
        "sha256": None,
    }
    assert startup_guard["evidence"][6] == {
        "label": "First live day runbook artifact",
        "status": "blocked",
        "detail": "Artifact fingerprint is not recorded.",
        "path": "runbook-first-live-day.md",
        "sha256": None,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_different_readiness_live_risk_adr(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                        "sha256": "b" * 64,
                        "accepted": True,
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "sha256": "c" * 64,
                        "live_risk_adr": {
                            "path": "013-phase6-live-risk-gate.md",
                            "sha256": "d" * 64,
                        },
                        "expected_live_risk_adr_sha256": "b" * 64,
                        "continuity_artifacts": [
                            {
                                "bundle_dir": "data/testnet/run-1",
                                "manifest_path": (
                                    "data/testnet/run-1/run_manifest.json"
                                ),
                                "sha256": "e" * 64,
                            }
                        ],
                        "continuity_artifact_problems": [],
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                        "sha256": "f" * 64,
                        "accepted": True,
                    },
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert (
        "evidence:Readiness live-risk ADR SHA-256 match"
        in startup_guard["blockers"]
    )
    assert startup_guard["evidence"][2] == {
        "label": "Readiness live-risk ADR SHA-256 match",
        "status": "blocked",
        "detail": (
            "Readiness report ADR fingerprint does not match the startup artifact."
        ),
        "path": "013-phase6-live-risk-gate.md",
        "sha256": "d" * 64,
        "expected_sha256": "b" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_stale_readiness_freshness(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                        "sha256": "b" * 64,
                        "accepted": True,
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "sha256": "c" * 64,
                        "freshness": {
                            "fresh": False,
                            "problems": ["readiness_report_stale"],
                            "age_seconds": 90000.0,
                            "max_age_seconds": 86400.0,
                        },
                        "live_risk_adr": {
                            "path": "013-phase6-live-risk-gate.md",
                            "sha256": "b" * 64,
                        },
                        "expected_live_risk_adr_sha256": "b" * 64,
                        "continuity_artifacts": [
                            {
                                "bundle_dir": "data/testnet/run-1",
                                "manifest_path": (
                                    "data/testnet/run-1/run_manifest.json"
                                ),
                                "sha256": "d" * 64,
                            }
                        ],
                        "continuity_artifact_problems": [],
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                        "sha256": "e" * 64,
                        "accepted": True,
                    },
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert "evidence:Readiness freshness window" in startup_guard["blockers"]
    assert startup_guard["evidence"][7] == {
        "label": "Readiness freshness window",
        "status": "blocked",
        "detail": "Startup guard reported: readiness_report_stale",
        "path": "live-readiness.json",
        "sha256": "c" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_blocks_phase6_startup_with_continuity_artifact_problems(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    guard_path = tmp_path / "live-startup-guard.json"
    guard_path.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_startup_guard.v1",
                "source": "freqai_linear_v1",
                "model_version": "linear-mom-train20240105",
                "startup_allowed": True,
                "live_trading_authorized": False,
                "recommendation": "startup_preflight_passed_for_future_live_runner",
                "blockers": [],
                "evidence": {
                    "live_risk_adr": {
                        "path": "013-phase6-live-risk-gate.md",
                        "sha256": "b" * 64,
                        "accepted": True,
                    },
                    "live_readiness_report": {
                        "path": "live-readiness.json",
                        "sha256": "c" * 64,
                        "live_risk_adr": {
                            "path": "013-phase6-live-risk-gate.md",
                            "sha256": "b" * 64,
                        },
                        "expected_live_risk_adr_sha256": "b" * 64,
                        "continuity_artifacts": [
                            {
                                "bundle_dir": "data/testnet/run-1",
                                "manifest_path": (
                                    "data/testnet/run-1/run_manifest.json"
                                ),
                                "sha256": "d" * 64,
                            }
                        ],
                        "continuity_artifact_problems": [
                            "continuity_artifact_sha256_mismatch"
                        ],
                        "live_promotion_review": {
                            "accepted": True,
                            "path": "live-promotion.md",
                            "sha256": "a" * 64,
                        },
                        "expected_live_promotion_review_sha256": "a" * 64,
                    },
                    "live_promotion_review": {
                        "accepted": True,
                        "path": "live-promotion.md",
                        "sha256": "a" * 64,
                    },
                    "first_live_day_runbook": {
                        "path": "runbook-first-live-day.md",
                        "sha256": "e" * 64,
                        "accepted": True,
                    },
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        phase6_live_startup_guard_report_path=guard_path,
        generated_at_ns=REFERENCE_TS_NS,
    )

    startup_guard = snapshot["phase6"]["reports"][1]
    assert startup_guard["status"] == "blocked"
    assert (
        "evidence:Startup continuity artifact verification"
        in startup_guard["blockers"]
    )
    assert startup_guard["evidence"][3] == {
        "label": "Startup continuity artifact verification",
        "status": "blocked",
        "detail": (
            "Startup guard reported: continuity_artifact_sha256_mismatch"
        ),
        "path": "data/testnet/run-1/run_manifest.json",
        "sha256": "d" * 64,
    }
    assert snapshot["phase6"]["state"] == "blocked"


def test_snapshot_observability_missing_textfile_dir_is_empty(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        observability_textfile_dir=tmp_path / "missing-observability",
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert snapshot["observability"] == {
        "textfile_dir": str(tmp_path / "missing-observability"),
        "exists": False,
        "file_count": 0,
        "stale_after_seconds": 120.0,
        "counts": {
            "run_count": 0,
            "connected_count": 0,
            "stale_count": 0,
            "attention_count": 0,
            "open_orders": 0,
            "open_positions": 0,
            "alert_total": 0,
            "parse_error_count": 0,
        },
        "latest": None,
        "runs": [],
    }


def test_snapshot_reads_prometheus_textfile_observability(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    obs_dir = tmp_path / "observability"
    obs_dir.mkdir()
    (obs_dir / "testnet-run-new.prom").write_text(
        "\n".join(
            [
                'trader_canary_heartbeat_timestamp_seconds{kind="testnet",run_id="run-new"} 1778759970',
                'trader_canary_ws_connected{kind="testnet",run_id="run-new"} 1',
                'trader_canary_ws_reconnect_total{kind="testnet",run_id="run-new"} 0',
                'trader_canary_exchange_error_total{kind="testnet",run_id="run-new"} 1',
                'trader_canary_open_orders{kind="testnet",run_id="run-new"} 2',
                'trader_canary_open_positions{kind="testnet",run_id="run-new"} 1',
                'trader_canary_daily_pnl_usdt{kind="testnet",run_id="run-new"} -0.25',
                'trader_canary_account_total_usdt{kind="testnet",run_id="run-new"} 9999.75',
                'trader_canary_last_bar_timestamp_seconds{kind="testnet",run_id="run-new"} 1778759940',
                'trader_canary_last_signal_timestamp_seconds{kind="testnet",run_id="run-new"} 1778759985',
                'trader_canary_alert_total{alert="ws_disconnected",kind="testnet",run_id="run-new"} 2',
                'trader_canary_info{kind="testnet",run_id="run-new"} 1',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (obs_dir / "testnet-run-old.prom").write_text(
        "\n".join(
            [
                'trader_canary_heartbeat_timestamp_seconds{kind="testnet",run_id="run-old"} 1778759000',
                'trader_canary_ws_connected{kind="testnet",run_id="run-old"} 1',
                'trader_canary_info{kind="testnet",run_id="run-old"} 1',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        observability_textfile_dir=obs_dir,
        observability_limit=1,
        generated_at_ns=REFERENCE_TS_NS,
    )

    observability = snapshot["observability"]
    assert observability["exists"] is True
    assert observability["file_count"] == 2
    assert observability["counts"]["run_count"] == 2
    assert observability["counts"]["connected_count"] == 2
    assert observability["counts"]["stale_count"] == 1
    assert observability["counts"]["open_orders"] == 2
    assert observability["counts"]["open_positions"] == 1
    assert observability["counts"]["alert_total"] == 2
    assert len(observability["runs"]) == 1

    latest = observability["latest"]
    assert latest["run_id"] == "run-new"
    assert latest["state"] == "attention"
    assert latest["state_reason"] == "alerts_present"
    assert latest["heartbeat_age_seconds"] == 30.0
    assert latest["last_bar_age_seconds"] == 60.0
    assert latest["last_signal_age_seconds"] == 15.0
    assert latest["alerts_by_kind"] == {"ws_disconnected": 2}
    assert latest["exchange_error_total"] == 1


def test_markdown_snapshot_renders_observability_runs(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    obs_dir = tmp_path / "observability"
    obs_dir.mkdir()
    (obs_dir / "testnet-run-1.prom").write_text(
        'trader_canary_heartbeat_timestamp_seconds{kind="testnet",run_id="run-1"} 1778759970\n'
        'trader_canary_ws_connected{kind="testnet",run_id="run-1"} 1\n'
        'trader_canary_info{kind="testnet",run_id="run-1"} 1\n',
        encoding="utf-8",
    )
    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        observability_textfile_dir=obs_dir,
        generated_at_ns=REFERENCE_TS_NS,
    )

    out = dashboard_snapshot.render_markdown_snapshot(snapshot)

    assert "## Observability Textfiles" in out
    assert "## Snapshot Inputs" in out
    assert "| Project status | `project_status` | true | true |" in out
    assert "`run-1`" in out
    assert "| `run-1` | healthy | 30.0 | true | n/a | n/a | 0 | n/a |" in out


def test_cli_outputs_json(tmp_path: Path, capsys) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    db = tmp_path / "advice.db"
    AgentAdviceStore(db).write(_advice("advice-1", created_at_ns=REFERENCE_TS_NS))

    rc = dashboard_snapshot.main(
        [
            "--project-status-path",
            str(status_path),
            "--agent-advice-db",
            str(db),
            "--advice-limit",
            "1",
            "--snapshot-warning-after-seconds",
            "45",
            "--snapshot-stale-after-seconds",
            "180",
            "--grafana-base-url",
            "",
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_advice"]["latest"][0]["advice_id"] == "advice-1"
    assert out["snapshot_freshness"]["warning_after_seconds"] == 45.0
    assert out["snapshot_freshness"]["stale_after_seconds"] == 180.0
    assert out["reference_links"][0]["href"] is None


def test_snapshot_wraps_passive_bundle_reports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    paper_dir = tmp_path / "paper-run"
    testnet_dir = tmp_path / "testnet-run"
    paper_dir.mkdir()
    testnet_dir.mkdir()

    monkeypatch.setattr(
        dashboard_snapshot,
        "load_paper_bundle_report",
        lambda path: SimpleNamespace(
            bundle_dir=str(path),
            run_id="paper-1",
            kind="paper",
            git_dirty=False,
            source="freqai_linear_v1",
            model_version="linear-mom-train20240105",
            signal_rows=10,
            first_signal_ts_event_ns=PAPER_FIRST_SIGNAL_TS_NS,
            last_signal_ts_event_ns=PAPER_LAST_SIGNAL_TS_NS,
            accepted_signals=8,
            skipped_signals=2,
            dry_run_signals=0,
            expired_signals=1,
            unauthorized_signals=1,
            signal_lag_signals=0,
            kill_switch_signals=0,
            data_gap_signals=0,
            decision_counts={"target_long": 8, "skip": 2},
            reason_counts={
                "simulated": 8,
                "expired: signal ttl": 1,
                "reject_unauthorized_source: test": 1,
            },
            totals={"fills": 4, "positions": 2},
            pnl_total_by_currency={"USDT": 1.25},
            max_drawdown_pct_by_currency={"USDT": -0.01},
            eligible_for_review=True,
            review_blockers=[],
            promotion_blockers=["manual_review_required_before_paper_simulated"],
            recommendation="review_simulated_paper_evidence",
        ),
    )
    monkeypatch.setattr(
        dashboard_snapshot,
        "load_testnet_bundle_report",
        lambda path: SimpleNamespace(
            bundle_dir=str(path),
            run_id="testnet-1",
            kind="testnet",
            git_dirty=False,
            source="freqai_linear_v1",
            model_version="linear-mom-train20240105",
            clean_for_retro=True,
            first_signal_ts_event_ns=TESTNET_FIRST_SIGNAL_TS_NS,
            last_signal_ts_event_ns=TESTNET_LAST_SIGNAL_TS_NS,
            elapsed_seconds=21600,
            heartbeat_count=720,
            alert_count=0,
            order_count=2,
            fill_count=2,
            position_count=1,
            lineage_rows=3,
            decision_counts={
                "target_long": 2,
                "skip": 1,
            },
            reason_counts={
                "simulated": 2,
                "signal_lag: 180s > 120s": 1,
            },
            lineage_rows_with_order_ids=2,
            lineage_rows_with_fill_ids=2,
            lineage_rows_with_position_id=1,
            final_position_sides={"FLAT": 1},
            realized_pnl_total=0.1,
            max_ws_reconnect_count=0,
            max_exchange_error_count=0,
            review_blockers=[],
            recommendation="ready_for_retro_evidence",
        ),
    )

    snapshot = dashboard_snapshot.build_dashboard_snapshot(
        project_status_path=status_path,
        agent_advice_db_path=tmp_path / "missing.db",
        paper_bundle_dirs=(paper_dir,),
        testnet_bundle_dirs=(testnet_dir,),
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert snapshot["paper_bundles"][0]["run_id"] == "paper-1"
    assert snapshot["paper_bundles"][0]["fills"] == 4
    assert snapshot["testnet_bundles"][0]["run_id"] == "testnet-1"
    assert snapshot["testnet_bundles"][0]["clean_for_retro"] is True
    assert snapshot["snapshot_inputs"]["counts"]["attached"] >= 4
    input_items = {
        (item["category"], item["path"]): item
        for item in snapshot["snapshot_inputs"]["items"]
    }
    assert input_items[("paper_bundle", str(paper_dir))]["exists"] is True
    assert input_items[("testnet_bundle", str(testnet_dir))]["exists"] is True
    assert snapshot["ops_status"]["counts"]["paper_promotion_blockers"] == 1
    assert snapshot["ops_status"]["state"] == "attention"
    assert snapshot["signal_summary"]["bundle_count"] == 2
    assert snapshot["signal_summary"]["signal_rows"] == 13
    assert snapshot["signal_summary"]["accepted_signals"] == 10
    assert snapshot["signal_summary"]["skipped_signals"] == 3
    assert snapshot["signal_summary"]["rejection_signals"] == 3
    assert snapshot["signal_summary"]["rejection_reason_counts"] == {
        "expired": 1,
        "signal_lag": 1,
        "unauthorized": 1,
    }
    assert snapshot["signal_summary"]["freshness"] == {
        "latest_signal_ts_event_ns": TESTNET_LAST_SIGNAL_TS_NS,
        "latest_signal_age_seconds": 60.0,
        "latest_signal_run_id": "testnet-1",
        "latest_signal_kind": "testnet",
        "latest_signal_source": "freqai_linear_v1",
        "latest_signal_model_version": "linear-mom-train20240105",
    }
    assert snapshot["signal_summary"]["runs"][0]["latest_signal_age_seconds"] == 300.0
    assert snapshot["signal_summary"]["runs"][1]["latest_signal_age_seconds"] == 60.0
    assert snapshot["signal_summary"]["by_source_model"] == [
        {
            "source": "freqai_linear_v1",
            "model_version": "linear-mom-train20240105",
            "bundle_count": 2,
            "signal_rows": 13,
            "accepted_signals": 10,
            "skipped_signals": 3,
            "rejection_signals": 3,
            "kinds": {"paper": 1, "testnet": 1},
            "first_signal_ts_event_ns": PAPER_FIRST_SIGNAL_TS_NS,
            "last_signal_ts_event_ns": TESTNET_LAST_SIGNAL_TS_NS,
            "latest_signal_age_seconds": 60.0,
            "latest_signal_run_id": "testnet-1",
            "latest_signal_kind": "testnet",
            "top_rejection_reasons": [
                {"reason": "expired", "count": 1},
                {"reason": "signal_lag", "count": 1},
                {"reason": "unauthorized", "count": 1},
            ],
            "evidence_links": [
                {
                    "group": "grafana",
                    "label": "Signals overview",
                    "kind": "dashboard",
                    "path": "infra/grafana/dashboards/signals-overview.json",
                    "detail": (
                        "Read-only Grafana source/model drill-down for this "
                        "source/model row."
                    ),
                    "href": (
                        "http://127.0.0.1:3000/d/signals-overview/"
                        "signals-overview?var-source=freqai_linear_v1"
                        "&var-model_version=linear-mom-train20240105"
                        "&from=1778755800000&to=1778763540000"
                    ),
                },
                {
                    "group": "evidence",
                    "label": "testnet bundle testnet-1",
                    "kind": "bundle",
                    "path": str(testnet_dir),
                    "detail": (
                        "Attached passive bundle source for this "
                        "source/model row."
                    ),
                    "href": None,
                },
                {
                    "group": "evidence",
                    "label": "paper bundle paper-1",
                    "kind": "bundle",
                    "path": str(paper_dir),
                    "detail": (
                        "Attached passive bundle source for this "
                        "source/model row."
                    ),
                    "href": None,
                },
                {
                    "group": "evidence",
                    "label": "Testnet canary evidence",
                    "kind": "progress",
                    "path": "docs/progress/phase-3-testnet-canary-evidence.md",
                    "detail": "Clean and non-clean Phase 3 canary evidence ledger.",
                    "href": None,
                },
            ],
        }
    ]


def test_signals_overview_dashboard_filters_by_model_version() -> None:
    dashboard_path = Path("infra/grafana/dashboards/signals-overview.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    variables = {
        item["name"]: item
        for item in dashboard.get("templating", {}).get("list", [])
    }

    assert variables["model_version"]["query"] == (
        "SELECT DISTINCT model_version FROM signal_events "
        "WHERE source = ANY(string_to_array('$source', ',')) "
        "ORDER BY model_version"
    )
    assert variables["model_version"]["includeAll"] is True
    assert variables["model_version"]["allValue"] == "__all"

    raw_sql = [
        target["rawSql"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "rawSql" in target
    ]
    signal_event_queries = [
        query for query in raw_sql if " FROM signal_events " in query
    ]
    assert len(signal_event_queries) == 12
    assert all("$model_version" in query for query in signal_event_queries)
    assert all("model_version = ANY" in query for query in signal_event_queries)

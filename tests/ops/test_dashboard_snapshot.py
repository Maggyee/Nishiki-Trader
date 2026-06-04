from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from apps.agents.advice import AgentAdvice
from apps.agents.store import AgentAdviceStore
from apps.ops import dashboard_snapshot

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _write_status(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Project Status",
                "- **Last updated**: 2026-06-04 (snapshot test)",
                "- **Current phase**: Phase 4 entry (agent research foundation)",
                "- **Current objective**: Keep agent output out of the order path.",
                "",
                "No live trading without a separate live-risk ADR.",
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
    assert snapshot["boundaries"] == {
        "live_path_allowed": False,
        "signal_event_write_allowed": False,
        "source_policy_mutation_allowed": False,
        "exchange_api_access_allowed": False,
    }
    assert snapshot["project_status"] == {
        "path": str(status_path),
        "exists": True,
        "last_updated": "2026-06-04 (snapshot test)",
        "current_phase": "Phase 4 entry (agent research foundation)",
        "current_objective": "Keep agent output out of the order path.",
        "live_trading_blocked": True,
    }
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
    assert "signal_event_write_allowed=false" in out
    assert "`advice-1`" in out


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
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_advice"]["latest"][0]["advice_id"] == "advice-1"


def test_snapshot_wraps_passive_bundle_reports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    paper_dir = tmp_path / "paper-run"
    testnet_dir = tmp_path / "testnet-run"

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
            accepted_signals=8,
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
            elapsed_seconds=21600,
            heartbeat_count=720,
            alert_count=0,
            order_count=2,
            fill_count=2,
            position_count=1,
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

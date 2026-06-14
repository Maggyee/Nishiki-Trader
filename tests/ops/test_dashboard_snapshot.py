from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
    assert "Expand the dashboard with read-only operations panels." in out
    assert "signal_event_write_allowed=false" in out
    assert "## Reference Links" in out
    assert "Signals overview" in out
    assert "`advice-1`" in out


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
            "--grafana-base-url",
            "",
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_advice"]["latest"][0]["advice_id"] == "advice-1"
    assert out["reference_links"][0]["href"] is None


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
        }
    ]

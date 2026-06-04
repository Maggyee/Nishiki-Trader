from __future__ import annotations

import json
from pathlib import Path

from apps.agents.review_agent import (
    ReviewAgentInput,
    build_project_review_advice,
    main,
    run_review_agent,
)
from apps.agents.store import AgentAdviceStore
from apps.bridge.signal_event import SignalEvent
from apps.bridge.store import SignalStore

REFERENCE_TS_NS = 1_778_760_000_000_000_000


def _write_status(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Project Status",
                "- **Current phase**: Phase 4 entry (agent research foundation)",
                "- **Current objective**: Agents write AgentAdvice only. "
                "Strict continuity remains current_qualified_streak_days=0/14. "
                "No live trading without a separate live-risk ADR.",
                "",
                "The project has fifteen clean, sidecar-backed testnet canaries.",
                "Aggregate evidence has 30 orders but still only fifteen clean canaries.",
            ]
        ),
        encoding="utf-8",
    )


def test_build_project_review_advice_is_agent_advice_only(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    advice = build_project_review_advice(
        ReviewAgentInput(
            project_status_path=status_path,
            created_at_ns=REFERENCE_TS_NS,
            advice_id="review-1",
        )
    )

    assert advice.schema_version == "agent.advice.v1"
    assert advice.advice_type == "project_review"
    assert advice.agent_name == "review_agent"
    assert advice.payload["live_path_allowed"] is False
    assert advice.payload["signal_event_write_allowed"] is False
    assert advice.payload["source_policy_mutation_allowed"] is False
    assert advice.payload["phase"] == "Phase 4 entry (agent research foundation)"
    assert "Clean sidecar-backed canary count: 15" in advice.payload["observations"]
    assert advice.payload["dashboard_snapshot_ready"] is False
    assert advice.payload["recommended_next_actions"]


def test_review_advice_detects_dashboard_snapshot_surface(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    with status_path.open("a", encoding="utf-8") as fh:
        fh.write("\napps.ops.dashboard_snapshot emits dashboard.snapshot.v1.\n")

    advice = build_project_review_advice(
        ReviewAgentInput(
            project_status_path=status_path,
            created_at_ns=REFERENCE_TS_NS,
            advice_id="review-1",
        )
    )

    assert advice.payload["dashboard_snapshot_ready"] is True
    assert (
        "Use dashboard.snapshot.v1 as the read-only surface for future dashboard/frontend work."
        in advice.payload["recommended_next_actions"]
    )


def test_review_advice_cannot_parse_as_signal_event(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    advice = build_project_review_advice(
        ReviewAgentInput(project_status_path=status_path, created_at_ns=REFERENCE_TS_NS)
    )

    try:
        SignalEvent.model_validate(advice.model_dump())
    except Exception as exc:
        assert "signal_id" in str(exc) or "schema_version" in str(exc)
    else:
        raise AssertionError("AgentAdvice unexpectedly parsed as SignalEvent")


def test_run_review_agent_writes_only_agent_advice(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    advice_store = AgentAdviceStore(tmp_path / "advice.db")
    signal_store = SignalStore(tmp_path / "signals.db")

    result = run_review_agent(
        ReviewAgentInput(
            project_status_path=status_path,
            created_at_ns=REFERENCE_TS_NS,
            advice_id="review-1",
        ),
        store=advice_store,
    )

    assert result.wrote is True
    assert result.duplicate is False
    assert [advice.advice_id for advice in advice_store.replay()] == ["review-1"]
    assert signal_store.list_by_status("pending") == []


def test_run_review_agent_duplicate_is_nonfatal(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    store = AgentAdviceStore(tmp_path / "advice.db")
    input_data = ReviewAgentInput(
        project_status_path=status_path,
        created_at_ns=REFERENCE_TS_NS,
        advice_id="review-1",
    )

    first = run_review_agent(input_data, store=store)
    second = run_review_agent(input_data, store=store)

    assert first.wrote is True
    assert second.wrote is False
    assert second.duplicate is True


def test_review_agent_cli_dry_run_does_not_write(tmp_path: Path, capsys) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    db = tmp_path / "advice.db"

    rc = main(
        [
            "--db",
            str(db),
            "--project-status-path",
            str(status_path),
            "--created-at-ns",
            str(REFERENCE_TS_NS),
            "--advice-id",
            "review-1",
            "--dry-run",
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["_write_result"] == {"duplicate": False, "dry_run": True, "wrote": False}
    assert AgentAdviceStore(db).replay() == []


def test_review_agent_cli_writes(tmp_path: Path, capsys) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    db = tmp_path / "advice.db"

    rc = main(
        [
            "--db",
            str(db),
            "--project-status-path",
            str(status_path),
            "--created-at-ns",
            str(REFERENCE_TS_NS),
            "--advice-id",
            "review-1",
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["_write_result"] == {"duplicate": False, "dry_run": False, "wrote": True}
    assert [advice.advice_id for advice in AgentAdviceStore(db).replay()] == ["review-1"]

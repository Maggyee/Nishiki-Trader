from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from apps.strategies_nautilus.runners.live_startup_guard import (
    EXIT_OK,
    EXIT_STARTUP_VALIDATION,
    GitState,
    LiveStartupSettings,
    build_live_startup_guard_report,
    main,
    render_markdown_report,
)

SOURCE = "freqai_linear_v1"
MODEL_VERSION = "linear-mom-train20240105"
REFERENCE_TS_NS = time.time_ns()
GIT_CLEAN = GitState(commit="a" * 40, dirty=False)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _live_promotion_text(
    *,
    source: str = SOURCE,
    model_version: str = MODEL_VERSION,
    current_stage: str = "testnet_canary",
    target_stage: str = "live_canary",
    decision: str = "PROMOTE",
    decision_allowed: str = "yes",
    operator: str = "pytest",
    review_blockers: str = "none",
    promotion_gate_blockers: str = "none",
    rationale: str = "signed live promotion evidence",
) -> str:
    return "\n".join(
        [
            f"# Promotion review - {source} / {model_version}",
            f"- **Operator**: {operator}",
            f"- **Decision**: {decision}",
            f"- **Decision allowed by gates**: {decision_allowed}",
            "",
            "## 1. Source / model",
            f"- source: `{source}`",
            f"- model_version: `{model_version}`",
            "",
            "## 2. Current vs target policy",
            f"- current_stage: `{current_stage}`",
            f"- target_stage: `{target_stage}`",
            "",
            "## 7. Conclusion",
            f"- review_blockers: {review_blockers}",
            f"- promotion_gate_blockers: {promotion_gate_blockers}",
            f"- decision: **{decision}**",
            f"- decision_allowed: **{decision_allowed}**",
            "",
            "### Rationale",
            rationale,
        ]
    )


def _settings(tmp_path: Path, **overrides) -> LiveStartupSettings:
    paths = {
        "readiness": tmp_path / "live-readiness.json",
        "project_status": tmp_path / "project-status.md",
        "adr": tmp_path / "013-phase6-live-risk-gate.md",
        "promotion": tmp_path / "live-promotion.md",
        "runbook": tmp_path / "runbook-first-live-day.md",
    }
    if not all(path.exists() for path in paths.values()):
        paths = _write_evidence(tmp_path)
    values = {
        "mode": "live",
        "kind": "live",
        "allow_live_credentials": True,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "policy_dry_run": False,
        "policy_position_pct_multiplier": 0.1,
        "starting_capital_usdt": 100.0,
        "live_readiness_report_path": paths["readiness"],
        "live_promotion_review_path": paths["promotion"],
        "first_live_day_runbook_path": paths["runbook"],
        "project_status_path": paths["project_status"],
        "live_risk_adr_path": paths["adr"],
        "repo_root": tmp_path,
        "operator": "pytest",
    }
    values.update(overrides)
    return LiveStartupSettings(**values)


def _write_evidence(
    tmp_path: Path,
    *,
    runbook_status: str = "Accepted",
    generated_at_ns: int = REFERENCE_TS_NS,
) -> dict[str, Path]:
    readiness = tmp_path / "live-readiness.json"
    project_status = tmp_path / "project-status.md"
    adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    runbook = tmp_path / "runbook-first-live-day.md"
    bundle_dir = tmp_path / "testnet-run-1"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = bundle_dir / "run_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "testnet.run_manifest.v1",
                "kind": "testnet",
                "run_id": "testnet-run-1",
                "source": SOURCE,
                "model_version": MODEL_VERSION,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    promotion_text = _live_promotion_text()
    promotion.write_text(promotion_text, encoding="utf-8")
    project_status_text = "\n".join(
        [
            "# Project Status",
            "- **Current phase**: Phase 5 entry",
            "- **Current objective**: Phase 6 remains blocked.",
        ]
    )
    project_status.write_text(project_status_text, encoding="utf-8")
    adr_text = "\n".join(
        [
            "# ADR-013: Phase 6 Live Risk Gate",
            "- **Status**: Accepted",
        ]
    )
    adr.write_text(adr_text, encoding="utf-8")
    runbook.write_text(
        "\n".join(
            [
                "# First Live Day Runbook",
                f"- **Status**: {runbook_status}",
                "credential key-prefix audit",
                "emergency flatten",
                "manual exchange fallback",
                "first-hour observation",
                "post-run retro",
            ]
        ),
        encoding="utf-8",
    )
    readiness.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "generated_at_ns": generated_at_ns,
                "source": SOURCE,
                "model_version": MODEL_VERSION,
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "blockers": [],
                "git": {
                    "commit": "a" * 40,
                    "dirty": False,
                },
                "project_status": {
                    "path": str(project_status),
                    "exists": True,
                    "sha256": _text_sha256(project_status_text),
                    "live_trading_blocked": True,
                    "strict_continuity": "14/14",
                },
                "continuity_summary": {"required_gate_met": True},
                "continuity_artifacts": [
                    {
                        "bundle_dir": str(bundle_dir),
                        "manifest_path": str(manifest),
                        "exists": True,
                        "sha256": manifest_sha256,
                    }
                ],
                "capital_plan": {
                    "starting_capital_usdt": 100.0,
                    "within_live_canary_range": True,
                },
                "market_scope": {
                    "market_type": "spot",
                    "margin_enabled": False,
                    "max_leverage": 1.0,
                    "spot_only_no_margin_no_leverage": True,
                },
                "live_risk_adr": {
                    "path": str(adr),
                    "exists": True,
                    "sha256": _text_sha256(adr_text),
                    "status": "Accepted",
                    "accepted": True,
                },
                "live_promotion_review": {
                    "path": str(promotion),
                    "sha256": _text_sha256(promotion_text),
                    "accepted": True,
                    "blocker": "",
                    "problems": [],
                },
                "boundaries": {
                    "starts_runtime": False,
                    "loads_exchange_credentials": False,
                    "mutates_source_policy": False,
                    "writes_signal_event": False,
                    "places_orders": False,
                    "authorizes_live_trading": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return {
        "readiness": readiness,
        "project_status": project_status,
        "adr": adr,
        "promotion": promotion,
        "runbook": runbook,
        "bundle": bundle_dir,
        "manifest": manifest,
    }


def _replace_promotion(
    paths: dict[str, Path],
    text: str,
    *,
    readiness_accepted: bool = True,
) -> None:
    paths["promotion"].write_text(text, encoding="utf-8")
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["live_promotion_review"] = {
        "path": str(paths["promotion"]),
        "sha256": _text_sha256(text),
        "accepted": readiness_accepted,
        "blocker": "" if readiness_accepted else "live_canary_promotion_review_invalid",
        "problems": [] if readiness_accepted else ["test_fixture_invalid"],
    }
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")


def test_live_startup_guard_passes_with_complete_evidence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    report = build_live_startup_guard_report(
        settings,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    rendered = json.dumps(report, default=lambda value: value.__dict__, sort_keys=True)

    assert report.schema_version == "phase6.live_startup_guard.v1"
    assert report.startup_allowed is True
    assert report.live_trading_authorized is False
    assert report.recommendation == "startup_preflight_passed_for_future_live_runner"
    assert report.blockers == []
    assert report.market_scope == {
        "market_type": "spot",
        "margin_enabled": False,
        "max_leverage": 1.0,
        "spot_only_no_margin_no_leverage": True,
        "blockers": [],
        "detail": "Market scope is Binance Spot only, no margin, no leverage.",
    }
    assert report.boundaries == {
        "starts_runtime": False,
        "loads_exchange_credentials": False,
        "reads_exchange_credential_values": False,
        "builds_nautilus_node": False,
        "connects_exchange": False,
        "mutates_source_policy": False,
        "writes_signal_event": False,
        "places_orders": False,
        "authorizes_live_trading": False,
    }
    assert report.credential_boundary["values_inspected"] is False
    assert report.evidence["live_readiness_report"]["sha256"] == hashlib.sha256(
        settings.live_readiness_report_path.read_bytes()
    ).hexdigest()
    assert report.evidence["live_readiness_report"]["readiness_git"] == {
        "commit": "a" * 40,
        "dirty": False,
    }
    assert (
        report.evidence["live_readiness_report"]["expected_git_commit"]
        == "a" * 40
    )
    assert report.evidence["live_readiness_report"]["expected_git_dirty"] is False
    assert report.evidence["live_risk_adr"]["sha256"] == hashlib.sha256(
        settings.live_risk_adr_path.read_bytes()
    ).hexdigest()
    assert report.evidence["first_live_day_runbook"]["sha256"] == hashlib.sha256(
        settings.first_live_day_runbook_path.read_bytes()
    ).hexdigest()
    assert (
        report.evidence["live_readiness_report"]["project_status"]["sha256"]
        == hashlib.sha256(settings.project_status_path.read_bytes()).hexdigest()
    )
    assert (
        report.evidence["live_readiness_report"]["expected_project_status_sha256"]
        == hashlib.sha256(settings.project_status_path.read_bytes()).hexdigest()
    )
    assert (
        report.evidence["live_readiness_report"]["expected_project_status_path"]
        == str(settings.project_status_path)
    )
    assert (
        report.evidence["live_readiness_report"]["continuity_artifacts"][0]["sha256"]
        == hashlib.sha256(
            (tmp_path / "testnet-run-1" / "run_manifest.json").read_bytes()
        ).hexdigest()
    )
    assert report.evidence["live_readiness_report"]["continuity_artifact_problems"] == []
    assert (
        report.evidence["live_readiness_report"]["expected_live_risk_adr_sha256"]
        == report.evidence["live_risk_adr"]["sha256"]
    )
    assert (
        report.evidence["live_readiness_report"][
            "expected_live_promotion_review_sha256"
        ]
        == report.evidence["live_promotion_review"]["sha256"]
    )
    assert "BINANCE_LIVE_API_SECRET" in rendered
    assert "not-a-secret-value" not in rendered


def test_live_startup_guard_blocks_dirty_git(tmp_path: Path) -> None:
    report = build_live_startup_guard_report(
        _settings(tmp_path),
        git_state=GitState(commit="a" * 40, dirty=True),
    )

    assert report.startup_allowed is False
    assert "git_dirty" in report.blockers


def test_live_startup_guard_blocks_readiness_report_that_is_not_ready(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["readiness_gate_met"] = False
    payload["blockers"] = ["live_risk_adr_not_accepted"]
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers


def test_live_startup_guard_blocks_readiness_report_from_different_commit(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["git"]["commit"] = "b" * 40
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_git_commit" in report.evidence["live_readiness_report"]["problems"]
    assert report.evidence["live_readiness_report"]["readiness_git"] == {
        "commit": "b" * 40,
        "dirty": False,
    }
    assert (
        report.evidence["live_readiness_report"]["expected_git_commit"]
        == "a" * 40
    )


def test_live_startup_guard_blocks_stale_readiness_report(
    tmp_path: Path,
) -> None:
    two_days_ns = 2 * 24 * 60 * 60 * 1_000_000_000
    paths = _write_evidence(tmp_path, generated_at_ns=REFERENCE_TS_NS - two_days_ns)

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_report_stale" in readiness["problems"]
    assert readiness["freshness"]["fresh"] is False
    assert readiness["freshness"]["age_seconds"] == 2 * 24 * 60 * 60


def test_live_startup_guard_blocks_future_readiness_report(
    tmp_path: Path,
) -> None:
    one_minute_ns = 60 * 1_000_000_000
    paths = _write_evidence(tmp_path, generated_at_ns=REFERENCE_TS_NS + one_minute_ns)

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_generated_in_future" in readiness["problems"]
    assert readiness["freshness"]["fresh"] is False


def test_live_startup_guard_blocks_readiness_report_without_generated_at_ns(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload.pop("generated_at_ns")
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_generated_at_ns" in readiness["problems"]
    assert readiness["freshness"]["report_generated_at_ns"] is None


def test_live_startup_guard_blocks_dirty_readiness_report(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["git"]["dirty"] = True
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_git_dirty" in report.evidence["live_readiness_report"]["problems"]
    assert report.evidence["live_readiness_report"]["readiness_git"] == {
        "commit": "a" * 40,
        "dirty": True,
    }
    assert (
        report.evidence["live_readiness_report"]["expected_git_commit"]
        == "a" * 40
    )


def test_live_startup_guard_blocks_malformed_readiness_capital(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["capital_plan"]["starting_capital_usdt"] = "not-a-number"
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers


def test_live_startup_guard_blocks_readiness_report_with_open_boundary(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["boundaries"]["places_orders"] = True
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "readiness_boundaries" in report.evidence["live_readiness_report"]["problems"]
    assert report.evidence["live_readiness_report"]["opened_boundaries"] == [
        "places_orders"
    ]


def test_live_startup_guard_blocks_readiness_report_without_promotion_fingerprint(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload.pop("live_promotion_review")
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "live_promotion_review" in readiness["problems"]
    assert "live_promotion_review_sha256" in readiness["problems"]


def test_live_startup_guard_blocks_readiness_report_without_source_document_fingerprints(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload["project_status"].pop("sha256")
    payload["live_risk_adr"].pop("sha256")
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "project_status_sha256" in readiness["problems"]
    assert "live_risk_adr_sha256" in readiness["problems"]


def test_live_startup_guard_blocks_readiness_report_with_changed_project_status(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    paths["project_status"].write_text(
        "# Project Status\n- **Current phase**: Phase 6 entry attempt\n",
        encoding="utf-8",
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "project_status_sha256" in readiness["problems"]
    assert readiness["project_status"]["sha256"] != readiness[
        "expected_project_status_sha256"
    ]


def test_live_startup_guard_blocks_readiness_report_without_continuity_artifacts(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    payload.pop("continuity_artifacts")
    paths["readiness"].write_text(json.dumps(payload), encoding="utf-8")

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "testnet_continuity_artifacts" in readiness["problems"]
    assert "continuity_artifacts_missing" in readiness["continuity_artifact_problems"]


def test_live_startup_guard_blocks_readiness_report_with_missing_continuity_manifest(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    paths["manifest"].unlink()

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "testnet_continuity_artifacts" in readiness["problems"]
    assert (
        "continuity_artifact_manifest_not_found"
        in readiness["continuity_artifact_problems"]
    )


def test_live_startup_guard_blocks_readiness_report_with_changed_continuity_manifest(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    paths["manifest"].write_text(
        json.dumps({"run_id": "testnet-run-1", "tampered": True}),
        encoding="utf-8",
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "testnet_continuity_artifacts" in readiness["problems"]
    assert (
        "continuity_artifact_sha256_mismatch"
        in readiness["continuity_artifact_problems"]
    )


def test_live_startup_guard_blocks_readiness_report_from_different_live_risk_adr(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    paths["adr"].write_text(
        "\n".join(
            [
                "# ADR-013: Phase 6 Live Risk Gate",
                "- **Status**: Accepted",
                "Different operator-reviewed bytes.",
            ]
        ),
        encoding="utf-8",
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "live_risk_adr_sha256" in readiness["problems"]
    assert (
        readiness["expected_live_risk_adr_sha256"]
        == report.evidence["live_risk_adr"]["sha256"]
    )


def test_live_startup_guard_blocks_readiness_report_with_different_promotion_artifact(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    paths["promotion"].write_text(
        _live_promotion_text(
            operator="replacement-reviewer",
            rationale="a different signed artifact with otherwise valid fields",
        ),
        encoding="utf-8",
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_readiness_report_path=paths["readiness"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    readiness = report.evidence["live_readiness_report"]
    assert report.startup_allowed is False
    assert "live_readiness_report_gate_not_met" in report.blockers
    assert "live_promotion_review_sha256" in readiness["problems"]
    assert report.evidence["live_promotion_review"]["accepted"] is True


def test_live_startup_guard_blocks_non_spot_or_leveraged_scope(
    tmp_path: Path,
) -> None:
    report = build_live_startup_guard_report(
        _settings(
            tmp_path,
            market_type="margin",
            margin_enabled=True,
            max_leverage=2.0,
        ),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "market_type_must_be_spot" in report.blockers
    assert "margin_must_be_disabled" in report.blockers
    assert "leverage_must_be_one" in report.blockers


def test_live_startup_guard_blocks_policy_outside_live_canary_bounds(
    tmp_path: Path,
) -> None:
    report = build_live_startup_guard_report(
        _settings(
            tmp_path,
            policy_dry_run=True,
            policy_position_pct_multiplier=0.11,
        ),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "policy_must_not_be_dry_run_for_live_canary" in report.blockers
    assert "policy_multiplier_outside_live_canary_bounds" in report.blockers


def test_live_startup_guard_blocks_unaccepted_runbook(tmp_path: Path) -> None:
    paths = _write_evidence(tmp_path, runbook_status="Draft")

    report = build_live_startup_guard_report(
        _settings(tmp_path, first_live_day_runbook_path=paths["runbook"]),
        git_state=GIT_CLEAN,
    )

    assert report.startup_allowed is False
    assert "first_live_day_runbook_not_accepted" in report.blockers


def test_live_startup_guard_blocks_promotion_review_with_only_stage_mentions(
    tmp_path: Path,
) -> None:
    paths = _write_evidence(tmp_path)
    _replace_promotion(
        paths,
        _live_promotion_text(
            current_stage="paper_simulated",
            target_stage="testnet_canary",
            rationale=(
                "This rationale mentions live_canary and testnet_canary but the "
                "structured stage fields are not the live transition."
            ),
        ),
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_promotion_review_path=paths["promotion"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    promotion = report.evidence["live_promotion_review"]
    assert report.startup_allowed is False
    assert "live_promotion_review_invalid" in report.blockers
    assert "current_stage" in promotion["problems"]
    assert "target_stage" in promotion["problems"]


def test_live_startup_guard_blocks_non_promote_live_review(tmp_path: Path) -> None:
    paths = _write_evidence(tmp_path)
    _replace_promotion(
        paths,
        _live_promotion_text(decision="HOLD"),
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_promotion_review_path=paths["promotion"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    promotion = report.evidence["live_promotion_review"]
    assert report.startup_allowed is False
    assert "live_promotion_review_invalid" in report.blockers
    assert "decision" in promotion["problems"]


def test_live_startup_guard_accepts_json_promotion_review(tmp_path: Path) -> None:
    paths = _write_evidence(tmp_path)
    _replace_promotion(
        paths,
        json.dumps(
            {
                "source": SOURCE,
                "model_version": MODEL_VERSION,
                "current_stage": "testnet_canary",
                "target_stage": "live_canary",
                "decision": "promote",
                "decision_allowed": True,
                "operator": "pytest",
                "review_blockers": [],
                "promotion_gate_blockers": [],
            }
        ),
    )

    report = build_live_startup_guard_report(
        _settings(tmp_path, live_promotion_review_path=paths["promotion"]),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.startup_allowed is True
    assert report.evidence["live_promotion_review"]["accepted"] is True


def test_live_startup_guard_cli_outputs_json_and_exit_code(
    tmp_path: Path,
    capsys,
) -> None:
    paths = _write_evidence(tmp_path)

    rc = main(
        [
            "--mode",
            "live",
            "--kind",
            "live",
            "--allow-live-credentials",
            "--source",
            SOURCE,
            "--model-version",
            MODEL_VERSION,
            "--policy-position-pct-multiplier",
            "0.1",
            "--starting-capital-usdt",
            "100",
            "--live-readiness-report-path",
            str(paths["readiness"]),
            "--live-promotion-review-path",
            str(paths["promotion"]),
            "--first-live-day-runbook-path",
            str(paths["runbook"]),
            "--project-status-path",
            str(paths["project_status"]),
            "--live-risk-adr-path",
            str(paths["adr"]),
            "--repo-root",
            str(tmp_path),
        ],
        git_state=GIT_CLEAN,
    )

    assert rc == EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["startup_allowed"] is True
    assert out["live_trading_authorized"] is False


def test_live_startup_guard_cli_returns_validation_code_when_blocked(
    tmp_path: Path,
    capsys,
) -> None:
    paths = _write_evidence(tmp_path, runbook_status="Draft")

    rc = main(
        [
            "--mode",
            "live",
            "--kind",
            "live",
            "--source",
            SOURCE,
            "--model-version",
            MODEL_VERSION,
            "--policy-position-pct-multiplier",
            "0.1",
            "--starting-capital-usdt",
            "100",
            "--live-readiness-report-path",
            str(paths["readiness"]),
            "--live-promotion-review-path",
            str(paths["promotion"]),
            "--first-live-day-runbook-path",
            str(paths["runbook"]),
            "--live-risk-adr-path",
            str(paths["adr"]),
            "--repo-root",
            str(tmp_path),
            "--markdown",
        ],
        git_state=GIT_CLEAN,
    )

    assert rc == EXIT_STARTUP_VALIDATION
    markdown = capsys.readouterr().out
    assert "# Phase 6 Live Startup Guard" in markdown
    assert "startup_allowed: false" in markdown


def test_live_startup_guard_markdown_lists_checks(tmp_path: Path) -> None:
    report = build_live_startup_guard_report(
        _settings(tmp_path),
        git_state=GIT_CLEAN,
    )

    markdown = render_markdown_report(report)

    assert "| live_readiness_report | ok |" in markdown
    assert "live_trading_authorized: false" in markdown

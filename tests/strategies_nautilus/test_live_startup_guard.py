from __future__ import annotations

import json
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
REFERENCE_TS_NS = 1_778_760_000_000_000_000
GIT_CLEAN = GitState(commit="a" * 40, dirty=False)


def _settings(tmp_path: Path, **overrides) -> LiveStartupSettings:
    paths = {
        "readiness": tmp_path / "live-readiness.json",
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
        "live_risk_adr_path": paths["adr"],
        "repo_root": tmp_path,
        "operator": "pytest",
    }
    values.update(overrides)
    return LiveStartupSettings(**values)


def _write_evidence(tmp_path: Path, *, runbook_status: str = "Accepted") -> dict[str, Path]:
    readiness = tmp_path / "live-readiness.json"
    adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    runbook = tmp_path / "runbook-first-live-day.md"
    readiness.write_text(
        json.dumps(
            {
                "schema_version": "phase6.live_readiness.v1",
                "source": SOURCE,
                "model_version": MODEL_VERSION,
                "readiness_gate_met": True,
                "live_trading_allowed": False,
                "blockers": [],
                "continuity_summary": {"required_gate_met": True},
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
                "live_risk_adr": {"accepted": True},
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
    adr.write_text(
        "\n".join(
            [
                "# ADR-013: Phase 6 Live Risk Gate",
                "- **Status**: Accepted",
            ]
        ),
        encoding="utf-8",
    )
    promotion.write_text(
        "\n".join(
            [
                "# Promotion review",
                "decision_allowed: **yes**",
                f"source: {SOURCE}",
                f"model_version: {MODEL_VERSION}",
                "current_stage: testnet_canary",
                "target_stage: live_canary",
            ]
        ),
        encoding="utf-8",
    )
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
    return {
        "readiness": readiness,
        "adr": adr,
        "promotion": promotion,
        "runbook": runbook,
    }


def test_live_startup_guard_passes_with_complete_evidence(tmp_path: Path) -> None:
    report = build_live_startup_guard_report(
        _settings(tmp_path),
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

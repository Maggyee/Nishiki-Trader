from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from apps.ops import live_readiness
from apps.ops.live_readiness import GitState
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    TestnetContinuitySummary as ContinuitySummary,
)

REFERENCE_TS_NS = 1_778_760_000_000_000_000
GIT_CLEAN = GitState(commit="a" * 40, dirty=False)


def _live_promotion_text(
    *,
    source: str = "freqai_linear_v1",
    model_version: str = "linear-mom-train20240105",
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


def _write_status(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Project Status",
                "- **Last updated**: 2026-06-29",
                "- **Current phase**: Phase 5 entry (read-only frontend + monitoring; live trading still blocked)",
                "- **Current objective**: Strict continuity remains current_qualified_streak_days=0/14. No live trading without a separate live-risk ADR.",
            ]
        ),
        encoding="utf-8",
    )


def _write_live_adr(path: Path, *, status: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# ADR-013: Phase 6 Live Risk Gate",
                f"- **Status**: {status}",
                "",
                "This document does not authorize live trading.",
            ]
        ),
        encoding="utf-8",
    )


def _write_bundle_manifest(bundle_dir: Path) -> Path:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = bundle_dir / "run_manifest.json"
    manifest.write_text(
        json.dumps({"kind": "testnet", "run_id": bundle_dir.name}),
        encoding="utf-8",
    )
    return manifest


def _continuity_summary(*, gate_met: bool) -> ContinuitySummary:
    return ContinuitySummary(
        bundle_dirs=["data/testnet/run-1"],
        min_clean_hours_per_day=6.0,
        required_consecutive_days=14,
        day_count=14,
        qualified_day_count=14 if gate_met else 7,
        longest_qualified_streak_days=14 if gate_met else 5,
        current_qualified_streak_days=14 if gate_met else 0,
        required_gate_met=gate_met,
        total_exchange_error_count=0,
        total_ws_reconnect_count=0,
        max_restart_sequence=0,
        restart_drift_days=[],
        kill_switch_alerts=0,
        emergency_flatten_completed_alerts=0 if gate_met else 2,
        blockers=[] if gate_met else ["current_qualified_streak_days=0<required=14"],
        days=[],
        recommendation=(
            "ready_for_live_risk_adr_review"
            if gate_met
            else "continue_testnet_continuity"
        ),
    )


def test_live_readiness_blocks_without_continuity_or_accepted_adr(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)
    live_adr = tmp_path / "missing-adr.md"

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.schema_version == "phase6.live_readiness.v1"
    assert report.live_trading_allowed is False
    assert report.readiness_gate_met is False
    assert report.project_status["sha256"] == hashlib.sha256(
        status_path.read_bytes()
    ).hexdigest()
    assert report.live_risk_adr["sha256"] is None
    assert report.recommendation == "remain_blocked_before_phase6_live_canary"
    assert "live_risk_adr_not_accepted" in report.blockers
    assert "testnet_continuity_evidence_missing" in report.blockers
    assert "live_canary_promotion_review_required" in report.blockers
    assert report.live_promotion_review == {
        "path": None,
        "accepted": False,
        "blocker": "live_canary_promotion_review_required",
        "detail": "A signed live-canary promotion_review artifact is required.",
    }
    assert report.git == {
        "commit": "a" * 40,
        "dirty": False,
        "repo_root": ".",
    }
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
        "mutates_source_policy": False,
        "writes_signal_event": False,
        "places_orders": False,
        "authorizes_live_trading": False,
    }


def test_live_readiness_blocks_invalid_utf8_source_documents(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    status_path.write_bytes(b"\xff\xfe")
    live_adr.write_bytes(b"\xff\xfe")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert "project_status_invalid_utf8" in report.blockers
    assert "project_status_live_trading_not_blocked" in report.blockers
    assert "live_risk_adr_not_accepted" in report.blockers
    assert report.project_status["sha256"] == hashlib.sha256(b"\xff\xfe").hexdigest()
    assert report.project_status["decode_error"]
    assert report.project_status["live_trading_blocked"] is False
    assert report.live_risk_adr["sha256"] == hashlib.sha256(b"\xff\xfe").hexdigest()
    assert report.live_risk_adr["decode_error"]
    assert report.live_risk_adr["status"] == "invalid_utf8"
    assert report.live_risk_adr["accepted"] is False
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_uses_passive_continuity_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=False),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[tmp_path / "bundle-1"],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.continuity_summary is not None
    assert report.continuity_summary["required_gate_met"] is False
    assert "testnet_continuity:current_qualified_streak_days=0<required=14" in (
        report.blockers
    )
    assert report.market_scope["spot_only_no_margin_no_leverage"] is True
    assert report.live_risk_adr["status"] == "Draft"
    assert "live_risk_adr_not_accepted" in report.blockers


def test_live_readiness_blocks_continuity_required_days_below_phase6_minimum(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    _write_bundle_manifest(bundle_dir)

    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("continuity summary should not load invalid config")

    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        fail_if_loaded,
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        required_consecutive_days=1,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    config_check = next(
        check for check in report.checks if check.name == "testnet_continuity_config"
    )
    continuity_check = next(
        check for check in report.checks if check.name == "testnet_continuity"
    )
    assert report.readiness_gate_met is False
    assert report.continuity_summary is None
    assert "testnet_continuity_required_days_below_phase6_minimum" in report.blockers
    assert config_check.status == "blocked"
    assert "at least 14" in config_check.detail
    assert continuity_check.status == "blocked"
    assert "not loaded" in continuity_check.detail


def test_live_readiness_blocks_invalid_continuity_clean_hours_without_loader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    _write_bundle_manifest(bundle_dir)

    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("continuity summary should not load invalid config")

    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        fail_if_loaded,
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        min_clean_hours_per_day=0,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    config_check = next(
        check for check in report.checks if check.name == "testnet_continuity_config"
    )
    assert report.readiness_gate_met is False
    assert report.continuity_summary is None
    assert "testnet_continuity_min_clean_hours_invalid" in report.blockers
    assert config_check.status == "blocked"
    assert "finite and > 0" in config_check.detail


def test_live_readiness_blocks_non_finite_capital_and_leverage_with_strict_json(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=float("nan"),
        max_leverage=float("inf"),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert "starting_capital_not_finite" in report.blockers
    assert "leverage_must_be_finite" in report.blockers
    assert report.capital_plan["starting_capital_usdt"] is None
    assert report.market_scope["max_leverage"] is None
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_blocks_non_text_identity_and_market_type(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source=object(),
        model_version=object(),
        starting_capital_usdt=100,
        market_type=object(),
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert report.source is None
    assert report.model_version is None
    assert "source_not_declared" in report.blockers
    assert "market_type_must_be_text" in report.blockers
    assert report.market_scope["market_type"] is None
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_blocks_invalid_generated_at_ns_with_strict_json(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=float("nan"),
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert report.generated_at_ns is None
    assert "generated_at_ns_invalid" in report.blockers
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_blocks_non_boolean_margin_flag(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        starting_capital_usdt=100,
        margin_enabled=0,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert "margin_enabled_must_be_boolean" in report.blockers
    assert report.market_scope["margin_enabled"] is None
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_blocks_blank_source_identity(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="   ",
        model_version="\t",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    source_check = next(check for check in report.checks if check.name == "source_model")
    assert report.readiness_gate_met is False
    assert "source_not_declared" in report.blockers
    assert source_check.status == "blocked"
    assert "Source must be explicitly declared" in source_check.detail
    assert report.live_promotion_review is None


def test_live_readiness_blocks_blank_model_identity(tmp_path: Path) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Draft")

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[],
        source="freqai_linear_v1",
        model_version="\t",
        starting_capital_usdt=100,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    source_check = next(check for check in report.checks if check.name == "source_model")
    assert report.readiness_gate_met is False
    assert "model_version_not_declared" in report.blockers
    assert source_check.status == "blocked"
    assert "Model version must be explicitly declared" in source_check.detail
    assert report.live_promotion_review is None


def test_live_readiness_can_emit_markdown_when_all_evidence_is_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    manifest = _write_bundle_manifest(bundle_dir)
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    markdown = live_readiness.render_markdown_report(report)

    assert report.readiness_gate_met is True
    assert report.live_trading_allowed is False
    assert report.recommendation == "ready_for_manual_live_go_no_go_review"
    assert report.live_promotion_review is not None
    assert report.live_promotion_review["accepted"] is True
    assert report.live_promotion_review["path"] == str(promotion)
    assert len(report.live_promotion_review["sha256"]) == 64
    assert report.project_status["sha256"] == hashlib.sha256(
        status_path.read_bytes()
    ).hexdigest()
    assert report.live_risk_adr["sha256"] == hashlib.sha256(
        live_adr.read_bytes()
    ).hexdigest()
    assert report.continuity_artifacts == [
        {
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(manifest),
            "exists": True,
            "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
    ]
    assert report.market_scope["spot_only_no_margin_no_leverage"] is True
    assert "# Phase 6 Live Readiness" in markdown
    assert "live_trading_allowed: false" in markdown
    assert "| live_risk_adr | ok |" in markdown


def test_live_readiness_blocks_imprecise_live_promotion_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_bundle_manifest(bundle_dir)
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(
        _live_promotion_text(
            current_stage="paper_simulated",
            target_stage="testnet_canary",
            rationale=(
                "This rationale mentions live_canary and testnet_canary, but "
                "the structured stage fields are not the live transition."
            ),
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.readiness_gate_met is False
    assert "live_canary_promotion_review_invalid" in report.blockers
    source_check = next(check for check in report.checks if check.name == "source_model")
    assert "current_stage" in source_check.detail
    assert "target_stage" in source_check.detail


def test_live_readiness_blocks_invalid_utf8_live_promotion_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_bundle_manifest(bundle_dir)
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )
    encoded = json.dumps(asdict(report), allow_nan=False, sort_keys=True)

    assert report.readiness_gate_met is False
    assert "live_canary_promotion_review_invalid" in report.blockers
    assert report.live_promotion_review is not None
    assert report.live_promotion_review["sha256"] == hashlib.sha256(
        b"\xff\xfe"
    ).hexdigest()
    assert report.live_promotion_review["decode_error"]
    assert report.live_promotion_review["problems"] == ["invalid_utf8"]
    assert "NaN" not in encoded
    assert "Infinity" not in encoded


def test_live_readiness_blocks_missing_continuity_manifest_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-without-manifest"
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.readiness_gate_met is False
    assert "testnet_continuity_artifact_fingerprint_missing" in report.blockers
    assert report.continuity_artifacts == [
        {
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(bundle_dir / "run_manifest.json"),
            "exists": False,
            "sha256": None,
        }
    ]


def test_live_readiness_blocks_dirty_git_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_bundle_manifest(bundle_dir)
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        git_state=GitState(commit="a" * 40, dirty=True),
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.readiness_gate_met is False
    assert report.git["dirty"] is True
    assert "git_dirty" in report.blockers


def test_live_readiness_blocks_non_spot_or_leveraged_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "project-status.md"
    live_adr = tmp_path / "013-phase6-live-risk-gate.md"
    promotion = tmp_path / "live-promotion.md"
    bundle_dir = tmp_path / "bundle-1"
    _write_bundle_manifest(bundle_dir)
    _write_status(status_path)
    _write_live_adr(live_adr, status="Accepted")
    promotion.write_text(_live_promotion_text(), encoding="utf-8")
    monkeypatch.setattr(
        live_readiness,
        "load_testnet_continuity_summary",
        lambda bundle_dirs, **kwargs: _continuity_summary(gate_met=True),
    )

    report = live_readiness.build_live_readiness_report(
        project_status_path=status_path,
        live_risk_adr_path=live_adr,
        continuity_bundle_dirs=[bundle_dir],
        source="freqai_linear_v1",
        model_version="linear-mom-train20240105",
        live_promotion_review_path=promotion,
        starting_capital_usdt=250,
        market_type="margin",
        margin_enabled=True,
        max_leverage=2.0,
        git_state=GIT_CLEAN,
        generated_at_ns=REFERENCE_TS_NS,
    )

    assert report.readiness_gate_met is False
    assert report.market_scope["spot_only_no_margin_no_leverage"] is False
    assert "market_type_must_be_spot" in report.blockers
    assert "margin_must_be_disabled" in report.blockers
    assert "leverage_must_be_one" in report.blockers


def test_live_readiness_cli_outputs_json(tmp_path: Path, capsys) -> None:
    status_path = tmp_path / "project-status.md"
    _write_status(status_path)

    rc = live_readiness.main(
        [
            "--project-status-path",
            str(status_path),
            "--live-risk-adr-path",
            str(tmp_path / "missing.md"),
            "--source",
            "freqai_linear_v1",
            "--model-version",
            "linear-mom-train20240105",
            "--starting-capital-usdt",
            "100",
        ]
    )

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema_version"] == "phase6.live_readiness.v1"
    assert out["live_trading_allowed"] is False
    assert "testnet_continuity_evidence_missing" in out["blockers"]

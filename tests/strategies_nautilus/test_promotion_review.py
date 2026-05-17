"""Tests for ADR-007 §2.6 promotion review tooling."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.strategies_nautilus.result_schema import SCHEMA_VERSION
from apps.strategies_nautilus.runners.backtest_runner import _write_parquet
from apps.strategies_nautilus.runners.promotion_review import (
    DECISION_DEMOTE,
    DECISION_DISABLE,
    DECISION_HOLD,
    DECISION_PROMOTE,
    PAPER_SHADOW_MIN_DAYS,
    STAGE_LIVE_CANARY,
    STAGE_PAPER_SHADOW,
    STAGE_PAPER_SIMULATED,
    STAGE_TESTNET_CANARY,
    PolicyFields,
    build_promotion_review,
    main,
    render_markdown,
)

RUN_ID = "20260101-000000Z-00000000"
SOURCE = "freqai_linear_v1"
MODEL_VERSION = "linear-mom-train20240105"


def _lineage_row(signal_id: str, *, decision: str, reason: str) -> dict:
    return {
        "signal_id": signal_id,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "ts_event": 1_704_067_200_000_000_000,
        "decision": decision,
        "reason": reason,
        "order_ids": "",
        "fill_ids": "",
        "position_id": "",
        "ts_decision": 1_704_067_200_000_000_000,
    }


def _make_bundle(
    tmp_path: Path,
    *,
    bundle_name: str = RUN_ID,
    manifest_overrides: dict | None = None,
    runtime_overrides: dict | None = None,
    lineage_rows: list[dict] | None = None,
    order_rows: list[dict] | None = None,
    fill_rows: list[dict] | None = None,
    position_rows: list[dict] | None = None,
    policies: list[dict] | None = None,
    backtest_start: str = "2024-01-01T00:00:00.000Z",
    backtest_end: str = "2024-01-07T23:59:00.000Z",
) -> Path:
    bundle_dir = tmp_path / bundle_name
    bundle_dir.mkdir()
    lineage_rows = (
        lineage_rows
        if lineage_rows is not None
        else [
            _lineage_row("s1", decision="target_long", reason="dry_run"),
            _lineage_row("s2", decision="target_long", reason="dry_run"),
        ]
    )
    order_rows = order_rows or []
    fill_rows = fill_rows or []
    position_rows = position_rows or []
    account_rows = [
        {
            "ts_event": 1_704_067_140_000_000_000,
            "venue": "BINANCE",
            "account_id": "BINANCE-PAPER",
            "currency": "USDT",
            "total": 100_000.0,
            "free": 100_000.0,
            "locked": 0.0,
        }
    ]
    runtime = {
        "mode": "paper",
        "data_mode": "catalog_polling",
        "order_mode": "simulated",
        "heartbeat_interval_seconds": 30,
        "max_signal_lag_seconds": 120,
        "operator": "pytest",
    }
    if runtime_overrides:
        runtime.update(runtime_overrides)
    default_policies = [
        {
            "source": SOURCE,
            "model_version": MODEL_VERSION,
            "position_pct_multiplier": 0.2,
            "min_confidence_override": None,
            "dry_run": True,
        }
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": bundle_name,
        "kind": "paper",
        "trader_id": "PAPER_TRADER-001",
        "machine_id": "pytest",
        "git_commit": "0" * 40,
        "git_dirty": False,
        "nautilus_version": "1.226.0",
        "python_version": "3.12.0",
        "started_at": "2026-01-01T00:00:00.000Z",
        "finished_at": "2026-01-01T00:00:01.000Z",
        "elapsed_seconds": 1.0,
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
        "venues": ["BINANCE"],
        "instruments": ["BTCUSDT.BINANCE"],
        "strategies": [
            {
                "name": "baseline_signal_strategy",
                "params": {
                    "min_confidence": 0.5,
                    "max_position_pct": 0.05,
                    "daily_drawdown_stop_pct": 0.05,
                    "trade_size": "0.001",
                    "seed": 0,
                    "policies": policies if policies is not None else default_policies,
                },
            }
        ],
        "risk_rules": [
            {"name": "daily_drawdown_stop", "params": {"max_pct": 0.05}},
            {"name": "max_signal_lag", "params": {"max_seconds": 120}},
        ],
        "signal_source": {
            "store_path": "data/bridge/signals.db",
            "store_sha256": "a" * 64,
            "filter": {"source": SOURCE, "model_version": MODEL_VERSION},
            "row_count": len(lineage_rows),
            "min_ts_event_ns": 1_704_067_200_000_000_000,
            "max_ts_event_ns": 1_704_067_260_000_000_000,
        },
        "data_catalog": {
            "path": "data/catalog",
            "instruments": [
                {
                    "id": "BTCUSDT.BINANCE",
                    "bars": "BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL",
                    "rows": 10080,
                }
            ],
        },
        "totals": {
            "iterations": 10080,
            "events": len(lineage_rows),
            "orders": len(order_rows),
            "positions": len(position_rows),
            "fills": len(fill_rows),
        },
        "stats_pnls": {
            "USDT": {
                "PnL (total)": 0.0,
                "PnL% (total)": 0.0,
                "Win Rate": None,
                "Expectancy": None,
                "Max Drawdown (Pct)": -0.01,
                "Max Drawdown (Abs)": -10.0,
            }
        },
        "stats_returns": {
            "max_drawdown": -0.01,
            "max_drawdown_abs": -10.0,
        },
        "runtime": runtime,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (bundle_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_parquet(pd.DataFrame(order_rows), bundle_dir / "orders.parquet")
    _write_parquet(pd.DataFrame(fill_rows), bundle_dir / "fills.parquet")
    _write_parquet(pd.DataFrame(position_rows), bundle_dir / "positions.parquet")
    _write_parquet(pd.DataFrame(account_rows), bundle_dir / "account_balances.parquet")
    _write_parquet(pd.DataFrame(lineage_rows), bundle_dir / "signal_lineage.parquet")
    return bundle_dir


SHADOW_POLICY = PolicyFields(
    dry_run=True,
    position_pct_multiplier=0.2,
    min_confidence_override=None,
)
SIMULATED_POLICY = PolicyFields(
    dry_run=False,
    position_pct_multiplier=0.2,
    min_confidence_override=None,
)
DISABLED_POLICY = PolicyFields(
    dry_run=True,
    position_pct_multiplier=0.0,
    min_confidence_override=None,
)


def test_hold_review_passes_with_clean_dry_run_bundle(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SHADOW,
        current_policy=SHADOW_POLICY,
        target_policy=SHADOW_POLICY,
        decision=DECISION_HOLD,
        rationale="freqai_linear_v1 still under sample threshold; keep dry-run.",
        operator="nishiki",
    )

    assert review.decision == DECISION_HOLD
    assert review.decision_allowed is True
    assert review.review_blockers == []
    assert review.promotion_gate_blockers == []
    assert review.policy_diff == {}
    assert review.bundle_policy_matches_current is True
    assert review.bundle_policy_mismatches == []
    assert review.runtime_mode == "paper"
    assert review.runtime_data_mode == "catalog_polling"
    assert review.runtime_order_mode == "simulated"
    assert review.source == SOURCE
    assert review.model_version == MODEL_VERSION


def test_hold_rejects_mismatched_target_policy(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SHADOW,
        current_policy=SHADOW_POLICY,
        target_policy=PolicyFields(
            dry_run=True,
            position_pct_multiplier=0.1,
            min_confidence_override=None,
        ),
        decision=DECISION_HOLD,
        rationale="testing hold mismatch",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        reason.startswith("hold_requires_identical_policies")
        for reason in review.promotion_gate_blockers
    )


def test_promote_passes_with_sufficient_evidence(tmp_path):
    lineage_rows = [
        _lineage_row(f"s{i}", decision="target_long", reason="dry_run")
        for i in range(2)
    ]
    bundle_dir = _make_bundle(tmp_path, lineage_rows=lineage_rows)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="7 days of clean shadow runtime; ready to enable simulated orders.",
        operator="nishiki",
    )

    assert review.decision_allowed is True
    assert review.session_days_inclusive >= PAPER_SHADOW_MIN_DAYS
    assert review.policy_diff == {
        "dry_run": {"current": True, "target": False}
    }
    assert review.promotion_gate_blockers == []


def test_promote_rejects_when_evidence_below_threshold(tmp_path):
    bundle_dir = _make_bundle(
        tmp_path,
        backtest_start="2024-01-01T00:00:00.000Z",
        backtest_end="2024-01-03T23:59:00.000Z",  # 3 days < 7
        lineage_rows=[
            _lineage_row("s1", decision="target_long", reason="dry_run"),
        ],
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="trying premature promotion",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        reason.startswith("promote_evidence_below_adr007_threshold")
        for reason in review.promotion_gate_blockers
    )


def test_promote_rejects_when_policy_diff_empty(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SHADOW_POLICY,  # no diff
        decision=DECISION_PROMOTE,
        rationale="policy diff missing",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        reason.startswith("promote_requires_explicit_policy_diff")
        for reason in review.promotion_gate_blockers
    )


def test_promote_rejects_when_bundle_policy_mismatches_current(tmp_path):
    # Bundle's recorded policy says dry_run=False, but operator claims
    # current_policy is dry_run=True. This is the "different runtime than
    # claimed" case.
    bundle_dir = _make_bundle(
        tmp_path,
        policies=[
            {
                "source": SOURCE,
                "model_version": MODEL_VERSION,
                "position_pct_multiplier": 0.2,
                "min_confidence_override": None,
                "dry_run": False,
            }
        ],
        lineage_rows=[
            _lineage_row("s1", decision="target_long", reason=""),
        ],
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="bundle policy mismatch",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        "bundle_policy_mismatch" in reason
        for reason in review.promotion_gate_blockers
    )


def test_promote_rejects_when_target_stage_skips_levels(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_TESTNET_CANARY,  # skip paper_simulated
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="trying to skip a stage",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        reason.startswith("promote_stage_transition_invalid")
        for reason in review.promotion_gate_blockers
    )


def test_promote_rejects_target_beyond_phase_2_limit(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_TESTNET_CANARY,
        target_stage=STAGE_LIVE_CANARY,
        current_policy=SIMULATED_POLICY,
        target_policy=PolicyFields(
            dry_run=False,
            position_pct_multiplier=0.1,
            min_confidence_override=None,
        ),
        decision=DECISION_PROMOTE,
        rationale="should be blocked by phase 3 gate",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        reason.startswith("phase_3_not_ready")
        for reason in review.promotion_gate_blockers
    )


def test_promote_rejects_when_git_dirty(tmp_path):
    bundle_dir = _make_bundle(
        tmp_path,
        manifest_overrides={"git_dirty": True},
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="dirty repo should not promote",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert "git_dirty" in review.review_blockers
    assert any(
        reason == "review_blocker:git_dirty" for reason in review.decision_reasons
    )


def test_promote_rejects_when_review_blockers_present(tmp_path):
    # Use lineage with kill_switch reason — propagated into review_blockers
    # by report_paper_bundle.
    bundle_dir = _make_bundle(
        tmp_path,
        lineage_rows=[
            _lineage_row("k1", decision="skip", reason="kill_switch: daily_drawdown"),
        ],
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SIMULATED,
        current_policy=SHADOW_POLICY,
        target_policy=SIMULATED_POLICY,
        decision=DECISION_PROMOTE,
        rationale="kill switch fired; should not promote",
        operator="nishiki",
    )

    assert review.decision_allowed is False
    assert any(
        "kill_switch_signals" in blocker for blocker in review.review_blockers
    )


def test_demote_passes_when_target_stricter(tmp_path):
    bundle_dir = _make_bundle(
        tmp_path,
        policies=[
            {
                "source": SOURCE,
                "model_version": MODEL_VERSION,
                "position_pct_multiplier": 0.2,
                "min_confidence_override": None,
                "dry_run": False,
            }
        ],
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SIMULATED,
        target_stage=STAGE_PAPER_SHADOW,
        current_policy=SIMULATED_POLICY,
        target_policy=SHADOW_POLICY,
        decision=DECISION_DEMOTE,
        rationale="rolling back to shadow after issue",
        operator="nishiki",
    )

    assert review.decision_allowed is True
    assert review.promotion_gate_blockers == []


def test_disable_always_allowed_even_with_blockers(tmp_path):
    bundle_dir = _make_bundle(
        tmp_path,
        manifest_overrides={"git_dirty": True},
        lineage_rows=[
            _lineage_row("k1", decision="skip", reason="kill_switch: daily_drawdown"),
        ],
    )

    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SIMULATED,
        target_stage=STAGE_PAPER_SHADOW,
        current_policy=SIMULATED_POLICY,
        target_policy=DISABLED_POLICY,
        decision=DECISION_DISABLE,
        rationale="emergency disable after kill-switch",
        operator="nishiki",
    )

    assert review.decision_allowed is True
    # The bundle's review issues are still surfaced for audit, but they
    # don't block disabling.
    assert any(
        reason.startswith("review_blocker:") for reason in review.decision_reasons
    )


def test_build_review_rejects_blank_rationale(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    with pytest.raises(ValueError, match="rationale"):
        build_promotion_review(
            bundle_dir=bundle_dir,
            current_stage=STAGE_PAPER_SHADOW,
            target_stage=STAGE_PAPER_SHADOW,
            current_policy=SHADOW_POLICY,
            target_policy=SHADOW_POLICY,
            decision=DECISION_HOLD,
            rationale="   ",
            operator="nishiki",
        )


def test_build_review_rejects_blank_operator(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    with pytest.raises(ValueError, match="operator"):
        build_promotion_review(
            bundle_dir=bundle_dir,
            current_stage=STAGE_PAPER_SHADOW,
            target_stage=STAGE_PAPER_SHADOW,
            current_policy=SHADOW_POLICY,
            target_policy=SHADOW_POLICY,
            decision=DECISION_HOLD,
            rationale="operator missing",
            operator="",
        )


def test_render_markdown_contains_seven_sections(tmp_path):
    bundle_dir = _make_bundle(tmp_path)
    review = build_promotion_review(
        bundle_dir=bundle_dir,
        current_stage=STAGE_PAPER_SHADOW,
        target_stage=STAGE_PAPER_SHADOW,
        current_policy=SHADOW_POLICY,
        target_policy=SHADOW_POLICY,
        decision=DECISION_HOLD,
        rationale="hold for retro template",
        operator="nishiki",
    )

    md = render_markdown(review)

    for header in (
        "## 1. Source / model",
        "## 2. Current vs target policy",
        "## 3. Bundle path / manifest fingerprint",
        "## 4. Signals & lineage",
        "## 5. Execution outcome",
        "## 6. Runtime hygiene",
        "## 7. Conclusion",
    ):
        assert header in md
    assert "decision: **HOLD**" in md
    assert "decision_allowed: **yes**" in md
    assert "(no fields differ — policies are identical)" in md


def test_cli_writes_json_and_markdown(tmp_path, capsys):
    bundle_dir = _make_bundle(tmp_path)
    json_path = tmp_path / "out" / "review.json"
    md_path = tmp_path / "out" / "review.md"

    rc = main(
        [
            str(bundle_dir),
            "--current-stage",
            STAGE_PAPER_SHADOW,
            "--target-stage",
            STAGE_PAPER_SHADOW,
            "--current-dry-run",
            "--current-position-pct-multiplier",
            "0.2",
            "--target-dry-run",
            "--target-position-pct-multiplier",
            "0.2",
            "--decision",
            DECISION_HOLD,
            "--operator",
            "nishiki",
            "--rationale",
            "hold via CLI",
            "--output-json",
            str(json_path),
            "--output-markdown",
            str(md_path),
        ]
    )

    assert rc == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["decision"] == DECISION_HOLD
    assert payload["decision_allowed"] is True
    assert payload["source"] == SOURCE
    md = md_path.read_text(encoding="utf-8")
    assert "## 7. Conclusion" in md
    out = capsys.readouterr().out
    assert "decision: hold (allowed=True)" in out


def test_cli_returns_nonzero_when_decision_disallowed(tmp_path):
    bundle_dir = _make_bundle(
        tmp_path,
        manifest_overrides={"git_dirty": True},
    )

    rc = main(
        [
            str(bundle_dir),
            "--current-stage",
            STAGE_PAPER_SHADOW,
            "--target-stage",
            STAGE_PAPER_SIMULATED,
            "--current-dry-run",
            "--current-position-pct-multiplier",
            "0.2",
            "--target-no-dry-run",
            "--target-position-pct-multiplier",
            "0.2",
            "--decision",
            DECISION_PROMOTE,
            "--operator",
            "nishiki",
            "--rationale",
            "should fail because git_dirty",
        ]
    )

    assert rc == 1


def test_cli_rejects_invalid_decision(tmp_path):
    bundle_dir = _make_bundle(tmp_path)

    with pytest.raises(SystemExit):
        main(
            [
                str(bundle_dir),
                "--current-stage",
                STAGE_PAPER_SHADOW,
                "--target-stage",
                STAGE_PAPER_SHADOW,
                "--current-dry-run",
                "--current-position-pct-multiplier",
                "0.2",
                "--target-dry-run",
                "--target-position-pct-multiplier",
                "0.2",
                "--decision",
                "approve",  # not in ALL_DECISIONS
                "--operator",
                "nishiki",
                "--rationale",
                "bad decision name",
            ]
        )

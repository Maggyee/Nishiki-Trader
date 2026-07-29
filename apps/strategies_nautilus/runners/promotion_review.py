"""Generate an ADR-007 §2.6 promotion review record from a runtime bundle.

This tool packages a paper or testnet bundle into the seven review sections
required by ADR-007 §2.6 and validates whether the operator's intended
``SourcePolicy`` change is allowed under the ADR-007 §2.5 stage table.

It is consumer-side only:

- It never mutates ``SourcePolicy``, never starts a runtime, never talks to
  an exchange, and never reads exchange credentials.
- Running this tool with ``--decision promote`` does not promote anything.
  It produces an audit artifact and reports whether the requested transition
  passes the hard gates. Applying the policy change is a separate manual
  step.

Inputs (CLI):
    bundle_dir, --current-stage, --target-stage,
    --current-policy / --target-policy fields,
    --decision (promote|hold|demote|disable),
    --rationale, --operator,
    optional --output-json / --output-markdown.

Outputs:
    JSON, Markdown, or text summary of the §2.6 sections plus
    ``decision_allowed`` and ``decision_reasons`` explaining whether the
    requested transition passes ADR-007 gates.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.strategies_nautilus.runners.promotion_review_artifact import (
    evaluate_testnet_canary_policy_review,
)
from apps.strategies_nautilus.runners.report_paper_bundle import (
    PaperBundleReport,
    load_paper_bundle_report,
)
from apps.strategies_nautilus.runners.report_testnet_bundle import (
    TestnetBundleReport,
    load_testnet_bundle_report,
)

STAGE_BACKTEST_BASELINE = "backtest_baseline"
STAGE_PAPER_SHADOW = "paper_shadow"
STAGE_PAPER_SIMULATED = "paper_simulated"
STAGE_TESTNET_CANARY = "testnet_canary"
STAGE_LIVE_CANARY = "live_canary"
STAGE_LIVE_NORMAL = "live_normal"

STAGE_ORDER: tuple[str, ...] = (
    STAGE_BACKTEST_BASELINE,
    STAGE_PAPER_SHADOW,
    STAGE_PAPER_SIMULATED,
    STAGE_TESTNET_CANARY,
    STAGE_LIVE_CANARY,
    STAGE_LIVE_NORMAL,
)

# Hard ceiling on which ``target_stage`` this tool will allow without an
# explicit ADR-spec follow-up. After ADR-008 §6.6 Phase 3f stability soak
# landed, the ceiling moved from ``paper_simulated`` to ``testnet_canary``;
# anything beyond (live_canary / live_normal) still requires Phase 4 live
# trading ADRs, which the project explicitly has not written yet. The
# constant name is retained for ADR-008 §8 reference compatibility.
PHASE_2_STAGE_LIMIT = STAGE_TESTNET_CANARY

# Per-stage upper bounds for ``SourcePolicy`` (ADR-007 §2.5).
#
# - ``dry_run_required``: ``True`` means policy must be dry-run, ``False``
#   means policy must NOT be dry-run, ``None`` means no constraint.
# - ``max_multiplier``: hard upper bound on
#   ``position_pct_multiplier`` for that stage.
STAGE_BOUNDS: dict[str, dict[str, Any]] = {
    STAGE_BACKTEST_BASELINE: {"dry_run_required": None, "max_multiplier": 1.0},
    STAGE_PAPER_SHADOW: {"dry_run_required": True, "max_multiplier": 0.2},
    STAGE_PAPER_SIMULATED: {"dry_run_required": False, "max_multiplier": 0.2},
    STAGE_TESTNET_CANARY: {"dry_run_required": False, "max_multiplier": 0.2},
    STAGE_LIVE_CANARY: {"dry_run_required": False, "max_multiplier": 0.1},
    STAGE_LIVE_NORMAL: {"dry_run_required": False, "max_multiplier": 1.0},
}

DECISION_PROMOTE = "promote"
DECISION_HOLD = "hold"
DECISION_DEMOTE = "demote"
DECISION_DISABLE = "disable"
ALL_DECISIONS = (DECISION_PROMOTE, DECISION_HOLD, DECISION_DEMOTE, DECISION_DISABLE)

# ADR-007 §2.5 evidence threshold for paper_shadow → paper_simulated.
PAPER_SHADOW_MIN_SIGNALS = 50
PAPER_SHADOW_MIN_DAYS = 7


@dataclass(frozen=True)
class PolicyFields:
    """Minimal explicit ``SourcePolicy`` snapshot used in the review record."""

    dry_run: bool
    position_pct_multiplier: float
    min_confidence_override: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "position_pct_multiplier": self.position_pct_multiplier,
            "min_confidence_override": self.min_confidence_override,
        }


@dataclass(frozen=True)
class TestnetReviewBundleReport:
    """Testnet evidence normalized to the paper-review field contract."""

    bundle_dir: str
    run_id: str
    manifest_sha256: str
    kind: str
    git_commit: str
    git_dirty: bool
    runtime: dict[str, Any]
    source: str | None
    model_version: str | None
    signal_rows: int
    session_days_inclusive: int
    matching_policy: dict[str, Any] | None
    totals: dict[str, int]
    decision_counts: dict[str, int]
    reason_counts: dict[str, int]
    accepted_signals: int
    skipped_signals: int
    dry_run_signals: int
    expired_signals: int
    unauthorized_signals: int
    signal_lag_signals: int
    kill_switch_signals: int
    data_gap_signals: int
    runtime_data_gaps: int
    heartbeat_count: int
    restart_sequence: int
    previous_run_id: str | None
    pnl_total_by_currency: dict[str, float | int | None]
    max_drawdown_pct_by_currency: dict[str, float | int | None]
    max_drawdown_abs_by_currency: dict[str, float | int | None]
    missing_metrics: list[str]
    review_blockers: list[str]
    promotion_blockers: list[str]


ReviewBundleReport = PaperBundleReport | TestnetReviewBundleReport


@dataclass(frozen=True)
class LoadedReviewBundle:
    report: ReviewBundleReport
    policy_evidence_path: str
    policy_evidence_sha256: str


@dataclass(frozen=True)
class PromotionReview:
    """Full ADR-007 §2.6 review artifact for a single source/model bundle."""

    # Section 1: source / model
    source: str | None
    model_version: str | None

    # Section 2: current vs target policy
    current_stage: str
    target_stage: str
    current_policy: dict[str, Any]
    target_policy: dict[str, Any]
    policy_diff: dict[str, dict[str, Any]]
    bundle_policy_matches_current: bool
    bundle_policy_mismatches: list[str]

    # Section 3: bundle path / fingerprint
    bundle_dir: str
    run_id: str
    bundle_kind: str
    manifest_sha256: str
    git_commit: str
    git_dirty: bool
    policy_evidence_path: str
    policy_evidence_sha256: str
    runtime_mode: str | None
    runtime_data_mode: str | None
    runtime_order_mode: str | None

    # Section 4: signals & lineage
    signal_rows: int
    session_days_inclusive: int
    accepted_signals: int
    skipped_signals: int
    dry_run_signals: int
    expired_signals: int
    unauthorized_signals: int
    signal_lag_signals: int
    kill_switch_signals: int
    data_gap_signals: int
    decision_counts: dict[str, int]
    reason_counts: dict[str, int]

    # Section 5: execution outcome
    totals: dict[str, int]
    pnl_total_by_currency: dict[str, float | int | None]
    max_drawdown_pct_by_currency: dict[str, float | int | None]
    max_drawdown_abs_by_currency: dict[str, float | int | None]
    missing_metrics: list[str]
    kill_switch_fired: bool

    # Section 6: runtime hygiene
    heartbeat_count: int
    restart_sequence: int
    previous_run_id: str | None
    runtime_data_gaps: int

    # Section 7: conclusion
    review_blockers: list[str]
    promotion_gate_blockers: list[str]
    decision: str
    decision_allowed: bool
    decision_reasons: list[str]
    operator: str
    rationale: str
    generated_at: str

    # Phase 3 evidence paths (only meaningful for paper_simulated → testnet_canary)
    paper_simulated_retro_path: str | None = None
    testnet_runbook_signoff_path: str | None = None

    # Bookkeeping
    bundle_promotion_blockers: list[str] = field(default_factory=list)


def build_promotion_review(
    *,
    bundle_dir: Path,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
    decision: str,
    rationale: str,
    operator: str,
    paper_simulated_retro_path: Path | None = None,
    testnet_runbook_signoff_path: Path | None = None,
    now: datetime | None = None,
) -> PromotionReview:
    """Produce a :class:`PromotionReview` for the given bundle and inputs.

    Raises:
        ValueError: when stage names or decision are invalid, or when the
            bundle is missing / not kind=paper|testnet. The bundle loader
            handles the second case.
    """

    _validate_stage(current_stage, "current_stage")
    _validate_stage(target_stage, "target_stage")
    if decision not in ALL_DECISIONS:
        raise ValueError(f"decision must be one of {ALL_DECISIONS}, got {decision!r}")
    if not operator:
        raise ValueError("operator is required and must be non-empty")
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required and must be non-empty")

    loaded_bundle = _load_review_bundle(bundle_dir)
    report = loaded_bundle.report

    policy_diff = _policy_diff(current_policy, target_policy)
    bundle_policy_mismatches = _bundle_policy_mismatches(report, current_policy)
    bundle_policy_matches_current = not bundle_policy_mismatches

    runtime = report.runtime
    runtime_mode = _str_or_none(runtime.get("mode"))
    runtime_data_mode = _str_or_none(runtime.get("data_mode"))
    runtime_order_mode = _str_or_none(runtime.get("order_mode"))

    promotion_gate_blockers = _promotion_gate_blockers(
        report=report,
        current_stage=current_stage,
        target_stage=target_stage,
        current_policy=current_policy,
        target_policy=target_policy,
        decision=decision,
        bundle_policy_mismatches=bundle_policy_mismatches,
        policy_diff=policy_diff,
        paper_simulated_retro_path=paper_simulated_retro_path,
        testnet_runbook_signoff_path=testnet_runbook_signoff_path,
    )

    decision_allowed, decision_reasons = _decision_outcome(
        decision=decision,
        review_blockers=report.review_blockers,
        promotion_gate_blockers=promotion_gate_blockers,
    )

    generated_at = (now or datetime.now(tz=UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")

    return PromotionReview(
        source=report.source,
        model_version=report.model_version,
        current_stage=current_stage,
        target_stage=target_stage,
        current_policy=current_policy.to_dict(),
        target_policy=target_policy.to_dict(),
        policy_diff=policy_diff,
        bundle_policy_matches_current=bundle_policy_matches_current,
        bundle_policy_mismatches=bundle_policy_mismatches,
        bundle_dir=report.bundle_dir,
        run_id=report.run_id,
        bundle_kind=report.kind,
        manifest_sha256=report.manifest_sha256,
        git_commit=report.git_commit,
        git_dirty=report.git_dirty,
        policy_evidence_path=loaded_bundle.policy_evidence_path,
        policy_evidence_sha256=loaded_bundle.policy_evidence_sha256,
        runtime_mode=runtime_mode,
        runtime_data_mode=runtime_data_mode,
        runtime_order_mode=runtime_order_mode,
        signal_rows=report.signal_rows,
        session_days_inclusive=report.session_days_inclusive,
        accepted_signals=report.accepted_signals,
        skipped_signals=report.skipped_signals,
        dry_run_signals=report.dry_run_signals,
        expired_signals=report.expired_signals,
        unauthorized_signals=report.unauthorized_signals,
        signal_lag_signals=report.signal_lag_signals,
        kill_switch_signals=report.kill_switch_signals,
        data_gap_signals=report.data_gap_signals,
        decision_counts=dict(report.decision_counts),
        reason_counts=dict(report.reason_counts),
        totals=dict(report.totals),
        pnl_total_by_currency=dict(report.pnl_total_by_currency),
        max_drawdown_pct_by_currency=dict(report.max_drawdown_pct_by_currency),
        max_drawdown_abs_by_currency=dict(report.max_drawdown_abs_by_currency),
        missing_metrics=list(report.missing_metrics),
        kill_switch_fired=report.kill_switch_signals > 0,
        heartbeat_count=report.heartbeat_count,
        restart_sequence=report.restart_sequence,
        previous_run_id=report.previous_run_id,
        runtime_data_gaps=report.runtime_data_gaps,
        review_blockers=list(report.review_blockers),
        promotion_gate_blockers=promotion_gate_blockers,
        decision=decision,
        decision_allowed=decision_allowed,
        decision_reasons=decision_reasons,
        operator=operator,
        rationale=rationale.strip(),
        generated_at=generated_at,
        paper_simulated_retro_path=(
            str(paper_simulated_retro_path)
            if paper_simulated_retro_path is not None
            else None
        ),
        testnet_runbook_signoff_path=(
            str(testnet_runbook_signoff_path)
            if testnet_runbook_signoff_path is not None
            else None
        ),
        bundle_promotion_blockers=list(report.promotion_blockers),
    )


def render_markdown(review: PromotionReview) -> str:
    """Render the review as the docs/retros/ ADR-007 §2.6 Markdown form."""

    source_key = f"{review.source or 'unknown'} / {review.model_version or 'unknown'}"
    decision_label = review.decision.upper()
    allowed_label = "yes" if review.decision_allowed else "no"
    blockers = (
        ", ".join(review.review_blockers) if review.review_blockers else "none"
    )
    promotion_blockers = (
        ", ".join(review.promotion_gate_blockers)
        if review.promotion_gate_blockers
        else "none"
    )
    decision_reasons = (
        "\n".join(f"- {reason}" for reason in review.decision_reasons)
        if review.decision_reasons
        else "- (no automated reasons recorded)"
    )
    diff_lines = _format_policy_diff(review.policy_diff)
    bundle_mismatch_lines = (
        "\n".join(f"- {item}" for item in review.bundle_policy_mismatches)
        if review.bundle_policy_mismatches
        else "- (bundle policy matches current_policy)"
    )

    lines = [
        f"# Promotion review — {source_key}",
        "",
        f"- **Date (UTC)**: {review.generated_at}",
        f"- **Operator**: {review.operator}",
        f"- **Decision**: {decision_label}",
        f"- **Decision allowed by gates**: {allowed_label}",
        "",
        "## 1. Source / model",
        "",
        f"- source: `{review.source}`",
        f"- model_version: `{review.model_version}`",
        "",
        "## 2. Current vs target policy",
        "",
        f"- current_stage: `{review.current_stage}`",
        f"- target_stage: `{review.target_stage}`",
        "- current_policy: "
        f"dry_run={review.current_policy['dry_run']}, "
        f"position_pct_multiplier={review.current_policy['position_pct_multiplier']}, "
        "min_confidence_override="
        f"{review.current_policy['min_confidence_override']}",
        "- target_policy: "
        f"dry_run={review.target_policy['dry_run']}, "
        f"position_pct_multiplier={review.target_policy['position_pct_multiplier']}, "
        "min_confidence_override="
        f"{review.target_policy['min_confidence_override']}",
        "- policy_diff:",
        *diff_lines,
        f"- bundle_policy_matches_current: {review.bundle_policy_matches_current}",
        "- bundle_policy_mismatches:",
        bundle_mismatch_lines,
        "",
        "## 3. Bundle path / manifest fingerprint",
        "",
        f"- bundle_dir: `{review.bundle_dir}`",
        f"- run_id: `{review.run_id}`",
        f"- bundle_kind: `{review.bundle_kind}`",
        f"- manifest_sha256: `{review.manifest_sha256}`",
        f"- git_commit: `{review.git_commit}`",
        f"- git_dirty: {review.git_dirty}",
        f"- policy_evidence_path: `{review.policy_evidence_path}`",
        f"- policy_evidence_sha256: `{review.policy_evidence_sha256}`",
        "- runtime: "
        f"mode={review.runtime_mode}, "
        f"data_mode={review.runtime_data_mode}, "
        f"order_mode={review.runtime_order_mode}",
        "",
        "## 3a. Phase 3 evidence paths",
        "",
        "- paper_simulated_retro_path: "
        f"`{review.paper_simulated_retro_path or 'none'}`",
        "- testnet_runbook_signoff_path: "
        f"`{review.testnet_runbook_signoff_path or 'none'}`",
        "",
        "## 4. Signals & lineage",
        "",
        f"- signal_rows: {review.signal_rows}",
        f"- session_days_inclusive: {review.session_days_inclusive}",
        f"- accepted: {review.accepted_signals}",
        f"- skipped: {review.skipped_signals}",
        f"- dry_run: {review.dry_run_signals}",
        f"- expired: {review.expired_signals}",
        f"- unauthorized: {review.unauthorized_signals}",
        f"- signal_lag: {review.signal_lag_signals}",
        f"- kill_switch: {review.kill_switch_signals}",
        f"- data_gap_signals: {review.data_gap_signals}",
        "- lineage decision counts: "
        f"`{json.dumps(review.decision_counts, sort_keys=True)}`",
        "- lineage reason counts: "
        f"`{json.dumps(review.reason_counts, sort_keys=True)}`",
        "",
        "## 5. Execution outcome",
        "",
        f"- totals: `{json.dumps(review.totals, sort_keys=True)}`",
        "- PnL by currency: "
        f"`{json.dumps(review.pnl_total_by_currency, sort_keys=True)}`",
        "- max_drawdown_pct: "
        f"`{json.dumps(review.max_drawdown_pct_by_currency, sort_keys=True)}`",
        "- max_drawdown_abs: "
        f"`{json.dumps(review.max_drawdown_abs_by_currency, sort_keys=True)}`",
        f"- kill_switch_fired: {review.kill_switch_fired}",
        f"- missing_metrics: {review.missing_metrics or 'none'}",
        "",
        "## 6. Runtime hygiene",
        "",
        f"- heartbeat_count: {review.heartbeat_count}",
        f"- restart_sequence: {review.restart_sequence}",
        f"- previous_run_id: {review.previous_run_id or 'none'}",
        f"- runtime_data_gaps: {review.runtime_data_gaps}",
        "",
        "## 7. Conclusion",
        "",
        f"- review_blockers: {blockers}",
        f"- promotion_gate_blockers: {promotion_blockers}",
        f"- decision: **{decision_label}**",
        f"- decision_allowed: **{allowed_label}**",
        "- decision_reasons:",
        decision_reasons,
        "",
        "### Rationale",
        "",
        review.rationale,
        "",
    ]
    return "\n".join(lines)


def render_text(review: PromotionReview) -> str:
    """Render the review as a single-screen text summary."""

    blockers = (
        ", ".join(review.review_blockers) if review.review_blockers else "none"
    )
    promotion_blockers = (
        ", ".join(review.promotion_gate_blockers)
        if review.promotion_gate_blockers
        else "none"
    )
    diff = json.dumps(review.policy_diff, sort_keys=True)
    return "\n".join(
        [
            f"source_model: {review.source} / {review.model_version}",
            f"stages: {review.current_stage} -> {review.target_stage}",
            f"decision: {review.decision} (allowed={review.decision_allowed})",
            f"operator: {review.operator}",
            f"bundle: {review.bundle_dir} run_id={review.run_id}",
            f"bundle_kind: {review.bundle_kind}",
            f"manifest_sha256: {review.manifest_sha256}",
            f"policy_evidence_path: {review.policy_evidence_path}",
            f"policy_evidence_sha256: {review.policy_evidence_sha256}",
            f"git_dirty: {review.git_dirty}",
            f"signal_rows: {review.signal_rows} "
            f"session_days_inclusive: {review.session_days_inclusive}",
            f"policy_diff: {diff}",
            f"bundle_policy_matches_current: {review.bundle_policy_matches_current}",
            f"review_blockers: {blockers}",
            f"promotion_gate_blockers: {promotion_blockers}",
            f"decision_reasons: {'; '.join(review.decision_reasons) or 'none'}",
        ]
    )


def _load_review_bundle(bundle_dir: Path) -> LoadedReviewBundle:
    manifest_path = bundle_dir / "run_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    kind = str(manifest_payload.get("kind") or "")
    if kind == "paper":
        report = load_paper_bundle_report(bundle_dir)
        return LoadedReviewBundle(
            report=report,
            policy_evidence_path=str(manifest_path),
            policy_evidence_sha256=report.manifest_sha256,
        )
    if kind == "testnet":
        testnet_report = load_testnet_bundle_report(bundle_dir)
        return _testnet_review_bundle(
            bundle_dir=bundle_dir,
            manifest_payload=manifest_payload,
            report=testnet_report,
        )
    raise ValueError(
        f"{bundle_dir} is kind={kind!r}, expected 'paper' or 'testnet'"
    )


def _testnet_review_bundle(
    *,
    bundle_dir: Path,
    manifest_payload: dict[str, Any],
    report: TestnetBundleReport,
) -> LoadedReviewBundle:
    raw_evidence_path = manifest_payload.get("stage_evidence_path")
    evidence_path = _resolve_policy_evidence_path(
        bundle_dir,
        raw_evidence_path,
    )
    evidence = evaluate_testnet_canary_policy_review(
        evidence_path,
        source=report.source,
        model_version=report.model_version,
    )
    evidence_problems = [
        f"stage_policy_evidence:{problem}"
        for problem in evidence.get("problems", [])
    ]
    matching_policy = evidence.get("policy")
    if not isinstance(matching_policy, dict):
        matching_policy = None

    decision_counts = dict(report.decision_counts)
    reason_counts = dict(report.reason_counts)
    skipped = int(decision_counts.get("skip", 0))
    kill_switch_count = _reason_prefix_count(
        reason_counts,
        ("kill_switch",),
    ) + int(report.alert_msg_counts.get("kill_switch_fired", 0))
    data_gap_count = _reason_prefix_count(
        reason_counts,
        ("data_gap",),
    )
    runtime_data_gaps = (
        _int_or_zero(report.runtime.get("data_gap_count"))
        + int(report.alert_msg_counts.get("data_gap_exceeded_tolerance", 0))
    )

    normalized = TestnetReviewBundleReport(
        bundle_dir=report.bundle_dir,
        run_id=report.run_id,
        manifest_sha256=report.manifest_sha256,
        kind=report.kind,
        git_commit=report.git_commit or "unknown",
        git_dirty=report.git_dirty,
        runtime=dict(report.runtime),
        source=report.source,
        model_version=report.model_version,
        signal_rows=report.lineage_rows,
        session_days_inclusive=_session_days_inclusive(
            report.started_at,
            report.finished_at,
        ),
        matching_policy=matching_policy,
        totals={
            "events": report.lineage_rows,
            "orders": report.order_count,
            "fills": report.fill_count,
            "positions": report.position_count,
            "account_balances": report.account_balance_rows,
        },
        decision_counts=decision_counts,
        reason_counts=reason_counts,
        accepted_signals=max(report.lineage_rows - skipped, 0),
        skipped_signals=skipped,
        dry_run_signals=int(reason_counts.get("dry_run", 0)),
        expired_signals=_reason_prefix_count(reason_counts, ("expired:",)),
        unauthorized_signals=_reason_prefix_count(
            reason_counts,
            ("reject_unauthorized",),
        ),
        signal_lag_signals=_reason_prefix_count(
            reason_counts,
            ("signal_lag",),
        ),
        kill_switch_signals=kill_switch_count,
        data_gap_signals=data_gap_count,
        runtime_data_gaps=runtime_data_gaps,
        heartbeat_count=report.heartbeat_count,
        restart_sequence=_int_or_zero(report.runtime.get("restart_sequence")),
        previous_run_id=_str_or_none(report.runtime.get("previous_run_id")),
        pnl_total_by_currency={"USDT": report.realized_pnl_total},
        max_drawdown_pct_by_currency={"USDT": None},
        max_drawdown_abs_by_currency={"USDT": None},
        missing_metrics=["max_drawdown_pct", "max_drawdown_abs"],
        review_blockers=[*report.review_blockers, *evidence_problems],
        promotion_blockers=[],
    )
    evidence_sha256 = evidence.get("sha256")
    return LoadedReviewBundle(
        report=normalized,
        policy_evidence_path=str(evidence_path),
        policy_evidence_sha256=(
            evidence_sha256 if isinstance(evidence_sha256, str) else ""
        ),
    )


def _resolve_policy_evidence_path(
    bundle_dir: Path,
    raw_path: Any,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return bundle_dir / "missing-stage-evidence"

    path = Path(raw_path)
    if path.is_absolute() or path.is_file():
        return path

    for parent in bundle_dir.resolve().parents:
        candidate = parent / path
        if candidate.is_file():
            return candidate
    return path


def _session_days_inclusive(
    started_at: str | None,
    finished_at: str | None,
) -> int:
    if not started_at or not finished_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max((finish.date() - start.date()).days + 1, 0)


def _reason_prefix_count(
    reason_counts: dict[str, int],
    prefixes: tuple[str, ...],
) -> int:
    return sum(
        int(count)
        for reason, count in reason_counts.items()
        if reason.startswith(prefixes)
    )


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _validate_stage(stage: str, label: str) -> None:
    if stage not in STAGE_ORDER:
        raise ValueError(
            f"{label} must be one of {STAGE_ORDER}, got {stage!r}"
        )


def _policy_diff(
    current: PolicyFields,
    target: PolicyFields,
) -> dict[str, dict[str, Any]]:
    diff: dict[str, dict[str, Any]] = {}
    for field_name in ("dry_run", "position_pct_multiplier", "min_confidence_override"):
        cur = getattr(current, field_name)
        tgt = getattr(target, field_name)
        if cur != tgt:
            diff[field_name] = {"current": cur, "target": tgt}
    return diff


def _bundle_policy_mismatches(
    report: ReviewBundleReport,
    current: PolicyFields,
) -> list[str]:
    """Verify that the bundle's recorded policy matches the supplied current_policy.

    Paper bundles record the policy directly in the manifest. Testnet bundles
    link to the exact signed promotion artifact through ``stage_evidence_path``.
    If the operator's ``current_policy`` does not match that evidence, the
    review is fundamentally untrustworthy.
    """

    matching = report.matching_policy
    if matching is None:
        return [
            "bundle_policy_missing_for_source_model: "
            "no matching SourcePolicy found in run_manifest.json"
        ]

    bundle_dry_run = bool(matching.get("dry_run", False))
    bundle_multiplier = float(matching.get("position_pct_multiplier", 1.0))
    bundle_override_raw = matching.get("min_confidence_override")
    bundle_override = (
        float(bundle_override_raw) if bundle_override_raw is not None else None
    )

    mismatches: list[str] = []
    if bundle_dry_run != current.dry_run:
        mismatches.append(
            f"dry_run: bundle={bundle_dry_run} current_policy={current.dry_run}"
        )
    if bundle_multiplier != current.position_pct_multiplier:
        mismatches.append(
            "position_pct_multiplier: "
            f"bundle={bundle_multiplier} "
            f"current_policy={current.position_pct_multiplier}"
        )
    if bundle_override != current.min_confidence_override:
        mismatches.append(
            "min_confidence_override: "
            f"bundle={bundle_override} "
            f"current_policy={current.min_confidence_override}"
        )
    return mismatches


def _promotion_gate_blockers(
    *,
    report: ReviewBundleReport,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
    decision: str,
    bundle_policy_mismatches: list[str],
    policy_diff: dict[str, dict[str, Any]],
    paper_simulated_retro_path: Path | None,
    testnet_runbook_signoff_path: Path | None,
) -> list[str]:
    """Compute promotion-specific blockers on top of bundle review_blockers.

    These blockers are the ADR-007 §2.5 stage transition rules and the
    explicit-policy-diff requirement from the user's task description.
    They are reported separately from `review_blockers` (which are
    bundle-quality issues) so the operator can tell at a glance whether
    the bundle is bad or whether the requested transition is the issue.
    """

    blockers: list[str] = []

    blockers.extend(_phase_2_stage_blockers(target_stage))
    blockers.extend(
        _bundle_match_blockers(
            bundle_policy_mismatches=bundle_policy_mismatches,
            decision=decision,
        )
    )
    blockers.extend(
        _policy_bound_blockers(
            stage=current_stage,
            policy=current_policy,
            label="current_policy",
        )
    )
    blockers.extend(
        _policy_bound_blockers(
            stage=target_stage,
            policy=target_policy,
            label="target_policy",
        )
    )

    blockers.extend(
        _decision_specific_blockers(
            decision=decision,
            current_stage=current_stage,
            target_stage=target_stage,
            current_policy=current_policy,
            target_policy=target_policy,
            policy_diff=policy_diff,
            report=report,
        )
    )

    blockers.extend(
        _testnet_canary_promote_blockers(
            decision=decision,
            current_stage=current_stage,
            target_stage=target_stage,
            current_policy=current_policy,
            target_policy=target_policy,
            source=report.source,
            paper_simulated_retro_path=paper_simulated_retro_path,
            testnet_runbook_signoff_path=testnet_runbook_signoff_path,
        )
    )

    return blockers


def _phase_2_stage_blockers(target_stage: str) -> list[str]:
    """ADR-007 says testnet/live require Phase 3 work that does not exist yet."""

    if STAGE_ORDER.index(target_stage) > STAGE_ORDER.index(PHASE_2_STAGE_LIMIT):
        return [f"phase_3_not_ready: target_stage={target_stage} requires Phase 3 ADRs"]
    return []


def _bundle_match_blockers(
    *,
    bundle_policy_mismatches: list[str],
    decision: str,
) -> list[str]:
    if not bundle_policy_mismatches:
        return []
    if decision == DECISION_DISABLE:
        # Disabling a source despite policy mismatch is still allowed: the
        # operator is saying "stop using this regardless of which policy was
        # actually applied". We surface the mismatch for audit but do not block.
        return []
    return [f"bundle_policy_mismatch:{item}" for item in bundle_policy_mismatches]


def _policy_bound_blockers(
    *,
    stage: str,
    policy: PolicyFields,
    label: str,
) -> list[str]:
    """Reject any policy that violates the stage's ADR-007 §2.5 upper bounds."""

    bounds = STAGE_BOUNDS[stage]
    blockers: list[str] = []
    dry_run_required = bounds["dry_run_required"]
    if dry_run_required is True and not policy.dry_run:
        blockers.append(f"{label}_must_be_dry_run_for_stage:{stage}")
    if dry_run_required is False and policy.dry_run:
        blockers.append(f"{label}_must_not_be_dry_run_for_stage:{stage}")
    max_multiplier = float(bounds["max_multiplier"])
    if policy.position_pct_multiplier > max_multiplier:
        blockers.append(
            f"{label}_multiplier_above_stage_cap:"
            f"stage={stage} cap={max_multiplier} "
            f"value={policy.position_pct_multiplier}"
        )
    return blockers


def _decision_specific_blockers(
    *,
    decision: str,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
    policy_diff: dict[str, dict[str, Any]],
    report: ReviewBundleReport,
) -> list[str]:
    if decision == DECISION_PROMOTE:
        return _promote_blockers(
            current_stage=current_stage,
            target_stage=target_stage,
            current_policy=current_policy,
            target_policy=target_policy,
            policy_diff=policy_diff,
            report=report,
        )
    if decision == DECISION_HOLD:
        return _hold_blockers(
            current_stage=current_stage,
            target_stage=target_stage,
            policy_diff=policy_diff,
        )
    if decision == DECISION_DEMOTE:
        return _demote_blockers(
            current_stage=current_stage,
            target_stage=target_stage,
            current_policy=current_policy,
            target_policy=target_policy,
        )
    if decision == DECISION_DISABLE:
        return _disable_blockers(target_policy=target_policy)
    return []


def _promote_blockers(
    *,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
    policy_diff: dict[str, dict[str, Any]],
    report: ReviewBundleReport,
) -> list[str]:
    blockers: list[str] = []
    cur_idx = STAGE_ORDER.index(current_stage)
    tgt_idx = STAGE_ORDER.index(target_stage)
    if tgt_idx != cur_idx + 1:
        blockers.append(
            "promote_stage_transition_invalid:"
            f"{current_stage}->{target_stage} (must move exactly one stage up)"
        )
    if not policy_diff:
        blockers.append(
            "promote_requires_explicit_policy_diff:"
            "current_policy and target_policy are identical"
        )
    if (
        current_stage == STAGE_PAPER_SHADOW
        and target_stage == STAGE_PAPER_SIMULATED
    ):
        blockers.extend(_paper_shadow_evidence_blockers(report))
        if current_policy.dry_run is not True:
            blockers.append(
                "promote_paper_shadow_requires_current_dry_run_true"
            )
        if target_policy.dry_run is not False:
            blockers.append(
                "promote_paper_simulated_requires_target_dry_run_false"
            )
    return blockers


def _testnet_canary_promote_blockers(
    *,
    decision: str,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
    source: str | None,
    paper_simulated_retro_path: Path | None,
    testnet_runbook_signoff_path: Path | None,
) -> list[str]:
    """ADR-008 §6.6/§8 gate for ``paper_simulated → testnet_canary`` promotes.

    Only fires for the exact transition. It enforces:

    - both policies must already be live-style (``dry_run=False``);
    - operator supplied a paper_simulated retro path for this source, the
      file exists, and the file at least mentions ``paper_simulated`` and
      the source name (cheap sanity check, not a content audit);
    - operator supplied a testnet runbook signoff path, the file exists,
      and the file at least mentions ``ADR-008`` and ``§6.6`` (i.e. the
      ADR-008 §6.6 stability-soak retro).

    Multiplier and stage-transition shape are already enforced by
    ``_policy_bound_blockers`` and ``_promote_blockers`` respectively, so
    this function intentionally does not duplicate those checks.
    """

    if decision != DECISION_PROMOTE:
        return []
    if (
        current_stage != STAGE_PAPER_SIMULATED
        or target_stage != STAGE_TESTNET_CANARY
    ):
        return []

    blockers: list[str] = []

    if current_policy.dry_run:
        blockers.append(
            "promote_testnet_canary_requires_current_no_dry_run:"
            f"current_policy.dry_run={current_policy.dry_run}"
        )
    if target_policy.dry_run:
        blockers.append(
            "promote_testnet_canary_requires_target_no_dry_run:"
            f"target_policy.dry_run={target_policy.dry_run}"
        )

    blockers.extend(
        _evidence_path_blockers(
            path=paper_simulated_retro_path,
            label="paper_simulated_retro",
            cli_flag="--paper-simulated-retro-path",
            required_substrings=(
                ("paper_simulated", None),
                ("source", source),
            ),
        )
    )

    blockers.extend(
        _evidence_path_blockers(
            path=testnet_runbook_signoff_path,
            label="testnet_runbook_signoff",
            cli_flag="--testnet-runbook-signoff-path",
            required_substrings=(
                ("adr_marker", "ADR-008"),
                ("section_marker", "§6.6"),
            ),
        )
    )

    return blockers


def _evidence_path_blockers(
    *,
    path: Path | None,
    label: str,
    cli_flag: str,
    required_substrings: tuple[tuple[str, str | None], ...],
) -> list[str]:
    """Verify an evidence file is supplied, exists, and contains expected markers.

    ``required_substrings`` is a sequence of ``(marker_name, needle)``
    pairs. A ``needle`` of ``None`` is treated as "operator did not
    parameterize this marker" and is skipped (e.g. when ``source`` is
    missing from the manifest there is nothing to check against).
    """

    if path is None:
        return [
            f"promote_testnet_canary_missing_{label}:"
            f"pass {cli_flag} pointing at the relevant docs/retros/ file"
        ]
    if not path.is_file():
        return [
            f"promote_testnet_canary_{label}_not_found:{path}"
        ]
    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    for marker_name, needle in required_substrings:
        if needle is None:
            continue
        if needle not in text:
            missing.append(f"{marker_name}={needle!r}")
    if missing:
        return [
            f"promote_testnet_canary_{label}_invalid:"
            f"{path} missing_substrings=[{', '.join(missing)}]"
        ]
    return []


def _paper_shadow_evidence_blockers(report: ReviewBundleReport) -> list[str]:
    """ADR-007 §2.5 paper_shadow → paper_simulated evidence threshold.

    The threshold is ``≥7 days OR ≥50 signals``. Either alone is enough to
    move from "no evidence" to "enough evidence to review", but the runtime
    must also be free of schema/auth/freshness anomalies. Those anomalies
    are already surfaced by ``review_blockers``; this function only checks
    the sample-size half.
    """

    has_signals = report.signal_rows >= PAPER_SHADOW_MIN_SIGNALS
    has_days = report.session_days_inclusive >= PAPER_SHADOW_MIN_DAYS
    if has_signals or has_days:
        return []
    return [
        "promote_evidence_below_adr007_threshold:"
        f"signals={report.signal_rows} (need >={PAPER_SHADOW_MIN_SIGNALS})"
        f" and session_days={report.session_days_inclusive}"
        f" (need >={PAPER_SHADOW_MIN_DAYS})"
    ]


def _hold_blockers(
    *,
    current_stage: str,
    target_stage: str,
    policy_diff: dict[str, dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if current_stage != target_stage:
        blockers.append(
            "hold_stage_transition_invalid:"
            f"{current_stage}->{target_stage} (hold requires same stage)"
        )
    if policy_diff:
        blockers.append(
            "hold_requires_identical_policies:"
            f"diff={sorted(policy_diff.keys())}"
        )
    return blockers


def _demote_blockers(
    *,
    current_stage: str,
    target_stage: str,
    current_policy: PolicyFields,
    target_policy: PolicyFields,
) -> list[str]:
    blockers: list[str] = []
    cur_idx = STAGE_ORDER.index(current_stage)
    tgt_idx = STAGE_ORDER.index(target_stage)
    if tgt_idx > cur_idx:
        blockers.append(
            "demote_stage_transition_invalid:"
            f"{current_stage}->{target_stage} (demote target must be earlier or equal)"
        )
    if (
        target_policy.position_pct_multiplier
        > current_policy.position_pct_multiplier
    ):
        blockers.append(
            "demote_must_not_increase_multiplier:"
            f"current={current_policy.position_pct_multiplier} "
            f"target={target_policy.position_pct_multiplier}"
        )
    if current_policy.dry_run is True and target_policy.dry_run is False:
        blockers.append(
            "demote_must_not_disable_dry_run:"
            "current=dry_run target=live (use promote instead)"
        )
    return blockers


def _disable_blockers(*, target_policy: PolicyFields) -> list[str]:
    blockers: list[str] = []
    if (
        target_policy.position_pct_multiplier != 0.0
        and not target_policy.dry_run
    ):
        blockers.append(
            "disable_target_policy_must_be_zero_or_dry_run:"
            f"multiplier={target_policy.position_pct_multiplier} "
            f"dry_run={target_policy.dry_run}"
        )
    return blockers


def _decision_outcome(
    *,
    decision: str,
    review_blockers: list[str],
    promotion_gate_blockers: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if review_blockers:
        reasons.extend(f"review_blocker:{item}" for item in review_blockers)
    if promotion_gate_blockers:
        reasons.extend(promotion_gate_blockers)

    if decision == DECISION_DISABLE:
        # Disabling is always allowed, even with bundle problems: the operator
        # is taking the source out of service. The reasons list still records
        # any open bundle issues for the audit trail.
        return True, reasons or ["disable_always_allowed"]

    if reasons:
        return False, reasons

    if decision == DECISION_PROMOTE:
        return True, ["promote_gates_passed"]
    if decision == DECISION_HOLD:
        return True, ["hold_gates_passed"]
    if decision == DECISION_DEMOTE:
        return True, ["demote_gates_passed"]
    return True, []


def _format_policy_diff(diff: dict[str, dict[str, Any]]) -> list[str]:
    if not diff:
        return ["  - (no fields differ — policies are identical)"]
    lines: list[str] = []
    for field_name in sorted(diff):
        change = diff[field_name]
        lines.append(
            f"  - {field_name}: {change['current']!r} -> {change['target']!r}"
        )
    return lines


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an ADR-007 §2.6 promotion review record from a paper "
            "or testnet bundle."
        ),
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--current-stage", required=True, choices=STAGE_ORDER)
    parser.add_argument("--target-stage", required=True, choices=STAGE_ORDER)
    parser.add_argument("--decision", required=True, choices=ALL_DECISIONS)
    parser.add_argument("--operator", required=True, type=str)
    parser.add_argument("--rationale", required=True, type=str)

    current = parser.add_argument_group("current_policy")
    _add_policy_flags(current, "current")
    target = parser.add_argument_group("target_policy")
    _add_policy_flags(target, "target")

    parser.add_argument(
        "--paper-simulated-retro-path",
        type=Path,
        default=None,
        help=(
            "Path to the docs/retros/ entry that records this source's "
            "paper_simulated hold/promote evidence. Required when "
            "promoting paper_simulated -> testnet_canary."
        ),
    )
    parser.add_argument(
        "--testnet-runbook-signoff-path",
        type=Path,
        default=None,
        help=(
            "Path to the ADR-008 §6.6 testnet stability-soak retro. "
            "Required when promoting paper_simulated -> testnet_canary."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Write the full review JSON to this path (in addition to text on stdout).",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        help="Write the docs/retros/ Markdown form to this path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full review JSON to stdout instead of the text summary.",
    )
    return parser


def _add_policy_flags(group: argparse._ArgumentGroup, prefix: str) -> None:
    dry = group.add_mutually_exclusive_group(required=True)
    dry.add_argument(f"--{prefix}-dry-run", dest=f"{prefix}_dry_run", action="store_true")
    dry.add_argument(
        f"--{prefix}-no-dry-run",
        dest=f"{prefix}_dry_run",
        action="store_false",
    )
    group.add_argument(
        f"--{prefix}-position-pct-multiplier",
        dest=f"{prefix}_multiplier",
        required=True,
        type=float,
    )
    group.add_argument(
        f"--{prefix}-min-confidence-override",
        dest=f"{prefix}_override",
        default=None,
        type=_optional_float,
        help="Float in [0, 1] or 'none'. Defaults to no override.",
    )


def _optional_float(value: str) -> float | None:
    if value is None:
        return None
    if value.lower() in {"", "none", "null"}:
        return None
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            f"min_confidence_override must be in [0, 1] or 'none', got {value!r}"
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        current_policy = PolicyFields(
            dry_run=bool(args.current_dry_run),
            position_pct_multiplier=float(args.current_multiplier),
            min_confidence_override=args.current_override,
        )
        target_policy = PolicyFields(
            dry_run=bool(args.target_dry_run),
            position_pct_multiplier=float(args.target_multiplier),
            min_confidence_override=args.target_override,
        )
    except ValueError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    try:
        review = build_promotion_review(
            bundle_dir=args.bundle_dir,
            current_stage=args.current_stage,
            target_stage=args.target_stage,
            current_policy=current_policy,
            target_policy=target_policy,
            decision=args.decision,
            rationale=args.rationale,
            operator=args.operator,
            paper_simulated_retro_path=args.paper_simulated_retro_path,
            testnet_runbook_signoff_path=args.testnet_runbook_signoff_path,
        )
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(asdict(review), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(
            render_markdown(review),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(asdict(review), indent=2, sort_keys=True))
    else:
        print(render_text(review))
    return 0 if review.decision_allowed else 1


__all__ = [
    "ALL_DECISIONS",
    "DECISION_DEMOTE",
    "DECISION_DISABLE",
    "DECISION_HOLD",
    "DECISION_PROMOTE",
    "PAPER_SHADOW_MIN_DAYS",
    "PAPER_SHADOW_MIN_SIGNALS",
    "PHASE_2_STAGE_LIMIT",
    "PolicyFields",
    "PromotionReview",
    "STAGE_BACKTEST_BASELINE",
    "STAGE_BOUNDS",
    "STAGE_LIVE_CANARY",
    "STAGE_LIVE_NORMAL",
    "STAGE_ORDER",
    "STAGE_PAPER_SHADOW",
    "STAGE_PAPER_SIMULATED",
    "STAGE_TESTNET_CANARY",
    "build_promotion_review",
    "main",
    "render_markdown",
    "render_text",
]


if __name__ == "__main__":
    raise SystemExit(main())

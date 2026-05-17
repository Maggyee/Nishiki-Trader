"""Summarize an ADR-007 paper bundle for promotion review.

This reader is intentionally passive: it reads `data/paper/<run_id>` sidecars
and prints review evidence. It never changes `SourcePolicy`, starts a runtime,
or talks to an exchange.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from apps.strategies_nautilus.result_schema import BacktestManifest
from apps.strategies_nautilus.runners.backtest_runner import validate_sidecar_bundle

PNL_KEYS = (
    "PnL (total)",
    "pnl_total",
    "PnL Total",
    "total_pnl",
)
DRAWDOWN_KEYS = (
    "Max Drawdown (Pct)",
    "max_drawdown_pct",
    "max_drawdown",
    "Max Drawdown",
)
SIDECAR_FILES = {
    "orders": "orders.parquet",
    "fills": "fills.parquet",
    "positions": "positions.parquet",
    "account_balances": "account_balances.parquet",
    "signal_lineage": "signal_lineage.parquet",
}


@dataclass(frozen=True)
class PaperBundleReport:
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
    policies: list[dict[str, Any]]
    matching_policy: dict[str, Any] | None
    policy_dry_run: bool
    position_pct_multiplier: float
    totals: dict[str, int]
    sidecar_rows: dict[str, int]
    sidecar_mismatches: list[str]
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
    pnl_total_by_currency: dict[str, float | int | None]
    max_drawdown_pct_by_currency: dict[str, float | int | None]
    missing_metrics: list[str]
    eligible_for_review: bool
    review_blockers: list[str]
    promotion_blockers: list[str]
    recommendation: str


def load_paper_bundle_report(bundle_dir: Path) -> PaperBundleReport:
    manifest_path = bundle_dir / "run_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
    manifest = BacktestManifest.model_validate(manifest_payload)
    if manifest.kind != "paper":
        raise ValueError(f"{bundle_dir} is kind={manifest.kind!r}, expected 'paper'")

    validate_sidecar_bundle(bundle_dir)
    sidecars = {
        name: pd.read_parquet(bundle_dir / filename)
        for name, filename in SIDECAR_FILES.items()
    }
    lineage = sidecars["signal_lineage"]
    reason_counts = _value_counts(lineage, "reason")
    decision_counts = _value_counts(lineage, "decision")
    sidecar_rows = {name: len(df) for name, df in sidecars.items()}
    sidecar_mismatches = _sidecar_mismatches(manifest, sidecar_rows)

    source = _source_from_manifest_or_lineage(manifest, lineage)
    model_version = _model_from_manifest_or_lineage(manifest, lineage)
    policies = _extract_policies(manifest_payload)
    matching_policy = _matching_policy(policies, source, model_version)
    policy_dry_run = bool(matching_policy.get("dry_run", False)) if matching_policy else False
    multiplier = (
        float(matching_policy.get("position_pct_multiplier", 1.0))
        if matching_policy
        else 1.0
    )

    skipped = int(decision_counts.get("skip", 0))
    accepted = max(len(lineage) - skipped, 0)
    dry_run_count = _exact_reason_count(reason_counts, "dry_run")
    expired = _prefix_reason_count(reason_counts, ("expired:",))
    unauthorized = _prefix_reason_count(reason_counts, ("reject_unauthorized",))
    signal_lag = _prefix_reason_count(reason_counts, ("signal_lag",))
    kill_switch = _prefix_reason_count(reason_counts, ("kill_switch",))
    data_gap = _prefix_reason_count(reason_counts, ("data_gap",))
    session_days = _session_days_inclusive(manifest.backtest_start, manifest.backtest_end)

    pnl_total_by_currency = _stats_by_currency(manifest_payload, PNL_KEYS)
    max_drawdown_by_currency = _stats_by_currency(manifest_payload, DRAWDOWN_KEYS)
    missing_metrics: list[str] = []
    if not max_drawdown_by_currency or all(
        value is None for value in max_drawdown_by_currency.values()
    ):
        missing_metrics.append("max_drawdown_pct")

    review_blockers = _review_blockers(
        manifest=manifest,
        runtime=dict(manifest_payload.get("runtime") or {}),
        sidecar_mismatches=sidecar_mismatches,
        source=source,
        model_version=model_version,
        signal_rows=manifest.signal_source.row_count,
        expired=expired,
        unauthorized=unauthorized,
        signal_lag=signal_lag,
        kill_switch=kill_switch,
        data_gap=data_gap,
    )
    promotion_blockers = _promotion_blockers(
        review_blockers=review_blockers,
        policy_dry_run=policy_dry_run,
        signal_rows=manifest.signal_source.row_count,
        session_days_inclusive=session_days,
        accepted_signals=accepted,
        fills=manifest.totals.fills,
    )
    eligible = not review_blockers
    return PaperBundleReport(
        bundle_dir=str(bundle_dir),
        run_id=manifest.run_id,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        kind=manifest.kind,
        git_commit=manifest.git_commit,
        git_dirty=manifest.git_dirty,
        runtime=dict(manifest_payload.get("runtime") or {}),
        source=source,
        model_version=model_version,
        signal_rows=manifest.signal_source.row_count,
        session_days_inclusive=session_days,
        policies=policies,
        matching_policy=matching_policy,
        policy_dry_run=policy_dry_run,
        position_pct_multiplier=multiplier,
        totals=manifest.totals.model_dump(mode="json"),
        sidecar_rows=sidecar_rows,
        sidecar_mismatches=sidecar_mismatches,
        decision_counts=decision_counts,
        reason_counts=reason_counts,
        accepted_signals=accepted,
        skipped_signals=skipped,
        dry_run_signals=dry_run_count,
        expired_signals=expired,
        unauthorized_signals=unauthorized,
        signal_lag_signals=signal_lag,
        kill_switch_signals=kill_switch,
        data_gap_signals=data_gap,
        pnl_total_by_currency=pnl_total_by_currency,
        max_drawdown_pct_by_currency=max_drawdown_by_currency,
        missing_metrics=missing_metrics,
        eligible_for_review=eligible,
        review_blockers=review_blockers,
        promotion_blockers=promotion_blockers,
        recommendation=_recommendation(
            review_blockers=review_blockers,
            policy_dry_run=policy_dry_run,
        ),
    )


def render_text_report(report: PaperBundleReport) -> str:
    blockers = ", ".join(report.review_blockers) if report.review_blockers else "none"
    promotion = (
        ", ".join(report.promotion_blockers) if report.promotion_blockers else "none"
    )
    source_key = f"{report.source or 'unknown'} / {report.model_version or 'unknown'}"
    return "\n".join(
        [
            f"paper bundle: {report.bundle_dir}",
            f"run_id: {report.run_id}",
            f"manifest_sha256: {report.manifest_sha256}",
            f"source_model: {source_key}",
            (
                "policy: "
                f"dry_run={report.policy_dry_run} "
                f"position_pct_multiplier={report.position_pct_multiplier}"
            ),
            (
                "signals: "
                f"rows={report.signal_rows} accepted={report.accepted_signals} "
                f"skipped={report.skipped_signals} dry_run={report.dry_run_signals} "
                f"expired={report.expired_signals} "
                f"unauthorized={report.unauthorized_signals} "
                f"signal_lag={report.signal_lag_signals} "
                f"kill_switch={report.kill_switch_signals}"
            ),
            (
                "totals: "
                f"orders={report.totals['orders']} fills={report.totals['fills']} "
                f"positions={report.totals['positions']} "
                f"pnl={json.dumps(report.pnl_total_by_currency, sort_keys=True)} "
                "max_drawdown_pct="
                f"{json.dumps(report.max_drawdown_pct_by_currency, sort_keys=True)}"
            ),
            f"eligible_for_review: {report.eligible_for_review}",
            f"review_blockers: {blockers}",
            f"promotion_blockers: {promotion}",
            f"recommendation: {report.recommendation}",
        ]
    )


def _value_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    counts = df[column].fillna("").astype(str).value_counts(sort=False).to_dict()
    return {str(k): int(v) for k, v in counts.items()}


def _exact_reason_count(reason_counts: dict[str, int], reason: str) -> int:
    return int(reason_counts.get(reason, 0))


def _prefix_reason_count(
    reason_counts: dict[str, int],
    prefixes: tuple[str, ...],
) -> int:
    return sum(
        count
        for reason, count in reason_counts.items()
        if reason.startswith(prefixes)
    )


def _sidecar_mismatches(
    manifest: BacktestManifest,
    sidecar_rows: dict[str, int],
) -> list[str]:
    expected = {
        "events": manifest.totals.events,
        "orders": manifest.totals.orders,
        "fills": manifest.totals.fills,
        "positions": manifest.totals.positions,
    }
    actual = {
        "events": sidecar_rows["signal_lineage"],
        "orders": sidecar_rows["orders"],
        "fills": sidecar_rows["fills"],
        "positions": sidecar_rows["positions"],
    }
    return [
        f"sidecar_mismatch:{key} manifest={expected[key]} actual={actual[key]}"
        for key in sorted(expected)
        if expected[key] != actual[key]
    ]


def _source_from_manifest_or_lineage(
    manifest: BacktestManifest,
    lineage: pd.DataFrame,
) -> str | None:
    source = manifest.signal_source.filter.get("source")
    if isinstance(source, str) and source:
        return source
    return _single_lineage_value(lineage, "source")


def _model_from_manifest_or_lineage(
    manifest: BacktestManifest,
    lineage: pd.DataFrame,
) -> str | None:
    model = manifest.signal_source.filter.get("model_version")
    if isinstance(model, str) and model:
        return model
    return _single_lineage_value(lineage, "model_version")


def _single_lineage_value(df: pd.DataFrame, column: str) -> str | None:
    if df.empty or column not in df.columns:
        return None
    values = sorted(v for v in df[column].fillna("").astype(str).unique() if v)
    return values[0] if len(values) == 1 else None


def _extract_policies(manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    for strategy in manifest_payload.get("strategies") or []:
        params = strategy.get("params") or {}
        for policy in params.get("policies") or []:
            if isinstance(policy, dict):
                policies.append(dict(policy))
    return policies


def _matching_policy(
    policies: list[dict[str, Any]],
    source: str | None,
    model_version: str | None,
) -> dict[str, Any] | None:
    for policy in policies:
        if policy.get("source") == source and policy.get("model_version") == model_version:
            return dict(policy)
    return None


def _session_days_inclusive(start: str, end: str) -> int:
    start_dt = _parse_iso_ms_utc(start)
    end_dt = _parse_iso_ms_utc(end)
    return max((end_dt.date() - start_dt.date()).days + 1, 0)


def _parse_iso_ms_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _stats_by_currency(
    manifest_payload: dict[str, Any],
    keys: tuple[str, ...],
) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    for currency, stats in (manifest_payload.get("stats_pnls") or {}).items():
        value = None
        if isinstance(stats, dict):
            for key in keys:
                if key in stats:
                    value = _numeric_or_none(stats[key])
                    break
        out[str(currency)] = value
    return out


def _numeric_or_none(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _review_blockers(
    *,
    manifest: BacktestManifest,
    runtime: dict[str, Any],
    sidecar_mismatches: list[str],
    source: str | None,
    model_version: str | None,
    signal_rows: int,
    expired: int,
    unauthorized: int,
    signal_lag: int,
    kill_switch: int,
    data_gap: int,
) -> list[str]:
    blockers: list[str] = []
    if manifest.git_dirty:
        blockers.append("git_dirty")
    if runtime.get("mode") != "paper":
        blockers.append("runtime_mode_not_paper")
    if runtime.get("data_mode") != "catalog_polling":
        blockers.append("runtime_data_mode_not_catalog_polling")
    if runtime.get("order_mode") != "simulated":
        blockers.append("runtime_order_mode_not_simulated")
    if source is None:
        blockers.append("source_unknown")
    if model_version is None:
        blockers.append("model_version_unknown")
    if signal_rows <= 0:
        blockers.append("no_signals")
    blockers.extend(sidecar_mismatches)
    if expired:
        blockers.append(f"expired_signals={expired}")
    if unauthorized:
        blockers.append(f"unauthorized_signals={unauthorized}")
    if signal_lag:
        blockers.append(f"signal_lag_signals={signal_lag}")
    if kill_switch:
        blockers.append(f"kill_switch_signals={kill_switch}")
    if data_gap:
        blockers.append(f"data_gap_signals={data_gap}")
    return blockers


def _promotion_blockers(
    *,
    review_blockers: list[str],
    policy_dry_run: bool,
    signal_rows: int,
    session_days_inclusive: int,
    accepted_signals: int,
    fills: int,
) -> list[str]:
    blockers = list(review_blockers)
    if policy_dry_run:
        if signal_rows < 50 and session_days_inclusive < 7:
            blockers.append("shadow_evidence_below_adr007_threshold")
        blockers.append("manual_review_required_before_disabling_dry_run")
    elif accepted_signals > 0 and fills == 0:
        blockers.append("simulated_policy_without_fills")
    return blockers


def _recommendation(
    *,
    review_blockers: list[str],
    policy_dry_run: bool,
) -> str:
    if review_blockers:
        return "hold_until_review_blockers_clear"
    if policy_dry_run:
        return "manual_review_required_before_paper_simulated"
    return "review_simulated_paper_evidence"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize an ADR-007 paper bundle for promotion review.",
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full report as JSON instead of the text summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = load_paper_bundle_report(args.bundle_dir)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    return 0


__all__ = [
    "PaperBundleReport",
    "load_paper_bundle_report",
    "render_text_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

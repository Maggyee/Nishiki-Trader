"""Read-only provenance, repaired-pipeline and planned-capital diagnostics.

See docs/progress/strategy-followup-method-2026-09-08-v2.md. No execution, new
research, risk-setting mutation or automatic evidence acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from apps.bridge.signal_event import SignalEvent
from apps.ops import research_portfolio_evidence as evidence
from apps.ops.install_shadow_collectors import render_crontab
from apps.ops.research_portfolio_monitor import CANDIDATE_SPECS, load_candidate_data
from apps.ops.research_shadow_runtime import summarize_signal_pipeline

HISTORY_TIP = "f5963cdef902908e00a601a1eb8fef345e545b87"
PATTERNS = {
    "v8": "backtests/*/run_manifest.json",
    "v42": "confirmation_runs/*/*/run_manifest.json",
    "v46": "replays/btc_prem_diff5_negative_conf/*/*/run_manifest.json",
    "v48": "confirmation_replays/*/*/*/run_manifest.json",
}


def command(root: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=root, text=True).strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory_manifest(path: Path, spec: dict) -> dict:
    manifest = json.loads(path.read_text())
    problems = ["original_manifest_and_fills_hash_references_missing"]
    if manifest.get("git_dirty") is not False:
        problems.append("historical_git_not_clean")
    if manifest.get("kind") != "backtest":
        problems.append("not_backtest")
    filters = manifest.get("signal_source", {}).get("filter", {})
    if any(filters.get(k) != spec[k] for k in ("source", "model_version")):
        problems.append("identity_mismatch")
    if pd.Timestamp(manifest["backtest_start"]) != evidence.START or pd.Timestamp(
        manifest["backtest_end"]
    ) != evidence.END - pd.Timedelta(hours=1):
        problems.append("window_mismatch")
    return {
        "path": str(path.parent),
        "git_commit": manifest.get("git_commit"),
        "git_dirty": manifest.get("git_dirty"),
        "observed_now_hashes_not_original_proof": {
            name: digest(path.parent / name) for name in ("run_manifest.json", "fills.parquet")
        },
        "blockers": problems,
        "historical_provenance_verified": False,
    }


def audit_provenance(root: Path) -> list[dict]:
    results = []
    for spec in CANDIDATE_SPECS:
        protocol = spec["protocol"]
        if protocol not in PATTERNS:
            continue
        bundles, errors = [], []
        for path in sorted((root / f"data/research-{protocol}").glob(PATTERNS[protocol])):
            try:
                row = inventory_manifest(path, spec)
                row["path"] = str(path.parent.relative_to(root))
                bundles.append(row)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{path.relative_to(root)}:{exc}")
        tokens = [
            token
            for row in bundles
            for token in [
                Path(row["path"]).name,
                *row["observed_now_hashes_not_original_proof"].values(),
            ]
        ]
        matches = (
            command(
                root,
                "git",
                "log",
                HISTORY_TIP,
                "--format=%H",
                "-G",
                "|".join(tokens),
                "--",
                "docs",
                "apps",
                "infra",
                "notebooks",
            ).splitlines()
            if tokens
            else []
        )
        result_path = f"docs/progress/phase-2-research-{protocol}-confirmation-results.json"
        revisions = command(
            root, "git", "log", HISTORY_TIP, "--format=%H", "--", result_path
        ).splitlines()
        results.append(
            {
                "protocol": protocol,
                "bundles": bundles,
                "inventory_errors": errors,
                "result_revisions_searched": revisions,
                "historical_reference_leads": matches,
                "historical_provenance_verified": False,
                "decision": "remain_excluded_pending_original_proof_and_clean_code",
            }
        )
    return results


def audit_deployment(root: Path) -> dict:
    receipt = json.loads((root / "data/collector-deployments/active.json").read_text())
    deployment = Path(receipt["deployment"])
    current = subprocess.check_output(["crontab", "-l"], text=True)
    if hashlib.sha256(current.encode()).hexdigest() != receipt["crontab_sha256"]:
        raise ValueError("crontab differs from deployment receipt")
    if render_crontab(current, root, deployment, receipt["commit"]) != current:
        raise ValueError("collector cron differs from pinned rendering")
    if command(deployment, "git", "rev-parse", "HEAD") != receipt["commit"]:
        raise ValueError("deployment revision mismatch")
    if command(deployment, "git", "status", "--porcelain"):
        raise ValueError("deployment is dirty")
    command(root, "git", "merge-base", "--is-ancestor", receipt["commit"], "origin/main")
    return {
        "commit": receipt["commit"],
        "cron_matches_receipt": True,
        "pinned_checkout_clean": True,
        "existing_job_count": len(receipt["protocols"]),
        "schedules_changed": False,
    }


def check_prospective(
    records: list[dict], status: dict, events: list[SignalEvent], now: datetime
) -> dict:
    summary = summarize_signal_pipeline(records, gate_days=7, gate_signals=50)
    fields = (
        "qualified_day_count",
        "qualified_collection_dates",
        "new_forward_signal_ids",
        "new_forward_signal_count",
        "anomaly_blockers",
        "threshold_met",
        "review_eligible",
        "legacy_attempt_count",
    )
    if any(status.get(k) != summary[k] for k in fields):
        raise ValueError("status disagrees with immutable journal summary")
    epoch = datetime.fromisoformat(status["signal_pipeline_started_at"])
    by_id = {event.signal_id: event for event in events}
    if len(by_id) != len(events):
        raise ValueError("duplicate stored signal IDs")
    if any(event.ts_event > int(now.timestamp() * 1e9) for event in events):
        raise ValueError("future stored event")
    seen = set()
    for row in records:
        if row.get("signal_pipeline_version") != 2:
            continue
        observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
        if (
            observed < epoch
            or observed > now
            or row["collection_date"] != observed.date().isoformat()
        ):
            raise ValueError("invalid prospective observation time")
        if row.get("qualified_day") and (
            row.get("blockers")
            or row["git"].get("dirty") is not False
            or row["git"].get("origin_main_contains_commit") is not True
        ):
            raise ValueError("invalid qualified attempt")
        for signal_id in row.get("new_forward_signal_ids", []):
            event = by_id.get(signal_id)
            if (
                event is None
                or signal_id in seen
                or not int(epoch.timestamp() * 1e9)
                < event.ts_event
                <= int(observed.timestamp() * 1e9)
            ):
                raise ValueError("backfill, duplicate or missing prospective signal")
            seen.add(signal_id)
    return {k: summary[k] for k in fields}


def audit_repaired_pipeline(root: Path, spec: dict, now: datetime) -> dict:
    protocol = spec["protocol"]
    directory = root / spec["db_path"].parent
    status_path = directory / "status.json"
    status = json.loads(status_path.read_text())
    if any(status.get(k) != spec[k] for k in ("source", "model_version")):
        raise ValueError("runtime identity mismatch")
    journal_paths = sorted((directory / "journal").glob("*.json"))
    records = [json.loads(path.read_text()) for path in journal_paths]
    current = [row for row in records if row.get("signal_pipeline_version") == 2]
    if not current:
        raise ValueError("no corrected attempts")
    verifier = importlib.import_module(f"apps.ops.research_{protocol}_snapshot").verify_snapshot
    for row in current:
        evidence.verified_bytes(root / row["btc"]["raw_path"], row["btc"]["raw_sha256"])
        factor = row[{"v22": "cor1m", "v34": "fvx", "v36": "vpn"}[protocol]]
        checked = verifier(root / factor["snapshot_path"])
        if checked["snapshot_sha256"] != factor["snapshot_sha256"]:
            raise ValueError("factor snapshot differs from attempt journal")
    with closing(
        sqlite3.connect((root / spec["db_path"]).resolve().as_uri() + "?mode=ro", uri=True)
    ) as conn:
        events = [
            SignalEvent.model_validate_json(row[0])
            for row in conn.execute("SELECT raw_json FROM signals")
        ]
    if any(
        event.source != spec["source"] or event.model_version != spec["model_version"]
        for event in events
    ):
        raise ValueError("unexpected stored identity")
    summary = check_prospective(records, status, events, now)
    return {
        "protocol": protocol,
        **summary,
        "stored_signal_count": len(events),
        "corrected_attempts_verified": len(current),
        "latest_blockers": status["latest_blockers"],
        "status_sha256_observed_now": digest(status_path),
        "pipeline_integrity_check_passed": True,
        "acceptance": "gate_ready_for_review_only"
        if summary["review_eligible"]
        else "continue_existing_schedule",
        "performance_evidence": False,
    }


def planned_budget(
    curves: dict,
    closes: pd.Series,
    weights: dict,
    *,
    capital: float,
    max_drawdown: float,
    daily_loss: float,
) -> dict:
    if (
        not all(math.isfinite(v) for v in (capital, max_drawdown, daily_loss))
        or capital <= 0
        or not 0 < max_drawdown <= 1
        or not 0 < daily_loss <= capital
    ):
        raise ValueError("invalid planned risk budget")
    marked = sum(curves[p][list(evidence.COSTS)] * w for p, w in weights.items())
    notional = sum(curves[p]["qty"] * w for p, w in weights.items()) * closes.iloc[1:]
    # The operator-confirmed research budget is not a runtime risk setting.
    # Do not silently replace it with the separate execution-rule reference.
    comparison_limit = daily_loss
    scenarios = {}
    for name in evidence.COSTS:
        pnl = marked[name]
        changes = pnl.diff()
        changes.iloc[0] = pnl.iloc[0]
        minimum_capital = max(0.0, float((notional - pnl).max()))
        loss = max(0.0, -float(changes.min()))
        dd = evidence.drawdown(pnl)
        scenarios[name] = {
            "daily_sampled_cash_funding_required_usdt": minimum_capital,
            "minimum_daily_sampled_free_cash_at_planned_capital_usdt": capital - minimum_capital,
            "cash_feasible_at_daily_marks": minimum_capital <= capital,
            "daily_marked_max_drawdown_usdt": dd,
            "drawdown_as_fraction_of_planned_initial_capital_not_account_return": dd / capital,
            "within_requested_drawdown_amount": dd <= capital * max_drawdown,
            "worst_sampled_daily_loss_usdt": loss,
            "days_at_or_above_fixed_diagnostic_loss_amount": int(
                (-changes >= comparison_limit).sum()
            ),
            "fixed_diagnostic_daily_loss_amount_usdt": comparison_limit,
        }
    return {
        "planned_capital_usdt": capital,
        "requested_max_drawdown_fraction": max_drawdown,
        "requested_daily_loss_usdt": daily_loss,
        "diagnostic_budget_source": "operator_input",
        "unchanged_runtime_daily_rule_fraction": 0.05,
        "differs_from_unchanged_runtime_daily_rule": daily_loss != capital * 0.05,
        "max_daily_marked_inventory_notional_usdt": float(notional.max()),
        "diagnostic_weights_not_source_policy": weights,
        "scenarios": scenarios,
        "actual_account_return_pct": None,
        "actual_account_leverage": None,
        "decision": "not_an_executable_allocation",
        "runtime_risk_settings_changed": False,
    }


def build_report(root: Path, *, capital: float, max_drawdown: float, daily_loss: float) -> dict:
    now = datetime.now(UTC)
    provenance = audit_provenance(root)
    repaired = []
    for spec in CANDIDATE_SPECS:
        if spec["protocol"] in {"v22", "v34", "v36"}:
            try:
                repaired.append(audit_repaired_pipeline(root, spec, now))
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                repaired.append(
                    {
                        "protocol": spec["protocol"],
                        "pipeline_integrity_check_passed": False,
                        "error": str(exc),
                    }
                )
    closes, _ = evidence.load_benchmark(root)
    portfolio = evidence.build_report(root)
    included = {row["protocol"] for row in portfolio["candidates"]}
    curves = {
        spec["protocol"]: evidence.load_candidate(root, spec, closes)[0]
        for spec in CANDIDATE_SPECS
        if spec["protocol"] in included
    }
    risks = {
        name: planned_budget(
            curves,
            closes,
            portfolio[name]["diagnostic_weights_not_source_policy"],
            capital=capital,
            max_drawdown=max_drawdown,
            daily_loss=daily_loss,
        )
        for name in ("raw_fixed_quantity_basket", "duplicate_normalized_diagnostic")
        if portfolio[name]
    }
    candidates = load_candidate_data(root, now=now)
    return {
        "schema_version": "research.strategy_followup.v2",
        "generated_at": now.isoformat(),
        "method": "docs/progress/strategy-followup-method-2026-09-08-v2.md",
        "history_search_tip": HISTORY_TIP,
        "provenance_inventory": provenance,
        "deployment": audit_deployment(root),
        "repaired_pipelines": repaired,
        "collector_overview": [
            {
                k: row[k]
                for k in (
                    "protocol",
                    "qualified_days",
                    "signals_count",
                    "anomaly_blockers",
                    "review_eligible",
                )
            }
            for row in candidates
        ],
        "verified_cohort": sorted(included),
        "excluded": portfolio["excluded"],
        "planned_capital_diagnostics": risks,
        "limitations": [
            "four original evidence chains remain unverified; no full ten-candidate claim",
            "prospective elapsed time cannot be manufactured",
            "planned capital is not verified account equity",
            "daily marks understate possible intraday cash needs and losses",
            "no kill switch, exchange constraints or executable sizing was simulated",
        ],
        "boundaries": {
            "live_path_touched": False,
            "source_policy_changed": False,
            "research_reopened": False,
            "future_blind_pnl_opened": False,
            "schedules_changed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--capital", type=float, required=True)
    parser.add_argument("--max-drawdown", type=float, required=True)
    parser.add_argument("--daily-loss", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("report must use a new path")
    report = build_report(
        args.repo_root.resolve(),
        capital=args.capital,
        max_drawdown=args.max_drawdown,
        daily_loss=args.daily_loss,
    )
    with args.output.open("x") as handle:
        handle.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        "partial: evidence/time/funding constraints remain; operator budget used; no trading changes"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

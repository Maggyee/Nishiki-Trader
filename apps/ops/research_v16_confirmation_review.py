"""Apply frozen v16 confirmation gates to duplicate Treasury-volatility bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v16 import IDENTITIES
from apps.ops.research_v8_review import _effective_bundle_blockers, _event_timestamps
from apps.ops.research_v9_review import STEP_NS, _months
from apps.ops.research_v16_confirmation import load_and_validate

SCHEMA_VERSION = "research.v16.confirmation_results.v1"
CANDIDATE = "treasury_volatility_relief"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _classification(performance_pass: bool, evidence_pass: bool) -> str:
    if performance_pass and evidence_pass:
        return "paper_shadow_review_eligible"
    if evidence_pass:
        return "reject_candidate"
    return "insufficient_confirmation_evidence"


def build_review(bundle_paths: list[Path], execution_audit: dict[str, Any]) -> dict[str, Any]:
    contract = load_and_validate()
    if len(bundle_paths) != 2:
        raise ValueError("Protocol v16 confirmation requires exactly two bundles")
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [
        _analyze_bundle(
            path,
            start_ns=int(start.timestamp() * 1_000_000_000),
            end_exclusive_ns=int(end.timestamp() * 1_000_000_000),
            months=_months(2023, 2025),
            bar_interval_ns=STEP_NS,
        )
        for path in bundle_paths
    ]
    primary = runs[0]
    if (primary["source"], primary["model_version"]) != IDENTITIES[CANDIDATE]:
        raise ValueError("Protocol v16 confirmation bundle identity drifted")
    if len(primary["monthly_metrics"]) != 36:
        raise ValueError("Protocol v16 confirmation requires 36 months")
    yearly = {"2023": 0.0, "2024": 0.0, "2025": 0.0}
    positive_months = 0
    for row in primary["monthly_metrics"]:
        base = float(row["scenarios"]["base"]["net_pnl"])
        yearly[str(row["month"])[:4]] += base
        positive_months += int(base > 0.0)
    scenario = primary["scenario_metrics"]
    gross = float(scenario["gross"]["net_pnl"])
    base = float(scenario["base"]["net_pnl"])
    stress = float(scenario["stress"]["net_pnl"])
    leave_best = float(primary["base_net_without_best_position"])
    verified_hours = {
        timestamp
        for window in execution_audit.get("verified_no_kline_windows", [])
        if window.get("classification") == "exchange_unavailable_not_missing_market_data"
        for timestamp in range(
            int(window["start_ts_ns"]),
            int(window["end_ts_ns"]) + STEP_NS,
            STEP_NS,
        )
    }
    event_hits = sorted(
        verified_hours.intersection(
            timestamp for path in bundle_paths for timestamp in _event_timestamps(path)
        )
    )
    effective_blockers = _effective_bundle_blockers(
        list(primary["blockers"]), execution_audit
    )
    reproducible = _runs_reproducible(runs)
    positive_years = sum(value > 0.0 for value in yearly.values())
    positions = int(primary["closed_positions"])
    performance_pass = bool(
        base > 0.0
        and stress > 0.0
        and positive_years >= 2
        and positive_months >= 18
        and positions >= 30
        and leave_best > 0.0
    )
    evidence_pass = bool(
        execution_audit.get("passed") is True
        and int(primary["short_positions"]) == 0
        and reproducible
        and not event_hits
        and not effective_blockers
    )
    manifest = json.loads((bundle_paths[0] / "run_manifest.json").read_text())
    candidate = {
        "key": CANDIDATE,
        "source": primary["source"],
        "model_version": primary["model_version"],
        "signal_count": int(manifest["signal_source"]["row_count"]),
        "gross_net_pnl": gross,
        "base_net_pnl": base,
        "stress_net_pnl": stress,
        "positive_years": positive_years,
        "yearly_base_net_pnl": yearly,
        "positive_months": positive_months,
        "calendar_months": 36,
        "closed_positions": positions,
        "leave_best_base_net_pnl": leave_best,
        "duplicate_replays": 2,
        "reproducible": reproducible,
        "short_positions": int(primary["short_positions"]),
        "verified_no_kline_event_hits": event_hits,
        "effective_blockers": effective_blockers,
        "performance_pass": performance_pass,
        "evidence_pass": evidence_pass,
        "classification": _classification(performance_pass, evidence_pass),
        "bundle_runs": [
            {
                "path": str(path),
                "manifest_sha256": _sha256(path / "run_manifest.json"),
                "fills_sha256": _sha256(path / "fills.parquet"),
            }
            for path in bundle_paths
        ],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "candidate": candidate,
        "recommendation": "enter_paper_shadow_review"
        if candidate["classification"] == "paper_shadow_review_eligible"
        else "stop_protocol_v16_confirmation_failed",
        "future_blind_status": "sealed_unopened",
        "boundaries": {
            "mutates_source_policy": False,
            "resumes_testnet": False,
            "loads_credentials": False,
            "touches_live_path": False,
            "opens_future_blind": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, action="append", required=True)
    parser.add_argument("--execution-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_review(args.bundle, json.loads(args.execution_audit.read_text()))
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

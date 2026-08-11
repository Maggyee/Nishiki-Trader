"""Apply the frozen Protocol v8 gates to duplicate GVZ confirmation bundles."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v8 import IDENTITY, load_and_validate
from apps.ops.research_v8_execution import SCHEMA_VERSION as EXECUTION_SCHEMA

SCHEMA_VERSION = "research.v8.review.v1"


def _months() -> list[str]:
    current = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    values: list[str] = []
    while current < end:
        values.append(current.strftime("%Y-%m"))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return values


def _event_timestamps(bundle: Path) -> set[int]:
    timestamps: set[int] = set()
    for filename, column in (("orders.parquet", "ts_init"), ("fills.parquet", "ts_event")):
        table = pq.read_table(bundle / filename, columns=[column])
        timestamps.update(int(value) for value in table[column].to_pylist())
    return timestamps


def _effective_bundle_blockers(
    raw_blockers: list[str],
    execution_audit: dict[str, Any],
) -> list[str]:
    """Remove only the row blocker explained by the frozen session-aware audit."""
    blockers = list(raw_blockers)
    if execution_audit.get("passed") is not True:
        return blockers
    official = int(execution_audit["official_bar_rows"])
    expected = int(execution_audit["expected_clock_rows"])
    verified = int(execution_audit["verified_no_kline_rows"])
    if official + verified != expected:
        raise ValueError("Protocol v8 execution audit row accounting drifted")
    explained = f"catalog_rows={official}!=expected={expected}"
    return [blocker for blocker in blockers if blocker != explained]


def build_review(bundle_paths: list[Path], execution_audit: dict[str, Any]) -> dict[str, Any]:
    """Build and classify the one fixed v8 confirmation candidate."""
    contract = load_and_validate()
    if execution_audit.get("schema_version") != EXECUTION_SCHEMA:
        raise ValueError("Protocol v8 execution audit schema drifted")
    start_ns = int(datetime(2023, 1, 1, tzinfo=UTC).timestamp() * 1_000_000_000)
    end_ns = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1_000_000_000)
    runs = [
        _analyze_bundle(
            path,
            start_ns=start_ns,
            end_exclusive_ns=end_ns,
            months=_months(),
            bar_interval_ns=3_600_000_000_000,
        )
        for path in bundle_paths
    ]
    if not runs:
        raise ValueError("Protocol v8 requires duplicate bundles")
    primary = runs[0]
    if (primary.get("source"), primary.get("model_version")) != IDENTITY:
        raise ValueError("Protocol v8 bundle identity drifted")
    monthly = primary["monthly_metrics"]
    if len(monthly) != 36:
        raise ValueError("Protocol v8 requires all 36 confirmation months")
    yearly: dict[str, float] = {"2023": 0.0, "2024": 0.0, "2025": 0.0}
    positive_months = 0
    for row in monthly:
        base = float(row["scenarios"]["base"]["net_pnl"])
        yearly[str(row["month"])[:4]] += base
        positive_months += int(base > 0.0)
    scenario = primary["scenario_metrics"]
    base_net = float(scenario["base"]["net_pnl"])
    stress_net = float(scenario["stress"]["net_pnl"])
    leave_best = float(primary["base_net_without_best_position"])
    reproducible = len(runs) >= 2 and _runs_reproducible(runs)
    verified_hours = {
        timestamp
        for window in execution_audit.get("verified_no_kline_windows", [])
        if window.get("classification") == "exchange_unavailable_not_missing_market_data"
        for timestamp in range(
            int(window["start_ts_ns"]),
            int(window["end_ts_ns"]) + 3_600_000_000_000,
            3_600_000_000_000,
        )
    }
    marker_hits = sorted(
        verified_hours.intersection(
            timestamp for path in bundle_paths for timestamp in _event_timestamps(path)
        )
    )
    raw_bundle_blockers = list(primary.get("blockers", []))
    effective_bundle_blockers = _effective_bundle_blockers(
        raw_bundle_blockers,
        execution_audit,
    )
    positive_years = sum(value > 0.0 for value in yearly.values())
    gates = {
        "base_net_positive": base_net > 0.0,
        "stress_net_positive": stress_net > 0.0,
        "positive_years": positive_years,
        "positive_years_required": 2,
        "positive_months": positive_months,
        "positive_months_required": 18,
        "closed_positions": int(primary["closed_positions"]),
        "closed_positions_required": 30,
        "leave_best_base_net_pnl": leave_best,
        "leave_best_base_net_pnl_positive": leave_best > 0.0,
        "short_positions": int(primary["short_positions"]),
        "duplicate_runs": len(runs),
        "duplicate_runs_required": 2,
        "reproducible": reproducible,
        "execution_audit_passed": execution_audit.get("passed") is True,
        "orders_or_fills_in_verified_no_kline_windows": marker_hits,
    }
    performance_pass = bool(
        gates["base_net_positive"]
        and gates["stress_net_positive"]
        and positive_years >= 2
        and positive_months >= 18
        and gates["closed_positions"] >= 30
        and gates["leave_best_base_net_pnl_positive"]
    )
    evidence_pass = bool(
        gates["short_positions"] == 0
        and len(runs) >= 2
        and reproducible
        and gates["execution_audit_passed"]
        and not marker_hits
        and not effective_bundle_blockers
    )
    if performance_pass and evidence_pass:
        classification = "paper_shadow_review_eligible"
    elif evidence_pass:
        classification = "reject_candidate"
    else:
        classification = "insufficient_confirmation_evidence"
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": contract["contract_sha256"],
        "source": IDENTITY[0],
        "model_version": IDENTITY[1],
        "bundle_runs": [str(path) for path in bundle_paths],
        "scenario_metrics": scenario,
        "yearly_base_net_pnl": yearly,
        "monthly_metrics": monthly,
        "gates": gates,
        "raw_bundle_blockers": raw_bundle_blockers,
        "effective_bundle_blockers": effective_bundle_blockers,
        "performance_pass": performance_pass,
        "evidence_pass": evidence_pass,
        "classification": classification,
        "future_blind_status": "sealed_unopened",
        "boundaries": {
            "mutates_source_policy": False,
            "resumes_testnet": False,
            "loads_credentials": False,
            "touches_live_path": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, action="append", required=True)
    parser.add_argument("--execution-audit", type=Path, required=True)
    args = parser.parse_args(argv)
    audit = json.loads(args.execution_audit.read_text())
    print(json.dumps(build_review(args.bundle, audit), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

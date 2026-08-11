"""Apply the frozen Protocol v7 replication gates to duplicate backtest bundles."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v7 import STRATEGY_IDENTITIES

SCHEMA_VERSION = "research.v7.review.v1"


def build_v7_alpha(candidate_specs: list[tuple[str, Path]]) -> dict[str, Any]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end_exclusive = datetime(2023, 1, 1, tzinfo=UTC)
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_exclusive_ns = int(end_exclusive.timestamp() * 1_000_000_000)
    months: list[str] = []
    current = start
    while current < end_exclusive:
        months.append(current.strftime("%Y-%m"))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    grouped: dict[str, list[Path]] = defaultdict(list)
    for label, path in candidate_specs:
        grouped[label].append(path)
    candidates: list[dict[str, Any]] = []
    for label, paths in grouped.items():
        runs = [
            _analyze_bundle(
                path,
                start_ns=start_ns,
                end_exclusive_ns=end_exclusive_ns,
                months=months,
            )
            for path in paths
        ]
        primary = dict(runs[0])
        reproducible = _runs_reproducible(runs)
        blockers = list(primary["blockers"])
        if len(runs) < 2:
            blockers.append("reproducibility_run_missing")
        elif not reproducible:
            blockers.append("reproducibility_mismatch")
        primary.update(
            {
                "label": label,
                "bundle_runs": [run["bundle_dir"] for run in runs],
                "run_count": len(runs),
                "reproducible": reproducible,
                "blockers": sorted(set(blockers)),
            }
        )
        candidates.append(primary)
    return {"schema_version": "alpha.review.v1", "candidates": candidates}


def classify_review(alpha: dict[str, Any], catalog_audit: dict[str, Any]) -> dict[str, Any]:
    if alpha.get("schema_version") != "alpha.review.v1":
        raise ValueError("Protocol v7 requires alpha.review.v1 input")
    if catalog_audit.get("schema_version") != "catalog.audit.v1":
        raise ValueError("Protocol v7 requires catalog.audit.v1 input")
    expected_identities = set(STRATEGY_IDENTITIES.values())
    candidates: list[dict[str, Any]] = []
    for candidate in alpha.get("candidates", []):
        identity = (candidate.get("source"), candidate.get("model_version"))
        if identity not in expected_identities:
            continue
        monthly = candidate.get("monthly_metrics")
        if not isinstance(monthly, list) or len(monthly) != 36:
            raise ValueError(f"{identity} must contain the exact 36-month reserve")
        yearly_base: dict[str, float] = defaultdict(float)
        positive_months = 0
        for row in monthly:
            month = str(row["month"])
            base = float(row["scenarios"]["base"]["net_pnl"])
            yearly_base[month[:4]] += base
            positive_months += int(base > 0.0)
        if set(yearly_base) != {"2020", "2021", "2022"}:
            raise ValueError(f"{identity} reserve years drifted")

        scenario = candidate["scenario_metrics"]
        base_net = float(scenario["base"]["net_pnl"])
        stress_net = float(scenario["stress"]["net_pnl"])
        leave_best = float(candidate["base_net_without_best_position"])
        closed_positions = int(candidate["closed_positions"])
        positive_years = sum(value > 0.0 for value in yearly_base.values())
        blockers = list(candidate.get("blockers", []))
        if catalog_audit.get("passed") is not True:
            blockers.append("execution_catalog_incomplete")
        gates = {
            "base_net_positive": base_net > 0.0,
            "stress_net_positive": stress_net > 0.0,
            "positive_calendar_years": positive_years,
            "positive_calendar_years_required": 2,
            "positive_months": positive_months,
            "positive_months_required": 18,
            "closed_positions": closed_positions,
            "closed_positions_required": 30,
            "leave_best_position_base_net_pnl": leave_best,
            "leave_best_position_base_net_pnl_positive": leave_best > 0.0,
            "spot_long_flat_only": int(candidate["short_positions"]) == 0,
            "duplicate_replays": int(candidate["run_count"]),
            "duplicate_replays_required": 2,
            "reproducible": candidate.get("reproducible") is True,
            "execution_catalog_complete": catalog_audit.get("passed") is True,
        }
        passed = bool(
            gates["base_net_positive"]
            and gates["stress_net_positive"]
            and positive_years >= 2
            and positive_months >= 18
            and closed_positions >= 30
            and gates["leave_best_position_base_net_pnl_positive"]
            and gates["spot_long_flat_only"]
            and gates["duplicate_replays"] >= 2
            and gates["reproducible"]
            and not blockers
        )
        classification = (
            "replication_pass_pending_future_blind"
            if passed
            else "insufficient_evidence"
            if base_net > 0.0 and stress_net > 0.0 and closed_positions < 30 and not blockers
            else "reject"
        )
        candidates.append(
            {
                "label": candidate["label"],
                "source": identity[0],
                "model_version": identity[1],
                "scenario_metrics": scenario,
                "yearly_base_net_pnl": dict(sorted(yearly_base.items())),
                "monthly_metrics": monthly,
                "blockers": sorted(set(blockers)),
                "gates": gates,
                "classification": classification,
            }
        )
    if {row["source"] for row in candidates} != {value[0] for value in expected_identities}:
        raise ValueError("Protocol v7 review must include all three locked candidates")
    passers = [row for row in candidates if row["classification"].startswith("replication_pass")]
    return {
        "schema_version": SCHEMA_VERSION,
        "candidates": candidates,
        "selected_candidate_count": len(passers),
        "recommendation": "future_blind_remains_sealed"
        if passers
        else "stop_before_testnet_resume",
        "catalog_audit": catalog_audit,
        "boundaries": {
            "places_orders": False,
            "writes_signal_event": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "resumes_testnet": False,
            "touches_live_path": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", required=True, help="label=run_dir")
    parser.add_argument("--catalog-audit", type=Path, required=True)
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--bar-type", required=True)
    args = parser.parse_args(argv)
    specs: list[tuple[str, Path]] = []
    for value in args.candidate:
        if "=" not in value:
            parser.error("--candidate must use label=run_dir")
        label, path = value.split("=", 1)
        specs.append((label, Path(path)))
    alpha = build_v7_alpha(specs)
    catalog_audit = json.loads(args.catalog_audit.read_text())
    print(
        json.dumps(
            classify_review(alpha, catalog_audit),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

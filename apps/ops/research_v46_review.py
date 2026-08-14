"""Evaluate Protocol v46 development replays against preregistered gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v46 import (
    GATES,
    IDENTITIES,
    load_and_validate,
)
from apps.ops.research_v9_review import STEP_NS, _months

SCHEMA_VERSION = "research.v46.development_results.v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_development(
    candidate_bundles: dict[str, list[Path]],
    output_path: Path,
) -> dict[str, Any]:
    validation = load_and_validate()
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 1, tzinfo=UTC)

    candidate_results: dict[str, Any] = {}
    passing: list[str] = []

    for key, (expected_source, expected_model) in IDENTITIES.items():
        bundles = candidate_bundles.get(key, [])
        if len(bundles) != 2:
            raise ValueError(f"expected 2 bundles for {key}, got {len(bundles)}")
        runs = [
            _analyze_bundle(
                p,
                start_ns=int(start.timestamp() * 1_000_000_000),
                end_exclusive_ns=int(end.timestamp() * 1_000_000_000),
                months=_months(2020, 2022),
                bar_interval_ns=STEP_NS,
            )
            for p in bundles
        ]
        for r in runs:
            if (r["source"], r["model_version"]) != (expected_source, expected_model):
                raise ValueError(f"bundle identity mismatch for {key}: {r['source']}, {r['model_version']}")
        primary = runs[0]
        reproducible = _runs_reproducible(runs)

        yearly = {"2020": 0.0, "2021": 0.0, "2022": 0.0}
        positive_months = 0
        for row in primary["monthly_metrics"]:
            base = float(row["scenarios"]["base"]["net_pnl"])
            yearly[str(row["month"])[:4]] += base
            positive_months += int(base > 0.0)

        scenario = primary["scenario_metrics"]
        base_pnl = float(scenario["base"]["net_pnl"])
        stress_pnl = float(scenario["stress"]["net_pnl"])
        leave_best = float(primary["base_net_without_best_position"])
        closed_pos = int(primary["closed_positions"])
        pos_years = sum(v > 0.0 for v in yearly.values())

        pass_gates = bool(
            base_pnl > float(GATES["base_net_pnl_gt"])
            and stress_pnl > float(GATES["stress_net_pnl_gt"])
            and pos_years >= int(GATES["positive_calendar_years_at_least"])
            and positive_months >= int(GATES["positive_calendar_months_at_least"])
            and closed_pos >= int(GATES["closed_positions_at_least"])
            and leave_best > float(GATES["leave_best_position_base_net_pnl_gt"])
            and reproducible
            and int(primary["short_positions"]) == 0
        )

        candidate_results[key] = {
            "key": key,
            "source": expected_source,
            "model_version": expected_model,
            "base_net_pnl": base_pnl,
            "stress_net_pnl": stress_pnl,
            "positive_years": pos_years,
            "positive_months": positive_months,
            "closed_positions": closed_pos,
            "leave_best_base_net_pnl": leave_best,
            "duplicate_replays": len(runs),
            "reproducible": reproducible,
            "short_positions": int(primary["short_positions"]),
            "pass_gates": pass_gates,
            "classification": "development_pass_confirmation_open_eligible"
            if pass_gates
            else "development_rejected",
        }
        if pass_gates:
            passing.append(key)

    best_candidate = None
    if passing:
        best_candidate = max(passing, key=lambda k: float(candidate_results[k]["base_net_pnl"]))

    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_sha256": validation["protocol_sha256"],
        "candidates": candidate_results,
        "passing_candidates": passing,
        "best_candidate": best_candidate,
        "boundaries": {
            "mutates_source_policy": False,
            "loads_credentials": False,
            "touches_live_path": False,
            "opens_confirmation_early": False,
            "opens_future_blind": False,
        },
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff5-a", type=Path, required=True)
    parser.add_argument("--diff5-b", type=Path, required=True)
    parser.add_argument("--loose-a", type=Path, required=True)
    parser.add_argument("--loose-b", type=Path, required=True)
    parser.add_argument("--minhold2-a", type=Path, required=True)
    parser.add_argument("--minhold2-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/progress/phase-2-research-v46-development-results.json"))
    args = parser.parse_args(argv)

    candidate_bundles = {
        "btc_prem_diff5_negative": [args.diff5_a, args.diff5_b],
        "btc_prem_diff5_loose": [args.loose_a, args.loose_b],
        "btc_prem_diff5_minhold2": [args.minhold2_a, args.minhold2_b],
    }
    evaluate_development(candidate_bundles, args.output)
    print(f"saved development review to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

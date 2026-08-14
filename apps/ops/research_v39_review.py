"""Evaluate Protocol v39 development replay results against the preregistered gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v39 import (
    GATES,
    IDENTITIES,
    load_and_validate,
)
from apps.ops.research_v9_review import STEP_NS, _months

SCHEMA_VERSION = "research.v39.development_results.v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_candidate(
    key: str,
    bundle_paths: list[Path],
) -> dict[str, Any]:
    expected_source, expected_model = IDENTITIES[key]
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 1, tzinfo=UTC)
    runs = [
        _analyze_bundle(
            p,
            start_ns=int(start.timestamp() * 1_000_000_000),
            end_exclusive_ns=int(end.timestamp() * 1_000_000_000),
            months=_months(2020, 2022),
            bar_interval_ns=STEP_NS,
        )
        for p in bundle_paths
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

    return {
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lovol-a", type=Path, required=True)
    parser.add_argument("--lovol-b", type=Path, required=True)
    parser.add_argument("--putd-a", type=Path, required=True)
    parser.add_argument("--putd-b", type=Path, required=True)
    parser.add_argument("--cndr-a", type=Path, required=True)
    parser.add_argument("--cndr-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    validation = load_and_validate()
    res_lovol = evaluate_candidate("lovol_expansion", [args.lovol_a, args.lovol_b])
    res_putd = evaluate_candidate("putd_expansion", [args.putd_a, args.putd_b])
    res_cndr = evaluate_candidate("cndr_expansion", [args.cndr_a, args.cndr_b])

    candidates = {
        "lovol_expansion": res_lovol,
        "putd_expansion": res_putd,
        "cndr_expansion": res_cndr,
    }
    passing = [k for k, v in candidates.items() if v["pass_gates"]]

    best_candidate = None
    if passing:
        best_candidate = sorted(
            passing,
            key=lambda k: (
                candidates[k]["positive_months"],
                candidates[k]["leave_best_base_net_pnl"],
                candidates[k]["base_net_pnl"],
            ),
            reverse=True,
        )[0]

    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_sha256": validation["protocol_sha256"],
        "candidates": candidates,
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"saved development review to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

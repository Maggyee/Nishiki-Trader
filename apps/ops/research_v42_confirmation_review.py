"""Evaluate Protocol v42 confirmation holdout results against preregistered gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v42 import (
    GATES,
)
from apps.ops.research_v9_review import STEP_NS, _months
from apps.ops.research_v42_confirmation import load_and_validate

SCHEMA_VERSION = "research.v42.confirmation_results.v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_confirmation(
    bundle_paths: list[Path],
    output_path: Path,
) -> dict[str, Any]:
    validation = load_and_validate()
    expected_source = "rule_cboe_vix6m_relief_v1"
    expected_model = "cboe-vix6m-diff5-negative-lag1d-v1"

    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [
        _analyze_bundle(
            p,
            start_ns=int(start.timestamp() * 1_000_000_000),
            end_exclusive_ns=int(end.timestamp() * 1_000_000_000),
            months=_months(2023, 2025),
            bar_interval_ns=STEP_NS,
        )
        for p in bundle_paths
    ]
    for r in runs:
        if (r["source"], r["model_version"]) != (expected_source, expected_model):
            raise ValueError(f"bundle identity mismatch: {r['source']}, {r['model_version']}")
    primary = runs[0]
    reproducible = _runs_reproducible(runs)

    yearly = {"2023": 0.0, "2024": 0.0, "2025": 0.0}
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

    result = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "confirmation_sha256": validation["confirmation_sha256"],
        "candidate": "vix6m_relief",
        "source": expected_source,
        "model_version": expected_model,
        "base_net_pnl": base_pnl,
        "stress_net_pnl": stress_pnl,
        "positive_years": pos_years,
        "positive_months": positive_months,
        "closed_positions": closed_pos,
        "leave_best_base_net_pnl": leave_best,
        "yearly_base_net_pnl": yearly,
        "duplicate_replays": len(runs),
        "reproducible": reproducible,
        "short_positions": int(primary["short_positions"]),
        "pass_gates": pass_gates,
        "classification": "paper_shadow_review_eligible"
        if pass_gates
        else "reject_candidate",
        "boundaries": {
            "mutates_source_policy": False,
            "loads_credentials": False,
            "touches_live_path": False,
            "opens_future_blind": False,
        },
    }
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-a", type=Path, required=True)
    parser.add_argument("--bundle-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/progress/phase-2-research-v42-confirmation-results.json"))
    args = parser.parse_args(argv)
    res = evaluate_confirmation([args.bundle_a, args.bundle_b], args.output)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

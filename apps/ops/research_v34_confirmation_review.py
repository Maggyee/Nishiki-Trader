"""Evaluate 2023-2025 confirmation results for Protocol v34 FVX relief."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps.ops.research_v13_review import (
    _calendar_year_net_pnl,
    _compute_leave_best_position_pnl,
    _is_cash_long_flat_run,
    _load_fills,
    _load_manifest,
    _load_positions,
    _monthly_net_pnl,
    _scenario_net_pnl,
    _sha256,
)
from apps.ops.research_v34_confirmation import DEFAULT_CONTRACT, load_and_validate_confirmation

SCHEMA_VERSION = "research.protocol.v34.confirmation.results.v1"


def evaluate_confirmation(
    bundle_paths: list[Path],
    *,
    contract_path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    validation = load_and_validate_confirmation(contract_path)
    contract = json.loads(contract_path.read_text())
    if len(bundle_paths) != 2:
        raise ValueError("Confirmation evaluation requires exactly two bundle paths")
    manifests = [_load_manifest(path) for path in bundle_paths]
    manifest_shas = [_sha256(path / "run_manifest.json") for path in bundle_paths]
    fills_shas = [_sha256(path / "fills.parquet") for path in bundle_paths]
    if fills_shas[0] != fills_shas[1]:
        raise ValueError("Confirmation runs produced non-deterministic fills")
    primary_manifest = manifests[0]
    fills_df = _load_fills(bundle_paths[0])
    positions_df = _load_positions(bundle_paths[0])
    gross_pnl = _scenario_net_pnl(fills_df, fee_bps=0.0, slippage_bps=0.0)
    base_pnl = _scenario_net_pnl(fills_df, fee_bps=10.0, slippage_bps=2.0)
    stress_pnl = _scenario_net_pnl(fills_df, fee_bps=10.0, slippage_bps=5.0)
    monthly = _monthly_net_pnl(fills_df, fee_bps=10.0, slippage_bps=2.0)
    yearly = _calendar_year_net_pnl(fills_df, fee_bps=10.0, slippage_bps=2.0)
    leave_best_pnl = _compute_leave_best_position_pnl(
        positions_df, fills_df, fee_bps=10.0, slippage_bps=2.0
    )
    closed_positions = len(positions_df) if not positions_df.empty else 0
    short_positions = 0
    if not positions_df.empty and "side" in positions_df.columns:
        short_positions = int((positions_df["side"] == "SHORT").sum())
    cash_long_flat = _is_cash_long_flat_run(primary_manifest)
    gates = contract["gates"]
    failures: list[str] = []
    if base_pnl <= gates["base_net_pnl_gt"]:
        failures.append("base_net_pnl_not_positive")
    if stress_pnl <= gates["stress_net_pnl_gt"]:
        failures.append("stress_net_pnl_not_positive")
    pos_years = sum(1 for v in yearly.values() if v > 0)
    if pos_years < gates["positive_calendar_years_at_least"]:
        failures.append(f"positive_calendar_years_{pos_years}_below_threshold")
    pos_months = sum(1 for v in monthly.values() if v > 0)
    if pos_months < gates["positive_calendar_months_at_least"]:
        failures.append(f"positive_calendar_months_{pos_months}_below_threshold")
    if closed_positions < gates["closed_positions_at_least"]:
        failures.append(f"closed_positions_{closed_positions}_below_threshold")
    if leave_best_pnl <= gates["leave_best_position_base_net_pnl_gt"]:
        failures.append("leave_best_position_not_positive")
    if not cash_long_flat or short_positions > 0:
        failures.append("not_cash_long_flat_only")
    passed = len(failures) == 0
    outcome = contract["outcomes"]["all_gates_pass" if passed else "performance_gate_fails"]
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": validation["contract_sha256"],
        "candidate": contract["candidate"]["key"],
        "passed": passed,
        "classification": outcome,
        "failures": failures,
        "metrics": {
            "gross_net_pnl": gross_pnl,
            "base_net_pnl": base_pnl,
            "stress_net_pnl": stress_pnl,
            "leave_best_base_net_pnl": leave_best_pnl,
            "closed_positions": closed_positions,
            "short_positions": short_positions,
            "positive_years": pos_years,
            "total_years": len(yearly),
            "positive_months": pos_months,
            "total_months": len(monthly),
            "yearly_base_net_pnl": yearly,
        },
        "reproducibility": {
            "duplicate_replays": 2,
            "manifest_shas": manifest_shas,
            "fills_shas": fills_shas,
            "reproducible": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", action="append", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_confirmation(args.bundle, contract_path=args.contract)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

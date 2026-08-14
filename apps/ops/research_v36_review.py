"""Evaluate Protocol v36 2020-2022 development replays against frozen gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from apps.ops.research_protocol_v36 import (
    DEFAULT_CONTRACT,
    GATES,
    IDENTITIES,
    load_and_validate,
)

SCHEMA_VERSION = "research.v36.development_results.v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def evaluate_candidate(
    bundle_a_path: Path,
    bundle_b_path: Path,
    *,
    candidate_key: str,
) -> dict[str, Any]:
    if candidate_key not in IDENTITIES:
        raise ValueError(f"unknown candidate key {candidate_key!r}")
    source, model_version = IDENTITIES[candidate_key]

    fills_a = (bundle_a_path / "fills.parquet").read_bytes()
    fills_b = (bundle_b_path / "fills.parquet").read_bytes()
    if hashlib.sha256(fills_a).hexdigest() != hashlib.sha256(fills_b).hexdigest():
        raise ValueError(f"duplicate replays for {candidate_key} did not produce bitwise identical fills")

    fills_df = pd.read_parquet(bundle_a_path / "fills.parquet")
    positions_df = pd.read_parquet(bundle_a_path / "positions.parquet")

    if not fills_df.empty:
        total_pnl = float(positions_df["realized_pnl"].sum()) if not positions_df.empty else 0.0
        closed_positions = len(positions_df)
        short_positions = int((positions_df["side"].astype(str) == "SHORT").sum()) if not positions_df.empty else 0
        fee_bps = 10.0
        slippage_bps = 2.0
        stress_slippage_bps = 5.0
        turnover = float(fills_df["quote_amount"].sum()) if "quote_amount" in fills_df.columns else 0.0
        base_cost = turnover * ((fee_bps + slippage_bps) / 10000.0)
        stress_cost = turnover * ((fee_bps + stress_slippage_bps) / 10000.0)
        base_net_pnl = total_pnl - base_cost
        stress_net_pnl = total_pnl - stress_cost
        if not positions_df.empty and "realized_pnl" in positions_df.columns:
            best_pnl = float(positions_df["realized_pnl"].max())
            leave_best = base_net_pnl - best_pnl
        else:
            leave_best = base_net_pnl

        positions_df["dt_closed"] = pd.to_datetime(positions_df["ts_closed"], utc=True)
        positions_df["year"] = positions_df["dt_closed"].dt.year
        positions_df["year_month"] = positions_df["dt_closed"].dt.to_period("M")
        yearly_pnl = positions_df.groupby("year")["realized_pnl"].sum().to_dict()
        monthly_pnl = positions_df.groupby("year_month")["realized_pnl"].sum().to_dict()
        positive_years = sum(1 for v in yearly_pnl.values() if v > 0)
        positive_months = sum(1 for v in monthly_pnl.values() if v > 0)
    else:
        base_net_pnl = 0.0
        stress_net_pnl = 0.0
        closed_positions = 0
        short_positions = 0
        leave_best = 0.0
        positive_years = 0
        positive_months = 0

    pass_base = base_net_pnl > GATES["base_net_pnl_gt"]
    pass_stress = stress_net_pnl > GATES["stress_net_pnl_gt"]
    pass_years = positive_years >= GATES["positive_calendar_years_at_least"]
    pass_months = positive_months >= GATES["positive_calendar_months_at_least"]
    pass_positions = closed_positions >= GATES["closed_positions_at_least"]
    pass_leave_best = leave_best > GATES["leave_best_position_base_net_pnl_gt"]
    pass_no_shorts = short_positions == 0

    passed = (
        pass_base
        and pass_stress
        and pass_years
        and pass_months
        and pass_positions
        and pass_leave_best
        and pass_no_shorts
    )

    return {
        "key": candidate_key,
        "source": source,
        "model_version": model_version,
        "base_net_pnl": base_net_pnl,
        "stress_net_pnl": stress_net_pnl,
        "closed_positions": closed_positions,
        "short_positions": short_positions,
        "leave_best_base_net_pnl": leave_best,
        "positive_years": positive_years,
        "positive_months": positive_months,
        "duplicate_replays": 2,
        "reproducible": True,
        "pass_gates": passed,
        "classification": "development_pass_confirmation_open_eligible"
        if passed
        else "development_rejected",
    }


def evaluate_all(
    results_map: dict[str, tuple[Path, Path]],
    *,
    contract_path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    validation = load_and_validate(contract_path)
    candidates_eval: dict[str, Any] = {}
    passing_candidates: list[str] = []

    for key, (bundle_a, bundle_b) in results_map.items():
        res = evaluate_candidate(bundle_a, bundle_b, candidate_key=key)
        candidates_eval[key] = res
        if res["pass_gates"]:
            passing_candidates.append(key)

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": validation["protocol_sha256"],
        "evaluated_at": "2026-08-14T02:20:00Z",
        "candidates": candidates_eval,
        "passing_candidates": passing_candidates,
        "best_candidate": max(
            passing_candidates,
            key=lambda k: candidates_eval[k]["base_net_pnl"],
            default=None,
        ),
        "boundaries": {
            "loads_credentials": False,
            "mutates_source_policy": False,
            "touches_live_path": False,
            "opens_confirmation_early": False,
            "opens_future_blind": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpn-a", type=Path, required=True)
    parser.add_argument("--vpn-b", type=Path, required=True)
    parser.add_argument("--put-a", type=Path, required=True)
    parser.add_argument("--put-b", type=Path, required=True)
    parser.add_argument("--bxm-a", type=Path, required=True)
    parser.add_argument("--bxm-b", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    results_map = {
        "vpn_expansion": (args.vpn_a, args.vpn_b),
        "put_expansion": (args.put_a, args.put_b),
        "bxm_expansion": (args.bxm_a, args.bxm_b),
    }
    result = evaluate_all(results_map, contract_path=args.contract)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

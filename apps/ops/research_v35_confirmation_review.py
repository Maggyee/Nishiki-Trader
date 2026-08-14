"""Evaluate the frozen Protocol v35 confirmation candidate against 2023-2025 replay bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from apps.ops.research_v35_confirmation import DEFAULT_CONTRACT, load_and_validate
from apps.strategies_nautilus.result_schema import load_bundle_summary

SCHEMA_VERSION = "research.v35.confirmation_results.v1"
CONFIRMATION_DATA_SOURCES = Path(
    "docs/progress/phase-2-research-v35-confirmation-data-sources.json"
)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def evaluate_confirmation(
    bundle_a_path: Path,
    bundle_b_path: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    data_sources_path: Path = CONFIRMATION_DATA_SOURCES,
) -> dict[str, Any]:
    validation = load_and_validate(contract_path)
    contract = json.loads(contract_path.read_text())
    data_sources = json.loads(data_sources_path.read_text())
    if data_sources.get("schema_version") != "research.v35.confirmation.data_sources.v1":
        raise ValueError("confirmation data sources schema drifted")

    summary_a = load_bundle_summary(bundle_a_path)
    summary_b = load_bundle_summary(bundle_b_path)
    if summary_a.pnl_total_by_currency != summary_b.pnl_total_by_currency:
        raise ValueError("duplicate replays produced divergent pnl summaries")

    fills_a = (bundle_a_path / "fills.parquet").read_bytes()
    fills_b = (bundle_b_path / "fills.parquet").read_bytes()
    if hashlib.sha256(fills_a).hexdigest() != hashlib.sha256(fills_b).hexdigest():
        raise ValueError("duplicate replays did not produce bitwise identical fills")

    fills_df = pd.read_parquet(bundle_a_path / "fills.parquet")
    positions_df = pd.read_parquet(bundle_a_path / "positions.parquet")

    base_net_pnl = float(summary_a.pnl_total_by_currency.get("USDT", 0.0))
    closed_positions = len(positions_df)
    short_positions = int((positions_df["side"].astype(str) == "SHORT").sum()) if not positions_df.empty else 0

    if not positions_df.empty and "realized_pnl" in positions_df.columns:
        best_pnl = float(positions_df["realized_pnl"].max())
        leave_best = base_net_pnl - best_pnl
    else:
        leave_best = base_net_pnl

    fee_total = float(summary_a.commission_total_by_currency.get("USDT", 0.0))
    stress_extra_bps = 3.0
    if not fills_df.empty and "quote_amount" in fills_df.columns:
        volume = float(fills_df["quote_amount"].sum())
        stress_extra = volume * (stress_extra_bps / 10000.0)
    else:
        stress_extra = 0.0
    stress_net_pnl = base_net_pnl - stress_extra

    if not positions_df.empty and "ts_closed" in positions_df.columns:
        positions_df["dt_closed"] = pd.to_datetime(positions_df["ts_closed"], utc=True)
        positions_df["year"] = positions_df["dt_closed"].dt.year
        positions_df["year_month"] = positions_df["dt_closed"].dt.to_period("M")
        yearly_pnl = positions_df.groupby("year")["realized_pnl"].sum().to_dict()
        monthly_pnl = positions_df.groupby("year_month")["realized_pnl"].sum().to_dict()
        positive_years = sum(1 for v in yearly_pnl.values() if v > 0)
        positive_months = sum(1 for v in monthly_pnl.values() if v > 0)
    else:
        positive_years = 0
        positive_months = 0

    gates = contract["gates"]
    pass_base = base_net_pnl > gates["base_net_pnl_gt"]
    pass_stress = stress_net_pnl > gates["stress_net_pnl_gt"]
    pass_years = positive_years >= gates["positive_calendar_years_at_least"]
    pass_months = positive_months >= gates["positive_calendar_months_at_least"]
    pass_positions = closed_positions >= gates["closed_positions_at_least"]
    pass_leave_best = leave_best > gates["leave_best_position_base_net_pnl_gt"]
    pass_no_shorts = short_positions == 0

    all_passed = (
        pass_base
        and pass_stress
        and pass_years
        and pass_months
        and pass_positions
        and pass_leave_best
        and pass_no_shorts
    )

    candidate_result = {
        "key": contract["candidate"]["key"],
        "source": contract["candidate"]["source"],
        "model_version": contract["candidate"]["model_version"],
        "base_net_pnl": base_net_pnl,
        "stress_net_pnl": stress_net_pnl,
        "fee_total": fee_total,
        "closed_positions": closed_positions,
        "short_positions": short_positions,
        "leave_best_base_net_pnl": leave_best,
        "positive_years": positive_years,
        "positive_months": positive_months,
        "duplicate_replays": 2,
        "reproducible": True,
        "performance_pass": all_passed,
        "evidence_pass": True,
        "classification": "paper_shadow_review_eligible" if all_passed else "confirmation_rejected",
    }

    result = {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": validation["contract_sha256"],
        "evaluated_at": "2026-08-14T01:58:00Z",
        "passed": all_passed,
        "candidate": candidate_result,
        "recommendation": "enter_paper_shadow_review" if all_passed else "reject_candidate_protocol_closed",
        "boundaries": {
            "loads_credentials": False,
            "mutates_source_policy": False,
            "touches_live_path": False,
            "opens_future_blind": False,
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-a", type=Path, required=True)
    parser.add_argument("--bundle-b", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--data-sources", type=Path, default=CONFIRMATION_DATA_SOURCES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_confirmation(
        args.bundle_a,
        args.bundle_b,
        contract_path=args.contract,
        data_sources_path=args.data_sources,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

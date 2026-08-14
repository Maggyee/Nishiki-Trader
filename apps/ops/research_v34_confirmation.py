"""Validate the frozen Protocol v34 FVX confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v34 import COMMON_PARAMETERS, IDENTITIES

DEFAULT_CONTRACT = Path("docs/progress/phase-2-research-v34-confirmation.json")
SCHEMA_VERSION = "research.protocol.v34.confirmation.v1"
CANDIDATE = "fvx_relief"
DEVELOPMENT_REVIEW = "5940fd2"
DEVELOPMENT_RESULTS_PATH = Path("docs/progress/phase-2-research-v34-development-results.json")
DEVELOPMENT_RESULTS_SHA256 = (
    "sha256:414d69aff29500ddd203d1468ccd88cf371d4140939f6f6ee297bfe95ce9dcaa"
)
PROTOCOL_SHA256 = "sha256:3764bb1c63c004fe511f665a677730f8dfae40a315a55bdebed17271c5eae082"
SNAPSHOT_PATH = Path("data/research-v34/raw/fvx-20260814T014407Z-75b2f82d3153.json")
SNAPSHOT_SHA256 = "sha256:75b2f82d31537e642123f62f7d44c732bc930e6c89aa74588fe88ed5579fc6ee"
EXECUTION_AUDIT_PATH = Path("data/research-v8/execution-audit.json")
EXECUTION_AUDIT_SHA256 = "sha256:02f3179b79a9720210419241af82ab9563ff2a67cb23f18641934edb3e7caca1"
COST_SCENARIOS = {
    "gross": {"fee_bps_per_fill": 0, "slippage_bps_per_fill": 0},
    "base": {"fee_bps_per_fill": 10, "slippage_bps_per_fill": 2},
    "stress": {"fee_bps_per_fill": 10, "slippage_bps_per_fill": 5},
}
GATES = {
    "base_net_pnl_gt": 0,
    "stress_net_pnl_gt": 0,
    "positive_calendar_years_at_least": 2,
    "positive_calendar_months_at_least": 18,
    "closed_positions_at_least": 30,
    "leave_best_position_base_net_pnl_gt": 0,
    "duplicate_replays_required": 2,
    "spot_long_flat_only": True,
    "evidence_blockers_required": 0,
}
OUTCOMES = {
    "all_gates_pass": "paper_shadow_review_eligible",
    "performance_gate_fails": "reject_candidate",
    "evidence_gate_fails": "insufficient_confirmation_evidence",
}
BOUNDARIES_EFFECT = {
    "loads_credentials": False,
    "makes_network_request": False,
    "mutates_source_policy": False,
    "touches_existing_paper_shadow": False,
    "resumes_testnet": False,
    "touches_live_path": False,
    "opens_future_blind": False,
}


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != (
        "preregistered_before_fvx_confirmation_value_access"
    ):
        raise ValueError("Protocol v34 confirmation identity drifted")
    development = payload.get("development_evidence", {})
    if (
        development.get("committed_review") != DEVELOPMENT_REVIEW
        or development.get("development_results") != str(DEVELOPMENT_RESULTS_PATH)
        or development.get("development_results_sha256") != DEVELOPMENT_RESULTS_SHA256
        or development.get("protocol_sha256") != PROTOCOL_SHA256
        or development.get("development_classification")
        != "development_pass_confirmation_open_eligible"
    ):
        raise ValueError("Protocol v34 development prerequisite drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if (
        disclosure.get("source_snapshot_already_captured_and_qualified") is not True
        or disclosure.get("confirmation_value_rows_reported") is not False
        or disclosure.get("confirmation_returns_computed") is not False
        or disclosure.get("confirmation_pnl_computed") is not False
        or disclosure.get("new_network_request_required") is not False
    ):
        raise ValueError("Protocol v34 confirmation access disclosure drifted")
    candidate = payload.get("candidate", {})
    if (
        (candidate.get("source"), candidate.get("model_version")) != IDENTITIES[CANDIDATE]
        or candidate.get("key") != CANDIDATE
        or candidate.get("index") != "FVX"
        or candidate.get("parameters") != COMMON_PARAMETERS
        or candidate.get("parameter_changes_forbidden") is not True
    ):
        raise ValueError("Protocol v34 confirmation candidate drifted")
    confirmation = payload.get("confirmation", {})
    if confirmation != {
        "start": "2023-01-01",
        "end": "2025-12-31",
        "pnl_status": "unconsumed",
        "fold_initial_state": "flat",
    }:
        raise ValueError("Protocol v34 confirmation partition drifted")
    data = payload.get("data_contract", {})
    if data.get("source_snapshot") != {
        "path": str(SNAPSHOT_PATH),
        "snapshot_sha256": SNAPSHOT_SHA256,
    }:
        raise ValueError("Protocol v34 confirmation snapshot drifted")
    if (
        data.get("value_column") != "FVX"
        or data.get("warmup_start") != "2022-11-01"
        or data.get("decision_lag_calendar_days") != 1
        or data.get("minimum_confirmation_rows") != 700
        or data.get("first_observation_on_or_before") != "2023-01-05"
        or data.get("last_observation_on_or_after") != "2025-12-29"
        or data.get("maximum_calendar_gap_days") != 5
        or data.get("missing_value_policy") != "drop missing official observation; never fill"
        or data.get("execution_catalog") != "data/research-v8/catalog"
        or data.get("execution_audit") != str(EXECUTION_AUDIT_PATH)
        or data.get("execution_audit_sha256") != EXECUTION_AUDIT_SHA256
    ):
        raise ValueError("Protocol v34 confirmation data contract drifted")
    if (
        payload.get("cost_scenarios") != COST_SCENARIOS
        or payload.get("gates") != GATES
        or payload.get("outcomes") != OUTCOMES
    ):
        raise ValueError("Protocol v34 confirmation costs, gates, or outcomes drifted")
    if payload.get("future_blind") != {
        "start": "2026-09-01",
        "end": "2027-01-31",
        "status": "sealed_unopened",
    }:
        raise ValueError("Protocol v34 future blind drifted")
    if payload.get("boundaries_effect") != BOUNDARIES_EFFECT:
        raise ValueError("Protocol v34 confirmation boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v34 confirmation root must be an object")
    result = validate_contract(payload)
    actual_development_hash = (
        "sha256:" + hashlib.sha256(DEVELOPMENT_RESULTS_PATH.read_bytes()).hexdigest()
    )
    if actual_development_hash != DEVELOPMENT_RESULTS_SHA256:
        raise ValueError("Protocol v34 committed development evidence drifted")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

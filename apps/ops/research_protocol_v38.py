"""Contract definitions and validation for Phase 2 Alpha Research Protocol v38."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL_PATH = Path("docs/progress/phase-2-research-protocol-v38.json")
SCHEMA_VERSION = "research.protocol.v38.v1"

INDEX_BY_CANDIDATE = {
    "vpd_expansion": "VPD",
    "pput_expansion": "PPUT",
    "cll_expansion": "CLL",
}

IDENTITIES = {
    "vpd_expansion": (
        "rule_cboe_vpd_expansion_v1",
        "cboe-vpd-diff5-positive-lag1d-v1",
    ),
    "pput_expansion": (
        "rule_cboe_pput_expansion_v1",
        "cboe-pput-diff5-positive-lag1d-v1",
    ),
    "cll_expansion": (
        "rule_cboe_cll_expansion_v1",
        "cboe-cll-diff5-positive-lag1d-v1",
    ),
}

COMMON_PARAMETERS = {
    "change_observations": 5,
    "direction": "positive",
    "threshold": 0.0,
    "publication_lag_calendar_days": 1,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}

COST_SCENARIOS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}

GATES = {
    "base_net_pnl_gt": 0.0,
    "stress_net_pnl_gt": 0.0,
    "positive_calendar_years_at_least": 2,
    "positive_calendar_months_at_least": 18,
    "closed_positions_at_least": 30,
    "leave_best_position_base_net_pnl_gt": 0.0,
    "duplicate_replays_required": 2,
    "spot_long_flat_only": True,
    "evidence_blockers_required": 0,
}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"expected schema {SCHEMA_VERSION}, got {payload.get('schema_version')}")
    if payload.get("status") != "preregistered_before_data_collection":
        raise ValueError(f"expected status preregistered_before_data_collection, got {payload.get('status')}")
    candidates = payload.get("candidates", {})
    if set(candidates) != set(INDEX_BY_CANDIDATE):
        raise ValueError(f"candidate mismatch: {sorted(candidates)} vs {sorted(INDEX_BY_CANDIDATE)}")
    for key, spec in candidates.items():
        expected_source, expected_model = IDENTITIES[key]
        if spec.get("source") != expected_source or spec.get("model_version") != expected_model:
            raise ValueError(f"identity mismatch for {key}")
        if spec.get("index") != INDEX_BY_CANDIDATE[key]:
            raise ValueError(f"index mismatch for {key}")
        if spec.get("parameters") != COMMON_PARAMETERS:
            raise ValueError(f"parameters mismatch for {key}")
    if payload.get("cost_scenarios") != COST_SCENARIOS:
        raise ValueError("cost scenarios drifted")
    if payload.get("gates") != GATES:
        raise ValueError("gates drifted")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": _sha256(canonical.encode()),
        "valid": True,
        "candidate_count": len(candidates),
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("protocol must be a JSON object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

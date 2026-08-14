"""Validate and load the frozen Protocol v36 pre-registration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_CONTRACT = Path("docs/progress/phase-2-research-protocol-v36.json")
SCHEMA_VERSION = "research.protocol.v36.v1"

IDENTITIES = {
    "vpn_expansion": (
        "rule_cboe_vpn_expansion_v1",
        "cboe-vpn-diff5-positive-lag1d-v1",
    ),
    "put_expansion": (
        "rule_cboe_put_expansion_v1",
        "cboe-put-diff5-positive-lag1d-v1",
    ),
    "bxm_expansion": (
        "rule_cboe_bxm_expansion_v1",
        "cboe-bxm-diff5-positive-lag1d-v1",
    ),
}

INDEX_BY_CANDIDATE = {
    "vpn_expansion": "VPN",
    "put_expansion": "PUT",
    "bxm_expansion": "BXM",
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


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"expected schema_version={SCHEMA_VERSION}, got {payload.get('schema_version')!r}"
        )
    if payload.get("status") != "preregistered_before_csv_body_access":
        raise ValueError(f"status drifted: {payload.get('status')!r}")
    if payload.get("common_parameters") != COMMON_PARAMETERS:
        raise ValueError("common parameters drifted")
    if payload.get("cost_scenarios") != COST_SCENARIOS:
        raise ValueError("cost scenarios drifted")
    if payload.get("gates") != GATES:
        raise ValueError("gates drifted")

    candidates = payload.get("candidates", [])
    if len(candidates) != 3:
        raise ValueError(f"expected 3 candidates, got {len(candidates)}")

    seen_keys: set[str] = set()
    for candidate in candidates:
        key = candidate.get("key")
        if key not in IDENTITIES:
            raise ValueError(f"unknown candidate key {key!r}")
        seen_keys.add(key)
        source, model = IDENTITIES[key]
        if candidate.get("source") != source or candidate.get("model_version") != model:
            raise ValueError(f"identity mismatch for {key}")
        if candidate.get("parameters") != COMMON_PARAMETERS:
            raise ValueError(f"parameter mismatch for {key}")

    if seen_keys != set(IDENTITIES):
        raise ValueError("candidates set does not match expected keys")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": _sha256(canonical.encode()),
        "candidate_count": len(candidates),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("protocol contract must be a JSON object")
    return validate_contract(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    result = load_and_validate(args.contract)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

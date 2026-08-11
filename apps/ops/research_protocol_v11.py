"""Validate the frozen Research Protocol v11 finalized-ledger contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v11.json")
SCHEMA_VERSION = "research.protocol.v11"
IDENTITIES = {
    "miner_hashrate_recovery": (
        "rule_miner_hashrate_recovery_v3",
        "chainfinalized-hashrate7-30-positive-lag2d-v1",
    ),
    "stablecoin_liquidity_expansion": (
        "rule_stablecoin_liquidity_v2",
        "chainfinalized-usdt-usdc-splycur30d-positive-lag2d-v1",
    ),
    "btc_fee_demand": ("rule_btc_fee_demand_v2", "chainfinalized-feetotntv7-30-positive-lag2d-v1"),
}
PARAMETERS = {
    "miner_hashrate_recovery": {
        "short_days": 7,
        "long_days": 30,
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
    "stablecoin_liquidity_expansion": {
        "change_days": 30,
        "maximum_change": 0.0,
        "assets": ["usdt", "usdc"],
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
    "btc_fee_demand": {
        "short_days": 7,
        "long_days": 30,
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
}
SNAPSHOTS = {
    "hashrate": "sha256:7cc0ce6692dd24ac4bdb7213b4f10930de39491ff759dbe0f23ff5879d2c72ab",
    "stablecoin_supply": "sha256:caf97d08177affc162d8bcf48d30b2071e16865836c032c8428108ad90a83815",
    "btc_fees": "sha256:328a58c3fb7fde94bd4631a40ca98e454b0271f90af70926fc0d1c0d21b8ecdc",
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Protocol v11 schema drifted")
    if payload.get("status") != "preregistered_after_schema_before_factor_value_and_pnl_access":
        raise ValueError("Protocol v11 pre-value status drifted")
    relation = payload.get("relationship_to_v10", {})
    if relation != {
        "v10_status": "closed_without_factor_value_or_pnl_access",
        "rules_and_parameters_unchanged": True,
        "raw_snapshots_reused_without_refresh": True,
        "new_data_semantics": "daily ledger-derived observations are consumed at D+2 00:00 UTC; no provider status-time claim is made",
    }:
        raise ValueError("Protocol v11 relationship to v10 drifted")
    point = payload.get("point_in_time_contract", {})
    if (
        point.get("decision_timestamp") != "D+2 at 00:00:00 UTC"
        or point.get("minimum_lag_hours") != 24
    ):
        raise ValueError("Protocol v11 information lag drifted")
    if (
        point.get("forward_fill_forbidden") is not True
        or point.get("provider_vintage_claimed") is not False
    ):
        raise ValueError("Protocol v11 point-in-time claims drifted")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v11 must lock exactly three candidates")
    actual = {row["key"]: (row["source"], row["model_version"]) for row in candidates}
    if actual != IDENTITIES:
        raise ValueError("Protocol v11 identities drifted")
    if {row["key"]: row.get("parameters") for row in candidates} != PARAMETERS:
        raise ValueError("Protocol v11 parameters drifted")
    if payload.get("snapshots") != SNAPSHOTS:
        raise ValueError("Protocol v11 snapshot identities drifted")
    if payload.get("gates", {}).get("multiple_testing", {}).get("candidate_count_locked") != 3:
        raise ValueError("Protocol v11 candidate count gate drifted")
    if not all(
        payload.get("gates", {}).get("multiple_testing", {}).get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v11 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v11 trading boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_count": 3,
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v11 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

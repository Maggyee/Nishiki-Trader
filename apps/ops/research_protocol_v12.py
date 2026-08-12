"""Validate the frozen Protocol v12 stablecoin-forward contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v12.json")
SCHEMA_VERSION = "research.protocol.v12"
SOURCE = "rule_stablecoin_liquidity_v3"
MODEL_VERSION = "forward-usdt-usdc-splycur30d-positive-d2-v1"


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Protocol v12 schema drifted")
    if payload.get("status") != "prospectively_locked_before_2026_coinmetrics_body_access":
        raise ValueError("Protocol v12 pre-access status drifted")
    if payload.get("relationship_to_v11") != {
        "v11_classification": "insufficient_evidence",
        "rule_and_sign_unchanged": True,
        "historical_confirmation_remains_sealed": True,
        "v11_pnl_not_used_for_parameter_selection": True,
    }:
        raise ValueError("Protocol v12 relationship to v11 drifted")
    candidate = payload.get("candidate", {})
    if (candidate.get("source"), candidate.get("model_version")) != (SOURCE, MODEL_VERSION):
        raise ValueError("Protocol v12 candidate identity drifted")
    if candidate.get("parameters") != {
        "change_observations": 30,
        "maximum_change": 0.0,
        "assets": ["usdt", "usdc"],
        "decision_lag_days": 2,
        "ttl_seconds": 86400,
        "confidence": 0.75,
    }:
        raise ValueError("Protocol v12 candidate parameters drifted")
    collection = payload.get("collection", {})
    if collection.get("coinmetrics_url") != (
        "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    ):
        raise ValueError("Protocol v12 Coin Metrics URL drifted")
    if collection.get("coinmetrics_params") != {
        "assets": "usdt,usdc",
        "metrics": "SplyCur",
        "start_time": "2026-06-01",
        "frequency": "1d",
        "page_size": "10000",
    }:
        raise ValueError("Protocol v12 Coin Metrics parameters drifted")
    if collection.get("end_time_rule") != "collection UTC date minus two calendar days":
        raise ValueError("Protocol v12 D+2 rule drifted")
    if collection.get("forward_observation_start") != "2026-08-12":
        raise ValueError("Protocol v12 forward observation boundary drifted")
    if collection.get("forward_decision_start") != "2026-08-14T00:00:00Z":
        raise ValueError("Protocol v12 forward decision boundary drifted")
    gate = payload.get("evidence_gate", {})
    if gate.get("qualified_distinct_forward_observation_days") != 180:
        raise ValueError("Protocol v12 observation gate drifted")
    if gate.get("new_forward_state_change_events") != 2 or gate.get("operator") != "and":
        raise ValueError("Protocol v12 state-change gate drifted")
    if gate.get("promotion_created") is not False:
        raise ValueError("Protocol v12 cannot create promotion eligibility")
    boundaries = payload.get("boundaries", {})
    if any(boundaries.values()):
        raise ValueError("Protocol v12 boundaries must remain false")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v12 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate the frozen Research Protocol v10 native-fundamental contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v10.json")
SCHEMA_VERSION = "research.protocol.v10"
IDENTITIES = {
    "miner_hashrate_recovery": (
        "rule_miner_hashrate_recovery_v2",
        "coinmetrics-hashrate7-30-positive-1d-v1",
    ),
    "stablecoin_liquidity_expansion": (
        "rule_stablecoin_liquidity_v1",
        "coinmetrics-usdt-usdc-splycur30d-positive-1d-v1",
    ),
    "btc_fee_demand": (
        "rule_btc_fee_demand_v1",
        "coinmetrics-feetotntv7-30-positive-1d-v1",
    ),
}
KINDS = ("hashrate", "stablecoin_supply", "btc_fees")
API_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
COMMON_PARAMS = {
    "start_time": "2019-11-01",
    "end_time": "2022-12-31",
    "frequency": "1d",
    "page_size": "10000",
}
REQUESTS = (
    {
        "kind": "hashrate",
        "url": API_URL,
        "params": {"assets": "btc", "metrics": "HashRate", **COMMON_PARAMS},
    },
    {
        "kind": "stablecoin_supply",
        "url": API_URL,
        "params": {"assets": "usdt,usdc", "metrics": "SplyCur", **COMMON_PARAMS},
    },
    {
        "kind": "btc_fees",
        "url": API_URL,
        "params": {"assets": "btc", "metrics": "FeeTotNtv", **COMMON_PARAMS},
    },
)


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Research Protocol v10 schema_version drifted")
    if payload.get("status") != "preregistered_before_coinmetrics_timeseries_body_access":
        raise ValueError("Research Protocol v10 pre-access status drifted")
    boundaries = payload.get("boundaries", {})
    if boundaries.get("development_reserve") != {
        "start": "2020-01-01",
        "end": "2022-12-31",
        "strategy_specific_pnl_access_status": "unconsumed",
        "max_openings": 1,
    }:
        raise ValueError("Protocol v10 development reserve drifted")
    if (
        boundaries.get("confirmation_holdout", {}).get("strategy_specific_pnl_access_status")
        != "sealed_until_development_pass"
    ):
        raise ValueError("Protocol v10 confirmation holdout drifted")
    if boundaries.get("final_future_blind", {}).get("shared_v8_blind_remains_sealed") is not True:
        raise ValueError("Protocol v10 future blind drifted")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v10 must lock exactly three candidates")
    actual = {
        str(row.get("key")): (str(row.get("source")), str(row.get("model_version")))
        for row in candidates
        if isinstance(row, dict)
    }
    if actual != IDENTITIES:
        raise ValueError("Protocol v10 candidate identities drifted")
    expected_params = {
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
    if {row["key"]: row.get("parameters") for row in candidates} != expected_params:
        raise ValueError("Protocol v10 candidate parameters drifted")
    multiple = payload.get("gates", {}).get("multiple_testing")
    if multiple != {
        "candidate_count_locked": 3,
        "parameter_grid_search_forbidden": True,
        "alternate_sign_forbidden": True,
        "pnl_selected_ensemble_forbidden": True,
        "failed_candidate_reparameterization_forbidden": True,
    }:
        raise ValueError("Protocol v10 multiple-testing guard drifted")
    qualification = payload.get("provider_qualification", {})
    requests = qualification.get("requests")
    if requests != list(REQUESTS):
        raise ValueError("Protocol v10 provider requests drifted")
    if qualification.get("response_body_access_status") != "unopened":
        raise ValueError("Protocol v10 provider bodies must remain unopened")
    if qualification.get("max_body_openings_per_request") != 1:
        raise ValueError("Protocol v10 provider opening limit drifted")
    effects = payload.get("boundaries_effect", {})
    if any(effects.values()):
        raise ValueError("Protocol v10 trading boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_count": 3,
        "candidate_identities": [
            {"key": key, "source": source, "model_version": model}
            for key, (source, model) in IDENTITIES.items()
        ],
        "development_reserve": boundaries["development_reserve"],
        "confirmation_holdout": boundaries["confirmation_holdout"],
        "future_blind": boundaries["final_future_blind"],
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Research Protocol v10 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

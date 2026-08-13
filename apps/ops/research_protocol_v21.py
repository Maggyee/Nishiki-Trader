"""Validate frozen Protocol v21 U.S. net-liquidity research contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v21.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v21-data-sources.json")
SCHEMA_VERSION = "research.protocol.v21"
CANDIDATE = "net_usd_liquidity_expansion"
IDENTITIES = {
    CANDIDATE: (
        "rule_us_net_liquidity_expansion_v1",
        "fred-walcl-wdtgal-rrpontsyd-diff4w-positive-lag7d-v1",
    )
}
SERIES_IDS = ("WALCL", "WDTGAL", "RRPONTSYD")
PARAMETERS = {
    "change_observations": 4,
    "minimum_change_millions_usd": 0.0,
    "publication_lag_calendar_days": 7,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}
DEVELOPMENT_GATES = {
    "base_net_pnl_gt": 0.0,
    "stress_net_pnl_gt": 0.0,
    "positive_calendar_years_at_least": 2,
    "positive_calendar_months_at_least": 18,
    "closed_positions_at_least": 30,
    "leave_best_position_base_net_pnl_gt": 0.0,
    "duplicate_replays_required": 2,
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != (
        "preregistered_before_fred_historical_body_access"
    ):
        raise ValueError("Protocol v21 pre-access identity drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if disclosure.get("historical_csv_bodies_opened") is not False or any(
        disclosure.get(key) is not False
        for key in (
            "development_factor_values_opened",
            "confirmation_factor_values_opened",
            "strategy_specific_pnl_opened",
        )
    ):
        raise ValueError("Protocol v21 historical data boundary drifted")
    data = payload.get("data_contract", {})
    if data.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v21 provider-contract path drifted")
    if data.get("series") != list(SERIES_IDS):
        raise ValueError("Protocol v21 series identity drifted")
    if data.get("conservative_decision_lag_calendar_days") != 7:
        raise ValueError("Protocol v21 decision lag drifted")
    if data.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v21 cannot claim historical vintages")
    candidate = payload.get("candidate", {})
    source, model = IDENTITIES[CANDIDATE]
    if (
        candidate.get("key") != CANDIDATE
        or candidate.get("source") != source
        or candidate.get("model_version") != model
        or candidate.get("parameters") != PARAMETERS
    ):
        raise ValueError("Protocol v21 candidate identity drifted")
    gates = payload.get("gates", {})
    if gates.get("development") != DEVELOPMENT_GATES:
        raise ValueError("Protocol v21 development gates drifted")
    multiple = gates.get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 1 or not all(
        multiple.get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v21 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v21 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 1,
        "valid": True,
    }


def validate_provider_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != "research.data_sources.v21"
        or payload.get("status") != "locked_before_fred_historical_body_access"
    ):
        raise ValueError("Protocol v21 provider contract drifted")
    if payload.get("authentication") != "none":
        raise ValueError("Protocol v21 provider must remain credential-free")
    requests = payload.get("requests")
    if not isinstance(requests, list) or [row.get("series_id") for row in requests] != list(
        SERIES_IDS
    ):
        raise ValueError("Protocol v21 provider series drifted")
    if any(row.get("cosd") != "2019-10-01" or row.get("coed") != "2022-12-31" for row in requests):
        raise ValueError("Protocol v21 provider window drifted")
    policy = payload.get("request_policy", {})
    if (
        policy.get("method") != "GET"
        or policy.get("maximum_body_openings") != 3
        or policy.get("retry_allowed") is not False
    ):
        raise ValueError("Protocol v21 request budget drifted")
    if payload.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v21 provider cannot claim vintages")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "provider_contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v21 root must be an object")
    result = validate_protocol(payload)
    provider = json.loads(PROVIDER_CONTRACT.read_text())
    if not isinstance(provider, dict):
        raise ValueError("Protocol v21 provider root must be an object")
    return {**result, **validate_provider_contract(provider)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

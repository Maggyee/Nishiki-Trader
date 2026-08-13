"""Validate frozen Protocol v27 DefiLlama protocol-fee research contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v27.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v27-data-sources.json")
SCHEMA_VERSION = "research.protocol.v27"
IDENTITIES = {
    "all_fees_expansion": (
        "rule_defillama_all_fees_expansion_v1",
        "defillama-all-fees-diff5-positive-lag2d-v1",
    ),
    "all_revenue_expansion": (
        "rule_defillama_all_revenue_expansion_v1",
        "defillama-all-revenue-diff5-positive-lag2d-v1",
    ),
    "all_holders_revenue_expansion": (
        "rule_defillama_all_holders_revenue_expansion_v1",
        "defillama-all-holders-revenue-diff5-positive-lag2d-v1",
    ),
}
KIND_BY_CANDIDATE = {
    "all_fees_expansion": "daily_fees",
    "all_revenue_expansion": "daily_revenue",
    "all_holders_revenue_expansion": "daily_holders_revenue",
}
COMMON_PARAMETERS = {
    "change_observations": 5,
    "direction": "positive",
    "threshold": 0.0,
    "publication_lag_calendar_days": 2,
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
LOCKED_EXECUTION = {
    "instrument_id": "BTCUSDT.BINANCE",
    "bar_type": "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
    "development_catalog_path": "data/research-v7-downtime-sensitivity/catalog",
    "confirmation_catalog_path": "data/research-v8/catalog",
    "trade_size_btc": 0.001,
    "starting_balance_usdt": 100000,
    "account_type": "cash",
    "min_confidence": 0.55,
    "long_flat_only": True,
    "costs_usdt_per_closed_position": {"gross": 0.0, "base": 0.08, "stress": 0.10},
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != (
        "preregistered_before_defillama_fee_body_access"
    ):
        raise ValueError("Protocol v27 pre-access identity drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if disclosure.get("historical_json_bodies_opened") is not False or any(
        disclosure.get(key) is not False
        for key in (
            "development_factor_values_opened",
            "confirmation_factor_values_opened",
            "strategy_specific_pnl_opened",
        )
    ):
        raise ValueError("Protocol v27 historical data boundary drifted")
    data = payload.get("data_contract", {})
    if data.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v27 provider path drifted")
    if data.get("conservative_decision_lag_calendar_days") != 2:
        raise ValueError("Protocol v27 decision lag drifted")
    if data.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v27 cannot claim historical vintages")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v27 must lock exactly three candidates")
    actual = {row["key"]: (row["source"], row["model_version"]) for row in candidates}
    if actual != IDENTITIES:
        raise ValueError("Protocol v27 candidate identities drifted")
    for row in candidates:
        key = row["key"]
        if row.get("kind") != KIND_BY_CANDIDATE[key] or row.get("parameters") != COMMON_PARAMETERS:
            raise ValueError("Protocol v27 candidate parameters drifted")
    execution = payload.get("execution", {})
    if {key: execution.get(key) for key in LOCKED_EXECUTION} != LOCKED_EXECUTION:
        raise ValueError("Protocol v27 execution contract drifted")
    if payload.get("gates", {}).get("development") != DEVELOPMENT_GATES:
        raise ValueError("Protocol v27 development gates drifted")
    multiple = payload.get("gates", {}).get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 3 or not all(
        multiple.get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v27 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v27 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 3,
        "valid": True,
    }


def validate_provider_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != "research.data_sources.v27"
        or payload.get("status") != "locked_before_defillama_fee_body_access"
    ):
        raise ValueError("Protocol v27 provider contract drifted")
    requests = payload.get("requests")
    if not isinstance(requests, list) or [row.get("kind") for row in requests] != [
        "daily_fees",
        "daily_revenue",
        "daily_holders_revenue",
    ]:
        raise ValueError("Protocol v27 provider request order drifted")
    policy = payload.get("request_policy", {})
    if (
        policy.get("method") != "GET"
        or policy.get("maximum_body_openings_per_kind") != 1
        or policy.get("retry_allowed") is not False
    ):
        raise ValueError("Protocol v27 request budget drifted")
    if payload.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v27 provider cannot claim historical vintages")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "provider_contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v27 root must be an object")
    result = validate_protocol(payload)
    provider = json.loads(PROVIDER_CONTRACT.read_text())
    if not isinstance(provider, dict):
        raise ValueError("Protocol v27 provider root must be an object")
    return {**result, **validate_provider_contract(provider)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

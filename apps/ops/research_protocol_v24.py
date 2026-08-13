"""Validate frozen Protocol v24 Fear and Greed research contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v24.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v24-data-sources.json")
SCHEMA_VERSION = "research.protocol.v24"
IDENTITIES = {
    "extreme_fear_hold": (
        "rule_alternative_extreme_fear_hold_v1",
        "alternative-fng-extreme-fear-lag2d-v1",
    ),
    "fear_hold": (
        "rule_alternative_fear_hold_v1",
        "alternative-fng-fear-or-extreme-fear-lag2d-v1",
    ),
    "non_greed_hold": (
        "rule_alternative_non_greed_hold_v1",
        "alternative-fng-not-greed-or-extreme-greed-lag2d-v1",
    ),
}
LONG_CLASSIFICATIONS = {
    "extreme_fear_hold": ["Extreme Fear"],
    "fear_hold": ["Extreme Fear", "Fear"],
    "non_greed_hold": ["Extreme Fear", "Fear", "Neutral"],
}
COMMON_PARAMETERS = {
    "publication_lag_calendar_days": 2,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}
ALLOWED_CLASSIFICATIONS = (
    "Extreme Fear",
    "Fear",
    "Neutral",
    "Greed",
    "Extreme Greed",
)
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
        "preregistered_before_alternative_fng_body_access"
    ):
        raise ValueError("Protocol v24 pre-access identity drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if disclosure.get("historical_json_bodies_opened") is not False or any(
        disclosure.get(key) is not False
        for key in (
            "development_factor_values_opened",
            "confirmation_factor_values_opened",
            "strategy_specific_pnl_opened",
        )
    ):
        raise ValueError("Protocol v24 historical data boundary drifted")
    data = payload.get("data_contract", {})
    if data.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v24 provider path drifted")
    if data.get("conservative_decision_lag_calendar_days") != 2:
        raise ValueError("Protocol v24 decision lag drifted")
    if data.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v24 cannot claim historical vintages")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v24 must lock exactly three candidates")
    actual = {row["key"]: (row["source"], row["model_version"]) for row in candidates}
    if actual != IDENTITIES:
        raise ValueError("Protocol v24 candidate identities drifted")
    for row in candidates:
        key = row["key"]
        if row.get("long_classifications") != LONG_CLASSIFICATIONS[key]:
            raise ValueError("Protocol v24 candidate classifications drifted")
        if row.get("parameters") != COMMON_PARAMETERS:
            raise ValueError("Protocol v24 candidate parameters drifted")
    execution = payload.get("execution", {})
    if {key: execution.get(key) for key in LOCKED_EXECUTION} != LOCKED_EXECUTION:
        raise ValueError("Protocol v24 execution contract drifted")
    gates = payload.get("gates", {})
    if gates.get("development") != DEVELOPMENT_GATES:
        raise ValueError("Protocol v24 development gates drifted")
    multiple = gates.get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 3 or not all(
        multiple.get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v24 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v24 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 3,
        "valid": True,
    }


def validate_provider_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != "research.data_sources.v24"
        or payload.get("status") != "locked_before_alternative_fng_body_access"
    ):
        raise ValueError("Protocol v24 provider contract drifted")
    request = payload.get("request", {})
    if request.get("kind") != "fng" or request.get("method") != "GET":
        raise ValueError("Protocol v24 provider request drifted")
    if request.get("maximum_body_openings") != 1 or request.get("retry_allowed") is not False:
        raise ValueError("Protocol v24 request budget drifted")
    locked = payload.get("locked_response", {})
    if locked.get("allowed_classifications") != list(ALLOWED_CLASSIFICATIONS):
        raise ValueError("Protocol v24 allowed classifications drifted")
    if payload.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v24 provider cannot claim historical vintages")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "provider_contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v24 root must be an object")
    result = validate_protocol(payload)
    provider = json.loads(PROVIDER_CONTRACT.read_text())
    if not isinstance(provider, dict):
        raise ValueError("Protocol v24 provider root must be an object")
    return {**result, **validate_provider_contract(provider)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

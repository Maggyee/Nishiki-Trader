"""Validate frozen Protocol v22 option-surface research contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v22.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v22-data-sources.json")
EXECUTION_AMENDMENT = Path("docs/progress/phase-2-research-v22-execution-amendment.json")
SCHEMA_VERSION = "research.protocol.v22"
IDENTITIES = {
    "tail_skew_relief": (
        "rule_cboe_tail_skew_relief_v1",
        "cboe-skew-diff5-negative-lag1d-v1",
    ),
    "implied_correlation_relief": (
        "rule_cboe_implied_correlation_relief_v1",
        "cboe-cor1m-diff5-negative-lag1d-v1",
    ),
    "implied_dispersion_expansion": (
        "rule_cboe_implied_dispersion_expansion_v1",
        "cboe-dspx-diff5-positive-lag1d-v1",
    ),
}
INDEX_BY_CANDIDATE = {
    "tail_skew_relief": "SKEW",
    "implied_correlation_relief": "COR1M",
    "implied_dispersion_expansion": "DSPX",
}
DIRECTION_BY_CANDIDATE = {
    "tail_skew_relief": "negative",
    "implied_correlation_relief": "negative",
    "implied_dispersion_expansion": "positive",
}
COMMON_PARAMETERS = {
    "change_observations": 5,
    "threshold": 0.0,
    "publication_lag_calendar_days": 1,
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
        "preregistered_before_cboe_option_surface_body_access"
    ):
        raise ValueError("Protocol v22 pre-access identity drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if disclosure.get("historical_csv_bodies_opened") is not False or any(
        disclosure.get(key) is not False
        for key in (
            "development_factor_values_opened",
            "confirmation_factor_values_opened",
            "strategy_specific_pnl_opened",
        )
    ):
        raise ValueError("Protocol v22 historical data boundary drifted")
    data = payload.get("data_contract", {})
    if data.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v22 provider path drifted")
    if data.get("conservative_decision_lag_calendar_days") != 1:
        raise ValueError("Protocol v22 decision lag drifted")
    if data.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v22 cannot claim historical vintages")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v22 must lock exactly three candidates")
    actual = {row["key"]: (row["source"], row["model_version"]) for row in candidates}
    if actual != IDENTITIES:
        raise ValueError("Protocol v22 candidate identities drifted")
    for row in candidates:
        key = row["key"]
        expected = {**COMMON_PARAMETERS, "direction": DIRECTION_BY_CANDIDATE[key]}
        if row.get("index") != INDEX_BY_CANDIDATE[key] or row.get("parameters") != expected:
            raise ValueError("Protocol v22 candidate parameters drifted")
    gates = payload.get("gates", {})
    if gates.get("development") != DEVELOPMENT_GATES:
        raise ValueError("Protocol v22 development gates drifted")
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
        raise ValueError("Protocol v22 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v22 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 3,
        "valid": True,
    }


def validate_provider_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != "research.data_sources.v22"
        or payload.get("status") != "locked_before_cboe_option_surface_body_access"
    ):
        raise ValueError("Protocol v22 provider contract drifted")
    requests = payload.get("requests")
    if not isinstance(requests, list) or [row.get("kind") for row in requests] != [
        "skew",
        "cor1m",
        "dspx",
    ]:
        raise ValueError("Protocol v22 provider request order drifted")
    if [row.get("index") for row in requests] != ["SKEW", "COR1M", "DSPX"]:
        raise ValueError("Protocol v22 provider index identity drifted")
    policy = payload.get("request_policy", {})
    if (
        policy.get("method") != "GET"
        or policy.get("maximum_body_openings_per_kind") != 1
        or policy.get("retry_allowed") is not False
    ):
        raise ValueError("Protocol v22 request budget drifted")
    if payload.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v22 provider cannot claim historical vintages")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "provider_contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "valid": True,
    }


def load_execution_amendment(
    path: Path = EXECUTION_AMENDMENT,
) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if (
        payload.get("schema_version") != "research.v22.execution_amendment.v1"
        or payload.get("status") != "frozen_after_zero_pnl_catalog_miss_before_successful_replay"
    ):
        raise ValueError("Protocol v22 execution amendment identity drifted")
    if payload.get("parent_protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v22 execution amendment parent drifted")
    trigger = payload.get("trigger", {})
    if (
        trigger.get("failed_process_count") != 4
        or trigger.get("backtest_engine_started") is not False
        or trigger.get("bundle_written") is not False
        or trigger.get("orders_created") is not False
        or trigger.get("fills_created") is not False
        or trigger.get("pnl_opened") is not False
    ):
        raise ValueError("Protocol v22 zero-PnL correction boundary drifted")
    correction = payload.get("correction", {})
    if (
        correction.get("development_catalog_path")
        != ("data/research-v7-downtime-sensitivity/catalog")
        or correction.get("confirmation_catalog_path") != "data/research-v8/catalog"
    ):
        raise ValueError("Protocol v22 catalog correction drifted")
    if not all(payload.get("unchanged", {}).values()) or any(
        payload.get("boundaries", {}).values()
    ):
        raise ValueError("Protocol v22 execution amendment changes research boundaries")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "execution_amendment_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "development_catalog_path": correction["development_catalog_path"],
        "confirmation_catalog_path": correction["confirmation_catalog_path"],
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v22 root must be an object")
    result = validate_protocol(payload)
    provider = json.loads(PROVIDER_CONTRACT.read_text())
    if not isinstance(provider, dict):
        raise ValueError("Protocol v22 provider root must be an object")
    return {**result, **validate_provider_contract(provider)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

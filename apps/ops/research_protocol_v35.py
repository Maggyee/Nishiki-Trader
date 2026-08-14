"""Validate the frozen Phase 2 Research Protocol v35 pre-registration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v35.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v35-data-sources.json")
SCHEMA_VERSION = "research.protocol.v35"

COMMON_PARAMETERS = {
    "change_observations": 5,
    "direction": "negative",
    "threshold": 0.0,
    "publication_lag_calendar_days": 1,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}

IDENTITIES = {
    "irx_relief": ("rule_cboe_irx_relief_v1", "cboe-irx-diff5-negative-lag1d-v1"),
    "vix1y_relief": ("rule_cboe_vix1y_relief_v1", "cboe-vix1y-diff5-negative-lag1d-v1"),
    "vix6m_relief": ("rule_cboe_vix6m_relief_v1", "cboe-vix6m-diff5-negative-lag1d-v1"),
}

INDEX_BY_KIND = {
    "irx": "IRX",
    "vix1y": "VIX1Y",
    "vix6m": "VIX6M",
}

LOCKED_WINDOWS = {
    "warmup_start": "2019-11-01",
    "development_start": "2020-01-01",
    "development_end": "2022-12-31",
    "confirmation_start": "2023-01-01",
    "confirmation_end": "2025-12-31",
    "future_blind_start": "2026-09-01",
    "future_blind_end": "2027-01-31",
}

LOCKED_EXECUTION = {
    "instrument": "BTCUSDT.BINANCE",
    "bar_type": "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL",
    "venue": "BINANCE",
    "account_type": "cash",
    "oms_type": "netting",
    "starting_balance": 100000.0,
    "trade_size": 0.001,
    "min_confidence": 0.55,
    "development_catalog": "data/research-v7-downtime-sensitivity/catalog",
    "confirmation_catalog": "data/research-v8/catalog",
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

BOUNDARIES = {
    "loads_credentials": False,
    "mutates_source_policy": False,
    "resumes_testnet": False,
    "touches_live_path": False,
    "opens_future_blind": False,
}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _validate_provider_contract(payload: dict[str, Any]) -> str:
    if payload.get("schema_version") != "research.data_sources.v35":
        raise ValueError("Protocol v35 provider schema drifted")
    if payload.get("provider") != "Cboe Global Indices":
        raise ValueError("Protocol v35 provider must be Cboe Global Indices")
    requests = payload.get("requests", [])
    if len(requests) != 3:
        raise ValueError("Protocol v35 requires exactly three provider requests")
    by_kind = {req.get("kind"): req for req in requests}
    if set(by_kind.keys()) != set(INDEX_BY_KIND.keys()):
        raise ValueError("Protocol v35 request kinds drifted")
    for kind, expected_idx in INDEX_BY_KIND.items():
        req = by_kind[kind]
        if req.get("index") != expected_idx:
            raise ValueError(f"Protocol v35 {kind} index drifted")
        if req.get("url") != f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{expected_idx}_History.csv":
            raise ValueError(f"Protocol v35 {kind} URL drifted")
        gates = req.get("coverage_gates", {})
        if (
            gates.get("development_minimum_observations") != 700
            or gates.get("development_first_observation_on_or_before") != "2020-01-05"
            or gates.get("development_last_observation_on_or_after") != "2022-12-28"
            or gates.get("warmup_minimum_observations") != 5
            or gates.get("maximum_calendar_gap_days") != 5
        ):
            raise ValueError(f"Protocol v35 {kind} coverage gates drifted")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return _sha256(canonical.encode())


def validate_protocol(
    payload: dict[str, Any], *, provider_payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Protocol v35 schema drifted")
    if payload.get("status") != "preregistered_before_provider_access":
        raise ValueError("Protocol v35 status drifted")
    if payload.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v35 provider contract path drifted")
    if payload.get("parameter_lock") != {
        "parameter_tuning_forbidden": True,
        "sign_flips_forbidden": True,
        "ensembles_forbidden": True,
        "post_data_candidate_additions_forbidden": True,
    }:
        raise ValueError("Protocol v35 parameter lock drifted")
    data_contract = payload.get("data_contract", {})
    for key, value in LOCKED_WINDOWS.items():
        if data_contract.get(key) != value:
            raise ValueError(f"Protocol v35 {key} drifted")
    if data_contract.get("publication_lag_calendar_days") != 1:
        raise ValueError("Protocol v35 publication lag must be 1 day")
    if data_contract.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v35 must not make historical vintage claim")
    if payload.get("execution_contract") != LOCKED_EXECUTION:
        raise ValueError("Protocol v35 execution contract drifted")
    if payload.get("cost_scenarios") != COST_SCENARIOS:
        raise ValueError("Protocol v35 cost scenarios drifted")
    if payload.get("gates") != GATES:
        raise ValueError("Protocol v35 gates drifted")
    if payload.get("boundaries") != BOUNDARIES:
        raise ValueError("Protocol v35 boundaries drifted")
    candidates = payload.get("candidates", [])
    if len(candidates) != 3:
        raise ValueError("Protocol v35 requires exactly three candidates")
    by_key = {c.get("key"): c for c in candidates}
    if set(by_key.keys()) != set(IDENTITIES.keys()):
        raise ValueError("Protocol v35 candidate keys drifted")
    for key, (expected_source, expected_model) in IDENTITIES.items():
        c = by_key[key]
        if c.get("source") != expected_source or c.get("model_version") != expected_model:
            raise ValueError(f"Protocol v35 {key} identity drifted")
        if c.get("parameters") != COMMON_PARAMETERS:
            raise ValueError(f"Protocol v35 {key} parameters drifted")
    provider_sha = _validate_provider_contract(
        provider_payload or json.loads(PROVIDER_CONTRACT.read_text())
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": _sha256(canonical.encode()),
        "provider_contract_sha256": provider_sha,
        "candidate_count": len(candidates),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v35 payload must be a dictionary")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

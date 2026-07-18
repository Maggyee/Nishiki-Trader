"""Validate and fingerprint the fail-closed Research Protocol v6 registration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.protocol.v6"
DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v6.json")
DEFAULT_SOURCES = Path("docs/progress/phase-2-research-v6-data-sources.json")
DEFAULT_FINGERPRINTS = Path(
    "docs/progress/phase-2-research-v6-candidate-fingerprints.json"
)

LOCKED_PROTOCOL_SHA256 = "sha256:e4af2e91b46e8657c113398a4c2f6851ed38baf3ab079143d6c7f099fdaa318f"
LOCKED_PROVIDER_CONTRACT_SHA256 = (
    "sha256:9944a172ae093deee6bc366d0fd19483f1bb2f4c8cad25a703ff9992bbac1f83"
)
LOCKED_FINGERPRINTS_SHA256 = (
    "sha256:bb8f0ebf2e476b977952af73836542a3773dd3da4e68b064f937cb49d3833262"
)

EXPECTED_FOLDS = [
    ("book_depth_2023_jan_may", "2023-01-01", "2023-05-31"),
    ("book_depth_2023_aug_dec", "2023-08-01", "2023-12-31"),
    ("book_depth_2024_jan_may", "2024-01-01", "2024-05-31"),
    ("book_depth_2024_aug_dec", "2024-08-01", "2024-12-31"),
    ("book_depth_2025_jan_may", "2025-01-01", "2025-05-31"),
    ("book_depth_2025_aug_dec", "2025-08-01", "2025-12-31"),
]
EXPECTED_PARAMETERS = {
    "percentage_magnitude": 1,
    "daily_aggregation": "median",
    "minimum_imbalance": 0.0,
    "historical_publication_lag_days": 2,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}
EXPECTED_FACTORS = ["bid_notional_at_minus_1pct", "ask_notional_at_plus_1pct"]
EXPECTED_FORMULA = (
    "(bid_notional_at_minus_1pct - ask_notional_at_plus_1pct) / "
    "(bid_notional_at_minus_1pct + ask_notional_at_plus_1pct)"
)
EXPECTED_COSTS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}
EXPECTED_EFFECTS = {
    "archive_bodies_accessed_during_preregistration": False,
    "writes_signal_store_during_preregistration": False,
    "loads_credentials": False,
    "runs_nautilus_during_preregistration": False,
    "computes_pnl_during_preregistration": False,
    "mutates_source_policy": False,
    "calls_promotion_review": False,
    "resumes_testnet": False,
    "touches_live_path": False,
}


def _strict_load(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r} is forbidden")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def _finite(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _finite(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _finite(child, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def _sha(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def candidate_fingerprint(row: dict[str, Any]) -> dict[str, Any]:
    feature_spec = {
        key: row.get(key)
        for key in (
            "parameters",
            "required_factors",
            "factor_formula",
            "daily_factor",
            "missing_state",
            "signal_emission",
        )
    }
    features_hash = _sha(feature_spec)
    identity = {
        "candidate": row.get("candidate"),
        "source": row.get("source"),
        "model_version": row.get("model_version"),
        "features_hash": features_hash,
    }
    return {**identity, "candidate_sha256": _sha(identity)}


def validate_protocol(
    protocol: dict[str, Any],
    sources: dict[str, Any],
    fingerprints: dict[str, Any],
) -> dict[str, Any]:
    for payload in (protocol, sources, fingerprints):
        _finite(payload)

    if protocol.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if protocol.get("status") != "preregistered_before_archive_body_access":
        raise ValueError("v6 must remain pre-registered before archive-body access")
    try:
        frozen_at = datetime.fromisoformat(str(protocol["frozen_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("frozen_at must be a timezone-aware ISO timestamp") from exc
    if frozen_at.tzinfo is None:
        raise ValueError("frozen_at must include a timezone")
    if sources.get("frozen_at") != protocol.get("frozen_at") or fingerprints.get(
        "frozen_at"
    ) != protocol.get("frozen_at"):
        raise ValueError("all v6 contracts must share one frozen_at")

    decision = protocol.get("identity_decision")
    if decision != {
        "candidate": "book_depth_imbalance",
        "decision": "accept_for_preregistration_only",
        "economic_mechanism": "resting_limit_order_liquidity_supply_asymmetry",
        "alpha_or_data_quality_claimed": False,
        "archive_semantics_qualified": False,
    }:
        raise ValueError("identity decision differs from the v6 lock")

    relationship = protocol.get("relationship_to_prior_work")
    if not isinstance(relationship, dict):
        raise ValueError("relationship_to_prior_work must be an object")
    if relationship.get("registry_v1") != "frozen_at_16_rejects_empty_selected_set":
        raise ValueError("the original candidate registry must remain frozen")
    if relationship.get("protocol_v5") != "frozen_with_both_candidates_rejected":
        raise ValueError("Protocol v5 must remain frozen with both candidates rejected")
    if any(
        relationship.get(name) != "frozen_and_unchanged"
        for name in ("protocol_v2", "protocol_v3", "protocol_v4")
    ):
        raise ValueError("Protocols v2-v4 must remain frozen and unchanged")
    for flag in (
        "new_source_model_identity_required",
        "failed_candidate_reparameterization_forbidden",
        "pnl_selected_ensemble_forbidden",
    ):
        if relationship.get(flag) is not True:
            raise ValueError(f"relationship guard {flag} must remain true")

    partitions = protocol.get("partitions")
    if not isinstance(partitions, dict):
        raise ValueError("partitions must be an object")
    qualification = partitions.get("july_qualification")
    if qualification != {
        "data_date": "2026-07-17",
        "allowed_use": (
            "schema_archive_semantics_lineage_timestamp_coverage_and_mark_price_sanity_only"
        ),
        "pnl_access_forbidden": True,
        "signal_generation_forbidden": True,
    }:
        raise ValueError("July qualification differs from the v6 lock")
    development = partitions.get("historical_development")
    if not isinstance(development, dict):
        raise ValueError("historical_development must be an object")
    actual_folds = [
        (row.get("name"), row.get("start"), row.get("end"))
        for row in development.get("folds", [])
        if isinstance(row, dict)
    ]
    if actual_folds != EXPECTED_FOLDS:
        raise ValueError("historical development folds differ from the v6 lock")
    if development.get("open_status") != "not_started":
        raise ValueError("historical development must remain unopened")
    if development.get("parameter_changes_after_open_forbidden") is not True:
        raise ValueError("development parameters must freeze before access")
    if partitions.get("final_future_blind") != {
        "start": "2026-08-01",
        "end": "2026-12-31",
        "access_status": "not_started",
        "parameter_changes_after_open_forbidden": True,
    }:
        raise ValueError("final future blind differs from the v6 lock")
    if partitions.get("second_future_confirmation") != {
        "start": "2027-01-01",
        "end": "2027-05-31",
        "required_after_2026_pass": True,
    }:
        raise ValueError("second future confirmation differs from the v6 lock")

    if protocol.get("cost_scenarios") != EXPECTED_COSTS:
        raise ValueError("cost scenarios differ from the v6 lock")
    execution = protocol.get("execution")
    if not isinstance(execution, dict) or execution.get("engine") != "NautilusTrader":
        raise ValueError("NautilusTrader must remain the sole execution engine")
    if execution.get("assets") != ["BTCUSDT", "ETHUSDT"]:
        raise ValueError("the BTC/ETH universe differs from the v6 lock")
    if execution.get("position_domain") != ["long", "flat"]:
        raise ValueError("v6 must remain Spot long/flat only")

    gates = protocol.get("gates")
    if not isinstance(gates, dict):
        raise ValueError("gates must be an object")
    provider_gate = gates.get("provider_qualification")
    if not isinstance(provider_gate, dict):
        raise ValueError("provider qualification gate must be an object")
    for flag in (
        "official_checksum_required",
        "exact_locked_columns_required",
        "exact_percentage_grid_required",
        "every_timestamp_group_complete",
        "negative_percentage_must_map_to_bid_side",
        "positive_percentage_must_map_to_ask_side",
        "mark_price_sanity_required",
        "known_public_misalignment_issue_must_not_reproduce",
        "both_assets_must_pass",
    ):
        if provider_gate.get(flag) is not True:
            raise ValueError(f"provider qualification guard {flag} must remain true")
    if provider_gate.get("mark_price_tolerance_fraction") != 0.01:
        raise ValueError("mark-price tolerance differs from the v6 lock")
    if "archive_semantics_unproven" not in gates.get("hard_blockers", []):
        raise ValueError("unproven archive semantics must remain a hard blocker")
    if "mark_price_consistency_failure" not in gates.get("hard_blockers", []):
        raise ValueError("mark-price inconsistency must remain a hard blocker")

    candidates = protocol.get("candidates")
    rows = fingerprints.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("v6 must contain exactly one candidate")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("v6 must contain exactly one candidate fingerprint")
    row = rows[0]
    if row.get("parameters") != EXPECTED_PARAMETERS:
        raise ValueError("candidate parameters differ from the v6 lock")
    if row.get("required_factors") != EXPECTED_FACTORS:
        raise ValueError("candidate factors differ from the v6 lock")
    if row.get("factor_formula") != EXPECTED_FORMULA:
        raise ValueError("candidate formula differs from the v6 lock")
    computed = candidate_fingerprint(row)
    for field, expected in computed.items():
        if row.get(field) != expected:
            raise ValueError(f"candidate fingerprint field {field} differs from the v6 lock")
    candidate = candidates[0]
    for field in ("source", "model_version", "features_hash"):
        if candidate.get(field) != row.get(field):
            raise ValueError(f"protocol candidate {field} differs from fingerprint")
    if candidate.get("data_access_status") != "not_accessed":
        raise ValueError("v6 archive data must remain not_accessed at pre-registration")
    if candidate.get("promotion_ceiling") != "research_only":
        raise ValueError("v6 candidate must remain research_only")

    if sources.get("schema_version") != "research.data_sources.v6":
        raise ValueError("provider contract schema differs from v6")
    if sources.get("status") != "locked_before_archive_body_access":
        raise ValueError("provider contract must remain locked before archive access")
    if sources.get("provider") != "Binance" or sources.get("authentication") != "none":
        raise ValueError("v6 data must remain Binance-only and credential-free")
    if sources.get("allowed_hosts") != ["data.binance.vision"]:
        raise ValueError("v6 provider hosts differ from the lock")
    datasets = sources.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError("provider datasets must be an object")
    book_depth = datasets.get("book_depth_factor")
    if not isinstance(book_depth, dict):
        raise ValueError("bookDepth provider contract is missing")
    if book_depth.get("archive_request") != (
        "data/futures/um/daily/bookDepth/{asset}/{asset}-bookDepth-{date}.zip"
    ):
        raise ValueError("bookDepth archive request differs from the v6 lock")
    if book_depth.get("locked_columns") != ["timestamp", "percentage", "depth", "notional"]:
        raise ValueError("bookDepth columns differ from the v6 lock")
    if book_depth.get("locked_percentage_grid") != [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]:
        raise ValueError("bookDepth percentage grid differs from the v6 lock")
    if book_depth.get("archive_to_rest_mapping_status") != (
        "must_be_proven_during_qualification"
    ):
        raise ValueError("archive semantics must remain unproven until qualification")
    mark_audit = datasets.get("mark_price_qualification_audit")
    if not isinstance(mark_audit, dict) or mark_audit.get("usage") != (
        "qualification_audit_only_never_a_candidate_factor"
    ):
        raise ValueError("mark price must remain qualification-only")
    qualification_boundaries = sources.get("qualification_boundaries")
    if not isinstance(qualification_boundaries, dict):
        raise ValueError("qualification boundaries are missing")
    for flag in ("signals_forbidden", "returns_forbidden", "pnl_forbidden"):
        if qualification_boundaries.get(flag) is not True:
            raise ValueError(f"qualification boundary {flag} must remain true")

    source_boundaries = sources.get("boundaries")
    if not isinstance(source_boundaries, dict) or any(
        value is not False for value in source_boundaries.values()
    ):
        raise ValueError("provider boundaries are missing or unsafe")
    if protocol.get("boundaries_effect") != EXPECTED_EFFECTS:
        raise ValueError("pre-registration trading boundaries are missing or unsafe")
    fingerprint_boundaries = fingerprints.get("boundaries")
    if not isinstance(fingerprint_boundaries, dict) or any(
        value is not False for value in fingerprint_boundaries.values()
    ):
        raise ValueError("candidate fingerprint boundaries are missing or unsafe")

    protocol_sha = _sha(protocol)
    provider_sha = _sha(sources)
    fingerprints_sha = _sha(fingerprints)
    if protocol_sha != LOCKED_PROTOCOL_SHA256:
        raise ValueError("protocol differs from the locked v6 pre-registration hash")
    if provider_sha != LOCKED_PROVIDER_CONTRACT_SHA256:
        raise ValueError("provider contract differs from the locked v6 pre-registration hash")
    if fingerprints_sha != LOCKED_FINGERPRINTS_SHA256:
        raise ValueError("fingerprints differ from the locked v6 pre-registration hash")

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": protocol_sha,
        "provider_contract_sha256": provider_sha,
        "fingerprints_sha256": fingerprints_sha,
        "candidate_fingerprint": computed,
        "archive_bodies_accessed": False,
        "signals_written": False,
        "pnl_computed": False,
        "valid": True,
    }


def load_and_validate_protocol(
    protocol_path: Path = DEFAULT_PROTOCOL,
    sources_path: Path = DEFAULT_SOURCES,
    fingerprints_path: Path = DEFAULT_FINGERPRINTS,
) -> dict[str, Any]:
    return validate_protocol(
        _strict_load(protocol_path),
        _strict_load(sources_path),
        _strict_load(fingerprints_path),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--fingerprints", type=Path, default=DEFAULT_FINGERPRINTS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            load_and_validate_protocol(args.protocol, args.sources, args.fingerprints),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

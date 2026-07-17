"""Validate and fingerprint the fail-closed Research Protocol v5 registration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.strategies_freqtrade.research.binance_mechanism_signals import (
    ASSETS,
    STRATEGY_IDENTITIES,
    candidate_fingerprint,
)

SCHEMA_VERSION = "research.protocol.v5"
LOCKED_PROTOCOL_SHA256 = "sha256:1abe832749d1a1926fb4e00c507af3d93b64dbd05e74f488a2c0ed3f242392f2"
LOCKED_PROVIDER_CONTRACT_SHA256 = "sha256:7eb70e124ce073a229413342d7d4460a31c995aed3581b057a8e68fb57995db4"
LOCKED_FINGERPRINTS_SHA256 = "sha256:fba1f3302e2eaa55c0e0bff65d95e4de873667ff0d2462a386fa1a3ce8a61365"
DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v5.json")
DEFAULT_SOURCES = Path("docs/progress/phase-2-research-v5-data-sources.json")
DEFAULT_FINGERPRINTS = Path(
    "docs/progress/phase-2-research-v5-candidate-fingerprints.json"
)

EXPECTED_FOLDS = {
    "curve_fast_track": [
        ("curve_2021_aug_dec", "2021-08-01", "2021-12-31"),
        ("curve_2022_jan_may", "2022-01-01", "2022-05-31"),
        ("curve_2022_aug_dec", "2022-08-01", "2022-12-31"),
    ],
    "bvol_fast_track_diagnostic": [
        ("bvol_2023_aug_dec", "2023-08-01", "2023-12-31"),
        ("bvol_2024_jan_may", "2024-01-01", "2024-05-31"),
        ("bvol_2024_aug_dec", "2024-08-01", "2024-12-31"),
        ("bvol_2025_jan_may", "2025-01-01", "2025-05-31"),
        ("bvol_2025_aug_dec", "2025-08-01", "2025-12-31"),
    ],
}
EXPECTED_COSTS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}
EXPECTED_EFFECTS = {
    "writes_signal_store_during_preregistration": False,
    "loads_credentials": False,
    "runs_nautilus_during_preregistration": False,
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


def _sha(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


def validate_protocol(
    protocol: dict[str, Any],
    sources: dict[str, Any],
    fingerprints: dict[str, Any],
) -> dict[str, Any]:
    for payload in (protocol, sources, fingerprints):
        _finite(payload)
    if protocol.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if protocol.get("status") != "preregistered_before_historical_body_access":
        raise ValueError("v5 must remain pre-registered before historical body access")
    try:
        frozen_at = datetime.fromisoformat(str(protocol["frozen_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("frozen_at must be a timezone-aware ISO timestamp") from exc
    if frozen_at.tzinfo is None:
        raise ValueError("frozen_at must include a timezone")
    if protocol.get("cost_scenarios") != EXPECTED_COSTS:
        raise ValueError("cost scenarios differ from the v5 lock")
    if protocol.get("boundaries_effect") != EXPECTED_EFFECTS:
        raise ValueError("pre-registration trading boundaries are missing or unsafe")

    relationship = protocol.get("relationship_to_prior_work")
    if not isinstance(relationship, dict) or any(
        relationship.get(name) != "frozen_and_unchanged"
        for name in ("protocol_v2", "protocol_v3", "protocol_v4")
    ):
        raise ValueError("v2/v3/v4 must remain frozen and unchanged")
    if relationship.get("registry_v1") != "frozen_at_16_rejects_empty_selected_set":
        raise ValueError("the original 16-candidate registry must remain frozen")
    if relationship.get("new_source_model_identity_required") is not True:
        raise ValueError("v5 requires new source/model identities")
    if relationship.get("pnl_selected_ensemble_forbidden") is not True:
        raise ValueError("PnL-selected ensembles must remain forbidden")

    partitions = protocol.get("partitions")
    if not isinstance(partitions, dict):
        raise ValueError("partitions must be an object")
    for partition, expected in EXPECTED_FOLDS.items():
        folds = partitions.get(partition, {}).get("folds")
        actual = [
            (row.get("name"), row.get("start"), row.get("end"))
            for row in folds or []
            if isinstance(row, dict)
        ]
        if actual != expected:
            raise ValueError(f"{partition} folds differ from the v5 lock")
    july = partitions.get("july_qualification", {})
    if (
        july.get("start") != "2026-07-01"
        or july.get("end") != "2026-07-31"
        or july.get("pnl_access_forbidden") is not True
    ):
        raise ValueError("July must remain qualification-only with PnL forbidden")
    future = partitions.get("final_future_blind", {})
    if future != {
        "start": "2026-08-01",
        "end": "2026-12-31",
        "access_status": "not_started",
        "parameter_changes_after_open_forbidden": True,
    }:
        raise ValueError("final future blind differs from the v5 lock")
    if partitions.get("bvol_second_future_confirmation") != {
        "start": "2027-01-01",
        "end": "2027-05-31",
        "required_after_2026_pass": True,
    }:
        raise ValueError("BVOL 2027 confirmation window differs from the v5 lock")

    execution = protocol.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("execution must be an object")
    expected_execution = {
        "venue": "BINANCE",
        "assets": list(ASSETS),
        "instrument_type": "Spot",
        "account_type": "CASH",
        "oms_type": "NETTING",
        "starting_balance_usdt": 100000,
        "engine": "NautilusTrader",
        "per_asset_target_notional_usdt": 50.0,
        "trade_size_formula": "floor((50 / fold_first_close) / size_increment) * size_increment",
        "maximum_concurrent_assets": 2,
        "maximum_initial_target_notional_usdt": 100.0,
        "position_domain": ["long", "flat"],
        "fold_initial_state": "flat",
        "duplicate_runs_required": 2,
        "benchmark": "equal_weight_buy_and_hold_same_asset_sizes_window_and_costs",
    }
    if execution != expected_execution:
        raise ValueError("shared execution contract differs from the v5 lock")

    candidates = protocol.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ValueError("v5 must contain exactly two candidates")
    implementation = {key: candidate_fingerprint(key) for key in STRATEGY_IDENTITIES}
    for candidate in candidates:
        key = candidate.get("key")
        expected = implementation.get(str(key))
        if expected is None:
            raise ValueError(f"unexpected v5 candidate {key!r}")
        for field in ("source", "model_version", "features_hash"):
            if candidate.get(field) != expected[field]:
                raise ValueError(f"candidate {key} {field} differs from implementation")
        if candidate.get("data_access_status") != "not_accessed":
            raise ValueError(f"candidate {key} historical data must remain not_accessed")
        if candidate.get("promotion_ceiling") != "research_only":
            raise ValueError(f"candidate {key} must remain research_only")

    if sources.get("schema_version") != "research.data_sources.v5":
        raise ValueError("provider contract schema differs from v5")
    if sources.get("status") != "locked_before_historical_body_access":
        raise ValueError("provider contract must remain locked before historical access")
    if sources.get("provider") != "Binance" or sources.get("authentication") != "none":
        raise ValueError("v5 data must remain Binance-only and credential-free")
    source_boundaries = sources.get("boundaries")
    if not isinstance(source_boundaries, dict) or any(
        source_boundaries.get(flag) is not False
        for flag in (
            "credentials_loaded",
            "third_party_data_allowed",
            "pnl_computed_during_collection",
            "signals_generated_during_collection",
            "source_policy_mutated",
            "testnet_resumed",
            "live_path_touched",
        )
    ):
        raise ValueError("provider boundaries are missing or unsafe")

    if fingerprints.get("schema_version") != "research.candidate_fingerprints.v5":
        raise ValueError("candidate fingerprint schema differs from v5")
    rows = fingerprints.get("candidates")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("fingerprint file must contain exactly two candidates")
    by_key = {row.get("candidate"): row for row in rows if isinstance(row, dict)}
    if by_key != implementation:
        raise ValueError("locked candidate fingerprints differ from implementation")
    fingerprint_boundaries = fingerprints.get("boundaries")
    if not isinstance(fingerprint_boundaries, dict) or any(
        fingerprint_boundaries.get(flag) is not False
        for flag in fingerprint_boundaries
    ):
        raise ValueError("candidate fingerprint boundaries are missing or unsafe")

    protocol_sha = _sha(protocol)
    provider_sha = _sha(sources)
    fingerprints_sha = _sha(fingerprints)
    if protocol_sha != LOCKED_PROTOCOL_SHA256:
        raise ValueError("protocol differs from the locked pre-registration hash")
    if provider_sha != LOCKED_PROVIDER_CONTRACT_SHA256:
        raise ValueError("provider contract differs from the locked pre-registration hash")
    if fingerprints_sha != LOCKED_FINGERPRINTS_SHA256:
        raise ValueError("fingerprints differ from the locked pre-registration hash")

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": protocol_sha,
        "provider_contract_sha256": provider_sha,
        "fingerprints_sha256": fingerprints_sha,
        "candidate_fingerprints": [implementation[key] for key in sorted(implementation)],
        "historical_bodies_accessed": False,
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

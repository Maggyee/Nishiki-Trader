"""Validate the frozen Research Protocol v7 contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v7.json")
SCHEMA_VERSION = "research.protocol.v7"

STRATEGY_IDENTITIES = {
    "equity_vol_relief": ("rule_equity_vol_relief_v3", "cboe-vix5obs-negative-1d-v1"),
    "energy_vol_relief": ("rule_energy_vol_relief_v1", "cboe-ovx5obs-negative-1d-v1"),
    "gold_vol_relief": ("rule_gold_vol_relief_v1", "cboe-gvz5obs-negative-1d-v1"),
}

LOCKED_PARAMETERS = {
    "change_observations": 5,
    "maximum_change": 0.0,
    "ttl_seconds": 86_400,
    "confidence": 0.75,
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Research Protocol v7 schema_version drifted")
    if payload.get("status") != "preregistered_before_cboe_csv_body_access":
        raise ValueError("Research Protocol v7 must remain pre-registered before access")

    boundaries = payload.get("boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("Research Protocol v7 boundaries are missing")
    if boundaries.get("historical_replication_reserve") != {
        "start": "2020-01-01",
        "end": "2022-12-31",
        "access_status": "unconsumed",
        "max_openings": 1,
    }:
        raise ValueError("historical replication reserve drifted")
    if boundaries.get("final_future_blind") != {
        "start": "2026-09-01",
        "end": "2027-01-31",
        "access_status": "not_started",
        "parameter_changes_after_open_forbidden": True,
    }:
        raise ValueError("future blind drifted")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Research Protocol v7 must lock exactly three candidates")
    actual: dict[str, tuple[str, str]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("every v7 candidate must be an object")
        key = str(candidate.get("key"))
        if candidate.get("parameters") != LOCKED_PARAMETERS:
            raise ValueError(f"candidate {key} parameters drifted")
        if candidate.get("promotion_ceiling") != "research_only":
            raise ValueError(f"candidate {key} promotion ceiling drifted")
        actual[key] = (str(candidate.get("source")), str(candidate.get("model_version")))
    if actual != STRATEGY_IDENTITIES:
        raise ValueError("Research Protocol v7 candidate identities drifted")

    multiple = payload.get("gates", {}).get("multiple_testing", {})
    if multiple != {
        "candidate_count_locked": 3,
        "parameter_grid_search_forbidden": True,
        "pnl_selected_ensemble_forbidden": True,
        "failed_candidate_reparameterization_forbidden": True,
    }:
        raise ValueError("Research Protocol v7 multiple-testing guard drifted")

    effects = payload.get("boundaries_effect")
    if effects != {
        "loads_credentials": False,
        "mutates_source_policy": False,
        "resumes_testnet": False,
        "touches_live_path": False,
    }:
        raise ValueError("Research Protocol v7 trading boundaries are unsafe")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_count": 3,
        "candidate_identities": [
            {"key": key, "source": source, "model_version": model}
            for key, (source, model) in STRATEGY_IDENTITIES.items()
        ],
        "historical_replication_reserve": boundaries["historical_replication_reserve"],
        "final_future_blind": boundaries["final_future_blind"],
        "valid": True,
    }


def load_and_validate_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Research Protocol v7 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate_protocol(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

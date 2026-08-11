"""Validate the frozen Research Protocol v9 option-risk contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v9.json")
SCHEMA_VERSION = "research.protocol.v9"
IDENTITIES = {
    "equity_vol_curve": ("rule_equity_vol_curve_v1", "cboe-vix9d-below-vix-1d-v1"),
    "vol_of_vol_relief": ("rule_vol_of_vol_relief_v1", "cboe-vvix5obs-negative-1d-v1"),
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Research Protocol v9 schema_version drifted")
    if payload.get("status") != "preregistered_before_vix9d_vvix_csv_body_access":
        raise ValueError("Research Protocol v9 pre-access status drifted")
    boundaries = payload.get("boundaries", {})
    if boundaries.get("development_reserve") != {
        "start": "2020-01-01",
        "end": "2022-12-31",
        "strategy_specific_pnl_access_status": "unconsumed",
        "max_openings": 1,
    }:
        raise ValueError("Protocol v9 development reserve drifted")
    if boundaries.get("confirmation_holdout") != {
        "start": "2023-01-01",
        "end": "2025-12-31",
        "strategy_specific_pnl_access_status": "sealed_until_development_pass",
        "max_openings": 1,
    }:
        raise ValueError("Protocol v9 confirmation holdout drifted")
    if boundaries.get("final_future_blind") != {
        "start": "2026-09-01",
        "end": "2027-01-31",
        "access_status": "not_started",
        "shared_v8_blind_remains_sealed": True,
    }:
        raise ValueError("Protocol v9 future blind drifted")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ValueError("Protocol v9 must lock exactly two candidates")
    actual = {
        str(row.get("key")): (str(row.get("source")), str(row.get("model_version")))
        for row in candidates
        if isinstance(row, dict)
    }
    if actual != IDENTITIES:
        raise ValueError("Protocol v9 candidate identities drifted")
    curve = next(row for row in candidates if row["key"] == "equity_vol_curve")
    if curve.get("parameters") != {
        "curve_ratio_threshold": 1.0,
        "comparison": "strictly_below",
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    }:
        raise ValueError("Protocol v9 curve parameters drifted")
    relief = next(row for row in candidates if row["key"] == "vol_of_vol_relief")
    if relief.get("parameters") != {
        "change_observations": 5,
        "maximum_change": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    }:
        raise ValueError("Protocol v9 VVIX parameters drifted")

    multiple = payload.get("gates", {}).get("multiple_testing")
    if multiple != {
        "candidate_count_locked": 2,
        "parameter_grid_search_forbidden": True,
        "alternate_sign_forbidden": True,
        "pnl_selected_ensemble_forbidden": True,
        "failed_candidate_reparameterization_forbidden": True,
    }:
        raise ValueError("Protocol v9 multiple-testing guard drifted")
    qualification = payload.get("provider_qualification", {})
    requests = qualification.get("unopened_requests")
    if not isinstance(requests, list) or [row.get("kind") for row in requests] != [
        "vix9d",
        "vvix",
    ]:
        raise ValueError("Protocol v9 provider requests drifted")
    if any(int(row.get("max_body_openings", 0)) != 1 for row in requests):
        raise ValueError("Protocol v9 provider requests must allow one body opening")
    reused = qualification.get("reused_vix_snapshot", {})
    if reused.get("snapshot_sha256") != (
        "sha256:b2cffe2c74b4b03cab1cf47759a4be741af17cd87853f1817ba03c6aea30d368"
    ) or reused.get("refresh_forbidden") is not True:
        raise ValueError("Protocol v9 reused VIX snapshot drifted")
    if payload.get("boundaries_effect") != {
        "loads_credentials": False,
        "mutates_source_policy": False,
        "resumes_testnet": False,
        "touches_live_path": False,
        "opens_future_blind": False,
    }:
        raise ValueError("Protocol v9 trading boundaries are unsafe")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_count": 2,
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
        raise ValueError("Research Protocol v9 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

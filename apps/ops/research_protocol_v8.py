"""Validate the frozen Research Protocol v8 confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v8.json")
DEFAULT_SOURCES = Path("docs/progress/phase-2-research-v8-data-sources.json")
SCHEMA_VERSION = "research.protocol.v8"
SOURCE_SCHEMA_VERSION = "research.data_sources.v8"
IDENTITY = ("rule_gold_vol_relief_v1", "cboe-gvz5obs-negative-1d-v1")
PARAMETERS = {
    "change_observations": 5,
    "maximum_change": 0.0,
    "ttl_seconds": 86_400,
    "confidence": 0.75,
}


def validate_protocol(payload: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Research Protocol v8 schema_version drifted")
    if payload.get("status") != "preregistered_before_2023_2025_execution_data_and_pnl_access":
        raise ValueError("Research Protocol v8 pre-access status drifted")
    holdout = payload.get("boundaries", {}).get("historical_confirmation_holdout")
    if holdout != {
        "start": "2023-01-01",
        "end": "2025-12-31",
        "strategy_specific_pnl_access_status": "unconsumed",
        "max_openings": 1,
    }:
        raise ValueError("Research Protocol v8 confirmation holdout drifted")
    future = payload.get("boundaries", {}).get("final_future_blind")
    if future != {
        "start": "2026-09-01",
        "end": "2027-01-31",
        "access_status": "not_started",
        "remains_sealed_during_v8": True,
    }:
        raise ValueError("Research Protocol v8 future blind drifted")
    candidate = payload.get("candidate", {})
    if (candidate.get("source"), candidate.get("model_version")) != IDENTITY:
        raise ValueError("Research Protocol v8 candidate identity drifted")
    if (
        candidate.get("parameters") != PARAMETERS
        or candidate.get("parameter_changes_forbidden") is not True
    ):
        raise ValueError("Research Protocol v8 parameters drifted")

    continuity = payload.get("market_session_continuity", {})
    if continuity.get("official_sha256_required_for_every_archive") is not True:
        raise ValueError("official archive checksums must be required")
    if continuity.get("synthetic_bars_forbidden") is not True:
        raise ValueError("synthetic bars must remain forbidden")
    if continuity.get("interpolation_forbidden") is not True:
        raise ValueError("interpolation must remain forbidden")
    if continuity.get("verified_no_kline_window") != {
        "archive_checksum_matches": True,
        "official_spot_rest_exact_window_returns_zero_klines": True,
        "classification": "exchange_unavailable_not_missing_market_data",
    }:
        raise ValueError("verified no-kline semantics drifted")

    if payload.get("multiple_testing") != {
        "candidate_count_locked": 1,
        "parameter_grid_search_forbidden": True,
        "threshold_change_forbidden": True,
        "alternate_sign_forbidden": True,
        "pnl_selected_subperiod_forbidden": True,
    }:
        raise ValueError("Research Protocol v8 multiple-testing guard drifted")
    if payload.get("boundaries_effect") != {
        "loads_credentials": False,
        "mutates_source_policy": False,
        "resumes_testnet": False,
        "touches_live_path": False,
    }:
        raise ValueError("Research Protocol v8 trading boundaries are unsafe")

    if sources.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ValueError("Research Protocol v8 source schema drifted")
    if sources.get("status") != "locked_before_2023_2025_execution_archive_access":
        raise ValueError("Research Protocol v8 sources were not locked before access")
    signal = sources.get("signal_source", {})
    if signal.get("snapshot_sha256") != (
        "sha256:d18a093c7f2b00bb4ed08d2c7e7970dde06a185b47df4e1344a2d6b5830491c1"
    ):
        raise ValueError("Research Protocol v8 GVZ snapshot drifted")
    execution = sources.get("execution_source", {})
    if execution.get("host") != "data.binance.vision":
        raise ValueError("Research Protocol v8 execution host drifted")
    if execution.get("months") != {"start": "2023-01", "end": "2025-12", "count": 36}:
        raise ValueError("Research Protocol v8 execution months drifted")

    canonical = json.dumps(
        {"protocol": payload, "sources": sources},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_source": IDENTITY[0],
        "candidate_model_version": IDENTITY[1],
        "confirmation_holdout": holdout,
        "future_blind": future,
        "valid": True,
    }


def load_and_validate(
    protocol_path: Path = DEFAULT_PROTOCOL,
    sources_path: Path = DEFAULT_SOURCES,
) -> dict[str, Any]:
    protocol = json.loads(protocol_path.read_text())
    sources = json.loads(sources_path.read_text())
    if not isinstance(protocol, dict) or not isinstance(sources, dict):
        raise ValueError("Research Protocol v8 roots must be objects")
    return validate_protocol(protocol, sources)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol, args.sources), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

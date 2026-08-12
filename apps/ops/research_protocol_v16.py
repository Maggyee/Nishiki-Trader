"""Validate the frozen Protocol v16 Treasury-direct rate contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v16.json")
SCHEMA_VERSION = "research.protocol.v16"
IDENTITIES = {
    "real_yield_relief": (
        "rule_us_real_yield_relief_v2",
        "treasury-real10-5-20-negative-lag2d-v1",
    ),
    "yield_curve_steepening": (
        "rule_us_yield_curve_steepening_v2",
        "treasury-10y2y-5-20-positive-lag2d-v1",
    ),
    "treasury_volatility_relief": (
        "rule_us_treasury_volatility_relief_v2",
        "treasury-nominal10-absdiff5-20-negative-lag2d-v1",
    ),
}
PARAMETERS = {
    "real_yield_relief": {"short_observations": 5, "long_observations": 20, "ttl_seconds": 86400, "confidence": 0.75},
    "yield_curve_steepening": {"short_observations": 5, "long_observations": 20, "ttl_seconds": 86400, "confidence": 0.75},
    "treasury_volatility_relief": {"change": "absolute_first_difference", "short_observations": 5, "long_observations": 20, "ttl_seconds": 86400, "confidence": 0.75}
}
YEARS = (2019, 2020, 2021, 2022)


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != "preregistered_before_treasury_rate_body_access":
        raise ValueError("Protocol v16 pre-access identity drifted")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v16 must lock exactly three candidates")
    if {row["key"]: (row["source"], row["model_version"]) for row in candidates} != IDENTITIES:
        raise ValueError("Protocol v16 candidate identities drifted")
    if {row["key"]: row["parameters"] for row in candidates} != PARAMETERS:
        raise ValueError("Protocol v16 parameters drifted")
    data = payload.get("data_contract", {})
    if data.get("years") != list(YEARS):
        raise ValueError("Protocol v16 years drifted")
    routes = data.get("routes", {})
    if routes.get("nominal") != {
        "params": {"type": "daily_treasury_yield_curve", "field_tdr_date_value": "{year}", "page": "", "_format": "csv"},
        "required_fields_normalized": ["date", "2 yr", "10 yr"],
    } or routes.get("real") != {
        "params": {"type": "daily_treasury_real_yield_curve", "field_tdr_date_value": "{year}", "page": "", "_format": "csv"},
        "required_fields_normalized": ["date", "10 yr"],
    }:
        raise ValueError("Protocol v16 routes drifted")
    if data.get("decision_lag_calendar_days") != 2 or data.get("missing_value_policy") != "inner join numeric nominal and real dates; never fill":
        raise ValueError("Protocol v16 information timing drifted")
    multiple = payload.get("gates", {}).get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 3 or not all(
        multiple.get(flag) is True
        for flag in ("parameter_grid_search_forbidden", "alternate_sign_forbidden", "pnl_selected_ensemble_forbidden", "failed_candidate_reparameterization_forbidden")
    ):
        raise ValueError("Protocol v16 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v16 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"schema_version": SCHEMA_VERSION, "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(), "candidate_count": 3, "valid": True}


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v16 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

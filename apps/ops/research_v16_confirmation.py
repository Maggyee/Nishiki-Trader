"""Validate the frozen Protocol v16 confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v16 import IDENTITIES, PARAMETERS

DEFAULT_CONTRACT = Path("docs/progress/phase-2-research-v16-confirmation.json")
SCHEMA_VERSION = "research.protocol.v16.confirmation.v1"
CANDIDATE = "treasury_volatility_relief"
YEARS = (2023, 2024, 2025)


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != "preregistered_before_treasury_confirmation_body_access":
        raise ValueError("Protocol v16 confirmation identity drifted")
    candidate = payload.get("candidate", {})
    if (candidate.get("source"), candidate.get("model_version")) != IDENTITIES[CANDIDATE] or candidate.get("parameters") != PARAMETERS[CANDIDATE]:
        raise ValueError("Protocol v16 confirmation candidate drifted")
    development = payload.get("development_evidence", {})
    if development.get("committed_review") != "2e4edbf" or development.get("development_classification") != "development_pass_confirmation_open_eligible":
        raise ValueError("Protocol v16 development prerequisite drifted")
    data = payload.get("data_contract", {})
    if data.get("years") != list(YEARS) or data.get("params") != {"type": "daily_treasury_yield_curve", "field_tdr_date_value": "{year}", "page": "", "_format": "csv"}:
        raise ValueError("Protocol v16 confirmation requests drifted")
    if data.get("development_warmup", {}).get("payload_sha256") != "sha256:c33cb2758e5e34c2c23b7ab759d18681091860f3f9e5960112859f64f31cd814":
        raise ValueError("Protocol v16 warmup fingerprint drifted")
    if data.get("decision_lag_calendar_days") != 2 or data.get("missing_value_policy") != "drop missing nominal observation; never fill":
        raise ValueError("Protocol v16 confirmation timing drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v16 confirmation boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"schema_version": SCHEMA_VERSION, "contract_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(), "valid": True}


def load_and_validate(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v16 confirmation root must be an object")
    return validate_contract(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate the frozen Protocol v37 confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v37 import (
    COMMON_PARAMETERS,
    COST_SCENARIOS,
    GATES,
    IDENTITIES,
)
from apps.ops.research_protocol_v37 import (
    load_and_validate as load_and_validate_parent,
)

DEFAULT_CONTRACT = Path("docs/progress/phase-2-research-v37-confirmation.json")
DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v37-development-results.json")
SCHEMA_VERSION = "research.protocol.v37.confirmation.v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Protocol v37 confirmation schema drifted")
    if payload.get("status") != "preregistered_before_confirmation_open":
        raise ValueError("Protocol v37 confirmation status drifted")
    parent_validation = load_and_validate_parent()
    if payload.get("parent_protocol_sha256") != parent_validation["protocol_sha256"]:
        raise ValueError("Protocol v37 confirmation parent protocol fingerprint mismatch")
    dev_payload = json.loads(DEVELOPMENT_RESULTS.read_text())
    if dev_payload.get("schema_version") != "research.v37.development_results.v1":
        raise ValueError("Protocol v37 dev results schema drifted")
    candidate = payload.get("candidate", {})
    if candidate.get("key") != "bxn_expansion":
        raise ValueError("candidate drifted; must be bxn_expansion")
    source, model = IDENTITIES["bxn_expansion"]
    if candidate.get("source") != source or candidate.get("model_version") != model:
        raise ValueError("candidate identity drifted")
    if candidate.get("parameters") != COMMON_PARAMETERS:
        raise ValueError("candidate parameters drifted")
    data_contract = payload.get("data_contract", {})
    if (
        data_contract.get("confirmation_start") != "2023-01-01"
        or data_contract.get("confirmation_end") != "2025-12-31"
        or data_contract.get("warmup_start") != "2022-11-01"
        or data_contract.get("publication_lag_calendar_days") != 1
    ):
        raise ValueError("data contract windows drifted")
    if payload.get("cost_scenarios") != COST_SCENARIOS:
        raise ValueError("cost scenarios drifted")
    if payload.get("gates") != GATES:
        raise ValueError("gates drifted")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": _sha256(canonical.encode()),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("confirmation contract must be a dict")
    return validate_contract(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

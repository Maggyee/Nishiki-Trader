"""Validate the frozen Protocol v34 FVX confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v34 import COMMON_PARAMETERS, IDENTITIES, load_and_validate
from apps.ops.research_v34_review import load_provider_qualification

DEFAULT_CONTRACT = Path("docs/progress/phase-2-research-v34-confirmation.json")
DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v34-development-results.json")
SCHEMA_VERSION = "research.protocol.v34.confirmation.v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Protocol v34 confirmation contract schema drifted")
    protocol = load_and_validate()
    qualification = load_provider_qualification()
    dev_results_bytes = DEVELOPMENT_RESULTS.read_bytes()
    expected_dev_sha = _sha256(dev_results_bytes)
    evidence = payload.get("development_evidence", {})
    if evidence.get("protocol_sha256") != protocol["protocol_sha256"]:
        raise ValueError("Protocol v34 confirmation protocol fingerprint mismatch")
    if evidence.get("development_results_sha256") != expected_dev_sha:
        raise ValueError("Protocol v34 confirmation development results fingerprint mismatch")
    if "fvx_relief" not in qualification["qualified_candidates"]:
        raise ValueError("fvx_relief must be in qualified candidates")
    candidate = payload.get("candidate", {})
    if candidate.get("key") != "fvx_relief":
        raise ValueError("Protocol v34 confirmation candidate key must be fvx_relief")
    expected_source, expected_model = IDENTITIES["fvx_relief"]
    if (
        candidate.get("source") != expected_source
        or candidate.get("model_version") != expected_model
        or candidate.get("index") != "FVX"
    ):
        raise ValueError("Protocol v34 confirmation candidate identity drifted")
    if candidate.get("parameters") != COMMON_PARAMETERS:
        raise ValueError("Protocol v34 confirmation candidate parameters drifted")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_sha256": _sha256(canonical.encode()),
        "valid": True,
    }


def load_and_validate_confirmation(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v34 confirmation payload must be a dictionary")
    return validate_contract(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate_confirmation(args.contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

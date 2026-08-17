"""Contract validation for Protocol v48 confirmation holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIRMATION_PATH = Path("docs/progress/phase-2-research-v48-confirmation.json")
SCHEMA_VERSION = "research.v48.confirmation.v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_confirmation_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"expected schema {SCHEMA_VERSION}, got {payload.get('schema_version')}")
    if payload.get("status") != "preregistered_before_confirmation_unseal":
        raise ValueError(f"expected status preregistered_before_confirmation_unseal, got {payload.get('status')}")
    candidate = payload.get("candidate", {})
    if candidate.get("key") != "btc_basis_below_ma10":
        raise ValueError("candidate mismatch")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": _sha256(canonical.encode()),
        "valid": True,
    }


def load_and_validate_confirmation(path: Path = DEFAULT_CONFIRMATION_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    return validate_confirmation_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_CONFIRMATION_PATH)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate_confirmation(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

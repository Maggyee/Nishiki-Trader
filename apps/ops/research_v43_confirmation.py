"""Validation for Protocol v43 confirmation holdout contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIRMATION_PATH = Path("docs/progress/phase-2-research-v43-confirmation.json")
SCHEMA_VERSION = "research.protocol.v43.confirmation.v1"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def validate_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"expected schema {SCHEMA_VERSION}, got {payload.get('schema_version')}")
    if payload.get("status") != "preregistered_before_confirmation_access":
        raise ValueError(f"expected status preregistered_before_confirmation_access, got {payload.get('status')}")
    cand = payload.get("candidate", {})
    if cand.get("key") != "btc_macd_vol_confirmed":
        raise ValueError(f"expected candidate btc_macd_vol_confirmed, got {cand.get('key')}")
    if cand.get("source") != "rule_crypto_btc_macd_vol_v1":
        raise ValueError("source drifted")
    if cand.get("model_version") != "crypto-btc-macd12-26-9-vol080-lag1d-v1":
        raise ValueError("model_version drifted")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "confirmation_sha256": _sha256(canonical.encode()),
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_CONFIRMATION_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    return validate_confirmation(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONFIRMATION_PATH)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

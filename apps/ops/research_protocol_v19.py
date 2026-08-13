"""Validate the frozen Protocol v19 Cboe size/style/China volatility contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v19.json")
SCHEMA_VERSION = "research.protocol.v19"
IDENTITIES = {
    "russell_vol_relief": ("rule_russell_vol_relief_v1", "cboe-rvx-ohlc5obs-negative-1d-v1"),
    "dow_vol_relief": ("rule_dow_vol_relief_v1", "cboe-vxd-ohlc5obs-negative-1d-v1"),
    "china_vol_relief": ("rule_china_vol_relief_v1", "cboe-vxfxi-ohlc5obs-negative-1d-v1"),
}
PARAMETERS = {
    "change_observations": 5,
    "maximum_change": 0.0,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}
INDEXES = {"russell_vol_relief": "RVX", "dow_vol_relief": "VXD", "china_vol_relief": "VXFXI"}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("status") != "preregistered_before_cboe_csv_body_access"
    ):
        raise ValueError("Protocol v19 pre-access identity drifted")
    if payload.get("data_access_disclosure", {}).get("csv_bodies_opened") is not False:
        raise ValueError("Protocol v19 must remain closed to CSV bodies")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v19 must lock exactly three candidates")
    actual = {row["key"]: (row["source"], row["model_version"]) for row in candidates}
    if actual != IDENTITIES:
        raise ValueError("Protocol v19 candidate identities drifted")
    if any(
        row.get("parameters") != PARAMETERS or row.get("index") != INDEXES[row["key"]]
        for row in candidates
    ):
        raise ValueError("Protocol v19 parameters or indexes drifted")
    multiple = payload.get("gates", {}).get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 3 or not all(
        multiple.get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v19 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v19 boundaries are unsafe")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 3,
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v19 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

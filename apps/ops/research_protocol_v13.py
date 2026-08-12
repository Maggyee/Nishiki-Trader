"""Validate the frozen Protocol v13 network-mechanism contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v13.json")
SCHEMA_VERSION = "research.protocol.v13"
IDENTITIES = {
    "active_address_expansion": (
        "rule_btc_active_address_expansion_v1",
        "chainfinalized-adractcnt7-30-positive-lag2d-v1",
    ),
    "transfer_count_expansion": (
        "rule_btc_transfer_expansion_v1",
        "chainfinalized-txtfrcnt7-30-positive-lag2d-v1",
    ),
    "mvrv_distress": ("rule_btc_mvrv_distress_v1", "chainfinalized-mvrv-below1-lag2d-v1"),
}
PARAMETERS = {
    "active_address_expansion": {
        "short_days": 7,
        "long_days": 30,
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
    "transfer_count_expansion": {
        "short_days": 7,
        "long_days": 30,
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
    "mvrv_distress": {
        "maximum_mvrv": 1.0,
        "comparison": "strictly_below",
        "ttl_seconds": 86400,
        "confidence": 0.75,
    },
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("status") != "preregistered_before_coinmetrics_network_body_access"
    ):
        raise ValueError("Protocol v13 pre-access identity drifted")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v13 must lock exactly three candidates")
    if {row["key"]: (row["source"], row["model_version"]) for row in candidates} != IDENTITIES:
        raise ValueError("Protocol v13 candidate identities drifted")
    if {row["key"]: row["parameters"] for row in candidates} != PARAMETERS:
        raise ValueError("Protocol v13 parameters drifted")
    data = payload.get("data_contract", {})
    if data.get("params") != {
        "assets": "btc",
        "metrics": "AdrActCnt,TxTfrCnt,CapMVRVCur",
        "start_time": "2019-11-01",
        "end_time": "2022-12-31",
        "frequency": "1d",
        "page_size": "10000",
    }:
        raise ValueError("Protocol v13 request parameters drifted")
    if data.get("decision_lag_days") != 2 or data.get("forward_fill_forbidden") is not True:
        raise ValueError("Protocol v13 information timing drifted")
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
        raise ValueError("Protocol v13 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v13 boundaries are unsafe")
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
        raise ValueError("Protocol v13 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

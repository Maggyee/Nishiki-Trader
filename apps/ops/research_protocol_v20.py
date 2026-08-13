"""Validate the frozen Protocol v20 OFR financial-stress contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v20.json")
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v20-data-sources.json")
SCHEMA_VERSION = "research.protocol.v20"
IDENTITIES = {
    "systemic_stress_relief": (
        "rule_ofr_systemic_stress_relief_v1",
        "ofr-fsi-total-diff5-negative-lag5d-v1",
    ),
    "credit_stress_relief": (
        "rule_ofr_credit_stress_relief_v1",
        "ofr-fsi-credit-diff5-negative-lag5d-v1",
    ),
    "safe_asset_stress_relief": (
        "rule_ofr_safe_asset_stress_relief_v1",
        "ofr-fsi-safe-assets-diff5-negative-lag5d-v1",
    ),
}
SERIES_KEYS = {
    "systemic_stress_relief": "OFRFSI",
    "credit_stress_relief": "Credit",
    "safe_asset_stress_relief": "Flight_to_Safety",
}
PARAMETERS = {
    "change_observations": 5,
    "maximum_change": 0.0,
    "publication_lag_calendar_days": 5,
    "ttl_seconds": 86400,
    "confidence": 0.75,
}
DEVELOPMENT_GATES = {
    "base_net_pnl_gt": 0.0,
    "stress_net_pnl_gt": 0.0,
    "positive_calendar_years_at_least": 2,
    "positive_calendar_months_at_least": 18,
    "closed_positions_at_least": 30,
    "leave_best_position_base_net_pnl_gt": 0.0,
    "duplicate_replays_required": 2,
}


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("status") != "preregistered_before_ofr_fsi_body_access"
    ):
        raise ValueError("Protocol v20 pre-access identity drifted")
    disclosure = payload.get("data_access_disclosure", {})
    if disclosure.get("json_body_opened") is not False or disclosure.get(
        "csv_body_opened"
    ) is not False:
        raise ValueError("Protocol v20 must remain closed to OFR data bodies")
    data_contract = payload.get("data_contract", {})
    if data_contract.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("Protocol v20 provider-contract path drifted")
    if data_contract.get("conservative_decision_lag_calendar_days") != 5:
        raise ValueError("Protocol v20 conservative publication lag drifted")
    if data_contract.get("historical_vintage_claim") is not False:
        raise ValueError("Protocol v20 cannot claim historical OFR vintages")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Protocol v20 must lock exactly three candidates")
    actual = {
        row["key"]: (row["source"], row["model_version"])
        for row in candidates
    }
    if actual != IDENTITIES:
        raise ValueError("Protocol v20 candidate identities drifted")
    if any(
        row.get("series_key") != SERIES_KEYS[row["key"]]
        or row.get("parameters") != PARAMETERS
        for row in candidates
    ):
        raise ValueError("Protocol v20 series or parameters drifted")
    gates = payload.get("gates", {})
    if gates.get("development") != DEVELOPMENT_GATES:
        raise ValueError("Protocol v20 development gates drifted")
    multiple = gates.get("multiple_testing", {})
    if multiple.get("candidate_count_locked") != 3 or not all(
        multiple.get(flag) is True
        for flag in (
            "parameter_grid_search_forbidden",
            "alternate_sign_forbidden",
            "pnl_selected_ensemble_forbidden",
            "failed_candidate_reparameterization_forbidden",
        )
    ):
        raise ValueError("Protocol v20 multiple-testing guard drifted")
    if any(payload.get("boundaries_effect", {}).values()):
        raise ValueError("Protocol v20 boundaries are unsafe")
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": "sha256:"
        + hashlib.sha256(canonical.encode()).hexdigest(),
        "candidate_count": 3,
        "valid": True,
    }


def load_and_validate(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Protocol v20 root must be an object")
    return validate_protocol(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args(argv)
    print(json.dumps(load_and_validate(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

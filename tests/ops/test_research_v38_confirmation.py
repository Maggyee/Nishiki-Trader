from __future__ import annotations

import json

import pytest

from apps.ops.research_v38_confirmation import (
    DEFAULT_CONTRACT,
    load_and_validate,
    validate_contract,
)


def test_v38_confirmation_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["contract_sha256"].startswith("sha256:")


def test_v38_confirmation_rejects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="candidate drifted"):
        validate_contract(payload)


def test_v38_confirmation_results_recorded_and_rejected() -> None:
    from pathlib import Path
    results_path = Path("docs/progress/phase-2-research-v38-confirmation-results.json")
    payload = json.loads(results_path.read_text())
    assert payload["schema_version"] == "research.v38.confirmation_results.v1"
    assert payload["recommendation"] == "stop_protocol_v38_confirmation_failed"
    candidate = payload["candidate"]
    assert candidate["key"] == "cll_expansion"
    assert candidate["classification"] == "reject_candidate"
    assert candidate["performance_pass"] is False
    assert candidate["positive_months"] == 15

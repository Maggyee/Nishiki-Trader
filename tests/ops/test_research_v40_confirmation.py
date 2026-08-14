from __future__ import annotations

import json

import pytest

from apps.ops.research_v40_confirmation import (
    DEFAULT_CONTRACT,
    load_and_validate,
    validate_contract,
)


def test_v40_confirmation_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["contract_sha256"].startswith("sha256:")


def test_v40_confirmation_rejects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="candidate drifted"):
        validate_contract(payload)


def test_v40_confirmation_results_recorded_and_passed() -> None:
    from pathlib import Path
    results_path = Path("docs/progress/phase-2-research-v40-confirmation-results.json")
    payload = json.loads(results_path.read_text())
    assert payload["schema_version"] == "research.v40.confirmation_results.v1"
    assert payload["recommendation"] == "enter_paper_shadow_review"
    candidate = payload["candidate"]
    assert candidate["key"] == "vxn_relief"
    assert candidate["classification"] == "paper_shadow_review_eligible"
    assert candidate["performance_pass"] is True
    assert candidate["positive_months"] == 20
    assert candidate["positive_years"] == 3
    assert candidate["base_net_pnl"] > 50.0

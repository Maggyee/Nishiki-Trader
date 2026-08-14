from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.ops.research_v34_confirmation import (
    DEFAULT_CONTRACT,
    load_and_validate,
    validate_contract,
)

CONFIRMATION_RESULTS = Path("docs/progress/phase-2-research-v34-confirmation-results.json")


def test_v34_confirmation_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["contract_sha256"].startswith("sha256:")


def test_v34_confirmation_rejects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="candidate drifted"):
        validate_contract(payload)


def test_v34_confirmation_results_pass_and_paper_shadow_eligible() -> None:
    payload = json.loads(CONFIRMATION_RESULTS.read_text())
    assert payload["schema_version"] == "research.v34.confirmation_results.v1"
    assert payload["recommendation"] == "enter_paper_shadow_review"
    candidate = payload["candidate"]
    assert candidate["classification"] == "paper_shadow_review_eligible"
    assert candidate["performance_pass"] is True
    assert candidate["evidence_pass"] is True
    assert candidate["reproducible"] is True
    assert candidate["base_net_pnl"] > 0.0
    assert candidate["stress_net_pnl"] > 0.0
    assert candidate["positive_years"] == 3
    assert candidate["positive_months"] >= 18
    assert candidate["closed_positions"] >= 30
    assert candidate["leave_best_base_net_pnl"] > 0.0
    assert candidate["short_positions"] == 0
    assert payload["boundaries"]["touches_live_path"] is False

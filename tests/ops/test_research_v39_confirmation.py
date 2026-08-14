from __future__ import annotations

import json

import pytest

from apps.ops.research_v39_confirmation import (
    DEFAULT_CONTRACT,
    load_and_validate,
    validate_contract,
)


def test_v39_confirmation_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["contract_sha256"].startswith("sha256:")


def test_v39_confirmation_rejects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="candidate drifted"):
        validate_contract(payload)

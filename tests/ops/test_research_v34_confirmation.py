from __future__ import annotations

import json

import pytest

from apps.ops.research_v34_confirmation import (
    DEFAULT_CONTRACT,
    load_and_validate_confirmation,
    validate_contract,
)


def test_v34_confirmation_contract_is_valid() -> None:
    result = load_and_validate_confirmation(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["contract_sha256"].startswith("sha256:")


def test_v34_confirmation_rejects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="key must be fvx_relief"):
        validate_contract(payload)

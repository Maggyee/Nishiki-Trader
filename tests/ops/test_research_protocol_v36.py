from __future__ import annotations

import json

import pytest

from apps.ops.research_protocol_v36 import (
    DEFAULT_CONTRACT,
    load_and_validate,
    validate_contract,
)


def test_v36_contract_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONTRACT)
    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["protocol_sha256"].startswith("sha256:")


def test_v36_rejects_mutated_status() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["status"] = "opened_prematurely"
    with pytest.raises(ValueError, match="status drifted"):
        validate_contract(payload)


def test_v36_rejects_missing_candidate() -> None:
    payload = json.loads(DEFAULT_CONTRACT.read_text())
    payload["candidates"].pop()
    with pytest.raises(ValueError, match="expected 3 candidates"):
        validate_contract(payload)

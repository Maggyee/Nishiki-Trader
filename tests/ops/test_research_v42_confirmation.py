from __future__ import annotations

import json

import pytest

from apps.ops.research_v42_confirmation import (
    DEFAULT_CONFIRMATION_PATH,
    load_and_validate,
    validate_confirmation,
)


def test_confirmation_v42_is_valid() -> None:
    result = load_and_validate(DEFAULT_CONFIRMATION_PATH)
    assert result["valid"] is True
    assert result["confirmation_sha256"].startswith("sha256:")


def test_confirmation_v42_detects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_CONFIRMATION_PATH.read_text())
    payload["candidate"]["key"] = "wrong_candidate"
    with pytest.raises(ValueError, match="expected candidate vix6m_relief"):
        validate_confirmation(payload)

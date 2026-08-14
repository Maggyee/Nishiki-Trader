from __future__ import annotations

import json

import pytest

from apps.ops.research_protocol_v42 import (
    DEFAULT_PROTOCOL_PATH,
    load_and_validate,
    validate_protocol,
)


def test_protocol_v42_is_valid() -> None:
    result = load_and_validate(DEFAULT_PROTOCOL_PATH)
    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["protocol_sha256"].startswith("sha256:")


def test_protocol_v42_detects_candidate_drift() -> None:
    payload = json.loads(DEFAULT_PROTOCOL_PATH.read_text())
    payload["candidates"]["vix9d_relief"]["parameters"]["direction"] = "positive"
    with pytest.raises(ValueError, match="parameters mismatch"):
        validate_protocol(payload)

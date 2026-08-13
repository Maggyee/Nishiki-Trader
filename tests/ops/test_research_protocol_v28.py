from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v28 import (
    DEFAULT_PROTOCOL,
    load_and_validate,
    validate_protocol,
)


def test_protocol_v28_is_frozen_and_valid() -> None:
    result = load_and_validate()

    assert result["valid"] is True
    assert result["candidate_count"] == 3


def test_protocol_v28_rejects_direction_drift() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    drifted = copy.deepcopy(payload)
    drifted["candidates"][0]["parameters"]["direction"] = "negative"

    with pytest.raises(ValueError, match="candidate parameters drifted"):
        validate_protocol(drifted)


def test_protocol_v28_rejects_opened_history() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    payload["data_access_disclosure"]["historical_json_bodies_opened"] = True

    with pytest.raises(ValueError, match="historical data boundary drifted"):
        validate_protocol(payload)

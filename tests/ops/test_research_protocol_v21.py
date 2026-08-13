from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v21 import (
    DEFAULT_PROTOCOL,
    load_and_validate,
    validate_protocol,
)


def test_protocol_v21_is_frozen_and_valid() -> None:
    result = load_and_validate()

    assert result["valid"] is True
    assert result["candidate_count"] == 1
    assert result["protocol_sha256"].startswith("sha256:")
    assert result["provider_contract_sha256"].startswith("sha256:")


def test_protocol_v21_rejects_rule_parameter_drift() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    drifted = copy.deepcopy(payload)
    drifted["candidate"]["parameters"]["change_observations"] = 5

    with pytest.raises(ValueError, match="candidate identity drifted"):
        validate_protocol(drifted)


def test_protocol_v21_rejects_opened_historical_body() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    payload["data_access_disclosure"]["historical_csv_bodies_opened"] = True

    with pytest.raises(ValueError, match="historical data boundary drifted"):
        validate_protocol(payload)

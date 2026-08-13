from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v20 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v20_protocol_is_valid() -> None:
    result = validate_protocol(_payload())
    assert result["valid"] is True
    assert result["candidate_count"] == 3


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("data_access_disclosure", "json_body_opened"), True),
        (("data_contract", "conservative_decision_lag_calendar_days"), 2),
        (("candidates", 0, "parameters", "change_observations"), 10),
        (("gates", "multiple_testing", "alternate_sign_forbidden"), False),
        (("boundaries_effect", "opens_confirmation"), True),
    ],
)
def test_v20_protocol_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

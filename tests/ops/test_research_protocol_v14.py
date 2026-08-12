from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v14 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v14_contract_is_valid() -> None:
    assert validate_protocol(_payload())["candidate_count"] == 3


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "short_days"), 5),
        (("candidates", 2, "parameters", "maximum_sopr"), 0.99),
        (("data_contract", "decision_lag_days"), 1),
        (("boundaries_effect", "reopens_v13"), True),
    ],
)
def test_v14_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v13 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v13_contract_is_valid() -> None:
    assert validate_protocol(_payload())["candidate_count"] == 3


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "short_days"), 5),
        (("candidates", 2, "parameters", "maximum_mvrv"), 1.2),
        (("data_contract", "decision_lag_days"), 1),
        (("boundaries_effect", "touches_v12_forward_collection"), True),
    ],
)
def test_v13_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

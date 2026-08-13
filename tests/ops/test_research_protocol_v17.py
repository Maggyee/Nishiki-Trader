from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v17 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v17_contract_is_valid() -> None:
    assert validate_protocol(_payload())["candidate_count"] == 3


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "change_observations"), 10),
        (("candidates", 1, "index"), "VIX"),
        (("data_access_disclosure", "csv_bodies_opened"), True),
        (("boundaries_effect", "reopens_v7_or_v9"), True),
    ],
)
def test_v17_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

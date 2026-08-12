from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_v16_confirmation import DEFAULT_CONTRACT, validate_contract


def _payload() -> dict:
    return json.loads(DEFAULT_CONTRACT.read_text())


def test_v16_confirmation_contract_is_valid() -> None:
    assert validate_contract(_payload())["valid"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidate", "parameters", "short_observations"), 3),
        (("development_evidence", "committed_review"), "uncommitted"),
        (("data_contract", "decision_lag_calendar_days"), 1),
        (("boundaries_effect", "opens_future_blind"), True),
    ],
)
def test_v16_confirmation_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_contract(payload)

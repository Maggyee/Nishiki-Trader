from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v11 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v11_contract_is_valid() -> None:
    assert validate_protocol(_payload())["valid"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("point_in_time_contract", "decision_timestamp"), "D+1"),
        (("relationship_to_v10", "rules_and_parameters_unchanged"), False),
        (("candidates", 0, "parameters", "short_days"), 5),
        (("snapshots", "hashrate"), "sha256:bad"),
        (("gates", "multiple_testing", "alternate_sign_forbidden"), False),
        (("boundaries_effect", "opens_confirmation_holdout"), True),
    ],
)
def test_v11_contract_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v10 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v10_contract_locks_three_candidates_and_sealed_holdouts() -> None:
    result = validate_protocol(_payload())

    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["development_reserve"]["strategy_specific_pnl_access_status"] == "unconsumed"
    assert (
        result["confirmation_holdout"]["strategy_specific_pnl_access_status"]
        == "sealed_until_development_pass"
    )
    assert result["future_blind"]["shared_v8_blind_remains_sealed"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "short_days"), 5),
        (("candidates", 1, "parameters", "change_days"), 60),
        (("candidates", 2, "parameters", "long_days"), 90),
        (("gates", "multiple_testing", "alternate_sign_forbidden"), False),
        (("provider_qualification", "requests", 0, "params", "metrics"), "HashRate30d"),
        (("boundaries_effect", "opens_confirmation_holdout"), True),
    ],
)
def test_v10_contract_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError):
        validate_protocol(payload)

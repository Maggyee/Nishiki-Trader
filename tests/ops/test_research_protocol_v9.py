from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v9 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v9_contract_locks_two_sequential_candidates() -> None:
    result = validate_protocol(_payload())

    assert result["valid"] is True
    assert result["candidate_count"] == 2
    assert result["development_reserve"]["strategy_specific_pnl_access_status"] == "unconsumed"
    assert (
        result["confirmation_holdout"]["strategy_specific_pnl_access_status"]
        == "sealed_until_development_pass"
    )
    assert result["future_blind"]["shared_v8_blind_remains_sealed"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "curve_ratio_threshold"), 0.95),
        (("candidates", 1, "parameters", "change_observations"), 10),
        (("gates", "multiple_testing", "alternate_sign_forbidden"), False),
        (("boundaries", "confirmation_holdout", "strategy_specific_pnl_access_status"), "open"),
        (("boundaries_effect", "opens_future_blind"), True),
    ],
)
def test_v9_contract_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError):
        validate_protocol(payload)

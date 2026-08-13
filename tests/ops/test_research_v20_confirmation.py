from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_v20_confirmation import DEFAULT_CONTRACT, validate_contract


def _payload() -> dict:
    return json.loads(DEFAULT_CONTRACT.read_text())


def test_v20_confirmation_contract_is_valid() -> None:
    assert validate_contract(_payload())["valid"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidate", "parameters", "change_observations"), 3),
        (("development_evidence", "committed_review"), "uncommitted"),
        (("data_contract", "decision_lag_calendar_days"), 2),
        (("data_contract", "historical_vintage_claim"), True),
        (("cost_scenarios", "base", "fee_bps_per_fill"), 9),
        (("data_access_disclosure", "confirmation_pnl_computed"), True),
        (("boundaries_effect", "opens_future_blind"), True),
    ],
)
def test_v20_confirmation_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_contract(payload)

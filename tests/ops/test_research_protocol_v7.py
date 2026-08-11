from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v7 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v7_protocol_is_valid_and_locks_three_candidates() -> None:
    result = validate_protocol(_payload())
    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["historical_replication_reserve"]["access_status"] == "unconsumed"
    assert result["final_future_blind"]["start"] == "2026-09-01"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidates", 0, "parameters", "change_observations"), 10),
        (("candidates", 1, "source"), "rule_energy_vol_relief_v2"),
        (("gates", "multiple_testing", "parameter_grid_search_forbidden"), False),
        (("boundaries_effect", "touches_live_path"), True),
    ],
)
def test_v7_protocol_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

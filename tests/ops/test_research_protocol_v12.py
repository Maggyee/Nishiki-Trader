from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v12 import DEFAULT_PROTOCOL, validate_protocol


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_v12_contract_locks_unchanged_forward_candidate() -> None:
    result = validate_protocol(_payload())

    assert result["valid"] is True
    assert result["source"] == "rule_stablecoin_liquidity_v3"
    assert result["model_version"].endswith("d2-v1")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("relationship_to_v11", "rule_and_sign_unchanged"), False),
        (("candidate", "parameters", "change_observations"), 14),
        (("collection", "forward_observation_start"), "2026-08-11"),
        (("evidence_gate", "qualified_distinct_forward_observation_days"), 30),
        (("evidence_gate", "promotion_created"), True),
        (("boundaries", "paper_shadow_authorized"), True),
    ],
)
def test_v12_contract_rejects_drift(path: tuple, value: object) -> None:
    payload = copy.deepcopy(_payload())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_protocol(payload)

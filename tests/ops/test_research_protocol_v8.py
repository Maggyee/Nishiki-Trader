from __future__ import annotations

import copy
import json

import pytest

from apps.ops.research_protocol_v8 import (
    DEFAULT_PROTOCOL,
    DEFAULT_SOURCES,
    validate_protocol,
)


def _payloads() -> tuple[dict, dict]:
    return json.loads(DEFAULT_PROTOCOL.read_text()), json.loads(DEFAULT_SOURCES.read_text())


def test_v8_contract_locks_one_unchanged_confirmation_candidate() -> None:
    result = validate_protocol(*_payloads())

    assert result["valid"] is True
    assert result["candidate_source"] == "rule_gold_vol_relief_v1"
    assert result["confirmation_holdout"]["strategy_specific_pnl_access_status"] == "unconsumed"
    assert result["future_blind"]["remains_sealed_during_v8"] is True


@pytest.mark.parametrize(
    ("document", "path", "value"),
    [
        ("protocol", ("candidate", "parameters", "change_observations"), 10),
        ("protocol", ("market_session_continuity", "synthetic_bars_forbidden"), False),
        ("protocol", ("multiple_testing", "threshold_change_forbidden"), False),
        ("sources", ("execution_source", "months", "end"), "2026-01"),
    ],
)
def test_v8_contract_rejects_drift(
    document: str,
    path: tuple,
    value: object,
) -> None:
    protocol, sources = copy.deepcopy(_payloads())
    target = protocol if document == "protocol" else sources
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError):
        validate_protocol(protocol, sources)

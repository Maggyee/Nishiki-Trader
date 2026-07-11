from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps.ops.research_protocol_v2 import (
    DEFAULT_PROTOCOL,
    load_and_validate_protocol,
    validate_protocol,
)


def _payload() -> dict:
    return json.loads(DEFAULT_PROTOCOL.read_text())


def test_repository_protocol_is_valid_and_fingerprinted() -> None:
    review = load_and_validate_protocol()

    assert review["valid"] is True
    assert review["candidate_count"] == 3
    assert review["protocol_sha256"].startswith("sha256:")
    assert len(review["protocol_sha256"]) == 71
    assert review["final_future_blind"]["start"] == "2026-08-01"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (
            lambda payload: payload["boundaries"]["opened_diagnostic_only"].update(
                {"pnl_selection_forbidden": False}
            ),
            "forbid PnL selection",
        ),
        (
            lambda payload: payload["boundaries"]["historical_replication_reserve"].update(
                {"max_openings": 2}
            ),
            "exactly one opening",
        ),
        (
            lambda payload: payload["cost_scenarios"]["base"].update(
                {"fee_bps_per_fill": 0.0}
            ),
            "cost scenarios",
        ),
        (
            lambda payload: payload["candidates"][0].update({"data_access_status": "opened"}),
            "not_accessed",
        ),
        (
            lambda payload: payload["gates"]["multiple_testing"].update(
                {"parameter_grid_search_forbidden": False}
            ),
            "research gates",
        ),
    ],
)
def test_protocol_fails_closed_when_anti_overfit_guards_change(mutate, match: str) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)

    with pytest.raises(ValueError, match=match):
        validate_protocol(payload)


def test_protocol_rejects_overlapping_partitions_and_identity_drift() -> None:
    overlapping = _payload()
    overlapping["boundaries"]["historical_replication_reserve"]["end"] = "2023-01-02"
    with pytest.raises(ValueError, match="partition dates"):
        validate_protocol(overlapping)

    drifted = _payload()
    drifted["candidates"][1]["model_version"] = "result-selected-v2"
    with pytest.raises(ValueError, match="identity differs"):
        validate_protocol(drifted)

    tuned = _payload()
    tuned["candidates"][2]["parameters"]["supply_change_days"] = 29
    with pytest.raises(ValueError, match="parameters differ"):
        validate_protocol(tuned)


def test_protocol_cli_input_can_be_loaded_from_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(_payload()))

    assert load_and_validate_protocol(path)["candidate_count"] == 3

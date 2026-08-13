from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps.ops.research_protocol_v24 import (
    DEFAULT_PROTOCOL,
    load_and_validate,
    validate_protocol,
)
from apps.ops.research_v24_review import load_provider_qualification


def test_protocol_v24_is_frozen_and_valid() -> None:
    result = load_and_validate()

    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["protocol_sha256"].startswith("sha256:")


def test_protocol_v24_rejects_classification_drift() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    drifted = copy.deepcopy(payload)
    drifted["candidates"][0]["long_classifications"] = ["Fear"]

    with pytest.raises(ValueError, match="candidate classifications drifted"):
        validate_protocol(drifted)


def test_protocol_v24_rejects_opened_history() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    payload["data_access_disclosure"]["historical_json_bodies_opened"] = True

    with pytest.raises(ValueError, match="historical data boundary drifted"):
        validate_protocol(payload)


def test_protocol_v24_provider_qualification_is_frozen() -> None:
    result = load_provider_qualification()

    assert result["classification"] == "provider_qualified"
    assert result["qualified_candidates"] == [
        "extreme_fear_hold",
        "fear_hold",
        "non_greed_hold",
    ]
    assert result["snapshot"]["development_row_count"] == 1096
    assert result["historical_vintage_claim"] is False


def test_protocol_v24_development_is_closed_without_confirmation() -> None:
    payload = json.loads(
        Path("docs/progress/phase-2-research-v24-development-results.json").read_text()
    )

    assert payload["recommendation"] == "stop_protocol_v24_no_confirmation_open"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []

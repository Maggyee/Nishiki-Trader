from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps.ops.research_protocol_v23 import (
    DEFAULT_PROTOCOL,
    load_and_validate,
    validate_protocol,
)
from apps.ops.research_v23_review import load_provider_qualification


def test_protocol_v23_is_frozen_and_valid() -> None:
    result = load_and_validate()

    assert result["valid"] is True
    assert result["candidate_count"] == 3
    assert result["protocol_sha256"].startswith("sha256:")


def test_protocol_v23_rejects_direction_drift() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    drifted = copy.deepcopy(payload)
    drifted["candidates"][0]["parameters"]["direction"] = "negative"

    with pytest.raises(ValueError, match="candidate parameters drifted"):
        validate_protocol(drifted)


def test_protocol_v23_rejects_opened_history() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    payload["data_access_disclosure"]["historical_json_bodies_opened"] = True

    with pytest.raises(ValueError, match="historical data boundary drifted"):
        validate_protocol(payload)


def test_protocol_v23_locks_development_catalog() -> None:
    payload = json.loads(DEFAULT_PROTOCOL.read_text())
    payload["execution"]["development_catalog_path"] = "data/research-v8/catalog"

    with pytest.raises(ValueError, match="execution contract drifted"):
        validate_protocol(payload)


def test_protocol_v23_provider_qualification_is_frozen() -> None:
    result = load_provider_qualification()

    assert result["classification"] == "provider_qualified"
    assert result["qualified_candidates"] == [
        "bitcoin_attention_expansion",
        "ethereum_attention_expansion",
        "cryptocurrency_attention_expansion",
    ]
    assert result["rejected_candidates"] == {}
    assert result["historical_vintage_claim"] is False


def test_protocol_v23_development_is_closed_without_confirmation() -> None:
    payload = json.loads(Path("docs/progress/phase-2-research-v23-development-results.json").read_text())

    assert payload["recommendation"] == "stop_protocol_v23_no_confirmation_open"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []
    assert payload["confirmation_holdout_status"] == "sealed_not_opened_no_development_passer"

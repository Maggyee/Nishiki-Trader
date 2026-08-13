from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v29_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v29-development-results.json")


def test_v29_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == [
        "fed_attention_relief",
        "inflation_attention_relief",
        "recession_attention_relief",
    ]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False
    assert payload["pre_data_commit"] == "4e15d2d"


def test_v29_development_results_reject_all_three_identities() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v29.development_results.v1"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []
    assert payload["recommendation"] == "stop_protocol_v29_no_confirmation_open"
    assert [row["key"] for row in payload["candidates"]] == [
        "fed_attention_relief",
        "inflation_attention_relief",
        "recession_attention_relief",
    ]
    assert all(row["classification"] == "reject_candidate" for row in payload["candidates"])
    assert all(row["reproducible"] is True for row in payload["candidates"])
    assert payload["boundaries"]["opens_confirmation"] is False
    recession = next(row for row in payload["candidates"] if row["key"] == "recession_attention_relief")
    assert recession["failure_reasons"] == ["positive_years_1_below_2"]
    assert recession["base_net_pnl"] > 0
    assert recession["stress_net_pnl"] > 0

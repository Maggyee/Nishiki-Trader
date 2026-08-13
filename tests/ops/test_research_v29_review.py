from __future__ import annotations

from apps.ops.research_v29_review import load_provider_qualification


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

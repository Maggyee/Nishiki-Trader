from __future__ import annotations

from apps.ops.research_v27_review import load_provider_qualification


def test_v27_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == [
        "all_fees_expansion",
        "all_revenue_expansion",
        "all_holders_revenue_expansion",
    ]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False

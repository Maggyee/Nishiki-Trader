from __future__ import annotations

from apps.ops.research_v34_review import load_provider_qualification


def test_v34_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["fvx_relief", "tnx_relief", "tyx_relief"]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False

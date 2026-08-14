from __future__ import annotations

from apps.ops.research_v33_review import load_provider_qualification


def test_v33_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["cor3m_relief", "cor6m_relief", "cor1y_relief"]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False

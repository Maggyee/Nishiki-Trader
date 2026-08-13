from __future__ import annotations

from apps.ops.research_v31_review import load_provider_qualification


def test_v31_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["long_treasury_etf_vol_relief"]
    assert payload["rejected_candidates"]["silver_vol_relief"]["retry_allowed"] is False
    assert payload["rejected_candidates"]["energy_sector_vol_relief"]["retry_allowed"] is False
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False
    assert payload["pre_data_commit"] == "8f22da9"

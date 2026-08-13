from __future__ import annotations

from apps.ops.research_v30_review import load_provider_qualification


def test_v30_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == [
        "apple_vol_relief",
        "amazon_vol_relief",
        "google_vol_relief",
    ]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False
    assert payload["pre_data_commit"] == "7e16b3f"

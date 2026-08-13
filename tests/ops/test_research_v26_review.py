from __future__ import annotations

from apps.ops.research_v26_review import load_provider_qualification


def test_v26_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == [
        "all_dex_volume_expansion",
        "ethereum_dex_volume_expansion",
    ]
    assert payload["rejected_candidates"] == {
        "solana_dex_volume_expansion": "development_reserve_only_453_observations"
    }
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False

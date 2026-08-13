from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v26_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v26-development-results.json")


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


def test_v26_development_results_reject_both_qualified_identities() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v26.development_results.v1"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []
    assert payload["recommendation"] == "stop_protocol_v26_no_confirmation_open"
    assert [row["key"] for row in payload["candidates"]] == [
        "all_dex_volume_expansion",
        "ethereum_dex_volume_expansion",
    ]
    assert all(row["classification"] == "reject_candidate" for row in payload["candidates"])
    assert all(row["reproducible"] is True for row in payload["candidates"])
    assert payload["boundaries"]["opens_confirmation"] is False

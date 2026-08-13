from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v30_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v30-development-results.json")


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


def test_v30_development_results_pass_only_google_vol_relief() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v30.development_results.v1"
    assert payload["development_passer_count"] == 1
    assert payload["confirmation_open_eligible_candidates"] == ["google_vol_relief"]
    assert payload["recommendation"] == "commit_development_results_before_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    assert by_key["apple_vol_relief"]["classification"] == "reject_candidate"
    assert by_key["amazon_vol_relief"]["classification"] == "reject_candidate"
    assert by_key["google_vol_relief"]["classification"] == (
        "development_pass_confirmation_open_eligible"
    )
    assert all(row["reproducible"] is True for row in payload["candidates"])
    assert payload["boundaries"]["opens_confirmation"] is False

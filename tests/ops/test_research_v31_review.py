from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v31_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v31-development-results.json")


def test_v31_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["long_treasury_etf_vol_relief"]
    assert payload["rejected_candidates"]["silver_vol_relief"]["retry_allowed"] is False
    assert payload["rejected_candidates"]["energy_sector_vol_relief"]["retry_allowed"] is False
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False
    assert payload["pre_data_commit"] == "8f22da9"


def test_v31_development_results_reject_vxtlt() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v31.development_results.v1"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []
    assert payload["recommendation"] == "stop_protocol_v31_no_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    assert by_key["long_treasury_etf_vol_relief"]["classification"] == "reject_candidate"
    assert by_key["long_treasury_etf_vol_relief"]["reproducible"] is True
    assert payload["boundaries"]["opens_confirmation"] is False

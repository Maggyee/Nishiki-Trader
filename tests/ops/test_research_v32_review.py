from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v32_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v32-development-results.json")


def test_v32_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["pound_fx_vol_relief"]
    assert payload["rejected_candidates"]["euro_fx_vol_relief"]["retry_allowed"] is False
    assert payload["rejected_candidates"]["yen_fx_vol_relief"]["retry_allowed"] is False
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False
    assert payload["pre_data_commit"] == "89a9a9c"


def test_v32_development_results_reject_bpvix() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v32.development_results.v1"
    assert payload["development_passer_count"] == 0
    assert payload["confirmation_open_eligible_candidates"] == []
    assert payload["recommendation"] == "stop_protocol_v32_no_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    assert by_key["pound_fx_vol_relief"]["classification"] == "reject_candidate"
    assert by_key["pound_fx_vol_relief"]["reproducible"] is True
    assert payload["boundaries"]["opens_confirmation"] is False

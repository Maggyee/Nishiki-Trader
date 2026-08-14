from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v34_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v34-development-results.json")


def test_v34_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["fvx_relief", "tnx_relief", "tyx_relief"]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False


def test_v34_development_results_pass_all_three() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v34.development_results.v1"
    assert payload["development_passer_count"] == 3
    assert payload["confirmation_open_eligible_candidates"] == [
        "fvx_relief",
        "tnx_relief",
        "tyx_relief",
    ]
    assert payload["recommendation"] == "commit_development_results_before_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    for key in ("fvx_relief", "tnx_relief", "tyx_relief"):
        assert by_key[key]["classification"] == "development_pass_confirmation_open_eligible"
        assert by_key[key]["reproducible"] is True
        assert by_key[key]["base_net_pnl"] > 0.0
        assert by_key[key]["leave_best_base_net_pnl"] > 0.0
    assert payload["boundaries"]["opens_confirmation"] is False


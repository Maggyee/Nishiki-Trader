from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_v33_review import load_provider_qualification

DEVELOPMENT_RESULTS = Path("docs/progress/phase-2-research-v33-development-results.json")


def test_v33_provider_qualification_matches_frozen_protocol() -> None:
    payload = load_provider_qualification()

    assert payload["qualified_candidates"] == ["cor3m_relief", "cor6m_relief", "cor1y_relief"]
    assert payload["rejected_candidates"] == {}
    assert payload["historical_vintage_claim"] is False
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False


def test_v33_development_results_pass_cor1y() -> None:
    payload = json.loads(DEVELOPMENT_RESULTS.read_text())

    assert payload["schema_version"] == "research.v33.development_results.v1"
    assert payload["development_passer_count"] == 1
    assert payload["confirmation_open_eligible_candidates"] == ["cor1y_relief"]
    assert payload["recommendation"] == "commit_development_results_before_confirmation_open"
    by_key = {row["key"]: row for row in payload["candidates"]}
    assert by_key["cor1y_relief"]["classification"] == "development_pass_confirmation_open_eligible"
    assert by_key["cor1y_relief"]["reproducible"] is True
    assert by_key["cor1y_relief"]["base_net_pnl"] > 0.0
    assert by_key["cor1y_relief"]["leave_best_base_net_pnl"] > 0.0
    assert by_key["cor3m_relief"]["classification"] == "reject_candidate"
    assert by_key["cor6m_relief"]["classification"] == "reject_candidate"
    assert payload["boundaries"]["opens_confirmation"] is False

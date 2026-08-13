from __future__ import annotations

import json
from pathlib import Path

from apps.ops.research_protocol_v28 import load_and_validate

QUALIFICATION = Path("docs/progress/phase-2-research-v28-provider-qualification.json")


def test_v28_provider_qualification_rejects_all_three() -> None:
    validation = load_and_validate()
    payload = json.loads(QUALIFICATION.read_text())

    assert payload["protocol_sha256"] == validation["protocol_sha256"]
    assert payload["provider_contract_sha256"] == validation["provider_contract_sha256"]
    assert payload["qualified_candidates"] == []
    assert payload["classification"] == "blocked_provider_qualification"
    assert payload["rejected_candidates"] == {
        "options_notional_expansion": "development_reserve_only_414_observations",
        "options_premium_expansion": "development_reserve_only_414_observations",
        "open_interest_expansion": "development_reserve_only_675_observations",
    }
    assert payload["boundaries"]["signals_generated"] is False
    assert payload["boundaries"]["pnl_opened"] is False

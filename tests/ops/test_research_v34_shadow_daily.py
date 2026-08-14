from __future__ import annotations

from apps.ops.research_v34_shadow_daily import (
    CONTRACT_PATH,
    load_contract,
    summarize_attempts,
)


def test_v34_paper_shadow_contract_is_valid() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["schema_version"] == "research.v34.paper_shadow_contract.v1"
    assert contract["candidate"]["source"] == "rule_cboe_fvx_relief_v1"
    assert contract["candidate"]["model_version"] == "cboe-fvx-diff5-negative-lag1d-v1"
    assert contract["policy"]["dry_run"] is True
    assert contract["collection"]["schedule"] == "weekdays at 02:45 UTC"


def test_v34_summarize_attempts_evaluates_gate() -> None:
    records = [
        {"collection_date": "2026-08-14", "qualified_day": True, "blockers": [], "new_forward_signal_ids": ["sig1"]},
        {"collection_date": "2026-08-15", "qualified_day": True, "blockers": [], "new_forward_signal_ids": []},
    ]
    status = summarize_attempts(records, gate_days=7, gate_signals=50)
    assert status["qualified_day_count"] == 2
    assert status["new_forward_signal_count"] == 1
    assert status["threshold_met"] is False
    assert status["review_eligible"] is False

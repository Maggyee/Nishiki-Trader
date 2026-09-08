from __future__ import annotations

from apps.ops.research_v36_shadow_daily import (
    CONTRACT_PATH,
    load_contract,
    summarize_attempts,
)


def test_v36_paper_shadow_contract_is_valid() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["schema_version"] == "research.v36.paper_shadow_contract.v1"
    assert contract["candidate"]["source"] == "rule_cboe_vpn_expansion_v1"
    assert contract["candidate"]["model_version"] == "cboe-vpn-diff5-positive-lag1d-v1"
    assert contract["policy"]["dry_run"] is True
    assert contract["collection"]["schedule"] == "weekdays at 03:00 UTC"


def test_v36_summarize_attempts_evaluates_gate() -> None:
    records = [
        {"collection_date": "2026-08-14", "qualified_day": True, "blockers": [], "new_forward_signal_ids": ["sig1"]},
        {"collection_date": "2026-08-15", "qualified_day": True, "blockers": [], "new_forward_signal_ids": []},
    ]
    status = summarize_attempts(records, gate_days=7, gate_signals=50)
    assert status["qualified_day_count"] == 0
    assert status["legacy_attempt_count"] == 2
    for record in records:
        record["signal_pipeline_version"] = 2
    status = summarize_attempts(records, gate_days=7, gate_signals=50)
    assert status["qualified_day_count"] == 2
    assert status["new_forward_signal_count"] == 1
    assert status["threshold_met"] is False
    assert status["review_eligible"] is False

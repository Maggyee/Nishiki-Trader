"""Tests for the ADR-014 mechanism-family registry."""

from __future__ import annotations

from pathlib import Path

from apps.ops.research_family_registry import (
    FAMILIES,
    FAMILY_STATUSES,
    OUTCOMES,
    PROTOCOLS,
    build_registry,
    check_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_family_statuses_and_outcomes_are_valid() -> None:
    for family_id, meta in FAMILIES.items():
        assert meta["status"] in FAMILY_STATUSES, family_id
        assert meta["rationale"]
    for entry in PROTOCOLS:
        assert entry["family"] in FAMILIES
        for cand in entry["candidates"]:
            assert cand["outcome"] in OUTCOMES
            assert (cand["family"] or entry["family"]) in FAMILIES


def test_saturated_relief_family_is_declared() -> None:
    assert FAMILIES["external_index_relief"]["status"] == "saturated"


def test_registry_totals_are_consistent() -> None:
    registry = build_registry(REPO_ROOT)
    totals = registry["totals"]
    assert totals["protocol_count"] == len(PROTOCOLS)
    assert totals["survivors_paper_shadow"] == 10
    assert totals["unique_identities"] <= totals["candidate_rows"]
    assert totals["unique_identities_pnl_opened"] < totals["unique_identities"]
    survivor_models = {
        cand["model_version"]
        for proto in registry["protocols"]
        for cand in proto["candidates"]
        if cand["outcome"] == "confirmation_passed_paper_shadow"
    }
    # Roster from docs/progress/phase-2-research-portfolio-shadow-report.md.
    assert survivor_models == {
        "cboe-gvz5obs-negative-1d-v1",
        "treasury-nominal10-absdiff5-20-negative-lag2d-v1",
        "cboe-vxn-ohlc5obs-negative-1d-v1",
        "cboe-cor1m-diff5-negative-lag1d-v1",
        "cboe-fvx-diff5-negative-lag1d-v1",
        "cboe-vpn-diff5-positive-lag1d-v1",
        "cboe-vxn-diff5-negative-lag1d-v1",
        "cboe-vix6m-diff5-negative-lag1d-v1",
        "crypto-btc-prem-diff5-negative-lag1d-v1",
        "crypto-btc-basis-below-ma10-lag1d-v1",
    }


def test_registry_check_passes_against_committed_json() -> None:
    # This is the ADR-014 §3.5 enforcement hook: adding research_protocol_v49.py
    # without a PROTOCOLS entry (or without regenerating the JSON) fails here.
    assert check_registry(REPO_ROOT) == []

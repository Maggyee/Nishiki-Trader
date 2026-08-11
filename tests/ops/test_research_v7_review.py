from __future__ import annotations

from copy import deepcopy

from apps.ops.research_v7_review import classify_review


def _candidate(source: str, model: str) -> dict:
    monthly = []
    for year in (2020, 2021, 2022):
        for month in range(1, 13):
            monthly.append(
                {
                    "month": f"{year}-{month:02d}",
                    "scenarios": {"base": {"net_pnl": 1.0}, "stress": {"net_pnl": 0.8}},
                }
            )
    return {
        "label": source,
        "source": source,
        "model_version": model,
        "monthly_metrics": monthly,
        "scenario_metrics": {"base": {"net_pnl": 36.0}, "stress": {"net_pnl": 28.8}},
        "base_net_without_best_position": 20.0,
        "closed_positions": 40,
        "short_positions": 0,
        "run_count": 2,
        "reproducible": True,
        "blockers": [],
    }


def _alpha() -> dict:
    identities = [
        ("rule_equity_vol_relief_v3", "cboe-vix5obs-negative-1d-v1"),
        ("rule_energy_vol_relief_v1", "cboe-ovx5obs-negative-1d-v1"),
        ("rule_gold_vol_relief_v1", "cboe-gvz5obs-negative-1d-v1"),
    ]
    return {
        "schema_version": "alpha.review.v1",
        "candidates": [_candidate(*row) for row in identities],
    }


def test_v7_review_passes_only_complete_clean_evidence() -> None:
    result = classify_review(_alpha(), {"schema_version": "catalog.audit.v1", "passed": True})
    assert result["selected_candidate_count"] == 3
    assert all(
        row["classification"] == "replication_pass_pending_future_blind"
        for row in result["candidates"]
    )


def test_v7_review_hard_blocks_incomplete_execution_catalog() -> None:
    result = classify_review(_alpha(), {"schema_version": "catalog.audit.v1", "passed": False})
    assert result["selected_candidate_count"] == 0
    assert all(row["classification"] == "reject" for row in result["candidates"])
    assert all("execution_catalog_incomplete" in row["blockers"] for row in result["candidates"])


def test_v7_review_rejects_concentrated_candidate() -> None:
    alpha = deepcopy(_alpha())
    alpha["candidates"][0]["base_net_without_best_position"] = -1.0
    result = classify_review(alpha, {"schema_version": "catalog.audit.v1", "passed": True})
    assert result["candidates"][0]["classification"] == "reject"

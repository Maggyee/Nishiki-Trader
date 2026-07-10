from __future__ import annotations

import json
from pathlib import Path

from apps.ops.strategy_tournament import build_tournament


def _review(
    root: Path,
    index: int,
    *,
    base: float = 10.0,
    stress: float = 8.0,
    gross: float = 12.0,
    positions: int = 30,
    best_position: float = 1.0,
) -> Path:
    starts = ["2024-01-01", "2024-08-01", "2025-01-01", "2025-08-01"]
    ends = ["2024-05-31", "2024-12-31", "2025-05-31", "2025-12-31"]
    candidate = {
        "is_research_candidate": True,
        "source": "rule_mean_reversion_v1",
        "model_version": "model-v1",
        "scenario_metrics": {
            "gross": {"net_pnl": gross},
            "base": {"net_pnl": base},
            "stress": {"net_pnl": stress},
        },
        "best_position_base_net_pnl": best_position,
        "closed_positions": positions,
        "short_positions": 0,
        "blockers": [],
        "reproducible": True,
        "monthly_metrics": [
            {"month": f"m{month}", "scenarios": {"base": {"net_pnl": 1.0}}}
            for month in range(5)
        ],
    }
    payload = {
        "schema_version": "alpha.review.v1",
        "inputs": {"blind_start": starts[index], "blind_end": ends[index]},
        "candidates": [candidate],
    }
    path = root / f"review-{index}.json"
    path.write_text(json.dumps(payload))
    return path


def test_tournament_accepts_multi_asset_review_schema(tmp_path) -> None:
    entries = []
    for index in range(4):
        path = _review(tmp_path, index)
        payload = json.loads(path.read_text())
        payload["schema_version"] = "multi_asset.review.v1"
        path.write_text(json.dumps(payload))
        entries.append(("rotation", path))

    result = build_tournament(entries)

    assert result["strategies"][0]["classification"] == "development_pass"
    assert "multi_asset.review.v1" in result["protocol"]["accepted_review_schemas"]


def test_low_frequency_multi_asset_watchlist_can_only_add_historical_evidence(
    tmp_path,
) -> None:
    entries = []
    for index in range(4):
        path = _review(tmp_path, index, positions=4)
        payload = json.loads(path.read_text())
        payload["schema_version"] = "multi_asset.review.v1"
        path.write_text(json.dumps(payload))
        entries.append(("rotation", path))

    result = build_tournament(entries)

    assert result["strategies"][0]["classification"] == "development_watchlist"
    assert result["ranking"] == []
    assert result["development_watchlist_count"] == 1
    assert result["recommendation"] == "eligible_for_historical_evidence_only"


def test_tournament_passes_robust_four_fold_candidate(tmp_path) -> None:
    entries = [("mean_reversion", _review(tmp_path, index)) for index in range(4)]

    result = build_tournament(entries)

    strategy = result["strategies"][0]
    assert strategy["classification"] == "development_pass"
    assert strategy["gates"]["base_positive_months"] == 20
    assert strategy["gates"]["closed_positions"] == 120
    assert result["ranking"] == ["mean_reversion"]
    assert result["recommendation"] == "eligible_for_historical_validation"


def test_tournament_rejects_concentrated_or_unprofitable_candidate(tmp_path) -> None:
    entries = [
        (
            "mean_reversion",
            _review(
                tmp_path,
                index,
                base=1.0,
                stress=-1.0 if index < 2 else 1.0,
                best_position=5.0,
            ),
        )
        for index in range(4)
    ]

    result = build_tournament(entries)

    strategy = result["strategies"][0]
    assert strategy["classification"] == "reject"
    assert strategy["gates"]["stress_profitable_folds"] == 2
    assert strategy["gates"]["aggregate_base_without_best_position_positive"] is False
    assert result["ranking"] == []

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.ops.multi_asset_review import build_multi_asset_review

MONTHS = ["2024-08", "2024-09", "2024-10", "2024-11", "2024-12"]
METRIC_FIELDS = {
    "recorded_pnl": 2.0,
    "recorded_commission": 0.0,
    "modeled_fee": 0.5,
    "modeled_slippage": 0.1,
    "net_pnl": 1.4,
}


def _asset_review(
    root: Path,
    symbol: str,
    lineage: list[tuple[int, str]],
    *,
    source: str = "rule_relative_value_rotation_v1",
) -> Path:
    bundle = root / f"bundle-{symbol}"
    bundle.mkdir()
    pd.DataFrame(
        [
            {
                "source": source,
                "model_version": "model-v1",
                "ts_event": ts_event,
                "decision": decision,
            }
            for ts_event, decision in lineage
        ]
    ).to_parquet(bundle / "signal_lineage.parquet")
    candidate = {
        "source": source,
        "model_version": "model-v1",
        "is_research_candidate": True,
        "bundle_runs": [str(bundle), str(bundle)],
        "scenario_metrics": {
            scenario: dict(METRIC_FIELDS) for scenario in ("gross", "base", "stress")
        },
        "monthly_metrics": [
            {
                "month": month,
                "scenarios": {
                    scenario: dict(METRIC_FIELDS)
                    for scenario in ("gross", "base", "stress")
                },
            }
            for month in MONTHS
        ],
        "fills": 2,
        "closed_positions": 1,
        "short_positions": 0,
        "best_position_base_net_pnl": 0.8,
        "reproducible": True,
        "blockers": [],
    }
    report = {
        "schema_version": "alpha.review.v1",
        "inputs": {
            "blind_start": "2024-08-01",
            "blind_end": "2024-12-31",
            "expected_months": MONTHS,
            "trade_size": 0.001,
        },
        "candidates": [candidate],
    }
    path = root / f"review-{symbol}.json"
    path.write_text(json.dumps(report))
    return path


def test_combines_assets_and_accepts_same_timestamp_rotation(tmp_path) -> None:
    eth = _asset_review(
        tmp_path,
        "ETHUSDT",
        [(1, "target_long"), (2, "target_flat")],
    )
    btc = _asset_review(
        tmp_path,
        "BTCUSDT",
        [(1, "target_flat"), (2, "target_long")],
    )

    result = build_multi_asset_review(
        "relative_value",
        [("BTCUSDT", btc), ("ETHUSDT", eth)],
    )

    candidate = result["candidates"][0]
    assert result["schema_version"] == "multi_asset.review.v1"
    assert candidate["scenario_metrics"]["base"]["net_pnl"] == pytest.approx(2.8)
    assert candidate["closed_positions"] == 2
    assert candidate["base_net_without_best_position"] == pytest.approx(2.0)
    assert candidate["exclusivity"]["exclusive"] is True
    assert candidate["blockers"] == []
    assert result["recommendation"] == "portfolio_fold_ready"


def test_fails_closed_when_asset_positions_overlap(tmp_path) -> None:
    btc = _asset_review(tmp_path, "BTCUSDT", [(1, "target_long")])
    eth = _asset_review(tmp_path, "ETHUSDT", [(2, "target_long")])

    result = build_multi_asset_review(
        "relative_value",
        [("BTCUSDT", btc), ("ETHUSDT", eth)],
    )

    candidate = result["candidates"][0]
    assert candidate["exclusivity"]["exclusive"] is False
    assert "portfolio_asset_overlap" in candidate["blockers"]
    assert result["recommendation"] == "reject_portfolio_evidence"


def test_diversified_source_allows_three_concurrent_assets(tmp_path) -> None:
    source = "rule_alt_diversified_momentum_v1"
    specs = [
        (
            symbol,
            _asset_review(
                tmp_path,
                symbol,
                [(1, "target_long")],
                source=source,
            ),
        )
        for symbol in ("BNBUSDT", "XRPUSDT", "ADAUSDT")
    ]

    result = build_multi_asset_review("diversified", specs)

    candidate = result["candidates"][0]
    assert candidate["exclusivity"]["maximum_concurrent_assets"] == 3
    assert candidate["exclusivity"]["within_limit"] is True
    assert candidate["blockers"] == []

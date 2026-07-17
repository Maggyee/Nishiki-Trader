from __future__ import annotations

from copy import deepcopy

from apps.ops.research_v5_review import _evaluate_candidate
from apps.strategies_freqtrade.research.binance_mechanism_signals import (
    STRATEGY_IDENTITIES,
)


def _metric(net: float) -> dict[str, float]:
    return {
        "recorded_pnl": net,
        "recorded_commission": 0.0,
        "modeled_fee": 0.0,
        "modeled_slippage": 0.0,
        "net_pnl": net,
    }


def _fold(candidate: str, *, months: int = 5, positive_months: int = 5, positions: int = 10):
    source, model = STRATEGY_IDENTITIES[candidate]
    monthly = []
    for index in range(months):
        net = 1.0 if index < positive_months else -1.0
        monthly.append(
            {
                "month": f"2024-{index + 1:02d}",
                "scenarios": {
                    "gross": _metric(net),
                    "base": _metric(net),
                    "stress": _metric(net),
                },
            }
        )
    portfolio = {
        "source": source,
        "model_version": model,
        "scenario_metrics": {
            "gross": _metric(10.0),
            "base": _metric(8.0),
            "stress": _metric(7.0),
        },
        "monthly_metrics": monthly,
        "asset_cost_results": {
            asset: {
                "gross": _metric(5.0),
                "base": _metric(4.0),
                "stress": _metric(3.5),
            }
            for asset in ("BTCUSDT", "ETHUSDT")
        },
        "closed_positions": positions,
        "short_positions": 0,
        "best_position_base_net_pnl": 1.0,
        "reproducible": True,
        "blockers": [],
        "risk_metrics": {
            "base": {
                "net_pnl": 8.0,
                "max_drawdown_usdt": -2.0,
                "net_pnl_to_abs_max_drawdown": 4.0,
            }
        },
        "benchmark": {
            "risk_metrics": {
                "base": {
                    "net_pnl": 5.0,
                    "max_drawdown_usdt": -4.0,
                    "net_pnl_to_abs_max_drawdown": 1.25,
                }
            }
        },
    }
    return {"candidates": [portfolio]}


def test_curve_gate_requires_all_three_folds_and_at_least_nine_months() -> None:
    folds = [(f"fold-{index}", _fold("curve_carry", positive_months=3)) for index in range(3)]
    passed = _evaluate_candidate("curve_fast_track", "curve_carry", folds)
    assert passed["passed"] is True
    assert passed["recommendation"] == "replication_pass_pending_future_blind"

    failed_fold = deepcopy(folds)
    failed_fold[1][1]["candidates"][0]["scenario_metrics"]["stress"]["net_pnl"] = -0.1
    assert _evaluate_candidate("curve_fast_track", "curve_carry", failed_fold)["passed"] is False

    eight_months = [(f"fold-{index}", _fold("curve_carry", positive_months=3)) for index in range(3)]
    eight_months[-1][1]["candidates"][0]["monthly_metrics"][2]["scenarios"]["base"]["net_pnl"] = -1.0
    assert _evaluate_candidate("curve_fast_track", "curve_carry", eight_months)["passed"] is False


def test_bvol_gate_boundary_is_four_folds_and_fifteen_months() -> None:
    folds = [(f"fold-{index}", _fold("bvol_relief", positive_months=3, positions=6)) for index in range(5)]
    assert _evaluate_candidate("bvol_fast_track_diagnostic", "bvol_relief", folds)["passed"] is True

    fourteen = deepcopy(folds)
    fourteen[-1][1]["candidates"][0]["monthly_metrics"][2]["scenarios"]["base"]["net_pnl"] = -1.0
    assert _evaluate_candidate("bvol_fast_track_diagnostic", "bvol_relief", fourteen)["passed"] is False

    three_folds = deepcopy(folds)
    for index in (0, 1):
        three_folds[index][1]["candidates"][0]["scenario_metrics"]["base"]["net_pnl"] = -0.1
    assert _evaluate_candidate("bvol_fast_track_diagnostic", "bvol_relief", three_folds)["passed"] is False


def test_future_gate_boundaries_positions_months_leave_best_and_risk() -> None:
    fold = _fold("curve_carry", positive_months=4, positions=30)
    result = _evaluate_candidate(
        "final_future_blind",
        "curve_carry",
        [("future_2026_aug_dec", fold)],
    )
    assert result["passed"] is True
    assert result["recommendation"] == "eligible_for_paper_shadow_review"

    three_months = deepcopy(fold)
    three_months["candidates"][0]["monthly_metrics"][3]["scenarios"]["base"]["net_pnl"] = -1.0
    assert _evaluate_candidate("final_future_blind", "curve_carry", [("future", three_months)])["passed"] is False

    twenty_nine = deepcopy(fold)
    twenty_nine["candidates"][0]["closed_positions"] = 29
    small = _evaluate_candidate("final_future_blind", "curve_carry", [("future", twenty_nine)])
    assert small["passed"] is False
    assert small["recommendation"] == "insufficient_evidence"

    blocked_small = deepcopy(twenty_nine)
    blocked_small["candidates"][0]["blockers"] = ["invalid_fill_lineage"]
    blocked = _evaluate_candidate(
        "final_future_blind",
        "curve_carry",
        [("future", blocked_small)],
    )
    assert blocked["recommendation"] == "reject_v5_candidate"

    concentrated = deepcopy(fold)
    concentrated["candidates"][0]["best_position_base_net_pnl"] = 8.0
    assert _evaluate_candidate("final_future_blind", "curve_carry", [("future", concentrated)])["passed"] is False

    worse_drawdown = deepcopy(fold)
    worse_drawdown["candidates"][0]["risk_metrics"]["base"]["max_drawdown_usdt"] = -5.0
    assert _evaluate_candidate("final_future_blind", "curve_carry", [("future", worse_drawdown)])["passed"] is False

    subsidized = deepcopy(fold)
    subsidized["candidates"][0]["asset_cost_results"]["ETHUSDT"]["stress"]["net_pnl"] = -0.1
    assert _evaluate_candidate("final_future_blind", "curve_carry", [("future", subsidized)])["passed"] is False


def test_bvol_future_pass_still_requires_2027_confirmation() -> None:
    fold = _fold("bvol_relief", positive_months=4, positions=30)
    result = _evaluate_candidate(
        "final_future_blind",
        "bvol_relief",
        [("future_2026_aug_dec", fold)],
    )

    assert result["passed"] is True
    assert result["recommendation"] == "future_pass_pending_2027_confirmation"


def test_nonfinite_review_input_fails_closed() -> None:
    fold = _fold("curve_carry", positive_months=4, positions=30)
    fold["candidates"][0]["scenario_metrics"]["base"]["net_pnl"] = float("nan")

    result = _evaluate_candidate("final_future_blind", "curve_carry", [("future", fold)])
    assert result["passed"] is False

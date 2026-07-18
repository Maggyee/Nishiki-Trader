"""Build the passive, fail-closed ``research.v5.review.v1`` gate report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import SCENARIOS
from apps.strategies_freqtrade.research.binance_mechanism_signals import (
    ASSETS,
    STRATEGY_IDENTITIES,
)
from apps.strategies_nautilus.runners.backtest_runner import validate_sidecar_bundle

SCHEMA_VERSION = "research.v5.review.v1"
DATA_BLOCKER_SCHEMA_VERSION = "research.v5.data_blocker.v1"
PHASES = ("curve_fast_track", "bvol_fast_track_diagnostic", "final_future_blind")
EXPECTED_FOLDS = {
    "curve_fast_track": {
        "curve_2021_aug_dec": ("2021-08-01", "2021-12-31"),
        "curve_2022_jan_may": ("2022-01-01", "2022-05-31"),
        "curve_2022_aug_dec": ("2022-08-01", "2022-12-31"),
    },
    "bvol_fast_track_diagnostic": {
        "bvol_2023_aug_dec": ("2023-08-01", "2023-12-31"),
        "bvol_2024_jan_may": ("2024-01-01", "2024-05-31"),
        "bvol_2024_aug_dec": ("2024-08-01", "2024-12-31"),
        "bvol_2025_jan_may": ("2025-01-01", "2025-05-31"),
        "bvol_2025_aug_dec": ("2025-08-01", "2025-12-31"),
    },
    "final_future_blind": {
        "future_2026_aug_dec": ("2026-08-01", "2026-12-31"),
    },
}


def _strict_json(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r} is forbidden")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    _assert_finite(payload)
    return payload


def _assert_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite(child, f"{path}[{index}]")


def _expected_costs() -> list[dict[str, Any]]:
    return list(SCENARIOS)


def _validate_sidecars(report: dict[str, Any], path: Path) -> None:
    candidate = report["candidates"][0]
    assets = candidate.get("assets")
    if not isinstance(assets, list) or {row.get("symbol") for row in assets} != {
        "BTCUSDT",
        "ETHUSDT",
    }:
        raise ValueError(f"{path} must contain BTCUSDT and ETHUSDT evidence")
    for asset in assets:
        review_path = Path(str(asset.get("review_path", "")))
        alpha = _strict_json(review_path)
        if alpha.get("schema_version") != "alpha.review.v1":
            raise ValueError(f"{review_path} is not alpha.review.v1")
        candidates = [row for row in alpha.get("candidates", []) if row.get("is_research_candidate")]
        if len(candidates) != 1:
            raise ValueError(f"{review_path} must contain one research candidate")
        for bundle in candidates[0].get("bundle_runs", []):
            validate_sidecar_bundle(Path(str(bundle)))


def _load_fold(path: Path, *, expected_window: tuple[str, str]) -> dict[str, Any]:
    report = _strict_json(path)
    if report.get("schema_version") != "multi_asset.review.v1":
        raise ValueError(f"{path} is not multi_asset.review.v1")
    if report.get("cost_scenarios") != _expected_costs():
        raise ValueError(f"{path} cost scenarios differ from Protocol v5")
    if (
        report.get("inputs", {}).get("blind_start"),
        report.get("inputs", {}).get("blind_end"),
    ) != expected_window:
        raise ValueError(f"{path} fold window differs from Protocol v5")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError(f"{path} must contain exactly one portfolio candidate")
    candidate = candidates[0]
    if candidate.get("source") not in {identity[0] for identity in STRATEGY_IDENTITIES.values()}:
        raise ValueError(f"{path} has an unregistered v5 source")
    expected = next(
        identity
        for identity in STRATEGY_IDENTITIES.values()
        if identity[0] == candidate["source"]
    )
    if candidate.get("model_version") != expected[1]:
        raise ValueError(f"{path} model_version differs from Protocol v5")
    required_fields = {
        "scenario_metrics",
        "monthly_metrics",
        "asset_cost_results",
        "risk_metrics",
        "benchmark",
        "notional_audit",
        "exclusivity",
        "closed_positions",
        "short_positions",
        "best_position_base_net_pnl",
        "reproducible",
        "blockers",
    }
    missing = sorted(required_fields - set(candidate))
    if missing:
        raise ValueError(f"{path} candidate is missing v5 fields: {missing}")
    if candidate["notional_audit"].get("within_limit") is not True:
        raise ValueError(f"{path} initial notional audit failed")
    if candidate["exclusivity"].get("within_limit") is not True:
        raise ValueError(f"{path} concurrency audit failed")
    if candidate.get("reproducible") is not True:
        raise ValueError(f"{path} duplicate runs are not reproducible")
    _validate_sidecars(report, path)
    return report


def _sum_scenarios(folds: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    fields = (
        "recorded_pnl",
        "recorded_commission",
        "modeled_fee",
        "modeled_slippage",
        "net_pnl",
    )
    return {
        scenario["name"]: {
            field: sum(
                float(fold["candidates"][0]["scenario_metrics"][scenario["name"]][field])
                for fold in folds
            )
            for field in fields
        }
        for scenario in SCENARIOS
    }


def _sum_asset_costs(folds: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {
        asset: {
            scenario: sum(
                float(fold["candidates"][0]["asset_cost_results"][asset][scenario]["net_pnl"])
                for fold in folds
            )
            for scenario in ("gross", "base", "stress")
        }
        for asset in ("BTCUSDT", "ETHUSDT")
    }


def _candidate_key(source: str) -> str:
    for key, identity in STRATEGY_IDENTITIES.items():
        if identity[0] == source:
            return key
    raise ValueError(f"unknown v5 source {source!r}")


def _evaluate_candidate(
    phase: str,
    candidate_key: str,
    fold_rows: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    folds = [report for _name, report in fold_rows]
    portfolio = [report["candidates"][0] for report in folds]
    scenarios = _sum_scenarios(folds)
    asset_costs = _sum_asset_costs(folds)
    months = [row for candidate in portfolio for row in candidate["monthly_metrics"]]
    positive_months = sum(
        float(row["scenarios"]["base"]["net_pnl"]) > 0.0 for row in months
    )
    closed_positions = sum(int(candidate["closed_positions"]) for candidate in portfolio)
    short_positions = sum(int(candidate["short_positions"]) for candidate in portfolio)
    best = max(float(candidate["best_position_base_net_pnl"]) for candidate in portfolio)
    base_without_best = float(scenarios["base"]["net_pnl"]) - best
    blockers = sorted(
        {
            blocker
            for candidate in portfolio
            for blocker in candidate.get("blockers", [])
        }
    )
    if short_positions:
        blockers.append("short_position")
    fold_base_stress = [
        float(candidate["scenario_metrics"]["base"]["net_pnl"]) > 0.0
        and float(candidate["scenario_metrics"]["stress"]["net_pnl"]) > 0.0
        for candidate in portfolio
    ]
    gates: dict[str, Any] = {
        "aggregate_gross_positive": float(scenarios["gross"]["net_pnl"]) > 0.0,
        "aggregate_base_positive": float(scenarios["base"]["net_pnl"]) > 0.0,
        "aggregate_stress_positive": float(scenarios["stress"]["net_pnl"]) > 0.0,
        "base_positive_months": positive_months,
        "closed_positions": closed_positions,
        "closed_positions_at_least_30": closed_positions >= 30,
        "base_without_best_position": base_without_best,
        "base_without_best_position_positive": base_without_best > 0.0,
        "each_asset_base_and_stress_positive": all(
            asset_costs[asset][scenario] > 0.0
            for asset in asset_costs
            for scenario in ("base", "stress")
        ),
        "spot_long_flat_only": short_positions == 0,
        "evidence_clean": not blockers,
        "reproducible": all(candidate.get("reproducible") is True for candidate in portfolio),
    }
    if phase == "curve_fast_track":
        gates.update(
            {
                "every_fold_base_and_stress_positive": all(fold_base_stress),
                "base_positive_months_required": 9,
                "calendar_months_total": 15,
            }
        )
        passed_except_sample = bool(
            gates["aggregate_gross_positive"]
            and gates["aggregate_base_positive"]
            and gates["aggregate_stress_positive"]
            and gates["every_fold_base_and_stress_positive"]
            and positive_months >= 9
            and len(months) == 15
            and gates["each_asset_base_and_stress_positive"]
            and gates["base_without_best_position_positive"]
            and gates["spot_long_flat_only"]
            and gates["evidence_clean"]
            and gates["reproducible"]
        )
        passed = passed_except_sample and gates["closed_positions_at_least_30"]
    elif phase == "bvol_fast_track_diagnostic":
        positive_folds = sum(fold_base_stress)
        gates.update(
            {
                "positive_base_and_stress_folds": positive_folds,
                "positive_base_and_stress_folds_required": 4,
                "base_positive_months_required": 15,
                "calendar_months_total": 25,
                "diagnostic_only": True,
            }
        )
        passed_except_sample = bool(
            positive_folds >= 4
            and positive_months >= 15
            and len(months) == 25
            and gates["each_asset_base_and_stress_positive"]
            and gates["base_without_best_position_positive"]
            and gates["spot_long_flat_only"]
            and gates["evidence_clean"]
            and gates["reproducible"]
        )
        passed = passed_except_sample and gates["closed_positions_at_least_30"]
    else:
        candidate_risk = portfolio[0]["risk_metrics"]["base"]
        benchmark_risk = portfolio[0]["benchmark"]["risk_metrics"]["base"]
        candidate_drawdown = abs(float(candidate_risk["max_drawdown_usdt"]))
        benchmark_drawdown = abs(float(benchmark_risk["max_drawdown_usdt"]))
        drawdown_better = candidate_drawdown < benchmark_drawdown
        benchmark_net = float(benchmark_risk["net_pnl"])
        if benchmark_net > 0.0:
            candidate_ratio = candidate_risk.get("net_pnl_to_abs_max_drawdown")
            benchmark_ratio = benchmark_risk.get("net_pnl_to_abs_max_drawdown")
            ratio_better = (
                candidate_ratio is not None
                and benchmark_ratio is not None
                and float(candidate_ratio) > float(benchmark_ratio)
            )
        else:
            ratio_better = gates["aggregate_base_positive"] and drawdown_better
        gates.update(
            {
                "base_positive_months_required": 4,
                "calendar_months_total": 5,
                "candidate_max_drawdown_strictly_below_benchmark": drawdown_better,
                "candidate_return_drawdown_gate": ratio_better,
                "benchmark_base_net_pnl": benchmark_net,
            }
        )
        passed_except_sample = bool(
            gates["aggregate_base_positive"]
            and gates["aggregate_stress_positive"]
            and positive_months >= 4
            and len(months) == 5
            and gates["each_asset_base_and_stress_positive"]
            and gates["base_without_best_position_positive"]
            and gates["candidate_max_drawdown_strictly_below_benchmark"]
            and gates["candidate_return_drawdown_gate"]
            and gates["spot_long_flat_only"]
            and gates["evidence_clean"]
            and gates["reproducible"]
        )
        passed = passed_except_sample and gates["closed_positions_at_least_30"]

    profitable_but_small = passed_except_sample and closed_positions < 30
    if passed and phase == "final_future_blind" and candidate_key == "curve_carry":
        recommendation = "eligible_for_paper_shadow_review"
    elif passed and phase == "final_future_blind":
        recommendation = "future_pass_pending_2027_confirmation"
    elif passed:
        recommendation = "replication_pass_pending_future_blind"
    elif profitable_but_small:
        recommendation = "insufficient_evidence"
    else:
        recommendation = "reject_v5_candidate"
    source, model_version = STRATEGY_IDENTITIES[candidate_key]
    return {
        "candidate": candidate_key,
        "source": source,
        "model_version": model_version,
        "folds": [name for name, _report in fold_rows],
        "scenario_metrics": scenarios,
        "asset_cost_results": asset_costs,
        "monthly_metrics": months,
        "risk_metrics": portfolio[0]["risk_metrics"] if phase == "final_future_blind" else None,
        "benchmark": portfolio[0]["benchmark"] if phase == "final_future_blind" else None,
        "closed_positions": closed_positions,
        "best_position_base_net_pnl": best,
        "base_net_without_best_position": base_without_best,
        "blockers": blockers,
        "gates": gates,
        "passed": passed,
        "recommendation": recommendation,
    }


def build_research_v5_review(
    phase: str,
    fold_specs: list[tuple[str, str, Path]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}")
    today = as_of or datetime.now(UTC).date()
    if phase == "final_future_blind" and today < date(2027, 1, 1):
        raise ValueError("the 2026-08..12 future blind cannot be opened before 2027-01-01")
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    input_rows = []
    for candidate_key, fold_name, path in fold_specs:
        if candidate_key not in STRATEGY_IDENTITIES:
            raise ValueError(f"unknown candidate {candidate_key!r}")
        expected = EXPECTED_FOLDS[phase].get(fold_name)
        if expected is None:
            raise ValueError(f"unexpected {phase} fold {fold_name!r}")
        report = _load_fold(path, expected_window=expected)
        if _candidate_key(report["candidates"][0]["source"]) != candidate_key:
            raise ValueError(f"{path} candidate identity differs from its --fold key")
        grouped[candidate_key].append((fold_name, report))
        input_rows.append({"candidate": candidate_key, "fold": fold_name, "path": str(path)})
    if not grouped:
        raise ValueError("provide at least one --fold candidate:fold=path")
    for candidate_key, rows in grouped.items():
        if {name for name, _report in rows} != set(EXPECTED_FOLDS[phase]):
            raise ValueError(f"{candidate_key} does not provide every locked {phase} fold")
    if phase == "curve_fast_track" and set(grouped) != {"curve_carry"}:
        raise ValueError("curve_fast_track accepts only curve_carry")
    if phase == "bvol_fast_track_diagnostic" and set(grouped) != {"bvol_relief"}:
        raise ValueError("bvol_fast_track_diagnostic accepts only bvol_relief")

    candidates = [
        _evaluate_candidate(phase, key, sorted(rows, key=lambda item: item[0]))
        for key, rows in sorted(grouped.items())
    ]
    recommendations = {candidate["recommendation"] for candidate in candidates}
    if "eligible_for_paper_shadow_review" in recommendations:
        recommendation = "eligible_for_paper_shadow_review"
    elif "future_pass_pending_2027_confirmation" in recommendations:
        recommendation = "future_pass_pending_2027_confirmation"
    elif "replication_pass_pending_future_blind" in recommendations:
        recommendation = "replication_pass_pending_future_blind"
    elif recommendations == {"insufficient_evidence"}:
        recommendation = "insufficient_evidence"
    else:
        recommendation = "stop_before_testnet_resume"
    report = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {"phase": phase, "as_of": today.isoformat(), "fold_reports": input_rows},
        "data_contract": {
            "provider": "Binance",
            "credential_free": True,
            "immutable_vintages_required": True,
            "sidecars_revalidated": True,
            "point_in_time_required": True,
        },
        "cost_scenarios": _expected_costs(),
        "folds": {
            key: [name for name, _report in rows] for key, rows in sorted(grouped.items())
        },
        "candidates": candidates,
        "monthly_metrics": {
            candidate["candidate"]: candidate["monthly_metrics"] for candidate in candidates
        },
        "risk_metrics": {
            candidate["candidate"]: candidate["risk_metrics"] for candidate in candidates
        },
        "benchmark": {
            candidate["candidate"]: candidate["benchmark"] for candidate in candidates
        },
        "gates": {
            candidate["candidate"]: candidate["gates"] for candidate in candidates
        },
        "recommendation": recommendation,
        "boundaries": {
            "passive_review_only": True,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "calls_promotion_review": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "resumes_testnet": False,
            "touches_live_path": False,
        },
    }
    _assert_finite(report)
    return report


def build_data_blocked_research_v5_review(
    phase: str,
    candidate_key: str,
    evidence_path: Path,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Build a v5 rejection without opening PnL when a hard data gate fails."""

    if phase not in {"curve_fast_track", "bvol_fast_track_diagnostic"}:
        raise ValueError("data blockers are accepted only for historical fast tracks")
    expected_candidate = (
        "curve_carry" if phase == "curve_fast_track" else "bvol_relief"
    )
    if candidate_key != expected_candidate:
        raise ValueError(f"{phase} requires data blocker candidate {expected_candidate}")
    evidence_bytes = evidence_path.read_bytes()
    evidence = _strict_json(evidence_path)
    if evidence.get("schema_version") != DATA_BLOCKER_SCHEMA_VERSION:
        raise ValueError(f"{evidence_path} is not {DATA_BLOCKER_SCHEMA_VERSION}")
    if evidence.get("phase") != phase or evidence.get("candidate") != candidate_key:
        raise ValueError("data blocker evidence phase/candidate differs from the review")
    if evidence.get("pnl_opened") is not False or evidence.get("signals_generated") is not False:
        raise ValueError("data blocker evidence must precede signals and PnL")
    reason = evidence.get("reason_code")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("data blocker evidence requires a reason_code")
    observations = evidence.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("data blocker evidence requires observations")
    observed_assets: set[str] = set()
    observed_folds: set[str] = set()
    for index, row in enumerate(observations):
        if not isinstance(row, dict):
            raise ValueError(f"data blocker observation {index} must be an object")
        fold = row.get("fold")
        asset = row.get("asset")
        data_date = row.get("data_date")
        if fold not in EXPECTED_FOLDS[phase]:
            raise ValueError(f"data blocker observation {index} has an unlocked fold")
        if asset not in ASSETS:
            raise ValueError(f"data blocker observation {index} has an unlocked asset")
        try:
            observed_day = date.fromisoformat(str(data_date))
        except ValueError as exc:
            raise ValueError(
                f"data blocker observation {index} has an invalid data_date"
            ) from exc
        start, end = (date.fromisoformat(value) for value in EXPECTED_FOLDS[phase][fold])
        if not start <= observed_day <= end:
            raise ValueError(f"data blocker observation {index} falls outside its fold")
        if row.get("dataset") != "spot_execution":
            raise ValueError(f"data blocker observation {index} must identify spot_execution")
        if row.get("execution_window_usable") is not False:
            raise ValueError(f"data blocker observation {index} is not fail-closed")
        if not isinstance(row.get("error"), str) or not row["error"].strip():
            raise ValueError(f"data blocker observation {index} requires an error")
        observed_assets.add(str(asset))
        observed_folds.add(str(fold))
    if observed_assets != set(ASSETS):
        raise ValueError("data blocker evidence must cover both locked assets")

    source, model_version = STRATEGY_IDENTITIES[candidate_key]
    gates = {
        "data_available": False,
        "spot_execution_catalog_complete": False,
        "pnl_evaluated": False,
        "evidence_clean": False,
        "reproducible": None,
    }
    candidate = {
        "candidate": candidate_key,
        "source": source,
        "model_version": model_version,
        "folds": sorted(observed_folds),
        "scenario_metrics": None,
        "asset_cost_results": None,
        "monthly_metrics": [],
        "risk_metrics": None,
        "benchmark": None,
        "closed_positions": 0,
        "best_position_base_net_pnl": None,
        "base_net_without_best_position": None,
        "blockers": [reason],
        "gates": gates,
        "passed": False,
        "recommendation": "reject_v5_candidate",
    }
    today = as_of or datetime.now(UTC).date()
    report = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "phase": phase,
            "as_of": today.isoformat(),
            "fold_reports": [],
            "data_blocker_evidence": {
                "path": str(evidence_path),
                "sha256": f"sha256:{hashlib.sha256(evidence_bytes).hexdigest()}",
            },
        },
        "data_contract": {
            "provider": "Binance",
            "credential_free": True,
            "immutable_vintages_required": True,
            "sidecars_revalidated": False,
            "sidecars_required": False,
            "point_in_time_required": True,
            "pnl_evaluated": False,
        },
        "cost_scenarios": _expected_costs(),
        "folds": {candidate_key: sorted(observed_folds)},
        "candidates": [candidate],
        "monthly_metrics": {candidate_key: []},
        "risk_metrics": {candidate_key: None},
        "benchmark": {candidate_key: None},
        "gates": {candidate_key: gates},
        "recommendation": "stop_before_testnet_resume",
        "boundaries": {
            "passive_review_only": True,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "calls_promotion_review": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "resumes_testnet": False,
            "touches_live_path": False,
        },
    }
    _assert_finite(report)
    return report


def _parse_fold(value: str) -> tuple[str, str, Path]:
    identity, separator, path = value.partition("=")
    candidate, colon, fold = identity.partition(":")
    if not separator or not colon or not candidate or not fold or not path:
        raise argparse.ArgumentTypeError("fold must be candidate:fold=multi_asset_review.json")
    return candidate, fold, Path(path)


def _parse_data_blocker(value: str) -> tuple[str, Path]:
    candidate, separator, path = value.partition("=")
    if not separator or not candidate or not path:
        raise argparse.ArgumentTypeError("data blocker must be candidate=evidence.json")
    return candidate, Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--fold", action="append", type=_parse_fold, default=[])
    parser.add_argument("--data-blocker", type=_parse_data_blocker)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.data_blocker is not None:
            if args.fold:
                raise ValueError("--data-blocker cannot be combined with --fold")
            candidate, evidence_path = args.data_blocker
            report = build_data_blocked_research_v5_review(
                args.phase,
                candidate,
                evidence_path,
            )
        else:
            report = build_research_v5_review(args.phase, args.fold)
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

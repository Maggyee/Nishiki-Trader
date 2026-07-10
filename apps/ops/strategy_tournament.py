"""Aggregate four strict alpha.review.v1 folds into a passive strategy tournament."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "strategy.tournament.v1"
EXPECTED_FOLDS = 4
REQUIRED_PROFITABLE_FOLDS = 3
REQUIRED_POSITIVE_MONTHS = 12
REQUIRED_POSITIONS = 120


def _strict_load(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
    if not isinstance(payload, dict) or payload.get("schema_version") != "alpha.review.v1":
        raise ValueError(f"{path} is not alpha.review.v1")
    _assert_finite(payload)
    return payload


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)


def build_tournament(entries: list[tuple[str, Path]]) -> dict[str, Any]:
    grouped: dict[str, list[tuple[Path, dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for label, path in entries:
        report = _strict_load(path)
        candidates = [
            candidate
            for candidate in report.get("candidates", [])
            if candidate.get("is_research_candidate")
        ]
        if len(candidates) != 1:
            raise ValueError(f"{path} must contain exactly one research candidate")
        grouped[label].append((path, report, candidates[0]))
    if not grouped:
        raise ValueError("provide at least one strategy=alpha_review.json entry")

    strategies = []
    for label, folds in sorted(grouped.items()):
        if len(folds) != EXPECTED_FOLDS:
            raise ValueError(f"{label} requires exactly {EXPECTED_FOLDS} folds")
        sources = {fold[2]["source"] for fold in folds}
        models = {fold[2]["model_version"] for fold in folds}
        windows = {
            (fold[1]["inputs"]["blind_start"], fold[1]["inputs"]["blind_end"])
            for fold in folds
        }
        if len(sources) != 1 or len(models) != 1 or len(windows) != EXPECTED_FOLDS:
            raise ValueError(f"{label} has inconsistent identity or duplicate windows")

        scenario_totals = {
            scenario: sum(
                float(fold[2]["scenario_metrics"][scenario]["net_pnl"]) for fold in folds
            )
            for scenario in ("gross", "base", "stress")
        }
        fold_base = [float(fold[2]["scenario_metrics"]["base"]["net_pnl"]) for fold in folds]
        fold_stress = [
            float(fold[2]["scenario_metrics"]["stress"]["net_pnl"]) for fold in folds
        ]
        best_position = max(float(fold[2]["best_position_base_net_pnl"]) for fold in folds)
        positions = sum(int(fold[2]["closed_positions"]) for fold in folds)
        positive_months = sum(
            1
            for fold in folds
            for month in fold[2]["monthly_metrics"]
            if float(month["scenarios"]["base"]["net_pnl"]) > 0.0
        )
        evidence_clean = all(
            not fold[2].get("blockers")
            and fold[2].get("reproducible") is True
            and int(fold[2].get("short_positions", 0)) == 0
            for fold in folds
        )
        gates = {
            "aggregate_gross_positive": scenario_totals["gross"] > 0.0,
            "aggregate_base_positive": scenario_totals["base"] > 0.0,
            "aggregate_stress_positive": scenario_totals["stress"] > 0.0,
            "base_profitable_folds": sum(value > 0.0 for value in fold_base),
            "stress_profitable_folds": sum(value > 0.0 for value in fold_stress),
            "profitable_folds_required": REQUIRED_PROFITABLE_FOLDS,
            "base_positive_months": positive_months,
            "base_positive_months_required": REQUIRED_POSITIVE_MONTHS,
            "closed_positions": positions,
            "closed_positions_required": REQUIRED_POSITIONS,
            "aggregate_base_without_best_position": scenario_totals["base"]
            - best_position,
            "aggregate_base_without_best_position_positive": scenario_totals["base"]
            - best_position
            > 0.0,
            "evidence_clean_reproducible_spot_only": evidence_clean,
        }
        economic_pass = bool(
            gates["aggregate_gross_positive"]
            and gates["aggregate_base_positive"]
            and gates["aggregate_stress_positive"]
            and gates["base_profitable_folds"] >= REQUIRED_PROFITABLE_FOLDS
            and gates["stress_profitable_folds"] >= REQUIRED_PROFITABLE_FOLDS
            and positive_months >= REQUIRED_POSITIVE_MONTHS
            and gates["aggregate_base_without_best_position_positive"]
            and evidence_clean
        )
        development_pass = economic_pass and positions >= REQUIRED_POSITIONS
        classification = (
            "development_pass"
            if development_pass
            else "insufficient_evidence"
            if economic_pass
            else "reject"
        )
        strategies.append(
            {
                "label": label,
                "source": next(iter(sources)),
                "model_version": next(iter(models)),
                "folds": [
                    {
                        "path": str(path),
                        "start": report["inputs"]["blind_start"],
                        "end": report["inputs"]["blind_end"],
                        "base_net_pnl": candidate["scenario_metrics"]["base"]["net_pnl"],
                        "stress_net_pnl": candidate["scenario_metrics"]["stress"]["net_pnl"],
                        "closed_positions": candidate["closed_positions"],
                    }
                    for path, report, candidate in folds
                ],
                "scenario_totals": scenario_totals,
                "minimum_fold_base_net_pnl": min(fold_base),
                "best_position_base_net_pnl": best_position,
                "gates": gates,
                "classification": classification,
            }
        )

    passers = [strategy for strategy in strategies if strategy["classification"] == "development_pass"]
    ranking = [
        strategy["label"]
        for strategy in sorted(
            passers,
            key=lambda strategy: (
                strategy["minimum_fold_base_net_pnl"],
                strategy["scenario_totals"]["stress"],
                strategy["gates"]["base_positive_months"],
            ),
            reverse=True,
        )
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol": {
            "expected_folds": EXPECTED_FOLDS,
            "required_profitable_folds": REQUIRED_PROFITABLE_FOLDS,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "required_positions": REQUIRED_POSITIONS,
            "parameter_search": False,
        },
        "strategies": strategies,
        "ranking": ranking,
        "development_pass_count": len(passers),
        "recommendation": (
            "eligible_for_historical_validation" if passers else "no_candidate_progresses"
        ),
        "boundaries": {
            "diagnostic_only": True,
            "writes_signal_event": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "starts_nautilus": False,
            "resumes_testnet": False,
        },
    }


def _parse_entry(value: str) -> tuple[str, Path]:
    label, separator, path = value.partition("=")
    if not separator or not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError("entry must be strategy=alpha_review.json")
    return label.strip(), Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", action="append", type=_parse_entry, default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(build_tournament(args.entry), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

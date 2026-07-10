"""Validate the cumulative research-candidate registry and enforce its stop rule."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.program.review.v1"
REGISTRY_SCHEMA_VERSION = "research.candidate.registry.v1"
CLASSIFICATIONS = {"reject", "development_watchlist", "development_pass"}


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("registry contains non-finite numeric value")
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)


def build_research_program_review(registry_path: Path, *, repo_root: Path) -> dict[str, Any]:
    payload = json.loads(
        registry_path.read_text(),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
    if not isinstance(payload, dict) or payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(f"{registry_path} is not {REGISTRY_SCHEMA_VERSION}")
    _assert_finite(payload)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("registry must contain candidates")
    identities = []
    missing_evidence = []
    for candidate in candidates:
        required = {
            "family",
            "source",
            "model_version",
            "classification",
            "base_net_pnl",
            "stress_net_pnl",
            "closed_positions",
            "evidence_path",
            "failure_reasons",
        }
        if not isinstance(candidate, dict) or not required <= set(candidate):
            raise ValueError("candidate registry row is incomplete")
        identity = (candidate["source"], candidate["model_version"])
        identities.append(identity)
        if candidate["classification"] not in CLASSIFICATIONS:
            raise ValueError(f"invalid classification for {identity}")
        if int(candidate["closed_positions"]) < 0:
            raise ValueError(f"negative positions for {identity}")
        evidence = repo_root / str(candidate["evidence_path"])
        if not evidence.is_file():
            missing_evidence.append(str(candidate["evidence_path"]))
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate source/model identity in registry")
    if missing_evidence:
        raise ValueError(f"missing evidence files: {missing_evidence}")

    classifications = Counter(str(row["classification"]) for row in candidates)
    families = Counter(str(row["family"]) for row in candidates)
    passers = [row for row in candidates if row["classification"] == "development_pass"]
    watchlist = [
        row for row in candidates if row["classification"] == "development_watchlist"
    ]
    stop_rule = bool(not passers and not watchlist)
    return {
        "schema_version": SCHEMA_VERSION,
        "registry": str(registry_path),
        "candidate_count": len(candidates),
        "family_count": len(families),
        "families": dict(sorted(families.items())),
        "classifications": dict(sorted(classifications.items())),
        "development_passers": [f"{row['source']} / {row['model_version']}" for row in passers],
        "development_watchlist": [
            f"{row['source']} / {row['model_version']}" for row in watchlist
        ],
        "stop_rule": {
            "triggered": stop_rule,
            "reason": (
                "no_registered_candidate_passed_or_reached_watchlist"
                if stop_rule
                else "candidate_requires_next_registered_evidence_stage"
            ),
            "prohibits": [
                "opened_sample_parameter_tuning",
                "pnl_selected_ensemble_weighting",
                "holdout_consumption_for_rejected_models",
                "testnet_resume",
            ],
        },
        "recommendation": (
            "pause_new_candidate_generation_until_independent_evidence"
            if stop_rule
            else "continue_only_registered_validation"
        ),
        "boundaries": {
            "read_only": True,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "mutates_source_policy": False,
            "loads_credentials": False,
            "resumes_testnet": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_research_program_review(args.registry, repo_root=args.repo_root)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

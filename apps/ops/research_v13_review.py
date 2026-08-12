"""Apply the frozen Protocol v13 gates to duplicate development bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v13 import IDENTITIES, load_and_validate
from apps.ops.research_v9_review import (
    STEP_NS,
    _effective_bundle_blockers,
    _event_timestamps,
    _months,
    _verified_gap_timestamps,
)

SCHEMA_VERSION = "research.v13.development_results.v1"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _classification(
    *, performance_pass: bool, evidence_pass: bool, base: float, stress: float, positions: int
) -> str:
    if performance_pass and evidence_pass:
        return "development_pass_confirmation_open_eligible"
    if evidence_pass and base > 0.0 and stress > 0.0 and positions < 30:
        return "insufficient_evidence"
    return "reject_candidate"


def build_standard_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    identities: dict[str, tuple[str, str]],
    load_protocol: Any,
    protocol_version: str,
    schema_version: str,
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    gap_detail_bytes: bytes,
) -> dict[str, Any]:
    protocol = load_protocol()
    verified_hours = _verified_gap_timestamps(
        downtime_results, gap_detail, gap_detail_bytes=gap_detail_bytes
    )
    grouped: dict[str, list[Path]] = defaultdict(list)
    for candidate, path in candidate_specs:
        if candidate not in identities:
            raise ValueError(f"unsupported Protocol {protocol_version} candidate {candidate!r}")
        grouped[candidate].append(path)
    if set(grouped) != set(identities):
        raise ValueError(f"Protocol {protocol_version} review requires all three candidates")
    if any(len(paths) != 2 for paths in grouped.values()):
        raise ValueError(f"Protocol {protocol_version} requires exactly two runs per candidate")

    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 1, tzinfo=UTC)
    candidates: list[dict[str, Any]] = []
    for candidate in identities:
        paths = grouped[candidate]
        runs = [
            _analyze_bundle(
                path,
                start_ns=int(start.timestamp() * 1_000_000_000),
                end_exclusive_ns=int(end.timestamp() * 1_000_000_000),
                months=_months(2020, 2022),
                bar_interval_ns=STEP_NS,
            )
            for path in paths
        ]
        primary = runs[0]
        identity = (primary["source"], primary["model_version"])
        if identity != identities[candidate]:
            raise ValueError(f"Protocol {protocol_version} {candidate} bundle identity drifted")
        if len(primary["monthly_metrics"]) != 36:
            raise ValueError(f"Protocol {protocol_version} {candidate} must contain 36 months")
        yearly = {"2020": 0.0, "2021": 0.0, "2022": 0.0}
        positive_months = 0
        for row in primary["monthly_metrics"]:
            base = float(row["scenarios"]["base"]["net_pnl"])
            yearly[str(row["month"])[:4]] += base
            positive_months += int(base > 0.0)
        scenario = primary["scenario_metrics"]
        gross = float(scenario["gross"]["net_pnl"])
        base = float(scenario["base"]["net_pnl"])
        stress = float(scenario["stress"]["net_pnl"])
        leave_best = float(primary["base_net_without_best_position"])
        effective_blockers = _effective_bundle_blockers(
            list(primary["blockers"]), verified_gap_count=len(verified_hours)
        )
        reproducible = _runs_reproducible(runs)
        event_hits = sorted(
            verified_hours.intersection(
                timestamp for path in paths for timestamp in _event_timestamps(path)
            )
        )
        positive_years = sum(value > 0.0 for value in yearly.values())
        positions = int(primary["closed_positions"])
        performance_pass = bool(
            base > 0.0
            and stress > 0.0
            and positive_years >= 2
            and positive_months >= 18
            and positions >= 30
            and leave_best > 0.0
        )
        evidence_pass = bool(
            int(primary["short_positions"]) == 0
            and reproducible
            and not event_hits
            and not effective_blockers
        )
        failures: list[str] = []
        if base <= 0.0:
            failures.append("base_net_pnl_not_positive")
        if stress <= 0.0:
            failures.append("stress_net_pnl_not_positive")
        if positive_years < 2:
            failures.append(f"positive_years_{positive_years}_below_2")
        if positive_months < 18:
            failures.append(f"positive_months_{positive_months}_below_18")
        if positions < 30:
            failures.append(f"closed_positions_{positions}_below_30")
        if leave_best <= 0.0:
            failures.append("leave_best_base_net_pnl_not_positive")
        if not evidence_pass:
            failures.append("evidence_gate_failed")
        manifest = json.loads((paths[0] / "run_manifest.json").read_text())
        candidates.append(
            {
                "key": candidate,
                "source": identity[0],
                "model_version": identity[1],
                "signal_count": int(manifest["signal_source"]["row_count"]),
                "gross_net_pnl": gross,
                "base_net_pnl": base,
                "stress_net_pnl": stress,
                "positive_years": positive_years,
                "yearly_base_net_pnl": yearly,
                "positive_months": positive_months,
                "calendar_months": 36,
                "closed_positions": positions,
                "leave_best_base_net_pnl": leave_best,
                "duplicate_replays": 2,
                "reproducible": reproducible,
                "short_positions": int(primary["short_positions"]),
                "verified_no_kline_event_hits": event_hits,
                "effective_blockers": effective_blockers,
                "performance_pass": performance_pass,
                "evidence_pass": evidence_pass,
                "failure_reasons": failures,
                "classification": _classification(
                    performance_pass=performance_pass,
                    evidence_pass=evidence_pass,
                    base=base,
                    stress=stress,
                    positions=positions,
                ),
                "signal_store_sha256": f"sha256:{manifest['signal_source']['store_sha256']}",
                "bundle_runs": [
                    {
                        "path": str(path),
                        "manifest_sha256": _sha256(path / "run_manifest.json"),
                        "fills_sha256": _sha256(path / "fills.parquet"),
                    }
                    for path in paths
                ],
            }
        )
    passers = [
        row["key"]
        for row in candidates
        if row["classification"] == "development_pass_confirmation_open_eligible"
    ]
    return {
        "schema_version": schema_version,
        "protocol_sha256": protocol["protocol_sha256"],
        "candidates": candidates,
        "development_passer_count": len(passers),
        "confirmation_open_eligible_candidates": passers,
        "recommendation": "commit_development_results_before_confirmation_open"
        if passers
        else f"stop_protocol_{protocol_version}_no_confirmation_open",
        "confirmation_holdout_status": "sealed_pending_committed_development_review"
        if passers
        else "sealed_not_opened_no_development_passer",
        "future_blind_status": "sealed_unopened",
        "boundaries": {
            "mutates_source_policy": False,
            "resumes_testnet": False,
            "loads_credentials": False,
            "touches_live_path": False,
            "opens_confirmation": False,
            "opens_future_blind": False,
        },
    }


def build_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    gap_detail_bytes: bytes,
) -> dict[str, Any]:
    return build_standard_review(
        candidate_specs,
        identities=IDENTITIES,
        load_protocol=load_and_validate,
        protocol_version="v13",
        schema_version=SCHEMA_VERSION,
        downtime_results=downtime_results,
        gap_detail=gap_detail,
        gap_detail_bytes=gap_detail_bytes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", required=True, help="key=bundle")
    parser.add_argument("--downtime-results", type=Path, required=True)
    parser.add_argument("--gap-detail", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    specs: list[tuple[str, Path]] = []
    for value in args.candidate:
        if "=" not in value:
            parser.error("--candidate must use key=bundle")
        key, path = value.split("=", 1)
        specs.append((key, Path(path)))
    gap_bytes = args.gap_detail.read_bytes()
    result = build_review(
        specs,
        downtime_results=json.loads(args.downtime_results.read_text()),
        gap_detail=json.loads(gap_bytes),
        gap_detail_bytes=gap_bytes,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

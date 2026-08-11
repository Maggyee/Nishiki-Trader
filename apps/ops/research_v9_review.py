"""Apply the frozen Protocol v9 gates to duplicate development bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from apps.ops.alpha_review import _analyze_bundle, _runs_reproducible
from apps.ops.research_protocol_v9 import load_and_validate
from apps.strategies_freqtrade.research.option_risk_signals import IDENTITIES, load_sources

SCHEMA_VERSION = "research.v9.development_review.v1"
STEP_NS = 3_600_000_000_000


def _months(start_year: int, end_year: int) -> list[str]:
    current = datetime(start_year, 1, 1, tzinfo=UTC)
    end = datetime(end_year + 1, 1, 1, tzinfo=UTC)
    values: list[str] = []
    while current < end:
        values.append(current.strftime("%Y-%m"))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return values


def _event_timestamps(bundle: Path) -> set[int]:
    timestamps: set[int] = set()
    for filename, column in (("orders.parquet", "ts_init"), ("fills.parquet", "ts_event")):
        table = pq.read_table(bundle / filename, columns=[column])
        timestamps.update(int(value) for value in table[column].to_pylist())
    return timestamps


def _verified_gap_timestamps(
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    *,
    gap_detail_bytes: bytes,
) -> set[int]:
    if downtime_results.get("schema_version") != "research.v7.downtime_sensitivity_results.v1":
        raise ValueError("Protocol v9 downtime result schema drifted")
    provider = downtime_results.get("provider_audit", {})
    if provider.get("monthly_archive_checksum_matches") != 36:
        raise ValueError("Protocol v9 requires all 36 development archive checksums")
    if provider.get("gap_windows_checked_with_official_rest") != 14 or provider.get(
        "gap_windows_empty_in_official_rest"
    ) != 14:
        raise ValueError("Protocol v9 requires all development gaps verified REST-empty")
    expected_hash = downtime_results.get("sensitivity_catalog", {}).get(
        "build_report_sha256"
    )
    if expected_hash != f"sha256:{hashlib.sha256(gap_detail_bytes).hexdigest()}":
        raise ValueError("Protocol v9 gap-detail fingerprint mismatch")
    if gap_detail.get("official_rows") != 26_274 or gap_detail.get("synthetic_marker_rows") != 30:
        raise ValueError("Protocol v9 gap-detail row accounting drifted")
    timestamps = {
        int(timestamp)
        for gap in gap_detail.get("gaps", [])
        for timestamp in gap.get("synthetic_marker_timestamps_ns", [])
    }
    if len(timestamps) != 30:
        raise ValueError("Protocol v9 requires exactly 30 verified no-kline hours")
    return timestamps


def _effective_bundle_blockers(raw: list[str], *, verified_gap_count: int) -> list[str]:
    if verified_gap_count != 30:
        return list(raw)
    explained = "catalog_rows=26274!=expected=26304"
    return [blocker for blocker in raw if blocker != explained]


def build_review(
    candidate_specs: list[tuple[str, Path]],
    *,
    downtime_results: dict[str, Any],
    gap_detail: dict[str, Any],
    gap_detail_bytes: bytes,
) -> dict[str, Any]:
    protocol = load_and_validate()
    load_sources()
    verified_hours = _verified_gap_timestamps(
        downtime_results, gap_detail, gap_detail_bytes=gap_detail_bytes
    )
    grouped: dict[str, list[Path]] = defaultdict(list)
    for candidate, path in candidate_specs:
        if candidate not in IDENTITIES:
            raise ValueError(f"unsupported Protocol v9 candidate {candidate!r}")
        grouped[candidate].append(path)
    if set(grouped) != set(IDENTITIES):
        raise ValueError("Protocol v9 development review requires both locked candidates")

    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2023, 1, 1, tzinfo=UTC)
    candidates: list[dict[str, Any]] = []
    for candidate in IDENTITIES:
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
        if not runs:
            raise ValueError(f"Protocol v9 candidate {candidate} has no bundles")
        primary = runs[0]
        identity = (primary.get("source"), primary.get("model_version"))
        if identity != IDENTITIES[candidate]:
            raise ValueError(f"Protocol v9 candidate {candidate} bundle identity drifted")
        if len(primary.get("monthly_metrics", [])) != 36:
            raise ValueError(f"Protocol v9 candidate {candidate} must contain 36 months")
        yearly: dict[str, float] = {"2020": 0.0, "2021": 0.0, "2022": 0.0}
        positive_months = 0
        for row in primary["monthly_metrics"]:
            base = float(row["scenarios"]["base"]["net_pnl"])
            yearly[str(row["month"])[:4]] += base
            positive_months += int(base > 0.0)
        scenario = primary["scenario_metrics"]
        base_net = float(scenario["base"]["net_pnl"])
        stress_net = float(scenario["stress"]["net_pnl"])
        leave_best = float(primary["base_net_without_best_position"])
        raw_blockers = list(primary.get("blockers", []))
        effective_blockers = _effective_bundle_blockers(
            raw_blockers, verified_gap_count=len(verified_hours)
        )
        reproducible = len(runs) >= 2 and _runs_reproducible(runs)
        event_hits = sorted(
            verified_hours.intersection(
                timestamp for path in paths for timestamp in _event_timestamps(path)
            )
        )
        positive_years = sum(value > 0.0 for value in yearly.values())
        gates = {
            "base_net_positive": base_net > 0.0,
            "stress_net_positive": stress_net > 0.0,
            "positive_years": positive_years,
            "positive_years_required": 2,
            "positive_months": positive_months,
            "positive_months_required": 18,
            "closed_positions": int(primary["closed_positions"]),
            "closed_positions_required": 30,
            "leave_best_base_net_pnl": leave_best,
            "leave_best_base_net_pnl_positive": leave_best > 0.0,
            "short_positions": int(primary["short_positions"]),
            "duplicate_runs": len(runs),
            "duplicate_runs_required": 2,
            "reproducible": reproducible,
            "verified_exchange_no_kline_hours": len(verified_hours),
            "orders_or_fills_in_verified_no_kline_hours": event_hits,
        }
        performance_pass = bool(
            gates["base_net_positive"]
            and gates["stress_net_positive"]
            and positive_years >= 2
            and positive_months >= 18
            and gates["closed_positions"] >= 30
            and gates["leave_best_base_net_pnl_positive"]
        )
        evidence_pass = bool(
            gates["short_positions"] == 0
            and len(runs) >= 2
            and reproducible
            and not event_hits
            and not effective_blockers
        )
        candidates.append(
            {
                "key": candidate,
                "source": identity[0],
                "model_version": identity[1],
                "bundle_runs": [str(path) for path in paths],
                "scenario_metrics": scenario,
                "yearly_base_net_pnl": yearly,
                "monthly_metrics": primary["monthly_metrics"],
                "gates": gates,
                "raw_bundle_blockers": raw_blockers,
                "effective_bundle_blockers": effective_blockers,
                "performance_pass": performance_pass,
                "evidence_pass": evidence_pass,
                "classification": "development_pass_confirmation_open_eligible"
                if performance_pass and evidence_pass
                else "reject_candidate",
            }
        )
    passers = [
        row for row in candidates if row["classification"] == "development_pass_confirmation_open_eligible"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": protocol["protocol_sha256"],
        "candidates": candidates,
        "development_passer_count": len(passers),
        "confirmation_open_eligible_candidates": [row["key"] for row in passers],
        "recommendation": "commit_development_results_before_confirmation_open"
        if passers
        else "stop_protocol_v9_no_confirmation_open",
        "confirmation_holdout_status": "sealed_pending_committed_development_review",
        "future_blind_status": "sealed_unopened",
        "boundaries": {
            "mutates_source_policy": False,
            "resumes_testnet": False,
            "loads_credentials": False,
            "touches_live_path": False,
            "opens_future_blind": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", required=True, help="key=bundle")
    parser.add_argument("--downtime-results", type=Path, required=True)
    parser.add_argument("--gap-detail", type=Path, required=True)
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
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Review paired multi-day Research Protocol v2 snapshots without prices, returns, or PnL."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_v2_snapshot import verify_snapshot

SCHEMA_VERSION = "research.snapshot.coverage.v1"
REQUIRED_KINDS = ("options", "basis")
MIN_CONTIGUOUS_DAYS = 7


def _missing_dates(dates: list[date]) -> list[str]:
    if len(dates) < 2:
        return []
    present = set(dates)
    current = dates[0]
    missing: list[str] = []
    while current <= dates[-1]:
        if current not in present:
            missing.append(current.isoformat())
        current += timedelta(days=1)
    return missing


def review_snapshots(snapshot_paths: list[Path]) -> dict[str, Any]:
    if not snapshot_paths:
        raise ValueError("at least one snapshot is required")
    records: list[dict[str, Any]] = []
    by_kind_day: dict[str, dict[date, list[dict[str, Any]]]] = {
        kind: defaultdict(list) for kind in REQUIRED_KINDS
    }
    for path in snapshot_paths:
        review = verify_snapshot(path)
        kind = str(review["kind"])
        if kind not in REQUIRED_KINDS:
            raise ValueError(f"coverage review does not accept {kind} snapshots")
        retrieved_day = date.fromisoformat(str(review["retrieved_at"])[:10])
        record = {
            "kind": kind,
            "retrieved_day": retrieved_day.isoformat(),
            "path": str(path),
            "snapshot_sha256": review["snapshot_sha256"],
            "audit": review["audit"],
        }
        records.append(record)
        by_kind_day[kind][retrieved_day].append(record)

    blockers: list[str] = []
    coverage: dict[str, Any] = {}
    date_sets: dict[str, set[date]] = {}
    for kind in REQUIRED_KINDS:
        days = sorted(by_kind_day[kind])
        date_sets[kind] = set(days)
        duplicates = sorted(
            day.isoformat() for day, values in by_kind_day[kind].items() if len(values) != 1
        )
        missing = _missing_dates(days)
        if not days:
            blockers.append(f"missing_kind:{kind}")
        if duplicates:
            blockers.append(f"duplicate_days:{kind}")
        if missing:
            blockers.append(f"internal_gaps:{kind}")
        coverage[kind] = {
            "snapshot_count": sum(len(values) for values in by_kind_day[kind].values()),
            "unique_day_count": len(days),
            "first_day": days[0].isoformat() if days else None,
            "last_day": days[-1].isoformat() if days else None,
            "dates": [day.isoformat() for day in days],
            "duplicate_dates": duplicates,
            "missing_dates": missing,
        }

    mismatch = sorted(
        day.isoformat() for day in date_sets["options"] ^ date_sets["basis"]
    )
    if mismatch:
        blockers.append("unpaired_dates")
    paired_days = sorted(date_sets["options"] & date_sets["basis"])
    enough_days = len(paired_days) >= MIN_CONTIGUOUS_DAYS
    if blockers:
        status = "blocked_invalid_coverage"
        recommendation = "repair_snapshot_collection_without_opening_pnl"
    elif not enough_days:
        status = "collecting_insufficient_days"
        recommendation = "continue_daily_snapshot_collection"
    else:
        status = "qualification_coverage_pass"
        recommendation = "factor_pipeline_qualification_allowed_without_pnl"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "required_kinds": list(REQUIRED_KINDS),
        "minimum_contiguous_days": MIN_CONTIGUOUS_DAYS,
        "coverage": coverage,
        "paired_dates": [day.isoformat() for day in paired_days],
        "paired_day_count": len(paired_days),
        "unpaired_dates": mismatch,
        "blockers": blockers,
        "snapshots": sorted(records, key=lambda row: (row["retrieved_day"], row["kind"])),
        "recommendation": recommendation,
        "boundaries": {
            "prices_summarized": False,
            "returns_loaded": False,
            "pnl_computed": False,
            "signals_generated": False,
            "signal_store_written": False,
            "nautilus_run": False,
            "source_policy_mutated": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(review_snapshots(args.snapshot), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

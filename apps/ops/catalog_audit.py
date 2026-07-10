"""Passively audit exact bar coverage and alignment in a Nautilus catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

SCHEMA_VERSION = "catalog.audit.v1"


def _fingerprint(bars: list[Any]) -> str:
    digest = hashlib.sha256()
    for bar in bars:
        digest.update(
            (
                f"{int(bar.ts_event)}|{bar.open}|{bar.high}|{bar.low}|"
                f"{bar.close}|{bar.volume}\n"
            ).encode()
        )
    return f"sha256:{digest.hexdigest()}"


def build_catalog_audit(
    catalog_path: Path,
    bar_types: list[str],
    *,
    start_date: str,
    end_date: str,
    interval_minutes: int = 1,
) -> dict[str, Any]:
    if not bar_types or len(set(bar_types)) != len(bar_types):
        raise ValueError("provide one or more unique bar types")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    if start != start.normalize() or end != end.normalize() or end < start:
        raise ValueError("start/end must be ordered UTC dates")
    end_exclusive = end + pd.Timedelta(days=1)
    step_ns = interval_minutes * 60_000_000_000
    expected_rows = int((end_exclusive.value - start.value) // step_ns)
    catalog = ParquetDataCatalog(str(catalog_path.resolve()))

    instruments = []
    timestamp_sets: list[tuple[int, ...]] = []
    for bar_type in bar_types:
        bars = sorted(
            catalog.bars(
                bar_types=[bar_type],
                start=int(start.value),
                end=int(end_exclusive.value) - 1,
            ),
            key=lambda bar: int(bar.ts_event),
        )
        timestamps = tuple(int(bar.ts_event) for bar in bars)
        unique = tuple(dict.fromkeys(timestamps))
        gaps = sum(
            max((right - left) // step_ns - 1, 0)
            for left, right in zip(unique, unique[1:], strict=False)
        )
        irregular_steps = sum(
            right - left != step_ns
            for left, right in zip(unique, unique[1:], strict=False)
        )
        blockers = []
        if len(bars) != expected_rows:
            blockers.append(f"rows={len(bars)}!=expected={expected_rows}")
        if len(timestamps) != len(unique):
            blockers.append(f"duplicate_timestamps={len(timestamps) - len(unique)}")
        if gaps or irregular_steps:
            blockers.append(f"minute_gaps={gaps};irregular_steps={irregular_steps}")
        expected_first = int(start.value)
        expected_last = int(end_exclusive.value) - step_ns
        if not timestamps or timestamps[0] != expected_first or timestamps[-1] != expected_last:
            blockers.append("timestamp_bounds_mismatch")
        instruments.append(
            {
                "bar_type": bar_type,
                "rows": len(bars),
                "expected_rows": expected_rows,
                "duplicate_timestamps": len(timestamps) - len(unique),
                "missing_intervals": int(gaps),
                "irregular_steps": int(irregular_steps),
                "first_ts_ns": timestamps[0] if timestamps else None,
                "last_ts_ns": timestamps[-1] if timestamps else None,
                "first_close": float(bars[0].close) if bars else None,
                "bars_sha256": _fingerprint(bars),
                "blockers": blockers,
                "passed": not blockers,
            }
        )
        timestamp_sets.append(unique)

    aligned = all(timestamps == timestamp_sets[0] for timestamps in timestamp_sets[1:])
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "catalog_path": str(catalog_path),
            "bar_types": bar_types,
            "start_date": start_date,
            "end_date": end_date,
            "interval_minutes": interval_minutes,
        },
        "expected_rows_per_instrument": expected_rows,
        "instruments": instruments,
        "timestamp_alignment": {
            "aligned": aligned,
            "instrument_count": len(instruments),
        },
        "passed": aligned and all(row["passed"] for row in instruments),
        "boundaries": {
            "read_only": True,
            "writes_catalog": False,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "loads_credentials": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-path", type=Path, required=True)
    parser.add_argument("--bar-type", action="append", default=[])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--interval-minutes", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_catalog_audit(
        args.catalog_path,
        args.bar_type,
        start_date=args.start_date,
        end_date=args.end_date,
        interval_minutes=args.interval_minutes,
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

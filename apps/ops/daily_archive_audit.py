"""Passively audit aligned daily warm-up/signal archives for a fixed universe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.flow_positioning_signals import (
    load_spot_aggregates,
)

SCHEMA_VERSION = "daily.archive.audit.v1"


def _fingerprint(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for index, row in frame.iterrows():
        digest.update(f"{int(index.value)}|".encode())
        digest.update("|".join(str(value) for value in row).encode())
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def build_daily_archive_audit(
    directories: dict[str, Path],
    *,
    expected_symbols: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    if set(directories) != set(expected_symbols):
        raise ValueError(f"directories must contain exactly {expected_symbols}")
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    if start != start.normalize() or end != end.normalize() or end < start:
        raise ValueError("start/end must be ordered UTC dates")
    end_exclusive = end + pd.Timedelta(days=1)
    expected_days = (end.date() - start.date()).days + 1
    rows = []
    indexes = []
    for symbol in expected_symbols:
        frame = load_spot_aggregates(
            directories[symbol],
            symbol,
            "1D",
            source_interval="1d",
        )
        frame = frame.loc[(frame.index >= start) & (frame.index < end_exclusive)]
        blockers = []
        if len(frame) != expected_days:
            blockers.append(f"days={len(frame)}!=expected={expected_days}")
        if frame.index.duplicated().any():
            blockers.append("duplicate_days")
        if not np.isfinite(frame[["open", "close", "quote_volume"]].to_numpy()).all():
            blockers.append("non_finite_daily_values")
        rows.append(
            {
                "symbol": symbol,
                "days": len(frame),
                "first_day": frame.index[0].date().isoformat() if not frame.empty else None,
                "last_day": frame.index[-1].date().isoformat() if not frame.empty else None,
                "sha256": _fingerprint(frame[["open", "close", "quote_volume"]]),
                "blockers": blockers,
                "passed": not blockers,
            }
        )
        indexes.append(tuple(frame.index.astype("int64")))
    aligned = all(index == indexes[0] for index in indexes[1:])
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "symbols": list(expected_symbols),
            "start_date": start_date,
            "end_date": end_date,
        },
        "expected_days": expected_days,
        "instruments": rows,
        "aligned": aligned,
        "passed": aligned and all(row["passed"] for row in rows),
        "boundaries": {
            "read_only": True,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "loads_credentials": False,
        },
    }


def _parse_directory(value: str) -> tuple[str, Path]:
    symbol, separator, path = value.partition("=")
    if not separator or not symbol.strip() or not path.strip():
        raise argparse.ArgumentTypeError("directory must be SYMBOL=PATH")
    return symbol.strip().upper(), Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    directories = dict(args.daily_dir)
    report = build_daily_archive_audit(
        directories,
        expected_symbols=tuple(directories),
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

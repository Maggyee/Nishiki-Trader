"""Audit raw spot-flow and USD-M funding features before signal generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apps.strategies_freqtrade.research.flow_positioning_signals import (
    load_funding_archives,
    load_spot_aggregates,
)
from apps.strategies_freqtrade.research.multi_asset_rotation_signals import UNIVERSE

SCHEMA_VERSION = "feature.audit.v1"
FUNDING_GAP_TOLERANCE_HOURS = 8.0 + 1.0 / 60.0


def _hash_rows(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for index, row in frame.iterrows():
        digest.update(f"{int(index.value)}|".encode())
        digest.update("|".join(str(value) for value in row).encode())
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def build_feature_audit(
    spot_dirs: dict[str, Path],
    funding_dirs: dict[str, Path],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    if set(spot_dirs) != set(UNIVERSE) or set(funding_dirs) != set(UNIVERSE):
        raise ValueError(f"spot/funding directories must contain exactly {UNIVERSE}")
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    if start != start.normalize() or end != end.normalize() or end < start:
        raise ValueError("start/end must be ordered UTC dates")
    end_exclusive = end + pd.Timedelta(days=1)
    expected_days = (end.date() - start.date()).days + 1
    instruments = []
    spot_indexes = []
    funding_indexes = []
    for symbol in UNIVERSE:
        daily = load_spot_aggregates(spot_dirs[symbol], symbol, "1D").loc[
            (lambda frame: (frame.index >= start) & (frame.index < end_exclusive))
        ]
        funding = load_funding_archives(funding_dirs[symbol], symbol)
        funding = funding.loc[(funding.index >= start) & (funding.index < end_exclusive)]
        buy_share = daily["taker_buy_quote"] / daily["quote_volume"]
        funding_days = funding.index.floor("D").unique()
        funding_gap_hours = (
            float(np.diff(funding.index.astype("int64")).max() / 3_600_000_000_000)
            if len(funding) > 1
            else float("inf")
        )
        blockers = []
        if len(daily) != expected_days:
            blockers.append(f"spot_days={len(daily)}!=expected={expected_days}")
        if len(funding_days) != expected_days:
            blockers.append(f"funding_days={len(funding_days)}!=expected={expected_days}")
        if funding.index.duplicated().any():
            blockers.append("duplicate_funding_timestamps")
        if funding_gap_hours > FUNDING_GAP_TOLERANCE_HOURS:
            blockers.append(f"funding_gap_hours={funding_gap_hours}")
        if not np.isfinite(buy_share.to_numpy()).all() or not np.isfinite(funding.to_numpy()).all():
            blockers.append("non_finite_features")
        if ((buy_share < 0.0) | (buy_share > 1.0)).any():
            blockers.append("buy_share_out_of_range")
        if (funding.abs() > 0.10).any():
            blockers.append("funding_rate_out_of_sanity_range")
        feature_frame = daily[["close", "quote_volume", "taker_buy_quote"]].copy()
        instruments.append(
            {
                "symbol": symbol,
                "spot_days": len(daily),
                "funding_rows": len(funding),
                "funding_days": len(funding_days),
                "maximum_funding_gap_hours": funding_gap_hours,
                "spot_flow_sha256": _hash_rows(feature_frame),
                "funding_sha256": _hash_rows(funding.to_frame("funding_rate")),
                "blockers": blockers,
                "passed": not blockers,
            }
        )
        spot_indexes.append(tuple(daily.index.astype("int64")))
        funding_indexes.append(tuple(funding.index.astype("int64")))
    spot_aligned = all(index == spot_indexes[0] for index in spot_indexes[1:])
    funding_aligned = all(index == funding_indexes[0] for index in funding_indexes[1:])
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "start_date": start_date,
            "end_date": end_date,
            "symbols": list(UNIVERSE),
        },
        "expected_days": expected_days,
        "funding_gap_tolerance_hours": FUNDING_GAP_TOLERANCE_HOURS,
        "instruments": instruments,
        "alignment": {
            "spot_daily_aligned": spot_aligned,
            "funding_timestamps_aligned": funding_aligned,
        },
        "passed": spot_aligned and all(row["passed"] for row in instruments),
        "boundaries": {
            "read_only": True,
            "writes_signal_event": False,
            "starts_nautilus": False,
            "loads_credentials": False,
        },
    }


def _parse_directory(value: str) -> tuple[str, Path]:
    symbol, separator, path = value.partition("=")
    symbol = symbol.strip().upper()
    if not separator or symbol not in UNIVERSE or not path.strip():
        raise argparse.ArgumentTypeError("directory must be SYMBOL=PATH")
    return symbol, Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spot-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--funding-dir", action="append", type=_parse_directory, default=[])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_feature_audit(
        dict(args.spot_dir),
        dict(args.funding_dir),
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

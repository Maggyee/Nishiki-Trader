"""Build a Protocol v7 downtime-marker catalog for sensitivity analysis only.

Binance does not publish Spot klines while its matching engine is unavailable.
This tool preserves the official bars and inserts explicit zero-volume markers
at the previous real close. The markers make the hourly clock continuous, but
they are synthetic and must never be treated as executable market evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.objects import Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

SCHEMA_VERSION = "research.v7.downtime_sensitivity.v1"


def _bars_sha256(bars: list[Bar]) -> str:
    digest = hashlib.sha256()
    for bar in bars:
        digest.update(
            (
                f"{int(bar.ts_event)}|{bar.open}|{bar.high}|{bar.low}|{bar.close}|{bar.volume}\n"
            ).encode()
        )
    return f"sha256:{digest.hexdigest()}"


def build_gap_markers(
    bars: list[Bar],
    *,
    step_ns: int,
    expected_start_ns: int,
    expected_end_ns: int,
) -> tuple[list[Bar], list[dict[str, Any]]]:
    """Return zero-volume carry-forward markers and their provenance rows."""
    ordered = sorted(bars, key=lambda bar: int(bar.ts_event))
    if not ordered:
        raise ValueError("source catalog contains no bars")
    if step_ns <= 0:
        raise ValueError("step_ns must be positive")
    timestamps = [int(bar.ts_event) for bar in ordered]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("source catalog contains duplicate timestamps")
    if timestamps[0] != expected_start_ns or timestamps[-1] != expected_end_ns:
        raise ValueError("source catalog boundaries do not match the requested window")

    zero_volume = Quantity.from_str("0.000000")
    markers: list[Bar] = []
    gaps: list[dict[str, Any]] = []
    for left, right in zip(ordered, ordered[1:], strict=False):
        left_ns = int(left.ts_event)
        right_ns = int(right.ts_event)
        delta = right_ns - left_ns
        if delta < step_ns or delta % step_ns:
            raise ValueError("source catalog contains an irregular non-grid timestamp")
        missing = delta // step_ns - 1
        if not missing:
            continue
        gap_timestamps: list[int] = []
        for offset in range(1, missing + 1):
            ts_event = left_ns + offset * step_ns
            gap_timestamps.append(ts_event)
            markers.append(
                Bar(
                    bar_type=left.bar_type,
                    open=left.close,
                    high=left.close,
                    low=left.close,
                    close=left.close,
                    volume=zero_volume,
                    ts_event=ts_event,
                    ts_init=ts_event,
                )
            )
        gaps.append(
            {
                "previous_real_bar_ts_ns": left_ns,
                "next_real_bar_ts_ns": right_ns,
                "synthetic_marker_timestamps_ns": gap_timestamps,
                "marker_count": len(gap_timestamps),
                "carry_forward_close": str(left.close),
            }
        )
    return markers, gaps


def build_sensitivity_catalog(
    *,
    source_catalog_path: Path,
    output_catalog_path: Path,
    bar_type: str,
    start_date: str,
    end_date: str,
    interval_minutes: int,
) -> dict[str, Any]:
    """Copy official bars and insert non-executable downtime markers."""
    if output_catalog_path.exists() and any(output_catalog_path.iterdir()):
        raise ValueError("output catalog must be absent or empty")
    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")
    if start != start.normalize() or end != end.normalize() or end < start:
        raise ValueError("start/end must be ordered UTC dates")
    step_ns = interval_minutes * 60_000_000_000
    end_exclusive_ns = int((end + pd.Timedelta(days=1)).value)
    expected_last_ns = end_exclusive_ns - step_ns

    source = ParquetDataCatalog(str(source_catalog_path.resolve()))
    instruments = source.instruments()
    if len(instruments) != 1:
        raise ValueError("sensitivity catalog requires exactly one instrument")
    official_bars = sorted(
        source.bars(
            bar_types=[bar_type],
            start=int(start.value),
            end=end_exclusive_ns - 1,
        ),
        key=lambda bar: int(bar.ts_event),
    )
    markers, gaps = build_gap_markers(
        official_bars,
        step_ns=step_ns,
        expected_start_ns=int(start.value),
        expected_end_ns=expected_last_ns,
    )
    combined = sorted([*official_bars, *markers], key=lambda bar: int(bar.ts_event))

    output_catalog_path.mkdir(parents=True, exist_ok=True)
    output = ParquetDataCatalog(str(output_catalog_path.resolve()))
    output.write_data(instruments)
    output.write_data(combined)

    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "post_hoc_sensitivity_only",
        "source_catalog_path": str(source_catalog_path),
        "output_catalog_path": str(output_catalog_path),
        "bar_type": bar_type,
        "start_date": start_date,
        "end_date": end_date,
        "official_rows": len(official_bars),
        "synthetic_marker_rows": len(markers),
        "combined_rows": len(combined),
        "gap_count": len(gaps),
        "official_bars_sha256": _bars_sha256(official_bars),
        "combined_bars_sha256": _bars_sha256(combined),
        "marker_semantics": {
            "ohlc": "previous_real_close",
            "volume": "zero",
            "trading_available": False,
            "executable_price_evidence": False,
        },
        "gaps": gaps,
        "boundaries": {
            "overwrites_protocol_v7": False,
            "modifies_signal_store": False,
            "loads_credentials": False,
            "authorizes_promotion": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--output-catalog", type=Path, required=True)
    parser.add_argument("--bar-type", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--interval-minutes", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_sensitivity_catalog(
        source_catalog_path=args.source_catalog,
        output_catalog_path=args.output_catalog,
        bar_type=args.bar_type,
        start_date=args.start_date,
        end_date=args.end_date,
        interval_minutes=args.interval_minutes,
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

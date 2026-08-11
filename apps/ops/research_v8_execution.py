"""Collect and session-audit the frozen Protocol v8 Binance execution holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from apps.ops.backfill_bars import run_backfill
from apps.ops.research_protocol_v8 import load_and_validate

SCHEMA_VERSION = "research.v8.execution_audit.v1"
BAR_TYPE = "BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"
STEP_NS = 3_600_000_000_000
Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v8"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _months(start: str, end: str) -> list[str]:
    first = pd.Period(start, freq="M")
    last = pd.Period(end, freq="M")
    return [str(period) for period in pd.period_range(first, last, freq="M")]


def missing_windows(
    timestamps: list[int],
    *,
    expected_start_ns: int,
    expected_end_ns: int,
    step_ns: int = STEP_NS,
) -> list[list[int]]:
    """Return contiguous expected-grid timestamps absent from observed bars."""
    if step_ns <= 0 or expected_end_ns < expected_start_ns:
        raise ValueError("invalid expected timestamp grid")
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("execution bars contain duplicate timestamps")
    observed = set(timestamps)
    expected = range(expected_start_ns, expected_end_ns + step_ns, step_ns)
    missing = [timestamp for timestamp in expected if timestamp not in observed]
    windows: list[list[int]] = []
    for timestamp in missing:
        if not windows or timestamp != windows[-1][-1] + step_ns:
            windows.append([timestamp])
        else:
            windows[-1].append(timestamp)
    return windows


def _checksum(checksum_bytes: bytes, filename: str) -> str:
    fields = checksum_bytes.decode("utf-8").strip().split()
    if len(fields) != 2 or fields[1].lstrip("*") != filename:
        raise ValueError(f"official checksum identity differs for {filename}")
    digest = fields[0].lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"official checksum is invalid for {filename}")
    return digest


def collect_and_audit(
    *,
    output_root: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Open the one allowed holdout and classify official no-kline windows."""
    contract = load_and_validate()
    report_path = output_root / "execution-audit.json"
    catalog_path = output_root / "catalog"
    raw_path = output_root / "raw-binance"
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("Protocol v8 output root must be absent or empty")
    raw_path.mkdir(parents=True, exist_ok=True)

    archive_rows: list[dict[str, Any]] = []
    for month in _months("2023-01", "2025-12"):
        filename = f"BTCUSDT-1h-{month}.zip"
        url = f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/{filename}"
        archive = fetch(url)
        checksum_bytes = fetch(f"{url}.CHECKSUM")
        expected = _checksum(checksum_bytes, filename)
        actual = hashlib.sha256(archive).hexdigest()
        if actual != expected:
            raise ValueError(f"official checksum mismatch for {filename}")
        archive_file = raw_path / filename
        archive_file.write_bytes(archive)
        (raw_path / f"{filename}.CHECKSUM").write_bytes(checksum_bytes)
        imported = run_backfill(
            raw_path=archive_file,
            download=False,
            symbol="BTCUSDT",
            interval="1h",
            date=None,
            raw_output_dir=raw_path,
            catalog_path=catalog_path,
        )
        archive_rows.append(
            {
                "month": month,
                "filename": filename,
                "archive_sha256": f"sha256:{actual}",
                "official_checksum_match": True,
                "bars_written": imported.bars_written,
            }
        )

    start = pd.Timestamp("2023-01-01", tz="UTC")
    end_exclusive = pd.Timestamp("2026-01-01", tz="UTC")
    expected_rows = int((end_exclusive.value - start.value) // STEP_NS)
    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    bars = sorted(
        catalog.bars(
            bar_types=[BAR_TYPE],
            start=int(start.value),
            end=int(end_exclusive.value) - 1,
        ),
        key=lambda bar: int(bar.ts_event),
    )
    timestamps = [int(bar.ts_event) for bar in bars]
    windows = missing_windows(
        timestamps,
        expected_start_ns=int(start.value),
        expected_end_ns=int(end_exclusive.value) - STEP_NS,
    )
    verified_windows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for window in windows:
        params = urllib.parse.urlencode(
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "startTime": window[0] // 1_000_000,
                "endTime": (window[-1] + STEP_NS) // 1_000_000 - 1,
                "limit": 1000,
            }
        )
        url = f"https://api.binance.com/api/v3/klines?{params}"
        raw = fetch(url)
        response = json.loads(raw)
        if not isinstance(response, list):
            raise ValueError("official Spot REST gap response must be a list")
        row = {
            "start_ts_ns": window[0],
            "end_ts_ns": window[-1],
            "missing_hours": len(window),
            "rest_url": url,
            "rest_response_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "rest_kline_rows": len(response),
            "classification": "exchange_unavailable_not_missing_market_data"
            if not response
            else "archive_rest_disagreement",
        }
        verified_windows.append(row)
        if response:
            blockers.append(f"archive_rest_disagreement:{window[0]}-{window[-1]}:{len(response)}")

    duplicate_count = len(timestamps) - len(set(timestamps))
    verified_missing = sum(
        row["missing_hours"] for row in verified_windows if not row["rest_kline_rows"]
    )
    if duplicate_count:
        blockers.append(f"duplicate_timestamps:{duplicate_count}")
    if len(bars) + verified_missing != expected_rows:
        blockers.append(f"session_rows:{len(bars)}+{verified_missing}!={expected_rows}")
    report = {
        "schema_version": SCHEMA_VERSION,
        "audited_at": (now or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        "contract_sha256": contract["contract_sha256"],
        "catalog_path": str(catalog_path),
        "bar_type": BAR_TYPE,
        "start": "2023-01-01",
        "end": "2025-12-31",
        "expected_clock_rows": expected_rows,
        "official_bar_rows": len(bars),
        "verified_no_kline_rows": verified_missing,
        "duplicate_timestamps": duplicate_count,
        "archive_count": len(archive_rows),
        "archive_checksum_matches": sum(row["official_checksum_match"] for row in archive_rows),
        "archives": archive_rows,
        "verified_no_kline_windows": verified_windows,
        "synthetic_bar_rows": 0,
        "blockers": sorted(blockers),
        "passed": not blockers,
        "boundaries": {
            "writes_signal_event": False,
            "starts_nautilus": False,
            "loads_credentials": False,
            "touches_live_path": False,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("data/research-v8"))
    args = parser.parse_args(argv)
    report = collect_and_audit(output_root=args.output_root)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

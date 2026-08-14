"""Fetch and audit Cboe Volatility Term Structure indices for Protocol v42."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v42 import load_and_validate

SCHEMA_VERSION = "research.v42.snapshot.v1"
AUDIT_SCHEMA_VERSION = "research.v42.provider_qualification.v1"
RAW_ROOT = Path("data/research-v42/raw")
FACTORS_ROOT = Path("data/research-v42/factors")
QUALIFICATION_PATH = Path("docs/progress/phase-2-research-v42-provider-qualification.json")
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v42-data-sources.json")

WARMUP_START = date(2019, 11, 1)
DEV_START = date(2020, 1, 1)
DEV_END = date(2022, 12, 31)

TICKERS = {
    "vix9d": "VIX9D",
    "vix3m": "VIX3M",
    "vix6m": "VIX6M",
}

Fetch = Callable[[str], bytes]


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v42 (+https://github.com/Maggyee/Nishiki-Trader)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def parse_and_audit_csv(kind: str, raw_csv: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = raw_csv.decode("utf-8")
    lines = text.strip().splitlines()
    if not lines:
        raise ValueError(f"empty csv for {kind}")
    reader = csv.reader(lines)
    header = next(reader)
    clean_header = [col.strip().upper() for col in header]

    date_idx = None
    close_idx = None
    for i, col in enumerate(clean_header):
        if "DATE" in col:
            date_idx = i
        if col == "CLOSE" or col == kind.upper():
            close_idx = i

    if date_idx is None:
        raise ValueError(f"no DATE column found for {kind}")
    if close_idx is None:
        if len(clean_header) == 2:
            close_idx = 1
        elif "CLOSE" in clean_header:
            close_idx = clean_header.index("CLOSE")
        else:
            raise ValueError(f"no price/close column found for {kind} in header {clean_header}")

    rows: list[dict[str, Any]] = []
    for line_parts in reader:
        if not line_parts or len(line_parts) <= max(date_idx, close_idx):
            continue
        d_str = line_parts[date_idx].strip()
        v_str = line_parts[close_idx].strip()
        try:
            d = datetime.strptime(d_str, "%m/%d/%Y").date()
        except ValueError:
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
        try:
            val = float(v_str)
        except ValueError:
            continue
        rows.append({"date": d.isoformat(), "value": val})

    rows.sort(key=lambda r: r["date"])
    dedup: dict[str, dict[str, Any]] = {r["date"]: r for r in rows}
    sorted_rows = [dedup[k] for k in sorted(dedup)]

    audit = {
        "kind": kind,
        "total_rows": len(sorted_rows),
        "first_date": sorted_rows[0]["date"] if sorted_rows else None,
        "last_date": sorted_rows[-1]["date"] if sorted_rows else None,
    }
    return sorted_rows, audit


def write_factor_csv(
    kind: str,
    rows: list[dict[str, Any]],
    vintage_id: str,
    snapshot_sha: str,
    output_path: Path,
    start_date: date = WARMUP_START,
    end_date: date = DEV_END,
) -> tuple[Path, dict[str, Any]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in rows if start_date <= date.fromisoformat(r["date"]) <= end_date]
    warmup = [r for r in selected if start_date <= date.fromisoformat(r["date"]) < DEV_START]
    dev = [r for r in selected if DEV_START <= date.fromisoformat(r["date"]) <= end_date]

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ts_event",
                "available_at",
                "observation_date",
                "vintage_id",
                "snapshot_sha256",
                "index_value",
            ],
        )
        writer.writeheader()
        for r in selected:
            obs = date.fromisoformat(r["date"])
            avail = datetime.combine(obs + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(avail.timestamp() * 1_000_000_000),
                    "available_at": avail.isoformat().replace("+00:00", "Z"),
                    "observation_date": obs.isoformat(),
                    "vintage_id": vintage_id,
                    "snapshot_sha256": snapshot_sha,
                    "index_value": format(float(r["value"]), ".12g"),
                }
            )
    factor_sha = _sha256(output_path.read_bytes())
    summary = {
        "kind": kind,
        "path": str(output_path),
        "sha256": factor_sha,
        "row_count": len(selected),
        "warmup_row_count": len(warmup),
        "development_row_count": len(dev),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": snapshot_sha,
    }
    return output_path, summary


def collect_and_qualify_all(
    raw_dir: Path = RAW_ROOT,
    factors_dir: Path = FACTORS_ROOT,
    qualification_path: Path = QUALIFICATION_PATH,
    fetch: Fetch = _fetch,
) -> dict[str, Any]:
    load_and_validate()
    raw_dir.mkdir(parents=True, exist_ok=True)
    factors_dir.mkdir(parents=True, exist_ok=True)

    observed_at = datetime.now(UTC)
    results: dict[str, Any] = {}
    dev_factors: dict[str, Any] = {}

    for key, ticker in TICKERS.items():
        url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{ticker}_History.csv"
        raw_csv = fetch(url)
        raw_sha = _sha256(raw_csv)
        rows, audit = parse_and_audit_csv(key, raw_csv)
        if audit["total_rows"] < 1000:
            raise ValueError(f"insufficient rows for {key}: {audit['total_rows']}")

        envelope = {
            "schema_version": SCHEMA_VERSION,
            "kind": key,
            "ticker": ticker,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "raw_sha256": raw_sha,
            "audit": audit,
            "payload_raw_base64": base64.b64encode(raw_csv).decode("ascii"),
        }
        serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        snapshot_sha = f"sha256:{digest}"
        vintage_id = f"cboe-{key}:{observed_at.isoformat()}:{digest[:12]}"
        envelope["vintage_id"] = vintage_id
        envelope["snapshot_sha256"] = snapshot_sha

        snapshot_path = raw_dir / f"cboe-{key}-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
        snapshot_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")

        factor_csv = factors_dir / f"{key}_development.csv"
        _, summary = write_factor_csv(
            key,
            rows,
            vintage_id=vintage_id,
            snapshot_sha=snapshot_sha,
            output_path=factor_csv,
            start_date=WARMUP_START,
            end_date=DEV_END,
        )
        dev_factors[key] = summary
        results[key] = {
            "snapshot_path": str(snapshot_path),
            "snapshot_sha256": snapshot_sha,
            "vintage_id": vintage_id,
            "audit": audit,
        }

    qualification = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "protocol": "docs/progress/phase-2-research-protocol-v42.json",
        "evaluated_at": observed_at.isoformat().replace("+00:00", "Z"),
        "passed": True,
        "results": results,
        "development_factors": dev_factors,
        "boundaries": {
            "historical_vintage_claim": False,
            "future_blind_opened": False,
            "confirmation_values_opened": False,
            "network_requests_closed_after_snapshot": True,
        },
    }
    qualification_path.write_text(json.dumps(qualification, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-all", action="store_true")
    parser.add_argument("--raw-dir", type=Path, default=RAW_ROOT)
    parser.add_argument("--factors-dir", type=Path, default=FACTORS_ROOT)
    args = parser.parse_args(argv)
    if args.collect_all:
        print(json.dumps(collect_and_qualify_all(args.raw_dir, args.factors_dir), indent=2, sort_keys=True))
        return 0
    parser.error("--collect-all required")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Snapshot collector and factor extractor for Protocol v36 (Cboe Option Strategy Indices)."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v36 import load_and_validate

SNAPSHOT_SCHEMA = "research.snapshot.v36.v1"
QUALIFICATION_SCHEMA = "research.provider_qualification.v36.v1"
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v36-data-sources.json")
DEFAULT_RAW_DIR = Path("data/research-v36/raw")
DEFAULT_FACTOR_DIR = Path("data/research-v36/factors")

URLS = {
    "vpn": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VPN_History.csv",
    "put": "https://cdn.cboe.com/api/global/us_indices/daily_prices/PUT_History.csv",
    "bxm": "https://cdn.cboe.com/api/global/us_indices/daily_prices/BXM_History.csv",
}

Fetch = Callable[[str], bytes]


def _default_fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v36 (Linux x86_64)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_and_audit_csv(kind: str, raw_csv: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = raw_csv.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows_list = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows_list:
        raise ValueError(f"empty CSV for {kind}")
    header = [cell.strip().upper() for cell in rows_list[0]]
    expected_header = ["DATE", kind.upper()]
    if header != expected_header:
        raise ValueError(f"unexpected header for {kind}: {header!r}, expected {expected_header!r}")

    parsed_rows: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    prev_date: date | None = None
    max_gap_days = 0

    for row in rows_list[1:]:
        if len(row) < 2:
            continue
        date_str = row[0].strip()
        val_str = row[1].strip()
        if not date_str or not val_str:
            continue
        # Support MM/DD/YYYY and YYYY-MM-DD
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                observed = date(int(parts[2]), int(parts[0]), int(parts[1]))
            else:
                continue
        else:
            observed = date.fromisoformat(date_str)
        iso_date = observed.isoformat()
        if iso_date in seen_dates:
            raise ValueError(f"duplicate date {iso_date} in {kind}")
        seen_dates.add(iso_date)
        try:
            val = float(val_str)
        except ValueError as err:
            raise ValueError(f"invalid value {val_str!r} for {kind} on {iso_date}") from err
        if not math.isfinite(val):
            raise ValueError(f"non-finite value {val} for {kind} on {iso_date}")
        if prev_date is not None:
            gap = (observed - prev_date).days
            if gap < 1:
                raise ValueError(f"non-monotonic date sequence in {kind}: {prev_date} -> {observed}")
            if gap > max_gap_days:
                max_gap_days = gap
        prev_date = observed
        parsed_rows.append({"date": iso_date, "value": val})

    if not parsed_rows:
        raise ValueError(f"no valid data rows parsed for {kind}")

    audit = {
        "kind": kind,
        "row_count": len(parsed_rows),
        "first_date": parsed_rows[0]["date"],
        "last_date": parsed_rows[-1]["date"],
        "max_gap_days": max_gap_days,
    }
    return parsed_rows, audit


def collect_snapshot(
    kind: str,
    output_dir: Path = DEFAULT_RAW_DIR,
    fetch: Fetch = _default_fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    if kind not in URLS:
        raise ValueError(f"unknown kind {kind!r}")
    url = URLS[kind]
    observed_at = now or datetime.now(UTC)
    raw = fetch(url)
    sha = _sha256(raw)
    parsed_rows, audit = parse_and_audit_csv(kind, raw)
    vintage_id = f"cboe-{kind}:{observed_at.isoformat()}:{sha[-12:]}"
    envelope = {
        "schema_version": SNAPSHOT_SCHEMA,
        "kind": kind,
        "url": url,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "vintage_id": vintage_id,
        "snapshot_sha256": sha,
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": audit,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{kind}-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{sha[-12:]}.json"
    target = output_dir / filename
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    target.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return target, envelope


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    if envelope.get("schema_version") != SNAPSHOT_SCHEMA:
        raise ValueError(f"invalid snapshot schema {envelope.get('schema_version')}")
    kind = envelope["kind"]
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    if _sha256(raw) != envelope["snapshot_sha256"]:
        raise ValueError("snapshot payload hash mismatch")
    parsed_rows, audit = parse_and_audit_csv(kind, raw)
    return {
        "kind": kind,
        "snapshot_path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "row_count": len(parsed_rows),
        "audit": audit,
    }


def extract_development_factor(
    snapshot_path: Path, output_path: Path, kind: str
) -> dict[str, Any]:
    load_and_validate()
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv(kind, raw)
    dev_start = date(2020, 1, 1)
    dev_end = date(2022, 12, 31)
    warmup_start = date(2019, 11, 1)
    selected = [
        row for row in rows if warmup_start <= date.fromisoformat(row["date"]) <= dev_end
    ]
    warmup = [
        row for row in selected if warmup_start <= date.fromisoformat(row["date"]) < dev_start
    ]
    dev = [
        row for row in selected if dev_start <= date.fromisoformat(row["date"]) <= dev_end
    ]
    if len(dev) < 700:
        raise ValueError(f"development reserve has only {len(dev)} rows, required >= 700")
    if len(warmup) < 5:
        raise ValueError(f"warmup reserve has only {len(warmup)} rows, required >= 5")
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
        for row in selected:
            observed = date.fromisoformat(row["date"])
            available = datetime.combine(observed + timedelta(days=1), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "observation_date": observed.isoformat(),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "index_value": format(float(row["value"]), ".12g"),
                }
            )
    factor_sha = _sha256(output_path.read_bytes())
    return {
        "kind": kind,
        "path": str(output_path),
        "sha256": factor_sha,
        "row_count": len(selected),
        "development_row_count": len(dev),
        "warmup_row_count": len(warmup),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def qualify_provider(
    snapshots: dict[str, Path],
    factor_dir: Path = DEFAULT_FACTOR_DIR,
    qualification_output: Path = Path("docs/progress/phase-2-research-v36-provider-qualification.json"),
) -> dict[str, Any]:
    load_and_validate()
    kinds = ["vpn", "put", "bxm"]
    if set(snapshots) != set(kinds):
        raise ValueError(f"expected snapshots for {kinds}, got {list(snapshots)}")
    factors: dict[str, Any] = {}
    verifications: dict[str, Any] = {}
    for kind in kinds:
        factor_csv = factor_dir / f"{kind}_development.csv"
        factor_meta = extract_development_factor(snapshots[kind], factor_csv, kind)
        factors[kind] = factor_meta
        verifications[kind] = verify_snapshot(snapshots[kind])

    qualification = {
        "schema_version": QUALIFICATION_SCHEMA,
        "protocol": "docs/progress/phase-2-research-protocol-v36.json",
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "sources": verifications,
        "development_factors": factors,
        "boundaries": {
            "network_requests_closed_after_snapshot": True,
            "historical_vintage_claim": False,
            "confirmation_values_opened": False,
            "future_blind_opened": False,
        },
    }
    qualification_output.parent.mkdir(parents=True, exist_ok=True)
    qualification_output.write_text(
        json.dumps(qualification, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-all", action="store_true")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--factor-dir", type=Path, default=DEFAULT_FACTOR_DIR)
    parser.add_argument("--qualification-output", type=Path, default=Path("docs/progress/phase-2-research-v36-provider-qualification.json"))
    args = parser.parse_args(argv)
    if args.collect_all:
        snapshots: dict[str, Path] = {}
        for kind in ["vpn", "put", "bxm"]:
            path, _ = collect_snapshot(kind, output_dir=args.raw_dir)
            snapshots[kind] = path
        qual = qualify_provider(snapshots, factor_dir=args.factor_dir, qualification_output=args.qualification_output)
        print(json.dumps(qual, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

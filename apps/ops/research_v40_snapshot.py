"""Fetch and audit Cboe historical CSVs for Protocol v40 (VXN, RVX, VXD)."""

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

from apps.ops.research_protocol_v40 import load_and_validate

SCHEMA_VERSION = "research.v40.snapshot.v1"
AUDIT_SCHEMA_VERSION = "research.v40.provider_qualification.v1"
RAW_ROOT = Path("data/research-v40/raw")
FACTORS_ROOT = Path("data/research-v40/factors")
QUALIFICATION_PATH = Path("docs/progress/phase-2-research-v40-provider-qualification.json")
DATA_SOURCES_PATH = Path("docs/progress/phase-2-research-v40-data-sources.json")

URLS = {
    "vxn": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv",
    "rvx": "https://cdn.cboe.com/api/global/us_indices/daily_prices/RVX_History.csv",
    "vxd": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXD_History.csv",
}

WARMUP_START = date(2019, 11, 1)
DEV_START = date(2020, 1, 1)
DEV_END = date(2022, 12, 31)

Fetch = Callable[[str], bytes]


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v40 (+https://github.com/Maggyee/Nishiki-Trader)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _parse_date(value: str) -> date:
    raw = value.strip()
    if "/" in raw:
        month, day, year = raw.split("/")
        return date(int(year), int(month), int(day))
    if "-" in raw:
        return date.fromisoformat(raw)
    raise ValueError(f"unsupported date format: {value!r}")


def parse_and_audit_csv(kind: str, payload_bytes: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lines = payload_bytes.decode("utf-8-sig").splitlines()
    if not lines:
        raise ValueError(f"{kind} payload is empty")
    reader = csv.reader(lines)
    header = [col.strip().upper() for col in next(reader)]
    date_col = next((i for i, col in enumerate(header) if "DATE" in col), None)
    close_col = next(
        (i for i, col in enumerate(header) if col in {"CLOSE", kind.upper(), "LAST_PRICE", "PRICE", "VALUE"}),
        None,
    )
    if date_col is None or close_col is None:
        raise ValueError(f"unable to locate date/close columns in header: {header}")
    rows: list[dict[str, Any]] = []
    for line in reader:
        if not line or len(line) <= max(date_col, close_col):
            continue
        date_str = line[date_col].strip()
        val_str = line[close_col].strip()
        if not date_str or not val_str:
            continue
        try:
            d = _parse_date(date_str)
            val = float(val_str)
        except Exception:
            continue
        rows.append({"date": d.isoformat(), "value": val})
    rows.sort(key=lambda r: r["date"])
    dates = [date.fromisoformat(r["date"]) for r in rows]
    if len(dates) < 500:
        raise ValueError(f"{kind} has insufficient rows: {len(dates)}")
    gaps = [(curr - prev).days for prev, curr in zip(dates, dates[1:], strict=False)]
    max_gap = max(gaps) if gaps else 0
    audit = {
        "kind": kind,
        "row_count": len(rows),
        "first_date": dates[0].isoformat(),
        "last_date": dates[-1].isoformat(),
        "max_gap_days": max_gap,
    }
    return rows, audit


def collect_snapshot(
    kind: str,
    output_dir: Path = RAW_ROOT,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    if kind not in URLS:
        raise ValueError(f"unknown kind {kind!r}")
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(URLS[kind])
    rows, audit = parse_and_audit_csv(kind, raw)
    digest = hashlib.sha256(raw).hexdigest()
    snapshot_sha = f"sha256:{digest}"
    vintage_id = f"cboe-{kind}:{observed_at.isoformat()}:{digest[:12]}"
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "ticker": kind.upper(),
        "vintage_id": vintage_id,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "source_url": URLS[kind],
        "snapshot_sha256": snapshot_sha,
        "row_count": len(rows),
        "audit": audit,
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{kind}-{observed_at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    target = output_dir / filename
    target.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return target, envelope


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    if envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unexpected schema: {envelope.get('schema_version')}")
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if f"sha256:{digest}" != envelope["snapshot_sha256"]:
        raise ValueError("payload sha256 mismatch")
    return envelope


def write_development_factor(
    kind: str,
    rows: list[dict[str, Any]],
    vintage_id: str,
    snapshot_sha: str,
    output_dir: Path = FACTORS_ROOT,
) -> tuple[Path, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{kind}_development.csv"
    selected = [
        r for r in rows if WARMUP_START <= date.fromisoformat(r["date"]) <= DEV_END
    ]
    warmup = [
        r for r in selected if WARMUP_START <= date.fromisoformat(r["date"]) < DEV_START
    ]
    dev = [
        r for r in selected if DEV_START <= date.fromisoformat(r["date"]) <= DEV_END
    ]
    if len(dev) < 700:
        raise ValueError(f"{kind} has only {len(dev)} development rows (expected >=700)")
    with target.open("w", newline="") as handle:
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
    factor_sha = _sha256(target.read_bytes())
    summary = {
        "kind": kind,
        "path": str(target),
        "sha256": factor_sha,
        "row_count": len(selected),
        "warmup_row_count": len(warmup),
        "development_row_count": len(dev),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": snapshot_sha,
    }
    return target, summary


def collect_and_qualify_all(
    raw_dir: Path = RAW_ROOT,
    factors_dir: Path = FACTORS_ROOT,
    qualification_path: Path = QUALIFICATION_PATH,
    fetch: Fetch = _fetch,
) -> dict[str, Any]:
    load_and_validate()
    sources: dict[str, Any] = {}
    factors: dict[str, Any] = {}
    for kind in sorted(URLS):
        target, envelope = collect_snapshot(kind, output_dir=raw_dir, fetch=fetch)
        raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
        rows, audit = parse_and_audit_csv(kind, raw)
        sources[kind] = {
            "kind": kind,
            "snapshot_path": str(target),
            "snapshot_sha256": envelope["snapshot_sha256"],
            "vintage_id": envelope["vintage_id"],
            "row_count": envelope["row_count"],
            "audit": audit,
        }
        _, factor_summary = write_development_factor(
            kind,
            rows,
            envelope["vintage_id"],
            envelope["snapshot_sha256"],
            output_dir=factors_dir,
        )
        factors[kind] = factor_summary
    qualification = {
        "schema_version": "research.provider_qualification.v40.v1",
        "protocol": "docs/progress/phase-2-research-protocol-v40.json",
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "sources": sources,
        "development_factors": factors,
        "boundaries": {
            "historical_vintage_claim": False,
            "future_blind_opened": False,
            "confirmation_values_opened": False,
            "network_requests_closed_after_snapshot": True,
        },
    }
    qualification_path.write_text(
        json.dumps(qualification, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
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

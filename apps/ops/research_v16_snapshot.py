"""Collect immutable Treasury-direct rate snapshots for Protocol v16."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v16 import DEFAULT_PROTOCOL, YEARS, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v16"
START = date(2019, 11, 1)
END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    return json.loads(DEFAULT_PROTOCOL.read_text())


def request_specs() -> list[dict[str, Any]]:
    data = _contract()["data_contract"]
    specs = []
    for year in YEARS:
        for route in ("nominal", "real"):
            params = {
                key: str(value).format(year=year)
                for key, value in data["routes"][route]["params"].items()
            }
            base = data["url_template"].format(year=year)
            specs.append(
                {
                    "year": year,
                    "route": route,
                    "url": f"{base}?{urllib.parse.urlencode(params)}",
                }
            )
    return specs


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v16"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_date(value: str) -> date:
    text = value.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"invalid Treasury date {value!r}")


def parse_route(raw: bytes, *, route: str, year: int) -> dict[date, dict[str, float]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Treasury response must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    normalized = {_normalize(field): field for field in reader.fieldnames or []}
    required = ("date", "2 yr", "10 yr") if route == "nominal" else ("date", "10 yr")
    if any(field not in normalized for field in required):
        raise ValueError(f"Treasury {route} {year} missing required fields {required}")
    rows: dict[date, dict[str, float]] = {}
    for row in reader:
        day = _parse_date(str(row[normalized["date"]]))
        if day.year != year or day in rows:
            raise ValueError(f"Treasury {route} {year} dates must be unique and in-year")
        values: dict[str, float] = {}
        for field in required[1:]:
            raw_value = str(row[normalized[field]]).strip()
            if raw_value in {"", "N/A", "n/a", "."}:
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"Treasury {route} {year} values must be finite")
            values[field] = value
        if len(values) == len(required) - 1:
            rows[day] = values
    minimum = 40 if year == 2019 else 240
    if len(rows) < minimum:
        raise ValueError(f"Treasury {route} {year} has too few numeric rows")
    return rows


def combine_and_audit(payloads: list[tuple[dict[str, Any], bytes]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(payloads) != 8:
        raise ValueError("Protocol v16 requires exactly eight annual payloads")
    parsed: dict[tuple[int, str], dict[date, dict[str, float]]] = {}
    route_counts: dict[str, int] = {}
    for spec, raw in payloads:
        key = (int(spec["year"]), str(spec["route"]))
        if key in parsed:
            raise ValueError("Protocol v16 annual route duplicated")
        parsed[key] = parse_route(raw, route=key[1], year=key[0])
        route_counts[f"{key[0]}_{key[1]}"] = len(parsed[key])
    rows: list[dict[str, Any]] = []
    days: list[date] = []
    for year in YEARS:
        nominal = parsed[(year, "nominal")]
        real = parsed[(year, "real")]
        for day in sorted(set(nominal).intersection(real)):
            if not START <= day <= END:
                continue
            days.append(day)
            rows.append(
                {
                    "observation_date": day.isoformat(),
                    "real_10y": real[day]["10 yr"],
                    "nominal_2y": nominal[day]["2 yr"],
                    "nominal_10y": nominal[day]["10 yr"],
                    "nominal_10y_minus_2y": nominal[day]["10 yr"] - nominal[day]["2 yr"],
                }
            )
    if len(rows) < 780 or len(days) != len(set(days)):
        raise ValueError("Protocol v16 joint development coverage is insufficient")
    if days[0] > date(2019, 11, 5) or days[-1] < date(2022, 12, 29):
        raise ValueError("Protocol v16 joint coverage boundaries are insufficient")
    max_gap = max(
        (right - left).days for left, right in zip(days, days[1:], strict=False)
    )
    if max_gap > 5:
        raise ValueError("Protocol v16 joint observations contain a gap above five days")
    return rows, {
        "annual_numeric_row_counts": route_counts,
        "joint_row_count": len(rows),
        "first_joint_date": days[0].isoformat(),
        "last_joint_date": days[-1].isoformat(),
        "maximum_joint_calendar_gap_days": max_gap,
        "forward_fill_used": False,
    }


def collect_snapshot(
    *, output_dir: Path, fetch: Fetch = _fetch, now: datetime | None = None
) -> tuple[Path, dict[str, Any]]:
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    payloads = [(spec, fetch(spec["url"])) for spec in request_specs()]
    _, audit = combine_and_audit(payloads)
    request_records = [
        {
            **spec,
            "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "payload_raw_base64": base64.b64encode(raw).decode(),
        }
        for spec, raw in payloads
    ]
    core = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": load_and_validate()["protocol_sha256"],
        "requests": request_records,
        "audit": audit,
        "boundaries": {"values_reported": False, "signals_generated": False, "pnl_opened": False, "trading_touched": False},
    }
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    envelope = {**core, "snapshot_sha256": "sha256:" + digest, "vintage_id": f"treasury-us-rates:{retrieved.isoformat()}:{digest[:12]}"}
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"treasury-us-rates-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v16 snapshot schema")
    if envelope.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v16 protocol fingerprint mismatch")
    if envelope.get("boundaries") != {"values_reported": False, "signals_generated": False, "pnl_opened": False, "trading_touched": False}:
        raise ValueError("Protocol v16 snapshot boundaries are unsafe")
    records = envelope.get("requests")
    specs = request_specs()
    if not isinstance(records, list) or len(records) != len(specs):
        raise ValueError("Protocol v16 snapshot request count mismatch")
    payloads = []
    for expected, record in zip(specs, records, strict=True):
        if any(record.get(key) != expected[key] for key in ("year", "route", "url")):
            raise ValueError("Protocol v16 snapshot request identity drifted")
        raw = base64.b64decode(str(record.get("payload_raw_base64")), validate=True)
        if record.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
            raise ValueError("Protocol v16 raw payload fingerprint mismatch")
        payloads.append((expected, raw))
    _, audit = combine_and_audit(payloads)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v16 snapshot audit mismatch")
    core = {key: value for key, value in envelope.items() if key not in {"snapshot_sha256", "vintage_id"}}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest or not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("Protocol v16 snapshot fingerprint mismatch")
    return {"path": str(path), "snapshot_sha256": envelope["snapshot_sha256"], "vintage_id": envelope["vintage_id"], "audit": audit, "valid": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v16/raw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True))
        return 0
    if args.dry_run:
        print(json.dumps({"requests": request_specs(), "network_accessed": False, "data_written": False}, indent=2))
        return 0
    path, result = collect_snapshot(output_dir=args.output_dir)
    print(json.dumps({**result, "path": str(path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect immutable Treasury nominal-rate confirmation snapshots for v16."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apps.ops.research_v16_confirmation import (
    DEFAULT_CONTRACT,
    YEARS,
    load_and_validate,
)
from apps.ops.research_v16_snapshot import parse_route

SCHEMA_VERSION = "research.raw_snapshot.v16.confirmation"
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    return json.loads(DEFAULT_CONTRACT.read_text())


def request_specs() -> list[dict[str, Any]]:
    data = _contract()["data_contract"]
    specs = []
    for year in YEARS:
        params = {
            key: str(value).format(year=year) for key, value in data["params"].items()
        }
        base = data["url_template"].format(year=year)
        specs.append({"year": year, "url": f"{base}?{urllib.parse.urlencode(params)}"})
    return specs


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v16-confirmation"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def combine_and_audit(payloads: list[tuple[dict[str, Any], bytes]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(payloads) != 3:
        raise ValueError("Protocol v16 confirmation requires three annual payloads")
    rows = []
    counts = {}
    days = []
    for spec, raw in payloads:
        year = int(spec["year"])
        parsed = parse_route(raw, route="nominal", year=year)
        counts[str(year)] = len(parsed)
        for day in sorted(parsed):
            days.append(day)
            rows.append({"observation_date": day.isoformat(), "nominal_10y": parsed[day]["10 yr"]})
    if len(rows) < 740 or len(days) != len(set(days)):
        raise ValueError("Protocol v16 confirmation coverage is insufficient")
    if days[0] > date(2023, 1, 5) or days[-1] < date(2025, 12, 29):
        raise ValueError("Protocol v16 confirmation boundaries are insufficient")
    max_gap = max((right - left).days for left, right in zip(days, days[1:], strict=False))
    if max_gap > 5:
        raise ValueError("Protocol v16 confirmation gap exceeds five days")
    return rows, {"annual_numeric_row_counts": counts, "row_count": len(rows), "first_date": days[0].isoformat(), "last_date": days[-1].isoformat(), "maximum_calendar_gap_days": max_gap, "forward_fill_used": False}


def collect_snapshot(*, output_dir: Path, fetch: Fetch = _fetch, now: datetime | None = None) -> tuple[Path, dict[str, Any]]:
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    payloads = [(spec, fetch(spec["url"])) for spec in request_specs()]
    _, audit = combine_and_audit(payloads)
    records = [{**spec, "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "payload_raw_base64": base64.b64encode(raw).decode()} for spec, raw in payloads]
    core = {"schema_version": SCHEMA_VERSION, "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"), "contract_sha256": load_and_validate()["contract_sha256"], "requests": records, "audit": audit, "boundaries": {"values_reported": False, "signals_generated": False, "pnl_opened": False, "future_blind_opened": False, "trading_touched": False}}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    envelope = {**core, "snapshot_sha256": "sha256:" + digest, "vintage_id": f"treasury-us-rates-confirmation:{retrieved.isoformat()}:{digest[:12]}"}
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"treasury-us-rates-confirmation-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v16 confirmation snapshot schema")
    if envelope.get("contract_sha256") != load_and_validate()["contract_sha256"]:
        raise ValueError("Protocol v16 confirmation contract fingerprint mismatch")
    expected_boundaries = {"values_reported": False, "signals_generated": False, "pnl_opened": False, "future_blind_opened": False, "trading_touched": False}
    if envelope.get("boundaries") != expected_boundaries:
        raise ValueError("Protocol v16 confirmation snapshot boundaries are unsafe")
    records = envelope.get("requests")
    specs = request_specs()
    if not isinstance(records, list) or len(records) != len(specs):
        raise ValueError("Protocol v16 confirmation request count mismatch")
    payloads = []
    for expected, record in zip(specs, records, strict=True):
        if record.get("year") != expected["year"] or record.get("url") != expected["url"]:
            raise ValueError("Protocol v16 confirmation request identity drifted")
        raw = base64.b64decode(str(record.get("payload_raw_base64")), validate=True)
        if record.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
            raise ValueError("Protocol v16 confirmation raw payload fingerprint mismatch")
        payloads.append((expected, raw))
    _, audit = combine_and_audit(payloads)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v16 confirmation snapshot audit mismatch")
    core = {key: value for key, value in envelope.items() if key not in {"snapshot_sha256", "vintage_id"}}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest or not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("Protocol v16 confirmation snapshot fingerprint mismatch")
    return {"path": str(path), "snapshot_sha256": envelope["snapshot_sha256"], "vintage_id": envelope["vintage_id"], "audit": audit, "valid": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v16/confirmation/raw"))
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

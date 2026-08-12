"""Collect one immutable FRED rates snapshot for Protocol v15."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v15 import DEFAULT_PROTOCOL, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v15"
FIELDS = ("observation_date", "DFII10", "T10Y2Y", "DGS10")
SERIES = FIELDS[1:]
START = date(2019, 11, 1)
END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    return json.loads(DEFAULT_PROTOCOL.read_text())


def request_url() -> str:
    data = _contract()["data_contract"]
    return f"{data['url']}?{urllib.parse.urlencode(data['params'])}"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v15"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _weekdays() -> list[date]:
    result: list[date] = []
    current = START
    while current <= END:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def parse_and_audit(raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Protocol v15 response must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ValueError(f"Protocol v15 CSV header must be exactly {list(FIELDS)}")
    parsed: list[dict[str, Any]] = []
    raw_days: list[date] = []
    missing = {series: 0 for series in SERIES}
    complete_days: list[date] = []
    for index, row in enumerate(reader):
        if None in row or set(row) != set(FIELDS) or any(value is None for value in row.values()):
            raise ValueError(f"Protocol v15 row {index} does not match its header")
        day = date.fromisoformat(str(row["observation_date"]).strip())
        raw_days.append(day)
        record: dict[str, Any] = {"observation_date": day.isoformat()}
        complete = True
        for series in SERIES:
            value_text = str(row[series]).strip()
            if value_text in {"", "."}:
                missing[series] += 1
                complete = False
                record[series] = None
                continue
            try:
                value = float(value_text)
            except ValueError as exc:
                raise ValueError(f"Protocol v15 {series} must be numeric or missing") from exc
            if not math.isfinite(value):
                raise ValueError(f"Protocol v15 {series} must be finite")
            record[series] = value
        if complete:
            complete_days.append(day)
        parsed.append(record)
    expected_days = _weekdays()
    if raw_days != expected_days:
        raise ValueError("Protocol v15 raw weekday grid is incomplete or unordered")
    if len(complete_days) < 780:
        raise ValueError("Protocol v15 has too few complete joint observations")
    if complete_days[0] > date(2019, 11, 5) or complete_days[-1] < date(2022, 12, 29):
        raise ValueError("Protocol v15 complete coverage boundaries are insufficient")
    max_gap = max(
        (right - left).days
        for left, right in zip(complete_days, complete_days[1:], strict=False)
    )
    if max_gap > 5:
        raise ValueError("Protocol v15 complete observations contain a gap above five days")
    return parsed, {
        "raw_weekday_row_count": len(raw_days),
        "complete_joint_row_count": len(complete_days),
        "first_raw_date": raw_days[0].isoformat(),
        "last_raw_date": raw_days[-1].isoformat(),
        "first_complete_date": complete_days[0].isoformat(),
        "last_complete_date": complete_days[-1].isoformat(),
        "missing_value_row_count_by_series": missing,
        "maximum_complete_calendar_gap_days": max_gap,
        "forward_fill_used": False,
        "complete_weekday_grid": True,
    }


def collect_snapshot(
    *, output_dir: Path, fetch: Fetch = _fetch, now: datetime | None = None
) -> tuple[Path, dict[str, Any]]:
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(request_url())
    _, audit = parse_and_audit(raw)
    core = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "url": request_url(),
        "protocol_sha256": load_and_validate()["protocol_sha256"],
        "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "payload_raw_base64": base64.b64encode(raw).decode(),
        "audit": audit,
        "boundaries": {
            "values_reported": False,
            "signals_generated": False,
            "pnl_opened": False,
            "trading_touched": False,
        },
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": "sha256:" + digest,
        "vintage_id": f"fred-us-rates:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"fred-us-rates-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v15 snapshot schema")
    if envelope.get("url") != request_url():
        raise ValueError("Protocol v15 snapshot request identity drifted")
    if envelope.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v15 protocol fingerprint mismatch")
    expected_boundaries = {
        "values_reported": False,
        "signals_generated": False,
        "pnl_opened": False,
        "trading_touched": False,
    }
    if envelope.get("boundaries") != expected_boundaries:
        raise ValueError("Protocol v15 snapshot boundaries are unsafe")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Protocol v15 raw payload fingerprint mismatch")
    _, audit = parse_and_audit(raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v15 snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest:
        raise ValueError("Protocol v15 snapshot fingerprint mismatch")
    if not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("Protocol v15 snapshot vintage mismatch")
    return {
        "path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v15/raw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True))
        return 0
    if args.dry_run:
        print(
            json.dumps(
                {"url": request_url(), "network_accessed": False, "data_written": False}, indent=2
            )
        )
        return 0
    path, result = collect_snapshot(output_dir=args.output_dir)
    print(json.dumps({**result, "path": str(path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

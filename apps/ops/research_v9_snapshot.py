"""Collect qualification-only immutable Cboe snapshots for Protocol v9."""

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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v9 import DEFAULT_PROTOCOL, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v9"
KINDS = ("vix9d", "vvix")
RESERVE_START = date(2020, 1, 1)
RESERVE_END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _strict_json(raw: str | bytes) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r}")
        ),
    )


def _request(kind: str) -> dict[str, Any]:
    load_and_validate()
    payload = _strict_json(DEFAULT_PROTOCOL.read_bytes())
    requests = payload["provider_qualification"]["unopened_requests"]
    try:
        return next(row for row in requests if row["kind"] == kind)
    except StopIteration as exc:
        raise ValueError(f"unsupported Protocol v9 kind {kind!r}") from exc


def request_plan(kind: str) -> dict[str, Any]:
    spec = _request(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v9",
        "kind": kind,
        "index": spec["index"],
        "url": spec["url"],
        "network_accessed": False,
        "data_written": False,
        "qualification_only": True,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v9"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _boundaries() -> dict[str, bool]:
    return {
        "strategy_values_exposed": False,
        "signals_generated": False,
        "pnl_calculated": False,
        "credentials_loaded": False,
        "source_policy_mutated": False,
        "testnet_resumed": False,
        "live_path_touched": False,
        "future_blind_opened": False,
    }


def _parse_date(value: str) -> date:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported Cboe DATE {value!r}")


def audit_csv(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Cboe history must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = reader.fieldnames
    if not columns or columns[0] != "DATE" or len(columns) < 2 or len(columns) != len(set(columns)):
        raise ValueError(f"Cboe history has invalid columns {columns!r}")
    previous: date | None = None
    row_count = 0
    reserve_dates: list[date] = []
    first_date: date | None = None
    last_date: date | None = None
    for index, row in enumerate(reader):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Cboe row {index} does not match the header")
        session = _parse_date(row["DATE"])
        if previous is not None and session <= previous:
            raise ValueError("Cboe DATE values must be unique and increasing")
        previous = session
        for column in columns[1:]:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(f"row {index} column {column} must be numeric") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"row {index} column {column} must be finite and positive")
        if first_date is None:
            first_date = session
        last_date = session
        row_count += 1
        if RESERVE_START <= session <= RESERVE_END:
            reserve_dates.append(session)
    if row_count == 0 or first_date is None or last_date is None:
        raise ValueError("Cboe history is empty")
    if len(reserve_dates) < 700:
        raise ValueError(f"development reserve has only {len(reserve_dates)} observations")
    if reserve_dates[0] > date(2020, 1, 3) or reserve_dates[-1] < date(2022, 12, 29):
        raise ValueError("development reserve boundary coverage is incomplete")
    return {
        "columns": columns,
        "row_count": row_count,
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "development_row_count": len(reserve_dates),
        "development_first_date": reserve_dates[0].isoformat(),
        "development_last_date": reserve_dates[-1].isoformat(),
        "development_coverage": True,
    }


def collect_snapshot(
    kind: str,
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    spec = _request(kind)
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(spec["url"])
    if not raw:
        raise ValueError(f"{kind} returned an empty response")
    audit = audit_csv(raw)
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "index": spec["index"],
        "url": spec["url"],
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_path": str(DEFAULT_PROTOCOL),
        "protocol_sha256": f"sha256:{hashlib.sha256(DEFAULT_PROTOCOL.read_bytes()).hexdigest()}",
        "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": audit,
        "boundaries": _boundaries(),
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": f"sha256:{digest}",
        "vintage_id": f"cboe-{kind}:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{kind}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = _strict_json(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v9 snapshot schema")
    spec = _request(str(envelope.get("kind")))
    if envelope.get("index") != spec["index"] or envelope.get("url") != spec["url"]:
        raise ValueError("Protocol v9 snapshot request identity drifted")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v9 snapshot boundaries are unsafe")
    expected_protocol = f"sha256:{hashlib.sha256(DEFAULT_PROTOCOL.read_bytes()).hexdigest()}"
    if envelope.get("protocol_sha256") != expected_protocol:
        raise ValueError("Protocol v9 snapshot contract fingerprint mismatch")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != f"sha256:{hashlib.sha256(raw).hexdigest()}":
        raise ValueError("Protocol v9 raw payload fingerprint mismatch")
    audit = audit_csv(raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v9 snapshot audit mismatch")
    core = {key: value for key, value in envelope.items() if key not in {"snapshot_sha256", "vintage_id"}}
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if envelope.get("snapshot_sha256") != f"sha256:{digest}":
        raise ValueError("Protocol v9 snapshot fingerprint mismatch")
    if not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("Protocol v9 snapshot vintage mismatch")
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "kind": envelope["kind"],
        "index": envelope["index"],
        "payload_sha256": envelope["payload_sha256"],
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v9/raw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        result = verify_snapshot(args.verify)
    elif args.kind and args.dry_run:
        result = request_plan(args.kind)
    elif args.kind:
        path, result = collect_snapshot(args.kind, output_dir=args.output_dir)
        result = {**result, "path": str(path)}
    else:
        parser.error("provide --kind or --verify")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

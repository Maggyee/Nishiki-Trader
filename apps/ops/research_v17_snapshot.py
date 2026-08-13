"""Collect immutable official Cboe snapshots for Protocol v17."""

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

from apps.ops.research_protocol_v17 import load_and_validate

PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v17-data-sources.json")
SCHEMA_VERSION = "research.raw_snapshot.v17"
KINDS = ("vxeem", "vxefa", "vxn")
RESERVE_START = date(2020, 1, 1)
RESERVE_END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(PROVIDER_CONTRACT.read_text())
    if payload.get("schema_version") != "research.data_sources.v17":
        raise ValueError("v17 provider contract schema drifted")
    if payload.get("status") != "locked_before_cboe_csv_body_access":
        raise ValueError("v17 provider contract status drifted")
    if payload.get("authentication") != "none":
        raise ValueError("v17 provider must remain credential-free")
    requests = payload.get("requests")
    if not isinstance(requests, list) or [row.get("kind") for row in requests] != list(KINDS):
        raise ValueError("v17 provider contract must lock vxeem, vxefa, vxn in order")
    return payload


def _request(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unsupported v17 kind {kind!r}")
    return next(row for row in _contract()["requests"] if row["kind"] == kind)


def request_plan(kind: str) -> dict[str, Any]:
    spec = _request(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v17",
        "kind": kind,
        "url": spec["url"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "historical_reserve": {"start": RESERVE_START.isoformat(), "end": RESERVE_END.isoformat()},
        "network_accessed": False,
        "data_written": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v17"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _boundaries() -> dict[str, bool]:
    return {
        "credentials_loaded": False,
        "source_policy_mutated": False,
        "testnet_resumed": False,
        "live_path_touched": False,
        "values_reported": False,
        "signals_generated": False,
        "pnl_opened": False,
    }


def _parse_date(value: str) -> date:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported Cboe DATE {value!r}")


def _positive(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{field} must be finite and positive")
    return result


def parse_and_audit_csv(kind: str, raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = _request(kind)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Cboe history must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected = spec["expected_columns"]
    if reader.fieldnames != expected:
        raise ValueError(f"{kind} columns {reader.fieldnames!r} != locked {expected!r}")
    rows: list[dict[str, Any]] = []
    previous: date | None = None
    value_column = str(spec["value_column"])
    validation_window = spec.get("ohlc_validation_window")
    for index, row in enumerate(reader):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{kind} row {index} does not match the locked header")
        session = _parse_date(row["DATE"])
        if previous is not None and session <= previous:
            raise ValueError(f"{kind} DATE values must be unique and increasing")
        previous = session
        close = _positive(row[value_column], f"rows[{index}].{value_column}")
        if validation_window is not None:
            open_px = _positive(row["OPEN"], f"rows[{index}].OPEN")
            high = _positive(row["HIGH"], f"rows[{index}].HIGH")
            low = _positive(row["LOW"], f"rows[{index}].LOW")
            validation_start = date.fromisoformat(validation_window["start"])
            validation_end = date.fromisoformat(validation_window["end"])
            if validation_start <= session <= validation_end and (
                low > min(open_px, close) or high < max(open_px, close) or high < low
            ):
                raise ValueError(f"{kind} row {index} has invalid in-scope OHLC bounds")
        rows.append({"date": session.isoformat(), "close": close})
    if not rows:
        raise ValueError(f"{kind} history is empty")
    reserve_rows = [
        row for row in rows if RESERVE_START <= date.fromisoformat(row["date"]) <= RESERVE_END
    ]
    if len(reserve_rows) < 700:
        raise ValueError(f"{kind} reserve has only {len(reserve_rows)} observations")
    if date.fromisoformat(reserve_rows[0]["date"]) > date(2020, 1, 3):
        raise ValueError(f"{kind} reserve starts too late")
    if date.fromisoformat(reserve_rows[-1]["date"]) < date(2022, 12, 29):
        raise ValueError(f"{kind} reserve ends too early")
    audit = {
        "row_count": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "reserve_row_count": len(reserve_rows),
        "reserve_first_date": reserve_rows[0]["date"],
        "reserve_last_date": reserve_rows[-1]["date"],
        "columns": expected,
        "forward_fill_used": False,
    }
    return rows, audit


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
    _, audit = parse_and_audit_csv(kind, raw)
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "index": spec["index"],
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": load_and_validate()["protocol_sha256"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "provider_contract_sha256": "sha256:" + hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest(),
        "url": spec["url"],
        "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": audit,
        "boundaries": _boundaries(),
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": "sha256:" + digest,
        "vintage_id": f"cboe-{kind}:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{kind}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v17 snapshot schema")
    kind = str(envelope.get("kind"))
    spec = _request(kind)
    if envelope.get("url") != spec["url"] or envelope.get("index") != spec["index"]:
        raise ValueError("Protocol v17 snapshot request identity drifted")
    if envelope.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v17 protocol fingerprint mismatch")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v17 snapshot boundaries are unsafe")
    expected_contract_hash = "sha256:" + hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest()
    if envelope.get("provider_contract_sha256") != expected_contract_hash:
        raise ValueError("Protocol v17 provider contract fingerprint mismatch")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Protocol v17 raw payload fingerprint mismatch")
    _, audit = parse_and_audit_csv(kind, raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v17 snapshot audit mismatch")
    core = {key: value for key, value in envelope.items() if key not in {"snapshot_sha256", "vintage_id"}}
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest or not str(envelope.get("vintage_id", "")).endswith(
        digest[:12]
    ):
        raise ValueError("Protocol v17 snapshot fingerprint mismatch")
    return {
        "path": str(path),
        "kind": kind,
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def write_factor_csv(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_bytes())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv(verification["kind"], raw)
    warmup_start = date(2019, 11, 1)
    selected = [row for row in rows if warmup_start <= date.fromisoformat(row["date"]) <= RESERVE_END]
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ts_event", "available_at", "vintage_id", "snapshot_sha256", "vol_close"],
        )
        writer.writeheader()
        for row in selected:
            available = datetime.combine(
                date.fromisoformat(row["date"]) + timedelta(days=1), datetime.min.time(), UTC
            )
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "vol_close": format(float(row["close"]), ".12g"),
                }
            )
    return {
        "schema_version": "research.factor.v17",
        "kind": verification["kind"],
        "output_path": str(output_path),
        "row_count": len(selected),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v17/raw"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--factor-output", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        result = (
            write_factor_csv(args.verify, args.factor_output)
            if args.factor_output
            else verify_snapshot(args.verify)
        )
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

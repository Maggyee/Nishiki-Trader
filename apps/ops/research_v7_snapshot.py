"""Collect and verify immutable official Cboe Protocol v7 history snapshots."""

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

PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v7-data-sources.json")
SCHEMA_VERSION = "research.raw_snapshot.v7"
KINDS = ("vix", "ovx", "gvz")
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


def _contract() -> dict[str, Any]:
    payload = _strict_json(PROVIDER_CONTRACT.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("v7 provider contract must be an object")
    if payload.get("schema_version") != "research.data_sources.v7":
        raise ValueError("v7 provider contract schema drifted")
    if payload.get("status") != "schema_correction_locked_after_fail_closed_probe":
        raise ValueError("v7 provider contract status drifted")
    if payload.get("authentication") != "none":
        raise ValueError("v7 provider must remain credential-free")
    requests = payload.get("requests")
    if not isinstance(requests, list) or [row.get("kind") for row in requests] != list(KINDS):
        raise ValueError("v7 provider contract must lock vix, ovx, gvz in order")
    return payload


def _request(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unsupported v7 kind {kind!r}")
    return next(row for row in _contract()["requests"] if row["kind"] == kind)


def request_plan(kind: str) -> dict[str, Any]:
    spec = _request(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v7",
        "kind": kind,
        "url": spec["url"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "historical_reserve": {"start": RESERVE_START.isoformat(), "end": RESERVE_END.isoformat()},
        "network_accessed": False,
        "data_written": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Nishiki-Trader/research-v7"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _boundaries() -> dict[str, bool]:
    return {
        "credentials_loaded": False,
        "source_policy_mutated": False,
        "testnet_resumed": False,
        "live_path_touched": False,
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
    reserve_count = 0
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
        if RESERVE_START <= session <= RESERVE_END:
            reserve_count += 1
        rows.append({"date": session.isoformat(), "close": close})
    if not rows:
        raise ValueError(f"{kind} history is empty")
    reserve_rows = [
        row for row in rows if RESERVE_START <= date.fromisoformat(row["date"]) <= RESERVE_END
    ]
    if reserve_count < 700:
        raise ValueError(f"{kind} reserve has only {reserve_count} observations")
    if date.fromisoformat(reserve_rows[0]["date"]) > date(2020, 1, 3):
        raise ValueError(f"{kind} reserve starts too late")
    if date.fromisoformat(reserve_rows[-1]["date"]) < date(2022, 12, 29):
        raise ValueError(f"{kind} reserve ends too early")
    audit = {
        "row_count": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "reserve_row_count": reserve_count,
        "reserve_first_date": reserve_rows[0]["date"],
        "reserve_last_date": reserve_rows[-1]["date"],
        "columns": expected,
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
        "provider_contract": str(PROVIDER_CONTRACT),
        "provider_contract_sha256": f"sha256:{hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest()}",
        "url": spec["url"],
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
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = _strict_json(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid v7 snapshot schema")
    kind = str(envelope.get("kind"))
    spec = _request(kind)
    if envelope.get("url") != spec["url"] or envelope.get("index") != spec["index"]:
        raise ValueError("v7 snapshot request identity drifted")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("v7 snapshot boundaries are unsafe")
    expected_contract_hash = f"sha256:{hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest()}"
    if envelope.get("provider_contract_sha256") != expected_contract_hash:
        raise ValueError("v7 provider contract fingerprint mismatch")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != f"sha256:{hashlib.sha256(raw).hexdigest()}":
        raise ValueError("v7 raw payload fingerprint mismatch")
    _, audit = parse_and_audit_csv(kind, raw)
    if envelope.get("audit") != audit:
        raise ValueError("v7 snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if envelope.get("snapshot_sha256") != f"sha256:{digest}":
        raise ValueError("v7 snapshot fingerprint mismatch")
    if not str(envelope.get("vintage_id", "")).endswith(digest[:12]):
        raise ValueError("v7 snapshot vintage mismatch")
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "kind": kind,
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def write_factor_csv(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    envelope = _strict_json(snapshot_path.read_bytes())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_csv(verification["kind"], raw)
    warmup_start = date(2019, 11, 1)
    selected = [
        row for row in rows if warmup_start <= date.fromisoformat(row["date"]) <= RESERVE_END
    ]
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
        "schema_version": "research.factor.v7",
        "kind": verification["kind"],
        "output_path": str(output_path),
        "row_count": len(selected),
        "first_ts_event": selected[0]["date"],
        "last_ts_event": selected[-1]["date"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v7/raw"))
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

"""Collect immutable official DefiLlama options-volume and open-interest snapshots for Protocol v28."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.ops.research_protocol_v28 import PROVIDER_CONTRACT, load_and_validate

SCHEMA_VERSION = "research.raw_snapshot.v28"
KINDS = ("options_notional", "options_premium", "open_interest")
WARMUP_START = date(2019, 11, 1)
DEVELOPMENT_START = date(2020, 1, 1)
DEVELOPMENT_END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(PROVIDER_CONTRACT.read_text())
    if payload.get("schema_version") != "research.data_sources.v28":
        raise ValueError("Protocol v28 provider schema drifted")
    return payload


def _request(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unsupported Protocol v28 kind {kind!r}")
    return next(row for row in _contract()["requests"] if row["kind"] == kind)


def request_plan(kind: str) -> dict[str, Any]:
    spec = _request(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v28",
        "kind": kind,
        "url": spec["url"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "network_accessed": False,
        "data_written": False,
        "values_reported": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": str(_contract()["user_agent"])})
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
        "confirmation_opened": False,
        "future_blind_opened": False,
    }


def _reject_constant(value: str) -> None:
    raise ValueError(f"DefiLlama options/OI JSON contains non-finite constant {value!r}")


def _parse_date(value: Any, *, kind: str, index: int) -> date:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{kind} items[{index}] date must be integer unix seconds")
    try:
        instant = datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{kind} items[{index}] date is invalid") from exc
    if instant.time() != datetime.min.time():
        raise ValueError(f"{kind} items[{index}] date must be UTC midnight")
    return instant.date()


def _amount(value: Any, *, kind: str, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{kind} items[{index}] amount must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{kind} items[{index}] amount must be finite and non-negative")
    return result


def parse_all_json_rows(kind: str, raw: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("DefiLlama options/OI response must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or "totalDataChart" not in payload:
        raise ValueError(f"{kind} root must be an object with totalDataChart")
    chart = payload.get("totalDataChart")
    if not isinstance(chart, list) or not chart:
        raise ValueError(f"{kind} history is empty")
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(chart):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{kind} items[{index}] must be a [date, amount] pair")
        observed = _parse_date(item[0], kind=kind, index=index)
        parsed.append(
            {
                "date": observed.isoformat(),
                "value": _amount(item[1], kind=kind, index=index),
            }
        )
    parsed.sort(key=lambda row: row["date"])
    previous: str | None = None
    for row in parsed:
        if previous is not None and row["date"] <= previous:
            raise ValueError(f"{kind} dates must be unique and increasing")
        previous = row["date"]
    return parsed


def parse_and_audit_json(kind: str, raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed = parse_all_json_rows(kind, raw)
    trailing = [row for row in parsed if date.fromisoformat(row["date"]) > DEVELOPMENT_END]
    rows = [row for row in parsed if date.fromisoformat(row["date"]) <= DEVELOPMENT_END]
    if not rows:
        raise ValueError(f"{kind} has no usable pre-confirmation rows")
    warmup = [
        row for row in rows if WARMUP_START <= date.fromisoformat(row["date"]) < DEVELOPMENT_START
    ]
    development = [
        row
        for row in rows
        if DEVELOPMENT_START <= date.fromisoformat(row["date"]) <= DEVELOPMENT_END
    ]
    if len(development) < 700:
        raise ValueError(f"{kind} development reserve has only {len(development)} observations")
    if len(warmup) < 5:
        raise ValueError(f"{kind} history has fewer than five warmup observations")
    development_dates = [date.fromisoformat(row["date"]) for row in development]
    if development_dates[0] > date(2020, 1, 3):
        raise ValueError(f"{kind} development reserve starts too late")
    if development_dates[-1] < date(2022, 12, 29):
        raise ValueError(f"{kind} development reserve ends too early")
    maximum_gap = max(
        (right - left).days
        for left, right in zip(development_dates, development_dates[1:], strict=False)
    )
    if maximum_gap > 5:
        raise ValueError(f"{kind} development reserve gap exceeds five days")
    return rows, {
        "row_count": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "development_row_count": len(development),
        "development_first_date": development[0]["date"],
        "development_last_date": development[-1]["date"],
        "warmup_row_count": len(warmup),
        "maximum_calendar_gap_days": maximum_gap,
        "trailing_rows_ignored": len(trailing),
        "forward_fill_used": False,
        "interpolation_used": False,
        "confirmation_values_used": False,
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
    _, audit = parse_and_audit_json(kind, raw)
    validation = load_and_validate()
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": validation["protocol_sha256"],
        "provider_contract_sha256": validation["provider_contract_sha256"],
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
        "vintage_id": f"defillama-{kind}:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{kind}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v28 snapshot schema")
    kind = str(envelope.get("kind"))
    spec = _request(kind)
    if envelope.get("url") != spec["url"]:
        raise ValueError("Protocol v28 snapshot request identity drifted")
    validation = load_and_validate()
    if envelope.get("protocol_sha256") != validation["protocol_sha256"]:
        raise ValueError("Protocol v28 protocol fingerprint mismatch")
    if envelope.get("provider_contract_sha256") != validation["provider_contract_sha256"]:
        raise ValueError("Protocol v28 provider fingerprint mismatch")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v28 snapshot boundaries are unsafe")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Protocol v28 raw payload fingerprint mismatch")
    _, audit = parse_and_audit_json(kind, raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v28 snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest or not str(
        envelope.get("vintage_id", "")
    ).endswith(digest[:12]):
        raise ValueError("Protocol v28 snapshot fingerprint mismatch")
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
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_json(verification["kind"], raw)
    selected = [
        row for row in rows if WARMUP_START <= date.fromisoformat(row["date"]) <= DEVELOPMENT_END
    ]
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
                "amount",
            ],
        )
        writer.writeheader()
        for row in selected:
            observed = date.fromisoformat(row["date"])
            available = datetime.combine(observed + timedelta(days=2), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "observation_date": observed.isoformat(),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "amount": format(float(row["value"]), ".12g"),
                }
            )
    return {
        "kind": verification["kind"],
        "path": str(output_path),
        "sha256": "sha256:" + hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "row_count": len(selected),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v28/raw"))
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

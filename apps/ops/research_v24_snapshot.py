"""Collect one immutable official Fear and Greed snapshot for Protocol v24."""

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
from zoneinfo import ZoneInfo

from apps.ops.research_protocol_v24 import (
    ALLOWED_CLASSIFICATIONS,
    PROVIDER_CONTRACT,
    load_and_validate,
)

SCHEMA_VERSION = "research.raw_snapshot.v24"
KIND = "fng"
WARMUP_START = date(2019, 11, 1)
DEVELOPMENT_START = date(2020, 1, 1)
DEVELOPMENT_END = date(2022, 12, 31)
NY = ZoneInfo("America/New_York")
REQUIRED_ITEM_FIELDS = ("value", "value_classification", "timestamp")
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(PROVIDER_CONTRACT.read_text())
    if payload.get("schema_version") != "research.data_sources.v24":
        raise ValueError("Protocol v24 provider schema drifted")
    return payload


def request_plan() -> dict[str, Any]:
    spec = _contract()["request"]
    return {
        "schema_version": "research.snapshot.request_plan.v24",
        "kind": KIND,
        "url": spec["url"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "network_accessed": False,
        "data_written": False,
        "values_reported": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    user_agent = str(_contract()["user_agent"])
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
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
    raise ValueError(f"Fear and Greed JSON contains non-finite constant {value!r}")


def _parse_timestamp(value: Any, *, index: int) -> date:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"data[{index}] timestamp must be an integer unix seconds string")
    raw = str(value).strip()
    if not raw.isdigit():
        raise ValueError(f"data[{index}] timestamp must be unix seconds")
    try:
        instant = datetime.fromtimestamp(int(raw), UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"data[{index}] timestamp is invalid") from exc
    return instant.astimezone(NY).date()


def _parse_value(value: Any, *, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"data[{index}] value must be an integer string")
    raw = str(value).strip()
    if not raw.isdigit():
        raise ValueError(f"data[{index}] value must be a non-negative integer string")
    result = int(raw)
    if result < 0 or result > 100:
        raise ValueError(f"data[{index}] value must be between 0 and 100")
    return result


def parse_and_audit_json(raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        payload = json.loads(raw, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Fear and Greed response must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Fear and Greed JSON root must be an object")
    if payload.get("name") != "Fear and Greed Index":
        raise ValueError("Fear and Greed name drifted")
    items = payload.get("data")
    if not isinstance(items, list) or not items:
        raise ValueError("Fear and Greed history is empty")
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or any(field not in item for field in REQUIRED_ITEM_FIELDS):
            raise ValueError(f"data[{index}] is missing locked fields")
        classification = item.get("value_classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"data[{index}] classification {classification!r} is not locked")
        parsed.append(
            {
                "date": _parse_timestamp(item.get("timestamp"), index=index).isoformat(),
                "value": _parse_value(item.get("value"), index=index),
                "classification": classification,
            }
        )
    parsed.sort(key=lambda row: row["date"])
    previous: str | None = None
    for row in parsed:
        if previous is not None and row["date"] <= previous:
            raise ValueError("Fear and Greed observation dates must be unique and increasing")
        previous = row["date"]
    trailing = [row for row in parsed if date.fromisoformat(row["date"]) > DEVELOPMENT_END]
    usable = [
        row for row in parsed if date.fromisoformat(row["date"]) <= DEVELOPMENT_END
    ]
    warmup = [
        row for row in usable if WARMUP_START <= date.fromisoformat(row["date"]) < DEVELOPMENT_START
    ]
    development = [
        row
        for row in usable
        if DEVELOPMENT_START <= date.fromisoformat(row["date"]) <= DEVELOPMENT_END
    ]
    if len(development) < 700:
        raise ValueError(f"development reserve has only {len(development)} observations")
    if len(warmup) < 5:
        raise ValueError("history has fewer than five warmup observations")
    development_dates = [date.fromisoformat(row["date"]) for row in development]
    if development_dates[0] > date(2020, 1, 3):
        raise ValueError("development reserve starts too late")
    if development_dates[-1] < date(2022, 12, 29):
        raise ValueError("development reserve ends too early")
    maximum_gap = max(
        (right - left).days
        for left, right in zip(development_dates, development_dates[1:], strict=False)
    )
    if maximum_gap > 5:
        raise ValueError("development reserve gap exceeds five days")
    return usable, {
        "row_count": len(usable),
        "first_date": usable[0]["date"],
        "last_date": usable[-1]["date"],
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
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    spec = _contract()["request"]
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(spec["url"])
    if not raw:
        raise ValueError("Fear and Greed returned an empty response")
    _, audit = parse_and_audit_json(raw)
    validation = load_and_validate()
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
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
        "vintage_id": f"alternative-fng:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{KIND}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v24 snapshot schema")
    spec = _contract()["request"]
    if envelope.get("url") != spec["url"] or envelope.get("kind") != KIND:
        raise ValueError("Protocol v24 snapshot request identity drifted")
    validation = load_and_validate()
    if envelope.get("protocol_sha256") != validation["protocol_sha256"]:
        raise ValueError("Protocol v24 protocol fingerprint mismatch")
    if envelope.get("provider_contract_sha256") != validation["provider_contract_sha256"]:
        raise ValueError("Protocol v24 provider fingerprint mismatch")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v24 snapshot boundaries are unsafe")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Protocol v24 raw payload fingerprint mismatch")
    _, audit = parse_and_audit_json(raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v24 snapshot audit mismatch")
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
        raise ValueError("Protocol v24 snapshot fingerprint mismatch")
    return {
        "path": str(path),
        "kind": KIND,
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def write_factor_csv(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_text())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_json(raw)
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
                "fear_greed_value",
                "value_classification",
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
                    "fear_greed_value": str(int(row["value"])),
                    "value_classification": row["classification"],
                }
            )
    return {
        "kind": KIND,
        "path": str(output_path),
        "sha256": "sha256:" + hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "row_count": len(selected),
        "first_date": selected[0]["date"],
        "last_date": selected[-1]["date"],
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v24/raw"))
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
    elif args.dry_run:
        result = request_plan()
    else:
        path, result = collect_snapshot(output_dir=args.output_dir)
        result = {**result, "path": str(path)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

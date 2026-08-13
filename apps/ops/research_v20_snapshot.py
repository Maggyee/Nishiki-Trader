"""Collect one immutable official OFR FSI snapshot for Protocol v20."""

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

from apps.ops.research_protocol_v20 import (
    PROVIDER_CONTRACT,
    SERIES_KEYS,
    load_and_validate,
)

SCHEMA_VERSION = "research.raw_snapshot.v20"
WARMUP_START = date(2019, 11, 1)
DEVELOPMENT_START = date(2020, 1, 1)
DEVELOPMENT_END = date(2022, 12, 31)
REQUIRED_SERIES = tuple(SERIES_KEYS.values())
FACTOR_COLUMNS = {
    "OFRFSI": "ofr_fsi",
    "Credit": "credit_stress",
    "Flight_to_Safety": "safe_asset_stress",
}
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(PROVIDER_CONTRACT.read_text())
    if payload.get("schema_version") != "research.data_sources.v20":
        raise ValueError("v20 provider contract schema drifted")
    if payload.get("status") != "locked_before_ofr_fsi_body_access":
        raise ValueError("v20 provider contract status drifted")
    if payload.get("authentication") != "none":
        raise ValueError("v20 provider must remain credential-free")
    request = payload.get("request", {})
    if request.get("method") != "GET" or request.get("maximum_body_openings") != 1:
        raise ValueError("v20 provider request budget drifted")
    if request.get("required_series") != list(REQUIRED_SERIES):
        raise ValueError("v20 required OFR series drifted")
    coverage = payload.get("coverage_gates", {})
    if coverage != {
        "warmup_start": "2019-11-01",
        "development_start": "2020-01-01",
        "development_end": "2022-12-31",
        "minimum_development_observations": 700,
        "first_development_observation_no_later_than": "2020-01-03",
        "last_development_observation_no_earlier_than": "2022-12-29",
        "maximum_calendar_gap_days": 5,
        "common_timestamps_required": True,
        "forward_fill_allowed": False,
    }:
        raise ValueError("v20 coverage gates drifted")
    return payload


def request_plan() -> dict[str, Any]:
    request = _contract()["request"]
    return {
        "schema_version": "research.snapshot.request_plan.v20",
        "url": request["url"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "required_series": list(REQUIRED_SERIES),
        "network_accessed": False,
        "data_written": False,
        "values_reported": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v20"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        content_type = response.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError(f"OFR response content type {content_type!r} is not application/json")
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
    raise ValueError(f"OFR JSON contains non-finite constant {value!r}")


def _parse_timestamp(value: Any, *, series: str, index: int) -> date:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{series} data[{index}] timestamp must be integer epoch_ms")
    try:
        instant = datetime.fromtimestamp(value / 1000, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{series} data[{index}] timestamp is invalid") from exc
    if instant.time() != datetime.min.time():
        raise ValueError(f"{series} data[{index}] timestamp must be UTC midnight")
    return instant.date()


def _finite(value: Any, *, series: str, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{series} data[{index}] value must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{series} data[{index}] value must be finite")
    return result


def parse_and_audit_json(raw: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        payload = json.loads(raw, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OFR FSI response must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("OFR FSI JSON root must be an object")

    values_by_series: dict[str, list[tuple[date, float]]] = {}
    names: dict[str, str] = {}
    for series in REQUIRED_SERIES:
        series_payload = payload.get(series)
        if not isinstance(series_payload, dict):
            raise ValueError(f"OFR FSI series {series!r} is missing or not an object")
        name = series_payload.get("name")
        points = series_payload.get("data")
        if not isinstance(name, str) or not name.strip() or not isinstance(points, list):
            raise ValueError(f"OFR FSI series {series!r} must contain name and data")
        parsed: list[tuple[date, float]] = []
        previous: date | None = None
        for index, point in enumerate(points):
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"{series} data[{index}] must be [epoch_ms, value]")
            observation = _parse_timestamp(point[0], series=series, index=index)
            if previous is not None and observation <= previous:
                raise ValueError(f"{series} timestamps must be unique and increasing")
            previous = observation
            parsed.append((observation, _finite(point[1], series=series, index=index)))
        if not parsed:
            raise ValueError(f"OFR FSI series {series!r} is empty")
        names[series] = name
        values_by_series[series] = parsed

    timestamp_lists = {
        series: [observation for observation, _ in points]
        for series, points in values_by_series.items()
    }
    reference = timestamp_lists[REQUIRED_SERIES[0]]
    if any(timestamp_lists[series] != reference for series in REQUIRED_SERIES[1:]):
        raise ValueError("required OFR FSI series do not share identical timestamps")

    development_dates = [
        observation
        for observation in reference
        if DEVELOPMENT_START <= observation <= DEVELOPMENT_END
    ]
    if len(development_dates) < 700:
        raise ValueError(
            f"OFR development reserve has only {len(development_dates)} observations"
        )
    if development_dates[0] > date(2020, 1, 3):
        raise ValueError("OFR development reserve starts too late")
    if development_dates[-1] < date(2022, 12, 29):
        raise ValueError("OFR development reserve ends too early")
    maximum_gap = max(
        (later - earlier).days
        for earlier, later in zip(
            development_dates[:-1], development_dates[1:], strict=True
        )
    )
    if maximum_gap > 5:
        raise ValueError(f"OFR development reserve gap exceeds 5 days: {maximum_gap}")
    warmup_dates = [
        observation
        for observation in reference
        if WARMUP_START <= observation < DEVELOPMENT_START
    ]
    if len(warmup_dates) < 5:
        raise ValueError("OFR development reserve has fewer than five warmup observations")

    lookup = {
        series: dict(points)
        for series, points in values_by_series.items()
    }
    selected_dates = [
        observation
        for observation in reference
        if WARMUP_START <= observation <= DEVELOPMENT_END
    ]
    rows = [
        {
            "date": observation.isoformat(),
            **{
                FACTOR_COLUMNS[series]: lookup[series][observation]
                for series in REQUIRED_SERIES
            },
        }
        for observation in selected_dates
    ]
    audit = {
        "series_keys": list(REQUIRED_SERIES),
        "series_names": names,
        "series_row_counts": {
            series: len(values_by_series[series]) for series in REQUIRED_SERIES
        },
        "common_timestamps": True,
        "development_row_count": len(development_dates),
        "development_first_date": development_dates[0].isoformat(),
        "development_last_date": development_dates[-1].isoformat(),
        "maximum_calendar_gap_days": maximum_gap,
        "warmup_row_count": len(warmup_dates),
        "forward_fill_used": False,
    }
    return rows, audit


def collect_snapshot(
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    request = _contract()["request"]
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    raw = fetch(request["url"])
    if not raw:
        raise ValueError("OFR FSI returned an empty response")
    _, audit = parse_and_audit_json(raw)
    core = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": load_and_validate()["protocol_sha256"],
        "provider_contract": str(PROVIDER_CONTRACT),
        "provider_contract_sha256": "sha256:"
        + hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest(),
        "url": request["url"],
        "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        "audit": audit,
        "boundaries": _boundaries(),
    }
    digest = hashlib.sha256(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": "sha256:" + digest,
        "vintage_id": f"ofr-fsi:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"fsi-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_bytes())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v20 snapshot schema")
    request = _contract()["request"]
    if envelope.get("url") != request["url"]:
        raise ValueError("Protocol v20 snapshot request identity drifted")
    if envelope.get("protocol_sha256") != load_and_validate()["protocol_sha256"]:
        raise ValueError("Protocol v20 protocol fingerprint mismatch")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v20 snapshot boundaries are unsafe")
    expected_contract_hash = "sha256:" + hashlib.sha256(PROVIDER_CONTRACT.read_bytes()).hexdigest()
    if envelope.get("provider_contract_sha256") != expected_contract_hash:
        raise ValueError("Protocol v20 provider contract fingerprint mismatch")
    raw = base64.b64decode(str(envelope.get("payload_raw_base64")), validate=True)
    if envelope.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("Protocol v20 raw payload fingerprint mismatch")
    _, audit = parse_and_audit_json(raw)
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v20 snapshot audit mismatch")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"snapshot_sha256", "vintage_id"}
    }
    digest = hashlib.sha256(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if envelope.get("snapshot_sha256") != "sha256:" + digest or not str(
        envelope.get("vintage_id", "")
    ).endswith(digest[:12]):
        raise ValueError("Protocol v20 snapshot fingerprint mismatch")
    return {
        "path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def write_factor_csv(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_bytes())
    raw = base64.b64decode(envelope["payload_raw_base64"], validate=True)
    rows, _ = parse_and_audit_json(raw)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts_event",
        "available_at",
        "vintage_id",
        "snapshot_sha256",
        *FACTOR_COLUMNS.values(),
    ]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            available = datetime.combine(
                date.fromisoformat(row["date"]) + timedelta(days=5),
                datetime.min.time(),
                UTC,
            )
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    **{
                        column: format(float(row[column]), ".12g")
                        for column in FACTOR_COLUMNS.values()
                    },
                }
            )
    return {
        "schema_version": "research.factor.v20",
        "output_path": str(output_path),
        "row_count": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "publication_lag_calendar_days": 5,
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v20/raw"))
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

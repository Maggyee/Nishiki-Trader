"""Collect and qualify one immutable FRED development snapshot for Protocol v21."""

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

from apps.ops.research_protocol_v21 import (
    PROVIDER_CONTRACT,
    SERIES_IDS,
    load_and_validate,
)

SCHEMA_VERSION = "research.raw_snapshot.v21"
WARMUP_START = date(2019, 10, 1)
DEVELOPMENT_START = date(2020, 1, 1)
DEVELOPMENT_END = date(2022, 12, 31)
Fetch = Callable[[str], bytes]


def _contract() -> dict[str, Any]:
    load_and_validate()
    payload = json.loads(PROVIDER_CONTRACT.read_text())
    if payload.get("schema_version") != "research.data_sources.v21":
        raise ValueError("Protocol v21 provider schema drifted")
    return payload


def request_specs() -> list[dict[str, str]]:
    contract = _contract()
    base = str(contract["base_url"])
    specs: list[dict[str, str]] = []
    for row in contract["requests"]:
        params = {
            "id": str(row["series_id"]),
            "cosd": str(row["cosd"]),
            "coed": str(row["coed"]),
        }
        specs.append(
            {
                "series_id": str(row["series_id"]),
                "url": base + "?" + urllib.parse.urlencode(params),
            }
        )
    return specs


def request_plan() -> dict[str, Any]:
    return {
        "schema_version": "research.snapshot.request_plan.v21",
        "requests": request_specs(),
        "network_accessed": False,
        "data_written": False,
        "values_reported": False,
        "boundaries": _boundaries(),
    }


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-v21"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        content_type = response.headers.get_content_type()
        if content_type not in {"text/csv", "application/csv", "application/octet-stream"}:
            disposition = response.headers.get("Content-Disposition", "").lower()
            if "csv" not in disposition:
                raise ValueError(f"FRED response content type {content_type!r} is not CSV")
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


def parse_series_csv(raw: bytes, *, series_id: str) -> dict[date, float]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"FRED {series_id} response must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != ["observation_date", series_id]:
        raise ValueError(f"FRED {series_id} header must be observation_date,{series_id}")
    values: dict[date, float] = {}
    previous: date | None = None
    for index, row in enumerate(reader):
        try:
            observed = date.fromisoformat(str(row["observation_date"]).strip())
        except ValueError as exc:
            raise ValueError(f"FRED {series_id} row {index} date is invalid") from exc
        if previous is not None and observed <= previous:
            raise ValueError(f"FRED {series_id} dates must be unique and increasing")
        previous = observed
        raw_value = str(row[series_id]).strip()
        if raw_value == ".":
            continue
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"FRED {series_id} row {index} value is invalid") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"FRED {series_id} values must be finite and nonnegative")
        values[observed] = value
    if not values:
        raise ValueError(f"FRED {series_id} contains no numeric observations")
    return values


def combine_and_audit(
    payloads: list[tuple[dict[str, str], bytes]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(payloads) != len(SERIES_IDS):
        raise ValueError("Protocol v21 requires exactly three FRED payloads")
    parsed: dict[str, dict[date, float]] = {}
    raw_counts: dict[str, int] = {}
    for spec, raw in payloads:
        series_id = spec["series_id"]
        if series_id in parsed or series_id not in SERIES_IDS:
            raise ValueError("Protocol v21 FRED request identity duplicated or unknown")
        parsed[series_id] = parse_series_csv(raw, series_id=series_id)
        raw_counts[series_id] = len(parsed[series_id])
    if set(parsed) != set(SERIES_IDS):
        raise ValueError("Protocol v21 FRED series set is incomplete")
    common_dates = sorted(set.intersection(*(set(parsed[key]) for key in SERIES_IDS)))
    selected = [day for day in common_dates if WARMUP_START <= day <= DEVELOPMENT_END]
    warmup = [day for day in selected if day < DEVELOPMENT_START]
    development = [day for day in selected if day >= DEVELOPMENT_START]
    if len(development) < 150:
        raise ValueError(
            f"Protocol v21 has only {len(development)} common development observations"
        )
    if len(warmup) < 8:
        raise ValueError("Protocol v21 has fewer than eight common warmup observations")
    if development[0] > date(2020, 1, 8):
        raise ValueError("Protocol v21 common development coverage starts too late")
    if development[-1] < date(2022, 12, 28):
        raise ValueError("Protocol v21 common development coverage ends too early")
    maximum_gap = max(
        (right - left).days for left, right in zip(development, development[1:], strict=False)
    )
    if maximum_gap > 14:
        raise ValueError(
            f"Protocol v21 common development gap exceeds fourteen days: {maximum_gap}"
        )
    rows = []
    for day in selected:
        walcl = parsed["WALCL"][day]
        tga = parsed["WDTGAL"][day]
        rrp_billions = parsed["RRPONTSYD"][day]
        rows.append(
            {
                "observation_date": day.isoformat(),
                "walcl_millions": walcl,
                "wdtgal_millions": tga,
                "rrpontsyd_billions": rrp_billions,
                "net_liquidity_millions": walcl - tga - 1000.0 * rrp_billions,
            }
        )
    return rows, {
        "series_numeric_row_counts": raw_counts,
        "common_row_count": len(selected),
        "development_common_row_count": len(development),
        "warmup_common_row_count": len(warmup),
        "first_development_observation": development[0].isoformat(),
        "last_development_observation": development[-1].isoformat(),
        "maximum_common_calendar_gap_days": maximum_gap,
        "common_timestamp_join": "exact_observation_date_intersection",
        "forward_fill_used": False,
        "interpolation_used": False,
    }


def collect_snapshot(
    *, output_dir: Path, fetch: Fetch = _fetch, now: datetime | None = None
) -> tuple[Path, dict[str, Any]]:
    retrieved = (now or datetime.now(UTC)).astimezone(UTC)
    specs = request_specs()
    payloads = [(spec, fetch(spec["url"])) for spec in specs]
    if any(not raw for _, raw in payloads):
        raise ValueError("Protocol v21 received an empty FRED response")
    _, audit = combine_and_audit(payloads)
    records = [
        {
            **spec,
            "payload_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
        }
        for spec, raw in payloads
    ]
    validation = load_and_validate()
    core = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
        "protocol_sha256": validation["protocol_sha256"],
        "provider_contract_sha256": validation["provider_contract_sha256"],
        "requests": records,
        "audit": audit,
        "boundaries": _boundaries(),
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    envelope = {
        **core,
        "snapshot_sha256": "sha256:" + digest,
        "vintage_id": f"fred-us-net-liquidity:{retrieved.isoformat()}:{digest[:12]}",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (
        f"fred-us-net-liquidity-{retrieved.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}.json"
    )
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path, verify_snapshot(path)


def _payloads_from_envelope(envelope: dict[str, Any]) -> list[tuple[dict[str, str], bytes]]:
    specs = request_specs()
    records = envelope.get("requests")
    if not isinstance(records, list) or len(records) != len(specs):
        raise ValueError("Protocol v21 snapshot request count mismatch")
    payloads: list[tuple[dict[str, str], bytes]] = []
    for expected, record in zip(specs, records, strict=True):
        if any(record.get(key) != expected[key] for key in ("series_id", "url")):
            raise ValueError("Protocol v21 snapshot request identity drifted")
        raw = base64.b64decode(str(record.get("payload_raw_base64")), validate=True)
        if record.get("payload_sha256") != "sha256:" + hashlib.sha256(raw).hexdigest():
            raise ValueError("Protocol v21 raw FRED payload fingerprint mismatch")
        payloads.append((expected, raw))
    return payloads


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid Protocol v21 snapshot schema")
    validation = load_and_validate()
    if envelope.get("protocol_sha256") != validation["protocol_sha256"]:
        raise ValueError("Protocol v21 protocol fingerprint mismatch")
    if envelope.get("provider_contract_sha256") != validation["provider_contract_sha256"]:
        raise ValueError("Protocol v21 provider fingerprint mismatch")
    if envelope.get("boundaries") != _boundaries():
        raise ValueError("Protocol v21 snapshot boundaries are unsafe")
    _, audit = combine_and_audit(_payloads_from_envelope(envelope))
    if envelope.get("audit") != audit:
        raise ValueError("Protocol v21 snapshot audit mismatch")
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
        raise ValueError("Protocol v21 snapshot fingerprint mismatch")
    return {
        "path": str(path),
        "snapshot_sha256": envelope["snapshot_sha256"],
        "vintage_id": envelope["vintage_id"],
        "audit": audit,
        "valid": True,
    }


def write_factor_csv(snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    envelope = json.loads(snapshot_path.read_text())
    rows, _ = combine_and_audit(_payloads_from_envelope(envelope))
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts_event",
        "available_at",
        "observation_date",
        "vintage_id",
        "snapshot_sha256",
        "walcl_millions",
        "wdtgal_millions",
        "rrpontsyd_billions",
        "net_liquidity_millions",
    ]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            observed = date.fromisoformat(row["observation_date"])
            available = datetime.combine(observed + timedelta(days=7), datetime.min.time(), UTC)
            writer.writerow(
                {
                    "ts_event": int(available.timestamp() * 1_000_000_000),
                    "available_at": available.isoformat().replace("+00:00", "Z"),
                    "observation_date": observed.isoformat(),
                    "vintage_id": envelope["vintage_id"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    **{
                        key: format(float(row[key]), ".12g")
                        for key in (
                            "walcl_millions",
                            "wdtgal_millions",
                            "rrpontsyd_billions",
                            "net_liquidity_millions",
                        )
                    },
                }
            )
    factor_hash = "sha256:" + hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "path": str(output_path),
        "sha256": factor_hash,
        "row_count": len(rows),
        "snapshot_sha256": verification["snapshot_sha256"],
    }


def write_qualification(
    snapshot_path: Path, factor: dict[str, Any], output_path: Path
) -> dict[str, Any]:
    verification = verify_snapshot(snapshot_path)
    validation = load_and_validate()
    result = {
        "schema_version": "research.v21.provider_qualification.v1",
        "classification": "provider_qualified",
        "protocol_sha256": validation["protocol_sha256"],
        "provider_contract_sha256": validation["provider_contract_sha256"],
        "snapshot": {
            "path": str(snapshot_path),
            "snapshot_sha256": verification["snapshot_sha256"],
            "vintage_id": verification["vintage_id"],
        },
        "factor": factor,
        "audit": verification["audit"],
        "historical_vintage_claim": False,
        "boundaries": {
            "network_accessed": True,
            "factor_values_reported": False,
            "signals_generated": False,
            "pnl_opened": False,
            "confirmation_opened": False,
            "source_policy_mutated": False,
            "trading_touched": False,
            "future_blind_opened": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v21/raw"))
    parser.add_argument("--factor-output", type=Path)
    parser.add_argument("--qualification-output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True))
        return 0
    if args.dry_run:
        print(json.dumps(request_plan(), indent=2, sort_keys=True))
        return 0
    if (args.factor_output is None) != (args.qualification_output is None):
        parser.error("--factor-output and --qualification-output must be supplied together")
    path, result = collect_snapshot(output_dir=args.output_dir)
    if args.factor_output is not None and args.qualification_output is not None:
        factor = write_factor_csv(path, args.factor_output)
        qualification = write_qualification(path, factor, args.qualification_output)
        result = {**result, "factor": factor, "classification": qualification["classification"]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

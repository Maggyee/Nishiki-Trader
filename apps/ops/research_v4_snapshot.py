"""Collect immutable, credential-free Research Protocol v4 qualification snapshots."""

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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.raw_snapshot.v1"
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v4-data-sources.json")
PROVIDER_CONTRACT_SHA256 = (
    "sha256:ed79e3e9e30c422808336a08b5d9cb2f32212fb1c0f89ec6793a00c8b2851ff0"
)
QUALIFICATION_START = date(2026, 7, 1)
QUALIFICATION_END = date(2026, 7, 31)
KINDS = ("broad_usd", "vix")

_BOUNDARIES = {
    "credentials_loaded": False,
    "pnl_computed": False,
    "signal_store_written": False,
    "nautilus_run": False,
    "source_policy_mutated": False,
    "testnet_resumed": False,
    "live_path_touched": False,
}


@dataclass(frozen=True)
class RequestSpec:
    name: str
    url: str
    params: dict[str, str]
    series_id: str

    @property
    def full_url(self) -> str:
        return f"{self.url}?{urllib.parse.urlencode(self.params)}"


_REQUESTS = {
    "broad_usd": RequestSpec(
        name="fred_dtwexbgs_july_2026",
        url="https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": "DTWEXBGS", "cosd": "2026-07-01", "coed": "2026-07-31"},
        series_id="DTWEXBGS",
    ),
    "vix": RequestSpec(
        name="fred_vixcls_july_2026",
        url="https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": "VIXCLS", "cosd": "2026-07-01", "coed": "2026-07-31"},
        series_id="VIXCLS",
    ),
}

Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v4"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _strict_json_loads(raw: bytes | str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON numeric constant {value!r} is forbidden")

    return json.loads(raw, parse_constant=reject_constant)


def _load_provider_contract() -> dict[str, Any]:
    raw = PROVIDER_CONTRACT.read_bytes()
    actual_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if actual_hash != PROVIDER_CONTRACT_SHA256:
        raise ValueError("Research Protocol v4 provider contract fingerprint drifted")
    payload = _strict_json_loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Research Protocol v4 provider contract must be an object")
    if payload.get("schema_version") != "research.data_sources.v4":
        raise ValueError("Research Protocol v4 provider contract schema drifted")
    if payload.get("status") != "provider_recovery_locked_before_direct_csv_access":
        raise ValueError("provider contract must be locked before direct CSV access")
    envelope = payload.get("snapshot_envelope")
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("provider contract snapshot envelope drifted")
    if payload.get("boundaries") != _BOUNDARIES:
        raise ValueError("provider contract boundaries are missing or unsafe")
    providers = payload.get("providers")
    if not isinstance(providers, dict) or set(providers) != set(KINDS):
        raise ValueError("provider contract must contain exactly broad_usd and vix")
    for kind, spec in _REQUESTS.items():
        provider = providers.get(kind)
        if not isinstance(provider, dict) or provider.get("authentication") != "none":
            raise ValueError(f"{kind} provider must remain credential-free")
        requests = provider.get("requests")
        if not isinstance(requests, list) or len(requests) != 1:
            raise ValueError(f"{kind} provider must define exactly one request")
        expected = {"name": spec.name, "url": spec.url, "params": spec.params}
        if requests[0] != expected:
            raise ValueError(f"{kind} request differs from the locked provider contract")
        if provider.get("locked_fields") != ["observation_date", spec.series_id]:
            raise ValueError(f"{kind} locked CSV fields drifted")
    return payload


def build_requests(kind: str) -> list[RequestSpec]:
    if kind not in KINDS:
        raise ValueError(f"unsupported Research Protocol v4 snapshot kind {kind!r}")
    _load_provider_contract()
    return [_REQUESTS[kind]]


def request_plan(kind: str) -> dict[str, Any]:
    specs = build_requests(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v1",
        "kind": kind,
        "provider_contract": str(PROVIDER_CONTRACT),
        "requests": [
            {"name": spec.name, "url": spec.full_url, "payload_format": "csv"}
            for spec in specs
        ],
        "qualification_window": {
            "start": QUALIFICATION_START.isoformat(),
            "end": QUALIFICATION_END.isoformat(),
            "use": "schema_lineage_freshness_only",
        },
        "boundaries": dict(_BOUNDARIES),
        "network_accessed": False,
        "data_written": False,
    }


def _ensure_qualification_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("snapshot time must be timezone-aware")
    utc_value = value.astimezone(UTC)
    if not QUALIFICATION_START <= utc_value.date() <= QUALIFICATION_END:
        raise ValueError("v4 snapshot collection must stay within July 2026 qualification")
    return utc_value


def _parse_csv(raw: bytes, *, spec: RequestSpec) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{spec.name} must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    expected = ["observation_date", spec.series_id]
    if reader.fieldnames != expected:
        raise ValueError(f"{spec.name} CSV header must be exactly {expected}")
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row or set(row) != set(expected) or any(value is None for value in row.values()):
            raise ValueError(f"{spec.name} CSV row does not match its header")
        if not any(str(value).strip() for value in row.values()):
            continue
        rows.append({field: str(row[field]).strip() for field in expected})
    if not rows:
        raise ValueError(f"{spec.name} CSV must contain at least one data row")
    return {"columns": expected, "rows": rows}


def _validate_payload(
    kind: str,
    payload: Any,
    *,
    retrieved_at: datetime,
) -> dict[str, Any]:
    spec = _REQUESTS[kind]
    if not isinstance(payload, dict):
        raise ValueError(f"FRED {kind} parsed payload must be an object")
    columns = payload.get("columns")
    rows = payload.get("rows")
    if columns != ["observation_date", spec.series_id]:
        raise ValueError(f"FRED {kind} columns differ from the provider contract")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"FRED {kind} rows must be non-empty")

    days: list[date] = []
    observed_days: list[date] = []
    missing_count = 0
    previous: date | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or list(row) != list(columns):
            raise ValueError(f"FRED {kind} row does not match its header")
        try:
            observation_day = date.fromisoformat(str(row["observation_date"]))
        except ValueError as exc:
            raise ValueError(f"FRED {kind} observation_date must use YYYY-MM-DD") from exc
        if not QUALIFICATION_START <= observation_day <= QUALIFICATION_END:
            raise ValueError(f"FRED {kind} contains a row outside July 2026 qualification")
        if observation_day > retrieved_at.date():
            raise ValueError(f"FRED {kind} contains a future observation")
        if previous is not None and observation_day <= previous:
            raise ValueError(f"FRED {kind} dates must be unique and increasing")
        previous = observation_day
        raw_value = str(row[spec.series_id])
        if raw_value == ".":
            missing_count += 1
        else:
            try:
                value = float(raw_value)
            except ValueError as exc:
                raise ValueError(f"FRED {kind} row {index} must be numeric or '.'") from exc
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"FRED {kind} row {index} must be finite and positive")
            observed_days.append(observation_day)
        days.append(observation_day)
    if len(observed_days) < 2:
        raise ValueError(f"FRED {kind} needs at least two observed rows")
    return {
        "series_id": spec.series_id,
        "row_count": len(days),
        "observed_row_count": len(observed_days),
        "missing_value_row_count": missing_count,
        "first_row_date": days[0].isoformat(),
        "last_row_date": days[-1].isoformat(),
        "first_observed_date": observed_days[0].isoformat(),
        "last_observed_date": observed_days[-1].isoformat(),
        "available_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "availability_rule": "snapshot_retrieved_at_then_later_utc_decision_boundary",
    }


def collect_snapshot(
    kind: str,
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    retrieved_at = _ensure_qualification_time(now or datetime.now(UTC))
    spec = build_requests(kind)[0]
    raw = fetch(spec.full_url)
    if not raw:
        raise ValueError(f"{spec.name} returned an empty response")
    payload = _parse_csv(raw, spec=spec)
    audit = _validate_payload(kind, payload, retrieved_at=retrieved_at)
    requests = [
        {
            "name": spec.name,
            "url": spec.full_url,
            "payload_format": "csv",
            "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
            "payload": payload,
        }
    ]
    core = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "provider_contract": str(PROVIDER_CONTRACT),
        "requests": requests,
        "audit": audit,
        "boundaries": dict(_BOUNDARIES),
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    snapshot_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    envelope = {
        **core,
        "vintage_id": f"{kind}:{core['retrieved_at']}:{snapshot_hash[7:19]}",
        "snapshot_sha256": snapshot_hash,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{kind}-{stamp}-{snapshot_hash[7:19]}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return path, envelope


def verify_snapshot(path: Path) -> dict[str, Any]:
    envelope = _strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("snapshot must be a research.raw_snapshot.v1 object")
    kind = str(envelope.get("kind", ""))
    spec = build_requests(kind)[0]
    if envelope.get("provider_contract") != str(PROVIDER_CONTRACT):
        raise ValueError("snapshot provider contract path drifted")
    if envelope.get("boundaries") != _BOUNDARIES:
        raise ValueError("snapshot boundaries are missing or unsafe")
    try:
        retrieved_at = datetime.fromisoformat(
            str(envelope["retrieved_at"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as exc:
        raise ValueError("snapshot retrieved_at is invalid") from exc
    retrieved_at = _ensure_qualification_time(retrieved_at)
    requests = envelope.get("requests")
    if not isinstance(requests, list) or len(requests) != 1:
        raise ValueError("snapshot request count differs from the provider contract")
    request = requests[0]
    if not isinstance(request, dict):
        raise ValueError("snapshot request must be an object")
    if request.get("name") != spec.name or request.get("url") != spec.full_url:
        raise ValueError("snapshot request identity differs from the provider contract")
    if request.get("payload_format") != "csv":
        raise ValueError("snapshot payload format differs from the provider contract")
    try:
        raw = base64.b64decode(request["payload_raw_base64"], validate=True)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{spec.name} raw payload is missing or invalid base64") from exc
    expected_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if request.get("payload_sha256") != expected_hash:
        raise ValueError(f"{spec.name} raw payload hash mismatch")
    parsed = _parse_csv(raw, spec=spec)
    if parsed != request.get("payload"):
        raise ValueError(f"{spec.name} parsed payload differs from raw bytes")
    audit = _validate_payload(kind, parsed, retrieved_at=retrieved_at)
    if envelope.get("audit") != audit:
        raise ValueError("snapshot audit summary differs from raw payload")
    core = {
        key: value
        for key, value in envelope.items()
        if key not in {"vintage_id", "snapshot_sha256"}
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    snapshot_hash = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    if envelope.get("snapshot_sha256") != snapshot_hash:
        raise ValueError("snapshot envelope hash mismatch")
    vintage = f"{kind}:{envelope['retrieved_at']}:{snapshot_hash[7:19]}"
    if envelope.get("vintage_id") != vintage:
        raise ValueError("snapshot vintage_id does not match the envelope hash")
    if snapshot_hash[7:19] not in path.name:
        raise ValueError("snapshot filename does not contain its hash prefix")
    return {
        "path": str(path),
        "kind": kind,
        "retrieved_at": envelope["retrieved_at"],
        "vintage_id": vintage,
        "snapshot_sha256": snapshot_hash,
        "audit": audit,
        "boundaries": dict(_BOUNDARIES),
        "valid": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v4/raw"))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify is not None:
        if args.kind or args.dry_run:
            raise SystemExit("--verify cannot be combined with --kind or --dry-run")
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True))
        return 0
    if args.kind is None:
        raise SystemExit("--kind is required unless --verify is used")
    if args.dry_run:
        print(json.dumps(request_plan(args.kind), indent=2, sort_keys=True))
        return 0
    path, envelope = collect_snapshot(args.kind, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "path": str(path),
                "kind": envelope["kind"],
                "vintage_id": envelope["vintage_id"],
                "snapshot_sha256": envelope["snapshot_sha256"],
                "audit": envelope["audit"],
                "boundaries": envelope["boundaries"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

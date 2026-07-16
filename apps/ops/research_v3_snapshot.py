"""Collect immutable, credential-free Research Protocol v3 qualification snapshots."""

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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.raw_snapshot.v1"
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v3-data-sources.json")
PROVIDER_CONTRACT_SHA256 = (
    "sha256:d7c7bab9dff4a00496302cfeca208840bb2f947c07b079ca91f5d1a2a28859ec"
)
QUALIFICATION_START = date(2026, 7, 1)
QUALIFICATION_END = date(2026, 7, 31)
KINDS = ("hashrate", "dxy", "vix")

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
    payload_format: str

    @property
    def full_url(self) -> str:
        query = urllib.parse.urlencode(self.params)
        return f"{self.url}?{query}" if query else self.url


_REQUESTS = {
    "hashrate": RequestSpec(
        name="btc_hash_rate",
        url="https://api.blockchain.info/charts/hash-rate",
        params={"timespan": "30days", "format": "json", "sampled": "false"},
        payload_format="json",
    ),
    "dxy": RequestSpec(
        name="dxy_daily_csv",
        url="https://stooq.com/q/d/l/",
        params={"s": "dx.f", "i": "d"},
        payload_format="csv",
    ),
    "vix": RequestSpec(
        name="vix_daily_csv",
        url="https://stooq.com/q/d/l/",
        params={"s": "^vix", "i": "d"},
        payload_format="csv",
    ),
}

Fetch = Callable[[str], bytes]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v3"},
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
        raise ValueError("Research Protocol v3 provider contract fingerprint drifted")
    payload = _strict_json_loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Research Protocol v3 provider contract must be an object")
    if payload.get("schema_version") != "research.data_sources.v3":
        raise ValueError("Research Protocol v3 provider contract schema drifted")
    if payload.get("status") != "provider_contract_locked_before_response_body_access":
        raise ValueError("provider contract must remain locked before response access")
    envelope = payload.get("snapshot_envelope")
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("provider contract snapshot envelope drifted")
    if payload.get("boundaries") != _BOUNDARIES:
        raise ValueError("provider contract boundaries are missing or unsafe")
    providers = payload.get("providers")
    if not isinstance(providers, dict) or set(providers) != set(KINDS):
        raise ValueError("provider contract must contain exactly hashrate, dxy, and vix")
    for kind in KINDS:
        provider = providers.get(kind)
        if not isinstance(provider, dict) or provider.get("authentication") != "none":
            raise ValueError(f"{kind} provider must remain credential-free")
        requests = provider.get("requests")
        if not isinstance(requests, list) or len(requests) != 1:
            raise ValueError(f"{kind} provider must define exactly one request")
        locked = requests[0]
        spec = _REQUESTS[kind]
        expected = {"name": spec.name, "url": spec.url, "params": spec.params}
        if locked != expected:
            raise ValueError(f"{kind} request differs from the locked provider contract")
    return payload


def build_requests(kind: str) -> list[RequestSpec]:
    if kind not in KINDS:
        raise ValueError(f"unsupported Research Protocol v3 snapshot kind {kind!r}")
    _load_provider_contract()
    return [_REQUESTS[kind]]


def request_plan(kind: str) -> dict[str, Any]:
    specs = build_requests(kind)
    return {
        "schema_version": "research.snapshot.request_plan.v1",
        "kind": kind,
        "provider_contract": str(PROVIDER_CONTRACT),
        "requests": [
            {
                "name": spec.name,
                "url": spec.full_url,
                "payload_format": spec.payload_format,
            }
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
        raise ValueError("v3 snapshot collection must stay within July 2026 qualification")
    return utc_value


def _finite_positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _parse_csv(raw: bytes, *, name: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = reader.fieldnames
    if not columns or any(not column for column in columns) or len(columns) != len(set(columns)):
        raise ValueError(f"{name} CSV header is missing or duplicated")
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{name} CSV row does not match its header")
        if not any(str(value).strip() for value in row.values()):
            continue
        rows.append({str(key): str(value).strip() for key, value in row.items()})
    if not rows:
        raise ValueError(f"{name} CSV must contain at least one data row")
    return {"columns": list(columns), "rows": rows}


def _parse_payload(kind: str, raw: bytes) -> tuple[str, Any]:
    spec = _REQUESTS[kind]
    if spec.payload_format == "json":
        try:
            return "json", _strict_json_loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"{spec.name} returned invalid JSON") from exc
    return "csv", _parse_csv(raw, name=spec.name)


def _validate_hashrate(payload: Any, *, retrieved_at: datetime) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Blockchain.com hashrate response must be an object")
    required = {"status", "name", "unit", "period", "description", "values"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Blockchain.com hashrate response is missing {missing}")
    if payload.get("status") != "ok":
        raise ValueError("Blockchain.com hashrate status must be ok")
    for field in ("name", "unit", "period", "description"):
        if not isinstance(payload.get(field), str) or not str(payload[field]).strip():
            raise ValueError(f"Blockchain.com hashrate {field} must be a non-empty string")
    values = payload.get("values")
    if not isinstance(values, list) or len(values) < 2:
        raise ValueError("Blockchain.com hashrate values must contain at least two rows")
    days: list[date] = []
    completed = 0
    incomplete = 0
    previous_x: int | None = None
    for index, row in enumerate(values):
        if not isinstance(row, dict) or set(row) != {"x", "y"}:
            raise ValueError("Blockchain.com hashrate rows must contain exactly x and y")
        x_number = _finite_positive(row.get("x"), f"values[{index}].x")
        if not x_number.is_integer():
            raise ValueError("Blockchain.com hashrate x must be integer Unix seconds")
        x = int(x_number)
        if x % 86_400 != 0:
            raise ValueError("Blockchain.com hashrate x must identify a UTC-day boundary")
        if previous_x is not None and x <= previous_x:
            raise ValueError("Blockchain.com hashrate x values must be unique and increasing")
        previous_x = x
        _finite_positive(row.get("y"), f"values[{index}].y")
        observation_day = datetime.fromtimestamp(x, tz=UTC).date()
        if observation_day > retrieved_at.date():
            raise ValueError("Blockchain.com hashrate response contains a future UTC day")
        if observation_day < retrieved_at.date():
            completed += 1
        else:
            incomplete += 1
        days.append(observation_day)
    if completed == 0:
        raise ValueError("Blockchain.com hashrate response has no completed UTC-day row")
    return {
        "row_count": len(days),
        "first_observation_day": days[0].isoformat(),
        "last_observation_day": days[-1].isoformat(),
        "completed_utc_day_count": completed,
        "incomplete_current_utc_day_count": incomplete,
        "unit": str(payload["unit"]),
        "period": str(payload["period"]),
        "publication_observed_at": retrieved_at.isoformat().replace("+00:00", "Z"),
    }


def _validate_stooq(kind: str, payload: Any, *, retrieved_at: datetime) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"Stooq {kind} parsed payload must be an object")
    columns = payload.get("columns")
    rows = payload.get("rows")
    required = {"Date", "Open", "High", "Low", "Close"}
    if not isinstance(columns, list) or not required.issubset(set(columns)):
        raise ValueError(f"Stooq {kind} CSV lacks locked OHLC columns")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Stooq {kind} CSV rows must be non-empty")
    sessions: list[date] = []
    eligible = 0
    not_yet_eligible = 0
    previous: date | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != set(columns):
            raise ValueError(f"Stooq {kind} row does not match its header")
        try:
            session = date.fromisoformat(str(row["Date"]))
        except ValueError as exc:
            raise ValueError(f"Stooq {kind} Date must use YYYY-MM-DD") from exc
        if previous is not None and session <= previous:
            raise ValueError(f"Stooq {kind} dates must be unique and increasing")
        previous = session
        open_price = _finite_positive(row["Open"], f"rows[{index}].Open")
        high = _finite_positive(row["High"], f"rows[{index}].High")
        low = _finite_positive(row["Low"], f"rows[{index}].Low")
        close = _finite_positive(row["Close"], f"rows[{index}].Close")
        if low > min(open_price, close) or high < max(open_price, close) or high < low:
            raise ValueError(f"Stooq {kind} OHLC bounds are invalid")
        if session > retrieved_at.date():
            raise ValueError(f"Stooq {kind} contains a future session")
        available_at = datetime.combine(session + timedelta(days=1), datetime.min.time(), UTC)
        if available_at <= retrieved_at:
            eligible += 1
        else:
            not_yet_eligible += 1
        sessions.append(session)
    if eligible == 0:
        raise ValueError(f"Stooq {kind} has no prior completed session eligible by publication lag")
    return {
        "row_count": len(sessions),
        "columns": list(columns),
        "first_session": sessions[0].isoformat(),
        "last_session": sessions[-1].isoformat(),
        "publication_lag_eligible_row_count": eligible,
        "not_yet_eligible_row_count": not_yet_eligible,
        "latest_eligible_available_at_rule": "next_utc_midnight_after_session",
    }


def _validate_payload(kind: str, payload: Any, *, retrieved_at: datetime) -> dict[str, Any]:
    if kind == "hashrate":
        return _validate_hashrate(payload, retrieved_at=retrieved_at)
    return _validate_stooq(kind, payload, retrieved_at=retrieved_at)


def collect_snapshot(
    kind: str,
    *,
    output_dir: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    retrieved_at = _ensure_qualification_time(now or datetime.now(UTC))
    specs = build_requests(kind)
    requests: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}
    for spec in specs:
        raw = fetch(spec.full_url)
        if not raw:
            raise ValueError(f"{spec.name} returned an empty response")
        payload_format, payload = _parse_payload(kind, raw)
        payloads[spec.name] = payload
        requests.append(
            {
                "name": spec.name,
                "url": spec.full_url,
                "payload_format": payload_format,
                "payload_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
                "payload_raw_base64": base64.b64encode(raw).decode("ascii"),
                "payload": payload,
            }
        )
    audit = _validate_payload(kind, payloads[specs[0].name], retrieved_at=retrieved_at)
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
    specs = build_requests(kind)
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
    if not isinstance(requests, list) or len(requests) != len(specs):
        raise ValueError("snapshot request count differs from the provider contract")
    payloads: dict[str, Any] = {}
    for request, spec in zip(requests, specs, strict=True):
        if not isinstance(request, dict):
            raise ValueError("snapshot request entries must be objects")
        if request.get("name") != spec.name or request.get("url") != spec.full_url:
            raise ValueError("snapshot request identity differs from the provider contract")
        if request.get("payload_format") != spec.payload_format:
            raise ValueError("snapshot payload format differs from the provider contract")
        try:
            raw = base64.b64decode(request["payload_raw_base64"], validate=True)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{spec.name} raw payload is missing or invalid base64") from exc
        expected_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if request.get("payload_sha256") != expected_hash:
            raise ValueError(f"{spec.name} raw payload hash mismatch")
        payload_format, parsed = _parse_payload(kind, raw)
        if payload_format != spec.payload_format or parsed != request.get("payload"):
            raise ValueError(f"{spec.name} parsed payload differs from raw bytes")
        payloads[spec.name] = parsed
    audit = _validate_payload(kind, payloads[specs[0].name], retrieved_at=retrieved_at)
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
    vintage_id = f"{kind}:{envelope['retrieved_at']}:{snapshot_hash[7:19]}"
    if envelope.get("vintage_id") != vintage_id:
        raise ValueError("snapshot vintage_id does not match the envelope hash")
    if snapshot_hash[7:19] not in path.name:
        raise ValueError("snapshot filename does not contain its hash prefix")
    return {
        "path": str(path),
        "kind": kind,
        "retrieved_at": envelope["retrieved_at"],
        "vintage_id": vintage_id,
        "snapshot_sha256": snapshot_hash,
        "audit": audit,
        "boundaries": dict(_BOUNDARIES),
        "valid": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research-v3/raw"))
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

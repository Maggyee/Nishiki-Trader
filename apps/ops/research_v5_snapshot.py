"""Collect and verify immutable Binance-native Research Protocol v5 snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from apps.strategies_freqtrade.research.binance_mechanism_signals import ASSETS

SCHEMA_VERSION = "research.raw_snapshot.v2"
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v5-data-sources.json")
KINDS = ("delivery_curve", "bvol")
BINANCE_DATA_ROOT = "https://data.binance.vision/data"

_KLINE_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)
_BVOL_COLUMNS = ("calc_time", "symbol", "base_asset", "quote_asset", "index_value")
_BOUNDARIES = {
    "authentication": "none",
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
    role: str
    url: str
    filename: str
    payload_format: str = "zip"


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    status: int
    final_url: str
    headers: dict[str, str]


Fetch = Callable[[str], HttpResponse]


def _fetch(url: str) -> HttpResponse:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v5"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return HttpResponse(
            body=response.read(),
            status=int(response.status),
            final_url=str(response.url),
            headers={str(key).lower(): str(value) for key, value in response.headers.items()},
        )


def _last_friday(year: int, month: int) -> date:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    current = next_month - timedelta(days=1)
    while current.weekday() != 4:
        current -= timedelta(days=1)
    return current


def quarterly_expiries(start_year: int, end_year: int) -> list[datetime]:
    return [
        datetime.combine(_last_friday(year, month), time(8), UTC)
        for year in range(start_year, end_year + 1)
        for month in (3, 6, 9, 12)
    ]


def select_quarterly_contracts(asset: str, data_day: date) -> tuple[tuple[str, datetime], ...]:
    asset = asset.upper()
    if asset not in ASSETS:
        raise ValueError(f"asset must be one of {ASSETS}")
    decision_at = datetime.combine(data_day + timedelta(days=1), time.min, UTC)
    future = [
        expiry
        for expiry in quarterly_expiries(data_day.year - 1, data_day.year + 2)
        if expiry > decision_at
    ]
    if len(future) < 2:
        raise ValueError("could not derive two unexpired quarterly contracts")
    return tuple(
        (f"{asset}_{expiry:%y%m%d}", expiry)
        for expiry in future[:2]
    )


def build_requests(kind: str, asset: str, data_day: date) -> list[RequestSpec]:
    asset = asset.upper()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if asset not in ASSETS:
        raise ValueError(f"asset must be one of {ASSETS}")
    stamp = data_day.isoformat()
    if kind == "bvol":
        symbol = f"{asset.removesuffix('USDT')}BVOLUSDT"
        filename = f"{symbol}-BVOLIndex-{stamp}.zip"
        url = f"{BINANCE_DATA_ROOT}/option/daily/BVOLIndex/{symbol}/{filename}"
        return [RequestSpec("bvol_index", url, filename)]

    contracts = select_quarterly_contracts(asset, data_day)
    index_name = f"{asset}-1d-{stamp}.zip"
    requests = [
        RequestSpec(
            "index_price",
            f"{BINANCE_DATA_ROOT}/futures/um/daily/indexPriceKlines/{asset}/1d/{index_name}",
            index_name,
        )
    ]
    for role, (symbol, _expiry) in zip(("front_contract", "next_contract"), contracts, strict=True):
        filename = f"{symbol}-1d-{stamp}.zip"
        requests.append(
            RequestSpec(
                role,
                f"{BINANCE_DATA_ROOT}/futures/um/daily/klines/{symbol}/1d/{filename}",
                filename,
            )
        )
    return requests


def _date_range(
    *,
    single_date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> list[date]:
    if single_date:
        if start_date or end_date:
            raise ValueError("--date cannot be combined with a date range")
        return [date.fromisoformat(single_date)]
    if not start_date or not end_date:
        raise ValueError("provide --date or both --start-date and --end-date")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end date is before start date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def request_plan(kind: str, asset: str, days: Iterable[date]) -> dict[str, Any]:
    rows = []
    for data_day in days:
        rows.append(
            {
                "data_date": data_day.isoformat(),
                "requests": [
                    {
                        "role": spec.role,
                        "url": spec.url,
                        "checksum_url": f"{spec.url}.CHECKSUM",
                        "filename": spec.filename,
                    }
                    for spec in build_requests(kind, asset, data_day)
                ],
            }
        )
    return {
        "schema_version": "research.snapshot.request_plan.v2",
        "kind": kind,
        "asset": asset.upper(),
        "provider_contract": str(PROVIDER_CONTRACT),
        "dates": rows,
        "boundaries": dict(_BOUNDARIES),
        "network_accessed": False,
        "data_written": False,
    }


def _sha256(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _strict_json_loads(raw: str | bytes) -> Any:
    return json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {value!r} is forbidden")
        ),
    )


def _checksum_expected(raw: bytes, filename: str) -> str:
    try:
        fields = raw.decode("utf-8").strip().split()
    except UnicodeDecodeError as exc:
        raise ValueError("official checksum must be UTF-8 text") from exc
    if len(fields) < 2 or fields[1].lstrip("*") != filename:
        raise ValueError("official checksum filename differs from the archive")
    digest = fields[0].lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("official checksum does not contain a SHA-256")
    return f"sha256:{digest}"


def _csv_rows(raw_zip: bytes, expected_columns: tuple[str, ...], filename: str) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if len(names) != 1 or not names[0].lower().endswith(".csv"):
                raise ValueError(f"{filename} must contain exactly one CSV")
            raw_csv = archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{filename} is not a valid ZIP") from exc
    try:
        rows = list(csv.reader(io.StringIO(raw_csv.decode("utf-8-sig"), newline="")))
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} CSV must be UTF-8") from exc
    rows = [row for row in rows if any(field.strip() for field in row)]
    if rows and tuple(field.strip().lower() for field in rows[0]) == expected_columns:
        rows = rows[1:]
    if not rows:
        raise ValueError(f"{filename} CSV has no data rows")
    if any(len(row) != len(expected_columns) for row in rows):
        raise ValueError(f"{filename} CSV row width differs from its locked schema")
    return [[field.strip() for field in row] for row in rows]


def _timestamp_ns(value: str, field: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer timestamp") from exc
    magnitude = abs(integer)
    if 10**12 <= magnitude < 10**15:
        return integer * 1_000_000
    if 10**15 <= magnitude < 10**18:
        return integer * 1_000
    if 10**18 <= magnitude < 10**20:
        return integer
    raise ValueError(f"{field} must use milliseconds, microseconds, or nanoseconds")


def _finite_positive(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return result


def _parse_kline(raw: bytes, *, filename: str, data_day: date) -> dict[str, Any]:
    rows = _csv_rows(raw, _KLINE_COLUMNS, filename)
    if len(rows) != 1:
        raise ValueError(f"{filename} daily 1d archive must contain exactly one row")
    row = dict(zip(_KLINE_COLUMNS, rows[0], strict=True))
    open_ns = _timestamp_ns(row["open_time"], f"{filename}.open_time")
    close_ns = _timestamp_ns(row["close_time"], f"{filename}.close_time")
    expected_open = int(datetime.combine(data_day, time.min, UTC).timestamp() * 1e9)
    expected_next = int(
        datetime.combine(data_day + timedelta(days=1), time.min, UTC).timestamp() * 1e9
    )
    if open_ns != expected_open or not expected_next - 1_000_000 <= close_ns < expected_next:
        raise ValueError(f"{filename} does not cover exactly the requested UTC day")
    prices = {
        key: _finite_positive(row[key], f"{filename}.{key}")
        for key in ("open", "high", "low", "close")
    }
    if prices["low"] > min(prices["open"], prices["close"]) or prices["high"] < max(
        prices["open"], prices["close"]
    ):
        raise ValueError(f"{filename} OHLC bounds are invalid")
    return {"open_time_ns": open_ns, "close_time_ns": close_ns, **prices}


def _parse_bvol(raw: bytes, *, filename: str, data_day: date, asset: str) -> dict[str, Any]:
    rows = _csv_rows(raw, _BVOL_COLUMNS, filename)
    expected_symbol = f"{asset.removesuffix('USDT')}BVOLUSDT"
    expected_base = asset.removesuffix("USDT")
    timestamps: list[int] = []
    values: list[float] = []
    for index, values_row in enumerate(rows):
        row = dict(zip(_BVOL_COLUMNS, values_row, strict=True))
        timestamp = _timestamp_ns(row["calc_time"], f"{filename}.calc_time[{index}]")
        if timestamps and timestamp <= timestamps[-1]:
            raise ValueError(f"{filename} calc_time rows must be unique and increasing")
        if pd.Timestamp(timestamp, unit="ns", tz="UTC").date() != data_day:
            raise ValueError(f"{filename} contains a row outside the requested UTC day")
        if row["symbol"] != expected_symbol or row["base_asset"] != expected_base:
            raise ValueError(f"{filename} BVOL symbol/base asset drifted")
        if row["quote_asset"] != "USDT":
            raise ValueError(f"{filename} BVOL quote asset must be USDT")
        timestamps.append(timestamp)
        values.append(_finite_positive(row["index_value"], f"{filename}.index_value[{index}]"))
    return {
        "row_count": len(rows),
        "first_calc_time_ns": timestamps[0],
        "last_calc_time_ns": timestamps[-1],
        "bvol_index": values[-1],
        "selection": "last_valid_observation_of_utc_day",
    }


def _parse_payloads(
    kind: str,
    asset: str,
    data_day: date,
    payloads: dict[str, bytes],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if kind == "bvol":
        parsed = _parse_bvol(
            payloads["bvol_index"],
            filename=build_requests(kind, asset, data_day)[0].filename,
            data_day=data_day,
            asset=asset,
        )
        return parsed, {"bvol_index": parsed["bvol_index"]}

    requests = build_requests(kind, asset, data_day)
    parsed = {
        spec.role: _parse_kline(
            payloads[spec.role], filename=spec.filename, data_day=data_day
        )
        for spec in requests
    }
    contracts = select_quarterly_contracts(asset, data_day)
    decision_at = datetime.combine(data_day + timedelta(days=1), time.min, UTC)
    front_days = (contracts[0][1] - decision_at).total_seconds() / 86_400
    next_days = (contracts[1][1] - decision_at).total_seconds() / 86_400
    index_close = parsed["index_price"]["close"]
    front_close = parsed["front_contract"]["close"]
    next_close = parsed["next_contract"]["close"]
    front_basis = (front_close / index_close - 1) * 365 / front_days
    next_basis = (next_close / index_close - 1) * 365 / next_days
    audit = {
        "row_count_by_role": {role: 1 for role in parsed},
        "front_contract": contracts[0][0],
        "next_contract": contracts[1][0],
        "front_expiry": contracts[0][1].isoformat().replace("+00:00", "Z"),
        "next_expiry": contracts[1][1].isoformat().replace("+00:00", "Z"),
        "quarter_order_valid": True,
    }
    normalized = {
        "index_close": index_close,
        "front_futures_close": front_close,
        "next_futures_close": next_close,
        "front_days_to_expiry": front_days,
        "next_days_to_expiry": next_days,
        "front_contract": contracts[0][0],
        "next_contract": contracts[1][0],
        "front_expiry": audit["front_expiry"],
        "next_expiry": audit["next_expiry"],
        "front_annualized_basis": front_basis,
        "next_annualized_basis": next_basis,
    }
    return audit, normalized


def _available_at(kind: str, data_day: date, retrieved_at: datetime) -> datetime:
    if kind == "delivery_curve":
        return datetime.combine(data_day + timedelta(days=1), time.min, UTC)
    if data_day < date(2026, 7, 1):
        return datetime.combine(data_day + timedelta(days=2), time.min, UTC)
    return datetime.combine(retrieved_at.astimezone(UTC).date() + timedelta(days=1), time.min, UTC)


def collect_snapshot(
    kind: str,
    asset: str,
    data_day: date,
    *,
    raw_root: Path,
    normalized_root: Path,
    fetch: Fetch = _fetch,
    now: datetime | None = None,
) -> dict[str, Any]:
    asset = asset.upper()
    retrieved_at = (now or datetime.now(UTC)).astimezone(UTC)
    specs = build_requests(kind, asset, data_day)
    response_rows: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    checksum_payloads: dict[str, bytes] = {}
    for spec in specs:
        archive = fetch(spec.url)
        checksum = fetch(f"{spec.url}.CHECKSUM")
        if archive.status != 200 or not archive.body or checksum.status != 200 or not checksum.body:
            raise ValueError(f"{spec.role} archive/checksum request did not return HTTP 200 bytes")
        expected = _checksum_expected(checksum.body, spec.filename)
        actual = _sha256(archive.body)
        if actual != expected:
            raise ValueError(f"official checksum mismatch for {spec.filename}")
        payloads[spec.role] = archive.body
        checksum_payloads[spec.role] = checksum.body
        response_rows.append(
            {
                "role": spec.role,
                "url": spec.url,
                "filename": spec.filename,
                "archive_sha256": actual,
                "checksum_sha256": _sha256(checksum.body),
                "http": {
                    "status": archive.status,
                    "final_url": archive.final_url,
                    "headers": dict(sorted(archive.headers.items())),
                    "checksum_status": checksum.status,
                    "checksum_final_url": checksum.final_url,
                    "checksum_headers": dict(sorted(checksum.headers.items())),
                },
            }
        )
    audit, normalized_values = _parse_payloads(kind, asset, data_day, payloads)
    content_core = [
        {key: row[key] for key in ("role", "url", "filename", "archive_sha256", "checksum_sha256")}
        for row in response_rows
    ]
    content_json = json.dumps(content_core, sort_keys=True, separators=(",", ":"))
    content_sha = f"sha256:{hashlib.sha256(content_json.encode()).hexdigest()}"
    date_root = raw_root / kind / asset / data_day.isoformat()

    if date_root.exists():
        for existing in sorted(date_root.glob("*/snapshot.json")):
            payload = _strict_json_loads(existing.read_text(encoding="utf-8"))
            if payload.get("content_sha256") == content_sha:
                verified = verify_snapshot(existing)
                return {**verified, "idempotent": True}

    vintage_id = f"{kind}:{asset}:{data_day.isoformat()}:{content_sha[7:19]}"
    vintage_dir = date_root / content_sha[7:19]
    vintage_dir.mkdir(parents=True, exist_ok=False)
    raw_hashes: dict[str, str] = {}
    try:
        for spec, response in zip(specs, response_rows, strict=True):
            archive_path = vintage_dir / spec.filename
            checksum_path = vintage_dir / f"{spec.filename}.CHECKSUM"
            archive_path.write_bytes(payloads[spec.role])
            checksum_path.write_bytes(checksum_payloads[spec.role])
            raw_hashes[spec.filename] = response["archive_sha256"]
            raw_hashes[checksum_path.name] = response["checksum_sha256"]

        available = _available_at(kind, data_day, retrieved_at)
        normalized = {
            "schema_version": "research.normalized_snapshot.v5",
            "kind": kind,
            "asset": asset,
            "data_date": data_day.isoformat(),
            "available_at": available.isoformat().replace("+00:00", "Z"),
            "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
            "vintage_id": vintage_id,
            "content_sha256": content_sha,
            "raw_file_hashes": json.dumps(dict(sorted(raw_hashes.items())), sort_keys=True),
            **normalized_values,
        }
        core = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "asset": asset,
            "data_date": data_day.isoformat(),
            "retrieved_at": normalized["retrieved_at"],
            "available_at": normalized["available_at"],
            "provider_contract": str(PROVIDER_CONTRACT),
            "content_sha256": content_sha,
            "vintage_id": vintage_id,
            "requests": response_rows,
            "raw_file_hashes": dict(sorted(raw_hashes.items())),
            "audit": audit,
            "normalized": normalized,
            "boundaries": dict(_BOUNDARIES),
        }
        canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
        snapshot_sha = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
        envelope = {**core, "snapshot_sha256": snapshot_sha}
        envelope["normalized"]["snapshot_sha256"] = snapshot_sha
        (vintage_dir / "snapshot.json").write_text(
            json.dumps(envelope, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (vintage_dir / "audit.json").write_text(
            json.dumps(audit, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        normalized_dir = normalized_root / kind / asset / data_day.isoformat()
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = normalized_dir / f"{content_sha[7:19]}.parquet"
        pd.DataFrame([envelope["normalized"]]).to_parquet(
            normalized_path,
            engine="pyarrow",
            compression="zstd",
            index=False,
        )
    except Exception:
        # Leave a visible incomplete vintage for audit; it will never verify or compare.
        raise

    prior = [path for path in date_root.glob("*/snapshot.json") if path.parent != vintage_dir]
    if prior:
        marker = date_root / f"comparison-blocked-{content_sha[7:19]}.json"
        marker.write_text(
            json.dumps(
                {
                    "schema_version": "research.vintage_conflict.v1",
                    "kind": kind,
                    "asset": asset,
                    "data_date": data_day.isoformat(),
                    "new_content_sha256": content_sha,
                    "existing_snapshots": [str(path) for path in sorted(prior)],
                    "result_comparison_blocked": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "path": str(vintage_dir / "snapshot.json"),
        "normalized_path": str(normalized_path),
        "kind": kind,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "vintage_id": vintage_id,
        "content_sha256": content_sha,
        "snapshot_sha256": snapshot_sha,
        "audit": audit,
        "result_comparison_blocked": bool(prior),
        "idempotent": False,
        "valid": True,
    }


def verify_snapshot(path: Path) -> dict[str, Any]:
    snapshot_path = path / "snapshot.json" if path.is_dir() else path
    envelope = _strict_json_loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("snapshot must be research.raw_snapshot.v2")
    if envelope.get("boundaries") != _BOUNDARIES:
        raise ValueError("snapshot safety boundaries drifted")
    kind = str(envelope.get("kind"))
    asset = str(envelope.get("asset"))
    data_day = date.fromisoformat(str(envelope.get("data_date")))
    specs = build_requests(kind, asset, data_day)
    request_rows = envelope.get("requests")
    if not isinstance(request_rows, list) or len(request_rows) != len(specs):
        raise ValueError("snapshot request count differs from the locked plan")
    payloads: dict[str, bytes] = {}
    raw_hashes: dict[str, str] = {}
    for spec, row in zip(specs, request_rows, strict=True):
        if row.get("role") != spec.role or row.get("url") != spec.url or row.get("filename") != spec.filename:
            raise ValueError("snapshot request identity differs from the locked plan")
        http = row.get("http")
        if (
            not isinstance(http, dict)
            or http.get("status") != 200
            or http.get("checksum_status") != 200
            or not isinstance(http.get("final_url"), str)
            or not http["final_url"]
            or not isinstance(http.get("checksum_final_url"), str)
            or not http["checksum_final_url"]
            or not isinstance(http.get("headers"), dict)
            or not isinstance(http.get("checksum_headers"), dict)
        ):
            raise ValueError("snapshot HTTP metadata is missing or invalid")
        archive_path = snapshot_path.parent / spec.filename
        checksum_path = snapshot_path.parent / f"{spec.filename}.CHECKSUM"
        archive = archive_path.read_bytes()
        checksum = checksum_path.read_bytes()
        if _sha256(archive) != row.get("archive_sha256"):
            raise ValueError(f"raw archive hash mismatch for {spec.filename}")
        if _sha256(checksum) != row.get("checksum_sha256"):
            raise ValueError(f"raw checksum hash mismatch for {spec.filename}")
        if _checksum_expected(checksum, spec.filename) != _sha256(archive):
            raise ValueError(f"official checksum mismatch for {spec.filename}")
        payloads[spec.role] = archive
        raw_hashes[spec.filename] = _sha256(archive)
        raw_hashes[checksum_path.name] = _sha256(checksum)
    if envelope.get("raw_file_hashes") != dict(sorted(raw_hashes.items())):
        raise ValueError("snapshot raw_file_hashes differs from raw bytes")
    content_core = [
        {
            key: row[key]
            for key in ("role", "url", "filename", "archive_sha256", "checksum_sha256")
        }
        for row in request_rows
    ]
    content_json = json.dumps(content_core, sort_keys=True, separators=(",", ":"))
    content_sha = f"sha256:{hashlib.sha256(content_json.encode()).hexdigest()}"
    if envelope.get("content_sha256") != content_sha:
        raise ValueError("snapshot content_sha256 differs from the raw request set")
    expected_vintage = f"{kind}:{asset}:{data_day.isoformat()}:{content_sha[7:19]}"
    if envelope.get("vintage_id") != expected_vintage:
        raise ValueError("snapshot vintage_id differs from its immutable content")

    try:
        retrieved_at = datetime.fromisoformat(
            str(envelope.get("retrieved_at", "")).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("snapshot retrieved_at must be an ISO timestamp") from exc
    if retrieved_at.tzinfo is None:
        raise ValueError("snapshot retrieved_at must be timezone-aware")
    expected_available = _available_at(kind, data_day, retrieved_at).isoformat().replace(
        "+00:00", "Z"
    )
    if envelope.get("available_at") != expected_available:
        raise ValueError("snapshot available_at violates the point-in-time contract")

    audit, normalized_values = _parse_payloads(kind, asset, data_day, payloads)
    if envelope.get("audit") != audit:
        raise ValueError("snapshot audit differs from raw bytes")
    normalized = envelope.get("normalized")
    if not isinstance(normalized, dict):
        raise ValueError("snapshot normalized envelope must be an object")
    expected_normalized = {
        "schema_version": "research.normalized_snapshot.v5",
        "kind": kind,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "available_at": expected_available,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "vintage_id": expected_vintage,
        "content_sha256": content_sha,
        "raw_file_hashes": json.dumps(dict(sorted(raw_hashes.items())), sort_keys=True),
    }
    for key, value in expected_normalized.items():
        if normalized.get(key) != value:
            raise ValueError(f"normalized field {key} violates the snapshot contract")
    for key, value in normalized_values.items():
        if normalized.get(key) != value:
            raise ValueError(f"normalized field {key} differs from raw bytes")
    core = {key: value for key, value in envelope.items() if key != "snapshot_sha256"}
    normalized = dict(core["normalized"])
    normalized.pop("snapshot_sha256", None)
    core["normalized"] = normalized
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), allow_nan=False)
    snapshot_sha = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    if envelope.get("snapshot_sha256") != snapshot_sha:
        raise ValueError("snapshot envelope hash mismatch")
    return {
        "path": str(snapshot_path),
        "kind": kind,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "vintage_id": envelope["vintage_id"],
        "content_sha256": envelope["content_sha256"],
        "snapshot_sha256": snapshot_sha,
        "audit": audit,
        "valid": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--asset", choices=ASSETS)
    parser.add_argument("--date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--download", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--verify", type=Path)
    parser.add_argument("--raw-root", type=Path, default=Path("data/research-v5/raw"))
    parser.add_argument(
        "--normalized-root",
        type=Path,
        default=Path("data/research-v5/normalized"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify is not None:
        if any((args.kind, args.asset, args.date, args.start_date, args.end_date)):
            raise SystemExit("--verify cannot be combined with collection arguments")
        print(json.dumps(verify_snapshot(args.verify), indent=2, sort_keys=True, allow_nan=False))
        return 0
    if args.kind is None or args.asset is None:
        raise SystemExit("--kind and --asset are required for --download/--dry-run")
    try:
        days = _date_range(
            single_date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        if args.dry_run:
            print(json.dumps(request_plan(args.kind, args.asset, days), indent=2, sort_keys=True))
            return 0
        results = [
            collect_snapshot(
                args.kind,
                args.asset,
                data_day,
                raw_root=args.raw_root,
                normalized_root=args.normalized_root,
            )
            for data_day in days
        ]
        print(json.dumps({"snapshots": results}, indent=2, sort_keys=True, allow_nan=False))
    except Exception as exc:
        raise SystemExit(f"research v5 snapshot failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

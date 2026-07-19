"""Collect and verify the one-day Research Protocol v6 provider qualification."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

QUALIFICATION_DATE = date(2026, 7, 17)
ASSETS = ("BTCUSDT", "ETHUSDT")
BINANCE_DATA_ROOT = "https://data.binance.vision/data"
PROVIDER_CONTRACT = Path("docs/progress/phase-2-research-v6-data-sources.json")
LOCKED_PROVIDER_CONTRACT_SHA256 = (
    "sha256:9944a172ae093deee6bc366d0fd19483f1bb2f4c8cad25a703ff9992bbac1f83"
)
SNAPSHOT_SCHEMA_VERSION = "research.raw_snapshot.v2"
QUALIFICATION_SCHEMA_VERSION = "research.v6.book_depth_qualification.v1"
AUDIT_SCHEMA_VERSION = "research.v6.book_depth_qualification_audit.v1"
HTTP_SCHEMA_VERSION = "research.v6.http_response.v1"
CONFLICT_SCHEMA_VERSION = "research.v6.vintage_conflict.v1"
BLOCKER_SCHEMA_VERSION = "research.v6.http_blocker.v1"

BOOK_DEPTH_COLUMNS = ("timestamp", "percentage", "depth", "notional")
MARK_PRICE_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)
PERCENTAGE_GRID = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
TOLERANCE = Decimal("0.01")

_BOUNDARIES = {
    "credentials_loaded": False,
    "historical_range_opened": False,
    "factor_values_computed": False,
    "factor_values_saved": False,
    "signals_generated": False,
    "returns_loaded": False,
    "pnl_computed": False,
    "nautilus_run": False,
    "source_policy_mutated": False,
    "testnet_resumed": False,
    "live_path_touched": False,
}

_AUDIT_COLUMNS = (
    "schema_version",
    "qualification_status",
    "asset",
    "data_date",
    "expected_git_commit",
    "snapshot_sha256",
    "book_depth_row_count",
    "timestamp_group_count",
    "first_group_utc",
    "last_group_utc",
    "maximum_group_gap_seconds",
    "percentage_grid_json",
    "book_depth_rows_sha256",
    "mark_price_row_count",
    "first_mark_minute_ns",
    "last_mark_minute_ns",
    "mark_price_rows_sha256",
    "mark_minute_matches",
    "band_rows_checked",
    "bid_rows_checked",
    "ask_rows_checked",
    "band_violation_count",
    "factor_values_saved",
    "signals_generated",
    "pnl_computed",
)


class QualificationError(ValueError):
    """Base class for fail-closed qualification errors."""


class PermanentQualificationError(QualificationError):
    """A provider, checksum, schema, or semantic failure that must not be retried."""


class RetryableDownloadError(QualificationError):
    """A timeout or server-side response for a request not yet saved successfully."""


@dataclass(frozen=True)
class RequestSpec:
    role: str
    url: str
    filename: str


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    status: int
    final_url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class CachedResponse:
    body: bytes
    metadata: dict[str, Any]
    body_path: Path


@dataclass(frozen=True)
class BookDepthRow:
    timestamp_ns: int
    timestamp_text: str
    percentage: int
    depth: Decimal
    notional: Decimal


@dataclass(frozen=True)
class BookDepthPayload:
    rows: tuple[BookDepthRow, ...]
    group_timestamps_ns: tuple[int, ...]
    group_timestamps_text: tuple[str, ...]
    canonical_rows_sha256: str


@dataclass(frozen=True)
class MarkPricePayload:
    closes_by_minute_ns: dict[int, Decimal]
    canonical_rows_sha256: str


Fetch = Callable[[str], HttpResponse]
Clock = Callable[[], datetime]


def _sha256(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return _sha256(raw)


def _strict_json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            PermanentQualificationError(
                f"non-standard JSON constant {value!r} is forbidden"
            )
        ),
    )
    if not isinstance(payload, dict):
        raise PermanentQualificationError(f"{path} must contain a JSON object")
    return payload


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("retrieval clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_date(data_day: date) -> None:
    if data_day != QUALIFICATION_DATE:
        raise PermanentQualificationError(
            "Research Protocol v6 permits only qualification date 2026-07-17"
        )


def _validate_asset(asset: str) -> str:
    normalized = asset.upper()
    if normalized not in ASSETS:
        raise PermanentQualificationError(f"asset must be one of {ASSETS}")
    return normalized


def selected_assets(selector: str) -> tuple[str, ...]:
    if selector == "all":
        return ASSETS
    return (_validate_asset(selector),)


def build_requests(asset: str, data_day: date) -> tuple[RequestSpec, RequestSpec]:
    asset = _validate_asset(asset)
    _validate_date(data_day)
    stamp = data_day.isoformat()
    book_filename = f"{asset}-bookDepth-{stamp}.zip"
    mark_filename = f"{asset}-1m-{stamp}.zip"
    return (
        RequestSpec(
            role="book_depth",
            url=(
                f"{BINANCE_DATA_ROOT}/futures/um/daily/bookDepth/"
                f"{asset}/{book_filename}"
            ),
            filename=book_filename,
        ),
        RequestSpec(
            role="mark_price",
            url=(
                f"{BINANCE_DATA_ROOT}/futures/um/daily/markPriceKlines/"
                f"{asset}/1m/{mark_filename}"
            ),
            filename=mark_filename,
        ),
    )


def request_plan(asset_selector: str, data_day: date, data_root: Path) -> dict[str, Any]:
    assets = selected_assets(asset_selector)
    _validate_date(data_day)
    requests = []
    for asset in assets:
        for spec in build_requests(asset, data_day):
            requests.append(
                {
                    "asset": asset,
                    "role": spec.role,
                    "url": spec.url,
                    "checksum_url": f"{spec.url}.CHECKSUM",
                    "filename": spec.filename,
                    "checksum_filename": f"{spec.filename}.CHECKSUM",
                }
            )
    data_root_empty = not data_root.exists() or not any(data_root.iterdir())
    return {
        "schema_version": "research.v6.qualification_request_plan.v1",
        "data_date": data_day.isoformat(),
        "assets": list(assets),
        "provider_contract": str(PROVIDER_CONTRACT),
        "archive_request_count": len(requests),
        "checksum_request_count": len(requests),
        "http_request_count": len(requests) * 2,
        "requests": requests,
        "data_root": str(data_root),
        "data_root_empty": data_root_empty,
        "boundaries": dict(_BOUNDARIES),
        "network_accessed": False,
        "data_written": False,
    }


def _fetch(url: str) -> HttpResponse:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v6-qualification"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return HttpResponse(
                body=response.read(),
                status=int(response.status),
                final_url=str(response.url),
                headers={
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                },
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            body=exc.read(),
            status=int(exc.code),
            final_url=str(exc.url),
            headers={
                str(key).lower(): str(value)
                for key, value in (exc.headers.items() if exc.headers else [])
            },
        )


def _response_directory(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
) -> Path:
    return data_root / "responses" / asset / data_day.isoformat() / spec.role / payload_kind


def _blocker_directory(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
) -> Path:
    return (
        data_root
        / "blocked-responses"
        / asset
        / data_day.isoformat()
        / spec.role
        / payload_kind
    )


def _body_filename(spec: RequestSpec, payload_kind: str) -> str:
    if payload_kind == "archive":
        return spec.filename
    if payload_kind == "checksum":
        return f"{spec.filename}.CHECKSUM"
    raise ValueError("payload_kind must be archive or checksum")


def _publish_directory(temp_dir: Path, target_dir: Path) -> bool:
    """Atomically publish a prepared directory without replacing an existing one."""

    try:
        os.rename(temp_dir, target_dir)
        return True
    except FileExistsError:
        return False
    except OSError:
        if target_dir.exists():
            return False
        raise


def _write_prepared_response(
    target_dir: Path,
    body_filename: str,
    body: bytes,
    metadata: dict[str, Any],
) -> bool:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir: Path | None = Path(
        tempfile.mkdtemp(prefix=".response-", dir=target_dir.parent)
    )
    try:
        assert temp_dir is not None
        body_path = temp_dir / body_filename
        body_path.write_bytes(body)
        metadata_path = temp_dir / "http.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for path in (body_path, metadata_path):
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        published = _publish_directory(temp_dir, target_dir)
        if published:
            temp_dir = None
        return published
    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir)


def _read_cached_response(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
) -> CachedResponse:
    directory = _response_directory(data_root, asset, data_day, spec, payload_kind)
    filename = _body_filename(spec, payload_kind)
    metadata = _strict_json_load(directory / "http.json")
    body_path = directory / filename
    body = body_path.read_bytes()
    expected_url = spec.url if payload_kind == "archive" else f"{spec.url}.CHECKSUM"
    expected_metadata = {
        "schema_version": HTTP_SCHEMA_VERSION,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "role": spec.role,
        "payload_kind": payload_kind,
        "filename": filename,
        "requested_url": expected_url,
        "status": 200,
    }
    for key, value in expected_metadata.items():
        if metadata.get(key) != value:
            raise PermanentQualificationError(
                f"cached {spec.role} {payload_kind} metadata field {key} drifted"
            )
    if metadata.get("final_url") != expected_url:
        raise PermanentQualificationError(
            f"cached {spec.role} {payload_kind} final URL differs from the locked request"
        )
    if not isinstance(metadata.get("headers"), dict):
        raise PermanentQualificationError("cached HTTP headers are missing")
    try:
        retrieved = datetime.fromisoformat(
            str(metadata.get("retrieved_at", "")).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise PermanentQualificationError("cached retrieved_at is invalid") from exc
    if retrieved.tzinfo is None:
        raise PermanentQualificationError("cached retrieved_at must be timezone-aware")
    if _iso_utc(retrieved) != metadata.get("retrieved_at"):
        raise PermanentQualificationError("cached retrieved_at must use canonical UTC text")
    if not body:
        raise PermanentQualificationError("cached HTTP 200 body is empty")
    if metadata.get("body_sha256") != _sha256(body):
        raise PermanentQualificationError(
            f"cached {spec.role} {payload_kind} body hash mismatch"
        )
    return CachedResponse(body=body, metadata=metadata, body_path=body_path)


def _record_conflict(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
    body: bytes,
    metadata: dict[str, Any],
    existing_sha256: str,
) -> Path:
    new_sha256 = _sha256(body)
    conflict_dir = (
        data_root
        / "conflicts"
        / asset
        / data_day.isoformat()
        / spec.role
        / payload_kind
        / new_sha256[7:19]
    )
    marker = {
        "schema_version": CONFLICT_SCHEMA_VERSION,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "role": spec.role,
        "payload_kind": payload_kind,
        "existing_sha256": existing_sha256,
        "new_sha256": new_sha256,
        "result_comparison_blocked": True,
    }
    if not conflict_dir.exists():
        _write_prepared_response(
            conflict_dir,
            _body_filename(spec, payload_kind),
            body,
            {**metadata, "conflict": marker},
        )
    _write_immutable_json(conflict_dir / "conflict.json", marker)
    return conflict_dir / "conflict.json"


def _persist_http_200(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
    response: HttpResponse,
    retrieved_at: datetime,
) -> CachedResponse:
    expected_url = spec.url if payload_kind == "archive" else f"{spec.url}.CHECKSUM"
    if response.status != 200 or not response.body:
        raise ValueError("_persist_http_200 requires a non-empty HTTP 200 response")
    if response.final_url != expected_url:
        raise PermanentQualificationError("HTTP final URL differs from the locked request")
    metadata = {
        "schema_version": HTTP_SCHEMA_VERSION,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "role": spec.role,
        "payload_kind": payload_kind,
        "filename": _body_filename(spec, payload_kind),
        "requested_url": expected_url,
        "final_url": response.final_url,
        "status": response.status,
        "headers": dict(sorted((str(k).lower(), str(v)) for k, v in response.headers.items())),
        "retrieved_at": _iso_utc(retrieved_at),
        "body_sha256": _sha256(response.body),
    }
    target = _response_directory(data_root, asset, data_day, spec, payload_kind)
    if target.exists():
        cached = _read_cached_response(data_root, asset, data_day, spec, payload_kind)
        if cached.body == response.body:
            return cached
        marker = _record_conflict(
            data_root,
            asset,
            data_day,
            spec,
            payload_kind,
            response.body,
            metadata,
            _sha256(cached.body),
        )
        raise PermanentQualificationError(f"vintage conflict recorded at {marker}")
    published = _write_prepared_response(
        target,
        _body_filename(spec, payload_kind),
        response.body,
        metadata,
    )
    if not published:
        return _persist_http_200(
            data_root,
            asset,
            data_day,
            spec,
            payload_kind,
            response,
            retrieved_at,
        )
    return _read_cached_response(data_root, asset, data_day, spec, payload_kind)


def _persist_permanent_http_blocker(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
    response: HttpResponse,
    retrieved_at: datetime,
) -> Path:
    directory = _blocker_directory(data_root, asset, data_day, spec, payload_kind)
    expected_url = spec.url if payload_kind == "archive" else f"{spec.url}.CHECKSUM"
    payload = {
        "schema_version": BLOCKER_SCHEMA_VERSION,
        "asset": asset,
        "data_date": data_day.isoformat(),
        "role": spec.role,
        "payload_kind": payload_kind,
        "requested_url": expected_url,
        "final_url": response.final_url,
        "status": response.status,
        "headers": dict(sorted((str(k).lower(), str(v)) for k, v in response.headers.items())),
        "retrieved_at": _iso_utc(retrieved_at),
        "response_body_sha256": _sha256(response.body),
        "retry_forbidden": True,
    }
    if directory.exists():
        return directory / "blocker.json"
    directory.parent.mkdir(parents=True, exist_ok=True)
    temp_dir: Path | None = Path(
        tempfile.mkdtemp(prefix=".blocker-", dir=directory.parent)
    )
    try:
        assert temp_dir is not None
        (temp_dir / "body.bin").write_bytes(response.body)
        (temp_dir / "blocker.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        published = _publish_directory(temp_dir, directory)
        if published:
            temp_dir = None
    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir)
    return directory / "blocker.json"


def _load_or_fetch_response(
    data_root: Path,
    asset: str,
    data_day: date,
    spec: RequestSpec,
    payload_kind: str,
    *,
    fetch: Fetch,
    clock: Clock,
) -> tuple[CachedResponse, bool]:
    cached_dir = _response_directory(data_root, asset, data_day, spec, payload_kind)
    if cached_dir.exists():
        return _read_cached_response(data_root, asset, data_day, spec, payload_kind), False
    blocker = _blocker_directory(data_root, asset, data_day, spec, payload_kind) / "blocker.json"
    if blocker.exists():
        payload = _strict_json_load(blocker)
        raise PermanentQualificationError(
            f"permanent HTTP blocker already recorded for {spec.role} {payload_kind}: "
            f"status={payload.get('status')}"
        )
    url = spec.url if payload_kind == "archive" else f"{spec.url}.CHECKSUM"
    try:
        response = fetch(url)
    except Exception as exc:
        raise RetryableDownloadError(
            f"{spec.role} {payload_kind} request timed out or failed before HTTP response: {exc}"
        ) from exc
    retrieved_at = clock()
    if 500 <= response.status <= 599:
        raise RetryableDownloadError(
            f"{spec.role} {payload_kind} returned retryable HTTP {response.status}"
        )
    parsed = urllib.parse.urlparse(response.final_url)
    if (
        400 <= response.status <= 499
        or response.status != 200
        or not response.body
        or parsed.scheme != "https"
        or parsed.netloc != "data.binance.vision"
        or response.final_url != url
    ):
        marker = _persist_permanent_http_blocker(
            data_root,
            asset,
            data_day,
            spec,
            payload_kind,
            response,
            retrieved_at,
        )
        raise PermanentQualificationError(
            f"{spec.role} {payload_kind} response is a permanent blocker at {marker}"
        )
    return (
        _persist_http_200(
            data_root,
            asset,
            data_day,
            spec,
            payload_kind,
            response,
            retrieved_at,
        ),
        True,
    )


def _checksum_expected(raw: bytes, filename: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PermanentQualificationError("official checksum must be UTF-8 text") from exc
    fields = text.strip().split()
    if len(fields) != 2 or fields[1].lstrip("*") != filename:
        raise PermanentQualificationError(
            "official checksum must name exactly the locked archive filename"
        )
    digest = fields[0].lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise PermanentQualificationError("official checksum does not contain one SHA-256")
    return f"sha256:{digest}"


def _zip_csv(raw_zip: bytes, filename: str) -> bytes:
    expected_csv = f"{filename.removesuffix('.zip')}.csv"
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if names != [expected_csv]:
                raise PermanentQualificationError(
                    f"{filename} must contain exactly {expected_csv}"
                )
            return archive.read(expected_csv)
    except zipfile.BadZipFile as exc:
        raise PermanentQualificationError(f"{filename} is not a valid ZIP") from exc


def _decimal(value: str, field: str, *, positive: bool) -> Decimal:
    if value != value.strip():
        raise PermanentQualificationError(f"{field} contains surrounding whitespace")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PermanentQualificationError(f"{field} must be numeric") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        qualifier = "positive" if positive else "finite"
        raise PermanentQualificationError(f"{field} must be finite and {qualifier}")
    return parsed


def _timestamp_ns(value: str, field: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise PermanentQualificationError(f"{field} must be an integer timestamp") from exc
    if str(integer) != value:
        raise PermanentQualificationError(f"{field} must use canonical integer text")
    magnitude = abs(integer)
    if 10**12 <= magnitude < 10**15:
        return integer * 1_000_000
    if 10**15 <= magnitude < 10**18:
        return integer * 1_000
    if 10**18 <= magnitude < 10**20:
        return integer
    raise PermanentQualificationError(
        f"{field} must use milliseconds, microseconds, or nanoseconds"
    )


def _book_timestamp(value: str, data_day: date, field: str) -> int:
    if value != value.strip():
        raise PermanentQualificationError(f"{field} contains surrounding whitespace")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise PermanentQualificationError(
            f"{field} must use exact UTC format YYYY-MM-DD HH:MM:SS"
        ) from exc
    if parsed.strftime("%Y-%m-%d %H:%M:%S") != value or parsed.date() != data_day:
        raise PermanentQualificationError(
            f"{field} must use exact UTC format on {data_day.isoformat()}"
        )
    start = datetime.combine(data_day, time.min, UTC)
    return int((parsed - start).total_seconds()) * 1_000_000_000 + int(
        start.timestamp()
    ) * 1_000_000_000


def _parse_csv(raw_csv: bytes, filename: str) -> list[list[str]]:
    try:
        text = raw_csv.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PermanentQualificationError(f"{filename} CSV must be UTF-8") from exc
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if any(not row or not any(field for field in row) for row in rows):
        raise PermanentQualificationError(f"{filename} CSV contains an empty row")
    return rows


def parse_book_depth(raw_zip: bytes, *, filename: str, data_day: date) -> BookDepthPayload:
    rows = _parse_csv(_zip_csv(raw_zip, filename), filename)
    if not rows or tuple(rows[0]) != BOOK_DEPTH_COLUMNS:
        raise PermanentQualificationError(
            "bookDepth CSV must contain the exact locked header and column order"
        )
    data_rows = rows[1:]
    if not data_rows:
        raise PermanentQualificationError("bookDepth CSV has no data rows")
    if any(len(row) != len(BOOK_DEPTH_COLUMNS) for row in data_rows):
        raise PermanentQualificationError("bookDepth CSV row width differs from locked schema")

    parsed_rows: list[BookDepthRow] = []
    groups: list[tuple[int, str, set[int]]] = []
    canonical = hashlib.sha256()
    current_ns: int | None = None
    current_text = ""
    current_grid: set[int] = set()
    for index, values in enumerate(data_rows):
        row = dict(zip(BOOK_DEPTH_COLUMNS, values, strict=True))
        timestamp_ns = _book_timestamp(
            row["timestamp"], data_day, f"{filename}.timestamp[{index}]"
        )
        try:
            percentage = int(row["percentage"])
        except ValueError as exc:
            raise PermanentQualificationError(
                f"{filename}.percentage[{index}] must be an integer"
            ) from exc
        if str(percentage) != row["percentage"]:
            raise PermanentQualificationError(
                f"{filename}.percentage[{index}] must use canonical integer text"
            )
        if current_ns is None or timestamp_ns != current_ns:
            if current_ns is not None:
                if current_grid != set(PERCENTAGE_GRID):
                    raise PermanentQualificationError(
                        "every bookDepth timestamp group must contain the exact ten-row grid"
                    )
                groups.append((current_ns, current_text, current_grid))
                if timestamp_ns <= current_ns:
                    raise PermanentQualificationError(
                        "bookDepth timestamp groups must be unique and strictly increasing"
                    )
            current_ns = timestamp_ns
            current_text = row["timestamp"]
            current_grid = set()
        if percentage not in PERCENTAGE_GRID:
            raise PermanentQualificationError("bookDepth percentage is outside the locked grid")
        if percentage in current_grid:
            raise PermanentQualificationError(
                "bookDepth percentage is duplicated within a timestamp group"
            )
        current_grid.add(percentage)
        depth = _decimal(row["depth"], f"{filename}.depth[{index}]", positive=True)
        notional = _decimal(
            row["notional"], f"{filename}.notional[{index}]", positive=True
        )
        parsed_rows.append(
            BookDepthRow(
                timestamp_ns=timestamp_ns,
                timestamp_text=row["timestamp"],
                percentage=percentage,
                depth=depth,
                notional=notional,
            )
        )
        canonical.update(("|".join(values) + "\n").encode())
    if current_ns is None or current_grid != set(PERCENTAGE_GRID):
        raise PermanentQualificationError(
            "every bookDepth timestamp group must contain the exact ten-row grid"
        )
    groups.append((current_ns, current_text, current_grid))

    start_ns = int(datetime.combine(data_day, time.min, UTC).timestamp()) * 1_000_000_000
    first_offset = (groups[0][0] - start_ns) // 1_000_000_000
    last_offset = (groups[-1][0] - start_ns) // 1_000_000_000
    if first_offset > 900:
        raise PermanentQualificationError("first bookDepth group is later than 00:15 UTC")
    if last_offset < 85_500:
        raise PermanentQualificationError("last bookDepth group is earlier than 23:45 UTC")
    gaps = [
        (current[0] - previous[0]) // 1_000_000_000
        for previous, current in zip(groups, groups[1:], strict=False)
    ]
    if gaps and max(gaps) > 900:
        raise PermanentQualificationError("bookDepth adjacent group gap exceeds 900 seconds")
    return BookDepthPayload(
        rows=tuple(parsed_rows),
        group_timestamps_ns=tuple(group[0] for group in groups),
        group_timestamps_text=tuple(group[1] for group in groups),
        canonical_rows_sha256=f"sha256:{canonical.hexdigest()}",
    )


def parse_mark_price(raw_zip: bytes, *, filename: str, data_day: date) -> MarkPricePayload:
    rows = _parse_csv(_zip_csv(raw_zip, filename), filename)
    if rows and tuple(rows[0]) == MARK_PRICE_COLUMNS:
        rows = rows[1:]
    if len(rows) != 1_440:
        raise PermanentQualificationError(
            "mark-price CSV must contain exactly 1,440 UTC minutes"
        )
    if any(len(row) != len(MARK_PRICE_COLUMNS) for row in rows):
        raise PermanentQualificationError("mark-price CSV row width differs from locked schema")
    start_ns = int(datetime.combine(data_day, time.min, UTC).timestamp()) * 1_000_000_000
    minute_ns = 60_000_000_000
    closes: dict[int, Decimal] = {}
    canonical = hashlib.sha256()
    for index, values in enumerate(rows):
        row = dict(zip(MARK_PRICE_COLUMNS, values, strict=True))
        open_ns = _timestamp_ns(row["open_time"], f"{filename}.open_time[{index}]")
        close_ns = _timestamp_ns(row["close_time"], f"{filename}.close_time[{index}]")
        expected_open = start_ns + index * minute_ns
        expected_next = expected_open + minute_ns
        if open_ns != expected_open:
            raise PermanentQualificationError(
                "mark-price CSV must contain one row in every UTC minute"
            )
        if not expected_next - 1_000_000 <= close_ns < expected_next:
            raise PermanentQualificationError("mark-price close_time is outside its UTC minute")
        prices = {
            key: _decimal(
                row[key], f"{filename}.{key}[{index}]", positive=True
            )
            for key in ("open", "high", "low", "close")
        }
        if prices["low"] > min(prices["open"], prices["close"]) or prices[
            "high"
        ] < max(prices["open"], prices["close"]):
            raise PermanentQualificationError(
                f"mark-price OHLC bounds are invalid at row {index}"
            )
        for key in (
            "volume",
            "quote_volume",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
        ):
            value = _decimal(row[key], f"{filename}.{key}[{index}]", positive=False)
            if value < 0:
                raise PermanentQualificationError(
                    f"{filename}.{key}[{index}] must be non-negative"
                )
        try:
            count = int(row["count"])
        except ValueError as exc:
            raise PermanentQualificationError(
                f"{filename}.count[{index}] must be an integer"
            ) from exc
        if str(count) != row["count"] or count < 0:
            raise PermanentQualificationError(
                f"{filename}.count[{index}] must be a canonical non-negative integer"
            )
        closes[open_ns] = prices["close"]
        canonical.update(("|".join(values) + "\n").encode())
    return MarkPricePayload(
        closes_by_minute_ns=closes,
        canonical_rows_sha256=f"sha256:{canonical.hexdigest()}",
    )


def qualification_audit(
    book: BookDepthPayload,
    mark: MarkPricePayload,
    *,
    asset: str,
    data_day: date,
) -> dict[str, Any]:
    bid_checked = 0
    ask_checked = 0
    matched_group_timestamps: set[int] = set()
    minute_ns = 60_000_000_000
    for index, row in enumerate(book.rows):
        mark_minute = row.timestamp_ns - row.timestamp_ns % minute_ns
        mark_close = mark.closes_by_minute_ns.get(mark_minute)
        if mark_close is None:
            raise PermanentQualificationError(
                "bookDepth timestamp minute has no matching mark-price close"
            )
        matched_group_timestamps.add(row.timestamp_ns)
        weighted_price = row.notional / row.depth
        percentage = Decimal(row.percentage) / Decimal(100)
        if row.percentage < 0:
            outer_boundary = mark_close * (Decimal(1) + percentage - TOLERANCE)
            valid = outer_boundary <= weighted_price < mark_close
            bid_checked += 1
        else:
            outer_boundary = mark_close * (Decimal(1) + percentage + TOLERANCE)
            valid = mark_close < weighted_price <= outer_boundary
            ask_checked += 1
        if not valid:
            raise PermanentQualificationError(
                "known bookDepth price-misalignment risk reproduced: "
                f"row {index} percentage {row.percentage} violates strict side/band rule"
            )
    gaps = [
        (current - previous) // 1_000_000_000
        for previous, current in zip(
            book.group_timestamps_ns,
            book.group_timestamps_ns[1:],
            strict=False,
        )
    ]
    mark_minutes = sorted(mark.closes_by_minute_ns)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "qualification_status": "asset_qualification_passed",
        "asset": asset,
        "data_date": data_day.isoformat(),
        "book_depth_row_count": len(book.rows),
        "timestamp_group_count": len(book.group_timestamps_ns),
        "first_group_utc": book.group_timestamps_text[0],
        "last_group_utc": book.group_timestamps_text[-1],
        "maximum_group_gap_seconds": max(gaps, default=0),
        "percentage_grid_json": json.dumps(PERCENTAGE_GRID, separators=(",", ":")),
        "book_depth_rows_sha256": book.canonical_rows_sha256,
        "mark_price_row_count": len(mark.closes_by_minute_ns),
        "first_mark_minute_ns": mark_minutes[0],
        "last_mark_minute_ns": mark_minutes[-1],
        "mark_price_rows_sha256": mark.canonical_rows_sha256,
        "mark_minute_matches": len(matched_group_timestamps),
        "band_rows_checked": len(book.rows),
        "bid_rows_checked": bid_checked,
        "ask_rows_checked": ask_checked,
        "band_violation_count": 0,
        "factor_values_saved": False,
        "signals_generated": False,
        "pnl_computed": False,
    }


def _request_evidence(
    spec: RequestSpec,
    archive: CachedResponse,
    checksum: CachedResponse,
) -> dict[str, Any]:
    return {
        "role": spec.role,
        "url": spec.url,
        "filename": spec.filename,
        "archive_sha256": _sha256(archive.body),
        "archive_http": archive.metadata,
        "checksum_url": f"{spec.url}.CHECKSUM",
        "checksum_filename": f"{spec.filename}.CHECKSUM",
        "checksum_sha256": _sha256(checksum.body),
        "checksum_http": checksum.metadata,
    }


def _content_sha256(requests: list[dict[str, Any]]) -> str:
    core = [
        {
            key: request[key]
            for key in (
                "role",
                "url",
                "filename",
                "archive_sha256",
                "checksum_url",
                "checksum_filename",
                "checksum_sha256",
            )
        }
        for request in requests
    ]
    return _canonical_sha(core)


def _snapshot_path(data_root: Path, asset: str, data_day: date) -> Path:
    return data_root / "snapshots" / asset / data_day.isoformat() / "snapshot.json"


def _audit_path(data_root: Path, asset: str, data_day: date) -> Path:
    return data_root / "audit" / asset / f"{data_day.isoformat()}.parquet"


def _write_immutable_json(path: Path, payload: dict[str, Any]) -> None:
    raw = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise PermanentQualificationError(f"immutable JSON conflict at {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=".json-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise PermanentQualificationError(
                    f"immutable JSON conflict at {path}"
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


def _audit_row(audit: dict[str, Any], snapshot_sha256: str, commit: str) -> dict[str, Any]:
    row = {
        **audit,
        "expected_git_commit": commit,
        "snapshot_sha256": snapshot_sha256,
    }
    return {column: row[column] for column in _AUDIT_COLUMNS}


def _write_audit_parquet(path: Path, row: dict[str, Any]) -> None:
    frame = pd.DataFrame([row], columns=_AUDIT_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_parquet(path)
        if list(existing.columns) != list(_AUDIT_COLUMNS) or existing.to_dict(
            orient="records"
        ) != [row]:
            raise PermanentQualificationError(f"immutable audit Parquet conflict at {path}")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".audit-", suffix=".parquet", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", compression="zstd", index=False)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = pd.read_parquet(path)
            if list(existing.columns) != list(_AUDIT_COLUMNS) or existing.to_dict(
                orient="records"
            ) != [row]:
                raise PermanentQualificationError(
                    f"immutable audit Parquet conflict at {path}"
                ) from None
    finally:
        temporary.unlink(missing_ok=True)


def _raw_file_hashes(
    data_root: Path,
    request_rows: list[dict[str, Any]],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for row in request_rows:
        for http_key, sha_key in (
            ("archive_http", "archive_sha256"),
            ("checksum_http", "checksum_sha256"),
        ):
            metadata = row[http_key]
            relative = Path("responses") / metadata["asset"] / metadata["data_date"]
            relative /= metadata["role"]
            relative /= metadata["payload_kind"]
            relative /= metadata["filename"]
            hashes[str(relative)] = row[sha_key]
    return dict(sorted(hashes.items()))


def _retrieved_at(request_rows: list[dict[str, Any]]) -> str:
    values = [
        datetime.fromisoformat(row[key]["retrieved_at"].replace("Z", "+00:00"))
        for row in request_rows
        for key in ("archive_http", "checksum_http")
    ]
    return _iso_utc(max(values))


def _parse_and_audit(
    specs: tuple[RequestSpec, RequestSpec],
    responses: dict[tuple[str, str], CachedResponse],
    *,
    asset: str,
    data_day: date,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request_rows = []
    archives: dict[str, bytes] = {}
    for spec in specs:
        archive = responses[(spec.role, "archive")]
        checksum = responses[(spec.role, "checksum")]
        expected = _checksum_expected(checksum.body, spec.filename)
        if _sha256(archive.body) != expected:
            raise PermanentQualificationError(
                f"official checksum mismatch for {spec.filename}"
            )
        archives[spec.role] = archive.body
        request_rows.append(_request_evidence(spec, archive, checksum))
    book = parse_book_depth(
        archives["book_depth"], filename=specs[0].filename, data_day=data_day
    )
    mark = parse_mark_price(
        archives["mark_price"], filename=specs[1].filename, data_day=data_day
    )
    return qualification_audit(book, mark, asset=asset, data_day=data_day), request_rows


def collect_asset(
    asset: str,
    data_day: date,
    *,
    data_root: Path,
    expected_git_commit: str,
    fetch: Fetch = _fetch,
    clock: Clock = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    asset = _validate_asset(asset)
    _validate_date(data_day)
    snapshot_path = _snapshot_path(data_root, asset, data_day)
    if snapshot_path.exists():
        verify_asset_snapshot(
            data_root,
            asset,
            data_day,
            expected_git_commit=expected_git_commit,
            verify_parquet=False,
        )
        envelope = _strict_json_load(snapshot_path)
        _write_audit_parquet(
            _audit_path(data_root, asset, data_day),
            _audit_row(
                envelope["audit"], envelope["snapshot_sha256"], expected_git_commit
            ),
        )
        verified = verify_asset_snapshot(
            data_root,
            asset,
            data_day,
            expected_git_commit=expected_git_commit,
        )
        return {**verified, "idempotent": True, "http_requests_made": 0}

    specs = build_requests(asset, data_day)
    responses: dict[tuple[str, str], CachedResponse] = {}
    requests_made = 0
    for spec in specs:
        for payload_kind in ("archive", "checksum"):
            response, fetched = _load_or_fetch_response(
                data_root,
                asset,
                data_day,
                spec,
                payload_kind,
                fetch=fetch,
                clock=clock,
            )
            responses[(spec.role, payload_kind)] = response
            requests_made += int(fetched)

    audit, request_rows = _parse_and_audit(
        specs, responses, asset=asset, data_day=data_day
    )
    content_sha256 = _content_sha256(request_rows)
    core = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "qualification_schema_version": QUALIFICATION_SCHEMA_VERSION,
        "kind": "book_depth_provider_qualification",
        "asset": asset,
        "data_date": data_day.isoformat(),
        "expected_git_commit": expected_git_commit,
        "provider": "Binance",
        "provider_contract": str(PROVIDER_CONTRACT),
        "provider_contract_sha256": LOCKED_PROVIDER_CONTRACT_SHA256,
        "retrieved_at": _retrieved_at(request_rows),
        "content_sha256": content_sha256,
        "requests": request_rows,
        "raw_file_hashes": _raw_file_hashes(data_root, request_rows),
        "audit": audit,
        "boundaries": dict(_BOUNDARIES),
    }
    snapshot_sha256 = _canonical_sha(core)
    envelope = {**core, "snapshot_sha256": snapshot_sha256}
    _write_immutable_json(snapshot_path, envelope)
    audit_path = _audit_path(data_root, asset, data_day)
    _write_audit_parquet(
        audit_path,
        _audit_row(audit, snapshot_sha256, expected_git_commit),
    )
    verified = verify_asset_snapshot(
        data_root,
        asset,
        data_day,
        expected_git_commit=expected_git_commit,
    )
    return {
        **verified,
        "audit_path": str(audit_path),
        "idempotent": False,
        "http_requests_made": requests_made,
    }


def _conflict_count(data_root: Path, asset: str | None = None) -> int:
    root = data_root / "conflicts"
    if asset is not None:
        root = root / asset / QUALIFICATION_DATE.isoformat()
    return len(list(root.rglob("conflict.json"))) if root.exists() else 0


def verify_asset_snapshot(
    data_root: Path,
    asset: str,
    data_day: date,
    *,
    expected_git_commit: str,
    verify_parquet: bool = True,
) -> dict[str, Any]:
    asset = _validate_asset(asset)
    _validate_date(data_day)
    snapshot_path = _snapshot_path(data_root, asset, data_day)
    envelope = _strict_json_load(snapshot_path)
    if envelope.get("schema_version") != SNAPSHOT_SCHEMA_VERSION or envelope.get(
        "qualification_schema_version"
    ) != QUALIFICATION_SCHEMA_VERSION:
        raise PermanentQualificationError("snapshot schema differs from v6 qualification")
    if envelope.get("kind") != "book_depth_provider_qualification":
        raise PermanentQualificationError("snapshot kind differs from v6 qualification")
    if envelope.get("asset") != asset or envelope.get("data_date") != data_day.isoformat():
        raise PermanentQualificationError("snapshot asset/date differs from requested evidence")
    if envelope.get("expected_git_commit") != expected_git_commit:
        raise PermanentQualificationError("snapshot commit differs from expected commit")
    if envelope.get("provider_contract_sha256") != LOCKED_PROVIDER_CONTRACT_SHA256:
        raise PermanentQualificationError("snapshot provider-contract hash drifted")
    if envelope.get("provider") != "Binance" or envelope.get(
        "provider_contract"
    ) != str(PROVIDER_CONTRACT):
        raise PermanentQualificationError("snapshot provider identity drifted")
    if envelope.get("boundaries") != _BOUNDARIES:
        raise PermanentQualificationError("snapshot safety boundaries drifted")

    specs = build_requests(asset, data_day)
    rows = envelope.get("requests")
    if not isinstance(rows, list) or len(rows) != 2:
        raise PermanentQualificationError("snapshot must contain exactly two archive requests")
    responses: dict[tuple[str, str], CachedResponse] = {}
    for spec, row in zip(specs, rows, strict=True):
        if not isinstance(row, dict):
            raise PermanentQualificationError("snapshot request entry must be an object")
        archive = _read_cached_response(data_root, asset, data_day, spec, "archive")
        checksum = _read_cached_response(data_root, asset, data_day, spec, "checksum")
        expected_row = _request_evidence(spec, archive, checksum)
        if row != expected_row:
            raise PermanentQualificationError(
                "snapshot request evidence differs from cached raw responses"
            )
        responses[(spec.role, "archive")] = archive
        responses[(spec.role, "checksum")] = checksum
    audit, request_rows = _parse_and_audit(
        specs, responses, asset=asset, data_day=data_day
    )
    if envelope.get("audit") != audit:
        raise PermanentQualificationError("snapshot audit differs from raw responses")
    if envelope.get("content_sha256") != _content_sha256(request_rows):
        raise PermanentQualificationError("snapshot content hash differs from raw responses")
    if envelope.get("raw_file_hashes") != _raw_file_hashes(data_root, request_rows):
        raise PermanentQualificationError("snapshot raw-file hashes differ from evidence")
    if envelope.get("retrieved_at") != _retrieved_at(request_rows):
        raise PermanentQualificationError("snapshot retrieval time differs from HTTP evidence")
    core = {key: value for key, value in envelope.items() if key != "snapshot_sha256"}
    snapshot_sha256 = _canonical_sha(core)
    if envelope.get("snapshot_sha256") != snapshot_sha256:
        raise PermanentQualificationError("snapshot envelope hash mismatch")
    if _conflict_count(data_root, asset):
        raise PermanentQualificationError("vintage conflict blocks provider qualification")

    audit_path = _audit_path(data_root, asset, data_day)
    parquet_sha256: str | None = None
    if verify_parquet:
        if not audit_path.is_file():
            raise PermanentQualificationError("qualification audit Parquet is missing")
        frame = pd.read_parquet(audit_path)
        expected_row = _audit_row(audit, snapshot_sha256, expected_git_commit)
        if list(frame.columns) != list(_AUDIT_COLUMNS) or frame.to_dict(
            orient="records"
        ) != [expected_row]:
            raise PermanentQualificationError(
                "qualification audit Parquet differs from snapshot/raw evidence"
            )
        parquet_sha256 = _sha256(audit_path.read_bytes())
    return {
        "path": str(snapshot_path),
        "audit_path": str(audit_path),
        "asset": asset,
        "data_date": data_day.isoformat(),
        "content_sha256": envelope["content_sha256"],
        "snapshot_sha256": snapshot_sha256,
        "audit_parquet_sha256": parquet_sha256,
        "audit": audit,
        "valid": True,
    }


def storage_summary(data_root: Path) -> dict[str, int]:
    snapshots = list((data_root / "snapshots").glob("*/2026-07-17/snapshot.json"))
    parquets = list((data_root / "audit").glob("*/2026-07-17.parquet"))
    archives = list((data_root / "responses").glob("*/2026-07-17/*/archive/*.zip"))
    checksums = list(
        (data_root / "responses").glob("*/2026-07-17/*/checksum/*.CHECKSUM")
    )
    blockers = list((data_root / "blocked-responses").rglob("blocker.json"))
    return {
        "snapshot_count": len(snapshots),
        "audit_parquet_count": len(parquets),
        "raw_zip_count": len(archives),
        "checksum_count": len(checksums),
        "cached_http_200_count": len(archives) + len(checksums),
        "conflict_count": _conflict_count(data_root),
        "permanent_http_blocker_count": len(blockers),
    }


def verify_evidence_root(
    data_root: Path,
    asset_selector: str,
    data_day: date,
    *,
    expected_git_commit: str,
) -> dict[str, Any]:
    assets = selected_assets(asset_selector)
    _validate_date(data_day)
    reviews = [
        verify_asset_snapshot(
            data_root,
            asset,
            data_day,
            expected_git_commit=expected_git_commit,
        )
        for asset in assets
    ]
    summary = storage_summary(data_root)
    if summary["conflict_count"]:
        raise PermanentQualificationError("evidence root contains a vintage conflict")
    if summary["permanent_http_blocker_count"]:
        raise PermanentQualificationError("evidence root contains a permanent HTTP blocker")
    if asset_selector == "all" and summary != {
        "snapshot_count": 2,
        "audit_parquet_count": 2,
        "raw_zip_count": 4,
        "checksum_count": 4,
        "cached_http_200_count": 8,
        "conflict_count": 0,
        "permanent_http_blocker_count": 0,
    }:
        raise PermanentQualificationError(
            "all-asset evidence root must contain exactly 2 snapshots, 2 audit Parquets, "
            "4 ZIPs, 4 checksums, and zero blockers/conflicts"
        )
    return {
        "schema_version": "research.v6.provider_qualification_verification.v1",
        "data_date": data_day.isoformat(),
        "assets": list(assets),
        "expected_git_commit": expected_git_commit,
        "snapshots": reviews,
        "storage": summary,
        "recommendation": (
            "provider_qualification_passed"
            if assets == ASSETS
            else "asset_qualification_passed_pending_other_asset"
        ),
        "network_accessed": False,
        "data_written": False,
        "boundaries": dict(_BOUNDARIES),
        "valid": True,
    }


def _clean_locked_commit(expected: str, repo_root: Path) -> dict[str, Any]:
    if len(expected) != 40 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("--expected-git-commit must be a 40-character lowercase SHA")
    marker = repo_root / ".collector-git-sha"
    if marker.is_file():
        actual = marker.read_text(encoding="ascii").strip()
        environment_sha = os.environ.get("TRADER_GIT_SHA")
        if environment_sha != actual:
            raise ValueError("collector image environment differs from its internal SHA marker")
        identity_mode = "immutable_image_marker"
        tracked_clean = True
    elif (repo_root / ".git").exists():
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo_root,
            text=True,
        ).strip()
        if dirty:
            raise ValueError("collector checkout has tracked working-tree changes")
        identity_mode = "clean_git_checkout"
        tracked_clean = True
    else:
        raise ValueError("collector requires a clean git checkout or immutable image marker")
    if actual != expected:
        raise ValueError(f"collector commit {actual} differs from locked commit {expected}")
    return {
        "git_commit": actual,
        "identity_mode": identity_mode,
        "tracked_worktree_clean": tracked_clean,
        "image_marker_checked": identity_mode == "immutable_image_marker",
        "valid": True,
    }


def _verify_provider_contract(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PROVIDER_CONTRACT
    payload = _strict_json_load(path)
    actual = _canonical_sha(payload)
    if actual != LOCKED_PROVIDER_CONTRACT_SHA256:
        raise ValueError("Protocol v6 provider contract differs from its locked hash")
    if payload.get("status") != "locked_before_archive_body_access":
        raise ValueError("Protocol v6 provider contract is not locked")
    return {"path": str(PROVIDER_CONTRACT), "sha256": actual, "valid": True}


def run_qualification(
    *,
    asset_selector: str,
    data_day: date,
    action: str,
    data_root: Path,
    expected_git_commit: str,
    verify_path: Path | None = None,
    repo_root: Path | None = None,
    fetch: Fetch = _fetch,
    clock: Clock = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    identity = _clean_locked_commit(expected_git_commit, repo_root)
    provider_contract = _verify_provider_contract(repo_root)
    assets = selected_assets(asset_selector)
    _validate_date(data_day)
    if action == "dry-run":
        plan = request_plan(asset_selector, data_day, data_root)
        if not plan["data_root_empty"]:
            raise PermanentQualificationError(
                "dry-run preflight requires an empty qualification data root"
            )
        return {**plan, "runtime_identity": identity, "provider_contract_audit": provider_contract, "complete": True}
    if action == "verify":
        if verify_path is None:
            raise ValueError("verify_path is required for verify")
        return {
            **verify_evidence_root(
                verify_path,
                asset_selector,
                data_day,
                expected_git_commit=expected_git_commit,
            ),
            "runtime_identity": identity,
            "provider_contract_audit": provider_contract,
            "complete": True,
        }
    if action != "download":
        raise ValueError("action must be download, dry-run, or verify")

    snapshots = []
    failures = []
    for asset in assets:
        try:
            snapshots.append(
                collect_asset(
                    asset,
                    data_day,
                    data_root=data_root,
                    expected_git_commit=expected_git_commit,
                    fetch=fetch,
                    clock=clock,
                )
            )
        except Exception as exc:
            failures.append(
                {
                    "asset": asset,
                    "data_date": data_day.isoformat(),
                    "error": str(exc),
                    "failure_class": (
                        "retryable_missing_request"
                        if isinstance(exc, RetryableDownloadError)
                        else "permanent_provider_qualification_blocker"
                    ),
                }
            )
    summary = storage_summary(data_root)
    complete = not failures and len(snapshots) == len(assets)
    if complete and assets == ASSETS:
        complete = summary == {
            "snapshot_count": 2,
            "audit_parquet_count": 2,
            "raw_zip_count": 4,
            "checksum_count": 4,
            "cached_http_200_count": 8,
            "conflict_count": 0,
            "permanent_http_blocker_count": 0,
        }
    permanent = any(
        failure["failure_class"] == "permanent_provider_qualification_blocker"
        for failure in failures
    )
    return {
        "schema_version": "research.v6.provider_qualification_batch.v1",
        "data_date": data_day.isoformat(),
        "assets": list(assets),
        "expected_git_commit": expected_git_commit,
        "runtime_identity": identity,
        "provider_contract_audit": provider_contract,
        "snapshots": snapshots,
        "failures": failures,
        "storage": summary,
        "complete": complete,
        "recommendation": (
            "provider_qualification_passed"
            if complete and assets == ASSETS
            else (
                "asset_qualification_passed_pending_other_asset"
                if complete
                else (
                    "blocked_provider_qualification"
                    if permanent
                    else "retry_missing_requests_only"
                )
            )
        ),
        "signals_generated": False,
        "pnl_computed": False,
        "boundaries": dict(_BOUNDARIES),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=(*ASSETS, "all"), required=True)
    parser.add_argument("--date", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--download", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--verify", type=Path)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--expected-git-commit", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        data_day = date.fromisoformat(args.date)
        action = "verify" if args.verify else "download" if args.download else "dry-run"
        report = run_qualification(
            asset_selector=args.asset,
            data_day=data_day,
            action=action,
            data_root=args.data_root,
            expected_git_commit=args.expected_git_commit,
            verify_path=args.verify,
        )
    except Exception as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report.get("complete", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())

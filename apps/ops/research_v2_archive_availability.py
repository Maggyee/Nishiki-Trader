"""Audit Binance archive metadata before opening Research Protocol v2 price bodies."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "research.archive_availability.v1"
S3_ENDPOINT = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
INDEX_PREFIX = "data/futures/cm/monthly/indexPriceKlines/BTCUSD/1d/"
CONTRACT_ROOT_PREFIX = "data/futures/cm/monthly/markPriceKlines/BTCUSD_"
REQUIRED_START = date(2020, 1, 1)
REQUIRED_END = date(2022, 12, 31)

_S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
_INDEX_FILE_RE = re.compile(r"^BTCUSD-1d-(20[0-9]{2}-[0-9]{2})\.zip$")
_CONTRACT_PREFIX_RE = re.compile(
    r"^data/futures/cm/monthly/markPriceKlines/(BTCUSD_([0-9]{6}))/\Z"
)

Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class S3Object:
    key: str
    size: int


@dataclass(frozen=True)
class S3Listing:
    objects: tuple[S3Object, ...]
    common_prefixes: tuple[str, ...]


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nishiki-Trader/research-protocol-v2-metadata"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def list_s3_metadata(
    prefix: str,
    *,
    delimiter: str | None = None,
    fetch: Fetch = _fetch,
) -> S3Listing:
    objects: list[S3Object] = []
    common_prefixes: list[str] = []
    continuation: str | None = None
    while True:
        params: dict[str, str] = {"list-type": "2", "prefix": prefix}
        if delimiter is not None:
            params["delimiter"] = delimiter
        if continuation is not None:
            params["continuation-token"] = continuation
        url = f"{S3_ENDPOINT}?{urllib.parse.urlencode(params)}"
        raw = fetch(url)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError("Binance S3 metadata response is invalid XML") from exc
        for node in root.findall("s3:Contents", _S3_NS):
            key = node.findtext("s3:Key", namespaces=_S3_NS)
            size = node.findtext("s3:Size", namespaces=_S3_NS)
            if key is None or size is None:
                raise ValueError("Binance S3 object metadata is incomplete")
            objects.append(S3Object(key=key, size=int(size)))
        for node in root.findall("s3:CommonPrefixes", _S3_NS):
            value = node.findtext("s3:Prefix", namespaces=_S3_NS)
            if value is None:
                raise ValueError("Binance S3 common prefix is incomplete")
            common_prefixes.append(value)
        truncated = root.findtext("s3:IsTruncated", namespaces=_S3_NS) == "true"
        if not truncated:
            break
        continuation = root.findtext("s3:NextContinuationToken", namespaces=_S3_NS)
        if not continuation:
            raise ValueError("truncated Binance S3 listing lacks continuation token")
    if len({obj.key for obj in objects}) != len(objects):
        raise ValueError("Binance S3 listing contains duplicate object keys")
    if len(set(common_prefixes)) != len(common_prefixes):
        raise ValueError("Binance S3 listing contains duplicate common prefixes")
    return S3Listing(tuple(objects), tuple(common_prefixes))


def _months(start: date, end: date) -> list[str]:
    year = start.year
    month = start.month
    result: list[str] = []
    while (year, month) <= (end.year, end.month):
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _contract_prefixes(
    prefixes: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    valid: list[dict[str, Any]] = []
    invalid: list[str] = []
    excluded: list[str] = []
    for prefix in prefixes:
        if prefix == CONTRACT_ROOT_PREFIX + "PERP/":
            excluded.append(prefix)
            continue
        match = _CONTRACT_PREFIX_RE.fullmatch(prefix)
        if not match:
            invalid.append(prefix)
            continue
        symbol, expiry_text = match.groups()
        try:
            expiry = date(
                2000 + int(expiry_text[:2]),
                int(expiry_text[2:4]),
                int(expiry_text[4:6]),
            )
        except ValueError:
            invalid.append(prefix)
            continue
        if expiry.month not in {3, 6, 9, 12}:
            invalid.append(prefix)
            continue
        valid.append({"symbol": symbol, "expiry": expiry.isoformat()})
    return sorted(valid, key=lambda row: row["expiry"]), sorted(invalid), sorted(excluded)


def audit_basis_archive_availability(*, fetch: Fetch = _fetch) -> dict[str, Any]:
    index_listing = list_s3_metadata(INDEX_PREFIX, fetch=fetch)
    contract_listing = list_s3_metadata(CONTRACT_ROOT_PREFIX, delimiter="/", fetch=fetch)
    zip_months: set[str] = set()
    checksum_months: set[str] = set()
    for obj in index_listing.objects:
        filename = obj.key.rsplit("/", 1)[-1]
        match = _INDEX_FILE_RE.fullmatch(filename)
        if match:
            if obj.size <= 0:
                raise ValueError(f"index archive {filename} has non-positive size metadata")
            zip_months.add(match.group(1))
            continue
        if filename.endswith(".zip.CHECKSUM"):
            base = filename[: -len(".CHECKSUM")]
            match = _INDEX_FILE_RE.fullmatch(base)
            if match:
                if obj.size <= 0:
                    raise ValueError(f"index checksum {filename} has non-positive size metadata")
                checksum_months.add(match.group(1))
    required_months = set(_months(REQUIRED_START, REQUIRED_END))
    missing_zips = sorted(required_months - zip_months)
    missing_checksums = sorted(required_months - checksum_months)
    valid_contracts, invalid_contract_prefixes, excluded_non_quarterly_prefixes = _contract_prefixes(
        contract_listing.common_prefixes
    )
    blockers: list[str] = []
    if missing_zips:
        blockers.append("missing_required_index_archive_months")
    if missing_checksums:
        blockers.append("missing_required_index_checksum_months")
    if blockers:
        status = "blocked_incomplete_historical_reserve"
        recommendation = "do_not_open_price_bodies_or_change_the_locked_year_gate"
    else:
        status = "metadata_index_coverage_pass_pending_contract_body_audit"
        recommendation = "preregister_contract_roll_and_body_audit_before_download"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "required_reserve": {
            "start": REQUIRED_START.isoformat(),
            "end": REQUIRED_END.isoformat(),
            "required_calendar_months": len(required_months),
        },
        "index_archive": {
            "prefix": INDEX_PREFIX,
            "first_available_month": min(zip_months) if zip_months else None,
            "last_available_month": max(zip_months) if zip_months else None,
            "available_month_count": len(zip_months),
            "missing_required_zip_months": missing_zips,
            "missing_required_checksum_months": missing_checksums,
        },
        "contract_archive": {
            "prefix": CONTRACT_ROOT_PREFIX,
            "valid_contract_count": len(valid_contracts),
            "valid_contracts": valid_contracts,
            "invalid_contract_prefixes": invalid_contract_prefixes,
            "excluded_non_quarterly_prefixes": excluded_non_quarterly_prefixes,
            "body_rows_opened": False,
        },
        "blockers": blockers,
        "recommendation": recommendation,
        "boundaries": {
            "http_methods": ["GET_S3_LIST_METADATA"],
            "zip_bodies_read": False,
            "checksum_bodies_read": False,
            "prices_read": False,
            "returns_loaded": False,
            "pnl_computed": False,
            "signals_generated": False,
            "nautilus_run": False,
            "source_policy_mutated": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main(argv: list[str] | None = None) -> int:
    _parser().parse_args(argv)
    print(json.dumps(audit_basis_archive_availability(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

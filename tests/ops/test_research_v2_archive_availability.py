from __future__ import annotations

import urllib.parse
from datetime import date
from xml.etree import ElementTree as ET

import pytest

from apps.ops.research_v2_archive_availability import (
    CONTRACT_ROOT_PREFIX,
    INDEX_PREFIX,
    S3_ENDPOINT,
    audit_basis_archive_availability,
    list_s3_metadata,
)

NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def _months(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start + "-01")
    finish = date.fromisoformat(end + "-01")
    result = []
    while current <= finish:
        result.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return result


def _xml(
    *,
    objects: list[tuple[str, int]] | None = None,
    prefixes: list[str] | None = None,
    truncated: bool = False,
    next_token: str | None = None,
) -> bytes:
    root = ET.Element("ListBucketResult", xmlns=NS)
    ET.SubElement(root, "IsTruncated").text = "true" if truncated else "false"
    if next_token is not None:
        ET.SubElement(root, "NextContinuationToken").text = next_token
    for key, size in objects or []:
        node = ET.SubElement(root, "Contents")
        ET.SubElement(node, "Key").text = key
        ET.SubElement(node, "Size").text = str(size)
    for prefix in prefixes or []:
        node = ET.SubElement(root, "CommonPrefixes")
        ET.SubElement(node, "Prefix").text = prefix
    return ET.tostring(root)


def _index_objects(months: list[str]) -> list[tuple[str, int]]:
    rows = []
    for month in months:
        filename = f"BTCUSD-1d-{month}.zip"
        rows.append((INDEX_PREFIX + filename, 1000))
        rows.append((INDEX_PREFIX + filename + ".CHECKSUM", 88))
    return rows


def _fetcher(index_months: list[str], *, zero_size: bool = False):
    objects = _index_objects(index_months)
    if zero_size:
        objects[0] = (objects[0][0], 0)
    prefixes = [
        CONTRACT_ROOT_PREFIX + "200925/",
        CONTRACT_ROOT_PREFIX + "201225/",
        CONTRACT_ROOT_PREFIX + "220631/",
        CONTRACT_ROOT_PREFIX + "230331/",
        CONTRACT_ROOT_PREFIX + "PERP/",
    ]

    def fetch(url: str) -> bytes:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        prefix = query["prefix"][0]
        if prefix == INDEX_PREFIX:
            return _xml(objects=objects)
        if prefix == CONTRACT_ROOT_PREFIX:
            return _xml(prefixes=prefixes)
        raise AssertionError(prefix)

    return fetch


def test_metadata_gate_blocks_missing_first_five_2020_months_without_price_access() -> None:
    review = audit_basis_archive_availability(
        fetch=_fetcher(_months("2020-06", "2026-06"))
    )

    assert review["status"] == "blocked_incomplete_historical_reserve"
    assert review["index_archive"]["first_available_month"] == "2020-06"
    assert review["index_archive"]["missing_required_zip_months"] == [
        "2020-01",
        "2020-02",
        "2020-03",
        "2020-04",
        "2020-05",
    ]
    assert review["recommendation"].startswith("do_not_open_price_bodies")
    assert review["boundaries"]["prices_read"] is False
    assert review["boundaries"]["pnl_computed"] is False


def test_complete_index_metadata_only_passes_to_future_body_preregistration() -> None:
    review = audit_basis_archive_availability(
        fetch=_fetcher(_months("2020-01", "2022-12"))
    )

    assert review["status"] == "metadata_index_coverage_pass_pending_contract_body_audit"
    assert review["blockers"] == []
    assert review["required_reserve"]["required_calendar_months"] == 36


def test_invalid_contract_expiry_prefix_is_reported_not_silently_parsed() -> None:
    review = audit_basis_archive_availability(
        fetch=_fetcher(_months("2020-01", "2022-12"))
    )

    assert review["contract_archive"]["valid_contracts"] == [
        {"symbol": "BTCUSD_200925", "expiry": "2020-09-25"},
        {"symbol": "BTCUSD_201225", "expiry": "2020-12-25"},
        {"symbol": "BTCUSD_230331", "expiry": "2023-03-31"},
    ]
    assert review["contract_archive"]["invalid_contract_prefixes"] == [
        CONTRACT_ROOT_PREFIX + "220631/"
    ]
    assert review["contract_archive"]["excluded_non_quarterly_prefixes"] == [
        CONTRACT_ROOT_PREFIX + "PERP/"
    ]


def test_s3_metadata_listing_follows_continuation_tokens() -> None:
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "continuation-token" not in query:
            return _xml(objects=[("prefix/one", 1)], truncated=True, next_token="next")
        assert query["continuation-token"] == ["next"]
        return _xml(objects=[("prefix/two", 2)])

    listing = list_s3_metadata("prefix/", fetch=fetch)

    assert [obj.key for obj in listing.objects] == ["prefix/one", "prefix/two"]
    assert len(calls) == 2
    assert calls[0].startswith(S3_ENDPOINT)


def test_non_positive_archive_size_fails_closed() -> None:
    with pytest.raises(ValueError, match="non-positive size"):
        audit_basis_archive_availability(
            fetch=_fetcher(_months("2020-01", "2022-12"), zero_size=True)
        )

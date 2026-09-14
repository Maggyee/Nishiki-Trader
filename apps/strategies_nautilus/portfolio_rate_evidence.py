"""Offline interpretation of original Binance rate fields, never network admission.

Limits, server counters and locally counted attempts are different evidence.
No function here authenticates an endpoint, identifies an egress IP or reserves
capacity. REST and WS API reports intentionally retain separate source scopes.
"""

from __future__ import annotations

import hashlib
import json

MAX_BODY = 16 * 1024 * 1024
MAX_HEADERS = 64 * 1024
INTERVALS = {"SECOND": (1, "s"), "MINUTE": (60, "m"), "HOUR": (3600, "h"), "DAY": (86400, "d")}
SCOPES = {"REQUEST_WEIGHT": "ip", "RAW_REQUESTS": "ip", "ORDERS": "account", "CONNECTIONS": "ip"}


class RateEvidenceError(ValueError):
    """Malformed or ambiguous original rate evidence."""


def _integer(value, *, positive=False):
    if type(value) is not int or value < int(positive):
        raise RateEvidenceError("invalid_rate_integer")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RateEvidenceError("duplicate_json_field")
        result[key] = value
    return result


def _body(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BODY:
        raise RateEvidenceError("rate_body_size_or_type")
    try:
        value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise RateEvidenceError("invalid_rate_json") from exc
    if not isinstance(value, dict):
        raise RateEvidenceError("rate_object_required")
    return value


def _invalid_constant(value):
    raise RateEvidenceError("nonfinite_json_number")


def _rates(rows, *, counts):
    if not isinstance(rows, list) or not rows or len(rows) > 64:
        raise RateEvidenceError("rate_limits_required")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RateEvidenceError("rate_row_required")
        kind, interval = row.get("rateLimitType"), row.get("interval")
        if (
            not isinstance(kind, str)
            or kind not in SCOPES
            or not isinstance(interval, str)
            or interval not in INTERVALS
        ):
            raise RateEvidenceError("unsupported_rate_type_or_interval")
        number = _integer(row.get("intervalNum"), positive=True)
        key = kind, interval, number
        if key in result:
            raise RateEvidenceError("duplicate_rate_interval")
        result[key] = {
            "rate_limit_type": kind,
            "scope": SCOPES[kind],
            "interval": interval,
            "interval_num": number,
            "interval_seconds": number * INTERVALS[interval][0],
            "limit": _integer(row.get("limit"), positive=True),
            "count": _integer(row.get("count")) if counts else None,
            "count_basis": "server_response_rateLimits" if counts else "not_observed",
        }
    return result


def _report(family, raw, rows, **extra):
    records = [rows[k] for k in sorted(rows)]
    if not any(r["rate_limit_type"] == "REQUEST_WEIGHT" for r in records):
        raise RateEvidenceError("request_weight_required")
    return {
        "schema_version": "portfolio.rate_evidence.v1",
        "status": "parsed_original_fields_not_admission",
        "endpoint_family": family,
        "body_sha256": hashlib.sha256(raw).hexdigest(),
        "rates": records,
        "exhausted_intervals": [
            {k: r[k] for k in ("rate_limit_type", "interval", "interval_num")}
            for r in records
            if r["count"] is not None and r["count"] >= r["limit"]
        ],
        "egress_ip": None,
        "source_authenticated": False,
        "freshness_verified": False,
        "cross_endpoint_ledger_verified": False,
        "connection_attempt_coverage_verified": False,
        "network_admitted": False,
        **extra,
    }


def rest_rate_evidence(metadata_raw, headers):
    """Parse one exchangeInfo body's limits and that same response's header pairs.

    Header pairs must be retained before normalization: a dict would erase case
    variants and duplicates. Missing advertised weight counters fail. Other limit
    types retain unknown usage, including RAW_REQUESTS and CONNECTIONS.
    """
    body = _body(metadata_raw)
    rows = _rates(body.get("rateLimits"), counts=False)
    if not isinstance(headers, (list, tuple)) or len(headers) > 256:
        raise RateEvidenceError("original_header_pairs_required")
    normalized, size = {}, 0
    for pair in headers:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise RateEvidenceError("invalid_header_pair")
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            raise RateEvidenceError("invalid_header_pair")
        size += len(name.encode()) + len(value.encode())
        if size > MAX_HEADERS:
            raise RateEvidenceError("rate_headers_too_large")
        name = name.lower()
        if name.startswith("x-mbx-used-weight-"):
            if name in normalized:
                raise RateEvidenceError("duplicate_weight_header")
            if not value or len(value) > 20 or not value.isascii() or not value.isdecimal():
                raise RateEvidenceError("invalid_weight_header")
            normalized[name] = int(value)
    expected = set()
    for (kind, interval, number), row in rows.items():
        if kind != "REQUEST_WEIGHT":
            continue
        header = f"x-mbx-used-weight-{number}{INTERVALS[interval][1]}"
        expected.add(header)
        if header not in normalized:
            raise RateEvidenceError("advertised_weight_usage_missing")
        row.update(count=normalized[header], count_basis="server_response_header")
    if set(normalized) != expected:
        raise RateEvidenceError("unadvertised_weight_interval")
    original = json.dumps(headers, ensure_ascii=True, separators=(",", ":")).encode()
    return _report(
        "spot_testnet_rest",
        metadata_raw,
        rows,
        header_pairs_sha256=hashlib.sha256(original).hexdigest(),
    )


def ws_rate_evidence(raw, *, request_id):
    """Parse a correlated WS API reply; result.rateLimits never supplies usage.

    CONNECTIONS in response status is retained if supplied, but does not prove
    market-endpoint coverage, pre-connect availability or counter semantics.
    """
    body = _body(raw)
    if (
        not isinstance(request_id, str)
        or not request_id
        or body.get("id") != request_id
        or type(body.get("status")) is not int
        or body["status"] != 200
        or "error" in body
        or "event" in body
        or not isinstance(body.get("result"), dict)
    ):
        raise RateEvidenceError("ws_successful_correlated_response_required")
    rows = _rates(body.get("rateLimits"), counts=True)
    result = body["result"]
    if "rateLimits" in result:
        definitions = _rates(result["rateLimits"], counts=False)
        for key, row in rows.items():
            if key not in definitions or row["limit"] != definitions[key]["limit"]:
                raise RateEvidenceError("ws_status_and_definitions_disagree")
        rows = {**definitions, **rows}
    return _report("spot_testnet_ws_api", raw, rows, request_id=request_id)

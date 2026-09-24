"""Original-route-bound REST depth anchors in a disposable joint parent."""

from __future__ import annotations

import base64
import json
import os
import re
from decimal import Decimal

PROFILE = "portfolio.installed_native_joint_depth.v1"
SELECTION_PROFILE = "portfolio.installed_joint_depth_request.v1"
TLS_PROFILE = "portfolio.installed_joint_depth_tls.v1"


def market_view():
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("market_ws_duplicate_key")
            value[key] = item
        return value

    def amount(value, *, positive=False):
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", value) is None
        ):
            raise ValueError("market_ws_decimal")
        number = Decimal(value)
        if (positive and number <= 0) or number != number.quantize(Decimal("0.00000001")):
            raise ValueError("market_ws_precision_or_price")
        return number

    return {
        "decode": lambda raw: json.loads(raw, object_pairs_hook=pairs),
        "amount": amount,
        "MAX_U64": 2**64 - 1,
    }


def response(raw):
    market = market_view()
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 5120:
        raise ValueError("joint_depth_original_limit")
    head, separator, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if not separator or lines[0] != b"HTTP/1.1 200 OK" or len(lines) != 4:
        raise ValueError("joint_depth_http_status")
    headers = {}
    for line in lines[1:]:
        key, sep, value = line.partition(b": ")
        if not sep or key.lower() in headers:
            raise ValueError("joint_depth_http_header")
        headers[key.lower()] = value
    if set(headers) != {b"content-length", b"connection", b"x-mbx-used-weight-1m"}:
        raise ValueError("joint_depth_http_headers")
    if (
        headers[b"connection"].lower() != b"close"
        or not headers[b"content-length"].isdigit()
        or not headers[b"x-mbx-used-weight-1m"].isdigit()
        or not 0 < int(headers[b"content-length"]) <= 4096
        or len(body) != int(headers[b"content-length"])
    ):
        raise ValueError("joint_depth_http_body")
    value = market["decode"](body)
    if (
        not isinstance(value, dict)
        or set(value) != {"lastUpdateId", "bids", "asks"}
        or type(value["lastUpdateId"]) is not int
        or not 0 < value["lastUpdateId"] <= market["MAX_U64"]
    ):
        raise ValueError("joint_depth_revision")
    for key, reverse in (("bids", True), ("asks", False)):
        rows = value[key]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("joint_depth_levels")
        prices = []
        for pair in rows:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("joint_depth_level")
            prices.append(market["amount"](pair[0], positive=True))
            market["amount"](pair[1], positive=True)
        if prices != sorted(set(prices), reverse=reverse):
            raise ValueError("joint_depth_order")
    if market["amount"](value["bids"][0][0]) >= market["amount"](value["asks"][0][0]):
        raise ValueError("joint_depth_crossed_book")
    return value


def expected_result(payload, symbol):
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or set(value) != {"profile", "tls_sha256", "header_receipt", "body_receipt", "response_b64"}
        or value["profile"] != "portfolio.installed_tls_receipt.v1"
    ):
        raise ValueError("joint_depth_receipt_schema")
    raw = base64.b64decode(value["response_b64"], validate=True)
    if base64.b64encode(raw).decode() != value["response_b64"]:
        raise ValueError("joint_depth_original_encoding")
    book = response(raw)
    return {
        "profile": PROFILE,
        "native_version": "1.226.0",
        "symbol": symbol,
        "last_update_id": book["lastUpdateId"],
        "levels": {key: book[key] for key in ("bids", "asks")},
        "tls_sha256": value["tls_sha256"],
        "header_receipt": value["header_receipt"],
        "body_receipt": value["body_receipt"],
        "snapshot_linked": False,
        "order_book_synchronized": False,
        "qualified_for_execution": False,
    }


def validate_native(payload):
    if os.geteuid() == 0:
        raise ValueError("joint_depth_native_root_refused")
    from nautilus_trader.core import nautilus_pyo3 as native

    if native.NAUTILUS_VERSION != "1.226.0":
        raise ValueError("joint_depth_native_version_changed")
    result = expected_result(payload, globals()["SYMBOL"])
    for side in ("bids", "asks"):
        for price, quantity in result["levels"][side]:
            if native.Price(Decimal(price), 8).as_decimal() != Decimal(price) or native.Quantity(
                Decimal(quantity), 8
            ).as_decimal() != Decimal(quantity):
                raise ValueError("joint_depth_native_rounding_refused")
    return result


def view(account, symbols, route_sha256, requests, *, index=10):
    if index not in {10, 11}:
        raise ValueError("joint_depth_fixed_index")
    selected = requests["view"](requests["base"], symbols, route_sha256)
    symbol = symbols[index - 10]
    endpoint = f"https://rest.fixture.invalid:23456/api/v3/depth?symbol={symbol}&limit=100"

    class DepthContract(account["AccountContract"]):
        SELECTION_PROFILE = SELECTION_PROFILE
        TLS_PROFILE = TLS_PROFILE
        ENDPOINT = endpoint
        LEDGER_PROFILE = "portfolio.fixture_joint_depth_tls_ledger.v1"
        CHALLENGE_INDEX = index
        CHALLENGE_FIELDS = {"route_sha256": route_sha256}
        PATH = "/api/v3/depth"
        SELECTION_FILE = "depth-request.json"

        def __init__(self, request_view, selection):
            super().__init__(request_view, selection)
            if (
                self.request
                != (
                    f"GET /api/v3/depth?symbol={symbol}&limit=100 HTTP/1.1\r\n"
                    "Host: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
                ).encode()
            ):
                raise ValueError("joint_depth_wire_request_changed")

    def ledger_view(module):
        return account["ledger_view"](
            module, profile=module.DEPTH_PROFILE, scope=module.DEPTH_SCOPE
        )

    def authorize(collector, ledger, authority, unused):
        return account["authorize"](
            collector, ledger, authority, selected, contract_type=DepthContract
        )

    def launch(authority, sources, launcher, runtime):
        return account["launch"](
            authority,
            sources,
            launcher,
            runtime,
            depth=True,
            depth_symbols=symbols,
            depth_route_sha=route_sha256,
            depth_index=index,
        )

    return {
        "PROFILE": PROFILE,
        "SELECTION_PROFILE": SELECTION_PROFILE,
        "AccountContract": DepthContract,
        "ledger_view": ledger_view,
        "rates_view": account["rates_view"],
        "transport_view": account["transport_view"],
        "authorize": authorize,
        "launch": launch,
        "expected_result": lambda payload: expected_result(payload, symbol),
    }


def child_loop(fd, parent):
    globals()["ACCOUNT"]["child_loop"](fd, parent, index=globals()["INDEX"], native=validate_native)

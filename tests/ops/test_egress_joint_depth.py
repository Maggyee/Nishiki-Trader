"""Route-bound 19-step selectors and the first native depth receipt."""

import base64
import json
import time

import pytest

from tests.ops.test_egress_installed_gateway import load

SYMBOLS = ["BNBUSDT", "BTCUSDT"]
ROUTE = "a" * 64


def fixture():
    base = load("gateway_native_requests")
    selector = load("gateway_joint_native_requests").view(vars(base), SYMBOLS, ROUTE)
    return base, selector


def challenge(index):
    return {
        "index": index,
        "nonce": "b" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "route_sha256": ROUTE,
    }


@pytest.mark.parametrize("index", range(19))
def test_joint_selector_maps_all_19_operations(index):
    base, selector = fixture()
    selected = challenge(index)
    raw = selector["native_request"](selected)
    assert selector["validate_request"](
        raw, selected, received=(time.time_ns(), time.monotonic_ns())
    ) == base.digest(raw)
    request = json.loads(raw)["request"]
    if index in {10, 11}:
        assert request["path"] == "/api/v3/depth"
        assert request["params"] == {"symbol": SYMBOLS[index - 10], "limit": "100"}
    elif index in {0, 12, 17}:
        assert request["path"] == "/api/v3/time"
    elif index in {3, 6, 13, 16}:
        assert request["path"] == "/api/v3/account"
    elif index in {4, 5, 14, 15}:
        assert request["path"] == "/api/v3/openOrders"
    elif index in {7, 8}:
        assert request["path"] == (
            "/api/v3/exchangeInfo" if index == 7 else "/api/v3/ticker/bookTicker"
        )
    elif index in {1, 9}:
        assert request["role"] == ("account" if index == 1 else "market")
    else:
        assert request["method"] == (
            "userDataStream.subscribe.signature" if index == 2 else "userDataStream.unsubscribe"
        )


@pytest.mark.parametrize("symbols,route", [
    (["BTCUSDT", "BNBUSDT"], ROUTE),
    (["BNBUSDT", "BNBUSDT"], ROUTE),
    (["BNBUSDT", "ETHUSDT", "BTCUSDT"], ROUTE),
    (SYMBOLS, "wrong"),
])
def test_joint_selector_requires_sorted_two_symbol_route(symbols, route):
    with pytest.raises(ValueError, match="joint_request_original_route_required"):
        load("gateway_joint_native_requests").view(vars(load("gateway_native_requests")), symbols, route)


@pytest.mark.parametrize("damage", ["route", "depth_symbol", "index", "stale", "clock", "signature"])
def test_joint_request_refuses_changed_original_or_signature(damage):
    base, selector = fixture()
    selected = challenge(13 if damage == "signature" else 10)
    raw = selector["native_request"](selected)
    envelope = json.loads(raw)
    received = (time.time_ns(), time.monotonic_ns())
    if damage == "route":
        selected["route_sha256"] = "c" * 64
    elif damage == "depth_symbol":
        envelope["request"]["params"]["symbol"] = "ETHUSDT"
    elif damage == "index":
        selected["index"] = 11
    elif damage == "stale":
        received = tuple(selected[k] + 5_000_000_001 for k in ("utc_ns", "monotonic_ns"))
    elif damage == "clock":
        received = (selected["utc_ns"] + 100_000_000, selected["monotonic_ns"])
    else:
        envelope["request"]["params"]["signature"] = base64.b64encode(b"z" * 64).decode()
    with pytest.raises(ValueError):
        selector["validate_request"](base.canonical(envelope), selected, received=received)


@pytest.mark.parametrize("damage", ["valid", "crossed", "duplicate", "precision", "truncated"])
def test_depth_original_matches_existing_snapshot_validation(damage):
    depth = load("gateway_joint_native_depth")
    snapshot = load("gateway_snapshot_ws")
    market = load("gateway_market_ws")
    body = {
        "lastUpdateId": 100,
        "bids": [["250.00000000", "2.00000000"]],
        "asks": [["251.00000000", "3.00000000"]],
    }
    if damage == "crossed":
        body["asks"][0][0] = "249.00000000"
    elif damage == "precision":
        body["bids"][0][1] = "2.000000001"
    raw_body = json.dumps(body, separators=(",", ":")).encode()
    if damage == "duplicate":
        raw_body = raw_body.replace(b'"lastUpdateId":100', b'"lastUpdateId":100,"lastUpdateId":100')
    raw = (
        b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(raw_body)).encode()
        + b"\r\nX-MBX-USED-WEIGHT-1M: 25\r\nConnection: close\r\n\r\n" + raw_body
    )
    if damage == "truncated":
        raw = raw[:-1]
    if damage == "valid":
        assert depth.response(raw) == snapshot.response(raw, vars(market))
        payload = json.dumps({
            "profile": "portfolio.installed_tls_receipt.v1",
            "tls_sha256": "d" * 64,
            "header_receipt": {"seq": 1, "utc_ns": 1, "monotonic_ns": 1},
            "body_receipt": {"seq": 2, "utc_ns": 2, "monotonic_ns": 2},
            "response_b64": base64.b64encode(raw).decode(),
        }).encode()
        assert depth.expected_result(payload, SYMBOLS[0])["snapshot_linked"] is False
    else:
        with pytest.raises(ValueError):
            depth.response(raw)
        with pytest.raises(ValueError):
            snapshot.response(raw, vars(market))

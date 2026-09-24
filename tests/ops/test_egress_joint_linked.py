"""Two-symbol snapshot linkage from exact buffered market event originals."""

import base64
import json
import time

import pytest

from tests.ops.test_egress_installed_gateway import load

SYMBOLS = ["BNBUSDT", "BTCUSDT"]
ROUTE = "a" * 64


def events(*, gap=False):
    market = load("gateway_market_ws")
    definitions = [{"symbol": s, "price_precision": 8, "size_precision": 8} for s in SYMBOLS]
    originals = []
    for symbol in SYMBOLS:
        for position in (0, 1):
            first = 104 if gap and symbol == "BNBUSDT" and position == 1 else 100 + 2 * position
            payload = json.dumps(
                {
                    "stream": symbol.lower() + "@depth@100ms",
                    "data": {
                        "e": "depthUpdate",
                        "E": time.time_ns() // 1_000_000,
                        "s": symbol,
                        "U": first,
                        "u": 101 if position == 0 else first,
                        "b": [["250.00000000", "2.00000000"]],
                        "a": [],
                    },
                },
                separators=(",", ":"),
            ).encode()
            originals.append(
                {
                    "raw_b64": base64.b64encode(payload).decode(),
                    "raw_sha256": market.digest(payload),
                    "receipt": {"utc_ns": 10 + len(originals), "monotonic_ns": 10 + len(originals)},
                }
            )
    return market.increments(originals, definitions, complete=True)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_each_selected_snapshot_links_one_original_successor(symbol):
    sequence = load("gateway_read_sequence")
    result = {
        "symbol": symbol,
        "last_update_id": 101,
        "header_receipt": {"utc_ns": 100, "monotonic_ns": 100},
        "tls_sha256": "b" * 64,
        "snapshot_linked": False,
        "order_book_synchronized": False,
    }
    originals = events()
    linked = sequence.joint_snapshot_link(result, originals)
    assert linked == {
        "symbol": symbol,
        "snapshot_last_update_id": 101,
        "linked_last_update_id": 102,
        "obsolete_events": 1,
        "linked_event_sha256": [
            next(
                item
                for item in originals
                if item["symbol"] == symbol and item["last_update_id"] == 102
            )["original_sha256"]
        ],
        "snapshot_tls_sha256": "b" * 64,
    }


@pytest.mark.parametrize(
    "damage", ["behind", "ahead", "late_event", "wrong_symbol", "claimed_link"]
)
def test_snapshot_refuses_unbound_revision_or_clock(damage):
    sequence = load("gateway_read_sequence")
    result = {
        "symbol": "BNBUSDT",
        "last_update_id": 101,
        "header_receipt": {"utc_ns": 100, "monotonic_ns": 100},
        "tls_sha256": "b" * 64,
        "snapshot_linked": False,
        "order_book_synchronized": False,
    }
    if damage == "behind":
        result["last_update_id"] = 99
    elif damage == "ahead":
        result["last_update_id"] = 103
    elif damage == "late_event":
        result["header_receipt"]["utc_ns"] = 10
    elif damage == "wrong_symbol":
        result["symbol"] = "ETHUSDT"
    else:
        result["snapshot_linked"] = True
    with pytest.raises(ValueError):
        sequence.joint_snapshot_link(result, events())


def test_market_gap_refused_before_any_depth_attempt():
    with pytest.raises(ValueError, match="market_ws_gap_duplicate_or_event_clock"):
        events(gap=True)


def test_second_depth_request_is_bound_to_original_two_symbol_route():
    base = load("gateway_native_requests")
    selector = load("gateway_joint_native_requests")
    account = load("gateway_native_account")
    depth = load("gateway_joint_native_depth").view(
        vars(account), SYMBOLS, ROUTE, {"view": selector.view, "base": vars(base)}, index=11
    )
    selected = selector.view(vars(base), SYMBOLS, ROUTE)
    challenge = {
        "index": 11,
        "nonce": "a" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "route_sha256": ROUTE,
    }
    assert depth["AccountContract"].CHALLENGE_INDEX == 11
    assert depth["AccountContract"].ENDPOINT.endswith("/api/v3/depth?symbol=BTCUSDT&limit=100")
    assert selected["selected_request"](challenge) == {
        "kind": "rest",
        "method": "GET",
        "path": "/api/v3/depth",
        "params": {"symbol": "BTCUSDT", "limit": "100"},
        "headers": {},
    }
    with pytest.raises(ValueError, match="joint_request_route_challenge"):
        selected["validate_challenge"]({**challenge, "route_sha256": "b" * 64}, 11)
    with pytest.raises(ValueError):
        selected["validate_challenge"]({**challenge, "index": 10}, 11)

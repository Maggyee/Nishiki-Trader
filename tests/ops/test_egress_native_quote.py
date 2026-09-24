"""Bounded fixture quote receipts agree between root stdlib and native L2."""

import base64
import copy
import hashlib
import json

import pytest
from nautilus_trader.core import nautilus_pyo3 as native

from tests.ops.test_egress_installed_gateway import load


def evidence():
    code = load("gateway_native_quote")
    snapshot = load("gateway_snapshot_ws")
    market = load("gateway_market_ws")
    symbol = "BTCUSDT"
    body = {
        "lastUpdateId": 101,
        "bids": [["100.00000000", "1.00000000"], ["99.00000000", "3.00000000"]],
        "asks": [["101.00000000", "2.00000000"]],
    }
    raw = json.dumps(body, sort_keys=True).encode()
    received = 1_800_000_000_300_000_000
    event_ns = received - 100_000_000
    instrument = native.InstrumentId.from_str(symbol + ".BINANCE")

    def delta(side, action, price, size):
        return native.OrderBookDelta(
            instrument,
            getattr(native.BookAction, action),
            native.BookOrder(
                getattr(native.OrderSide, side),
                native.Price.from_str(price),
                native.Quantity.from_str(size),
                0,
            ),
            128,
            103,
            event_ns,
            received,
        ).to_dict()

    result = {
        "anchors": [
            {
                "symbol": symbol,
                "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                "snapshot_last_update_id": 101,
                "linked_last_update_id": 103,
                "linked_event_sha256": ["a" * 64],
                "snapshot_receipt": {"utc_ns": received, "monotonic_ns": 1},
            }
        ],
        "market": [
            {
                "symbol": symbol,
                "first_update_id": 102,
                "last_update_id": 103,
                "original_sha256": "a" * 64,
                "receipt": {"utc_ns": received, "monotonic_ns": 1},
                "deltas": [
                    delta("BUY", "DELETE", "100.00000000", "0.00000000"),
                    delta("SELL", "UPDATE", "101.00000000", "2.00000000"),
                ],
            }
        ],
    }
    payload = market.canonical(
        {
            "snapshots": [
                {
                    "symbol": symbol,
                    "chunks": [{"raw_b64": base64.b64encode(raw).decode()}],
                }
            ]
        }
    )
    snapshot_scope = {
        "response": lambda data, _: json.loads(data),
        "QUOTE_RECEIPT": snapshot.QUOTE_RECEIPT,
    }
    return code, market.__dict__, snapshot_scope, payload, result


def test_root_expected_matches_native_quote(monkeypatch):
    code, market, snapshot, payload, result = evidence()
    expected = code.expected_result(payload, lambda _: result, market, snapshot)
    monkeypatch.setattr(code.os, "geteuid", lambda: 1000)
    actual = code.validate_native(payload, lambda _: result, market, snapshot)
    assert actual == expected
    assert actual["quotes"] == [
        {
            "type": "QuoteTick",
            "instrument_id": "BTCUSDT.BINANCE",
            "bid_price": "99.00000000",
            "ask_price": "101.00000000",
            "bid_size": "3.00000000",
            "ask_size": "2.00000000",
            "ts_event": 1_800_000_000_200_000_000,
            "ts_init": 1_800_000_000_300_000_000,
        }
    ]
    assert not actual["stream_fence_verified"] and not actual["qualified_for_execution"]


@pytest.mark.parametrize("damage", ["empty", "crossed", "stale", "revision", "original"])
def test_invalid_quote_never_acknowledged(damage):
    code, market, snapshot, payload, result = evidence()
    result = copy.deepcopy(result)
    if damage == "empty":
        value = json.loads(payload)
        body = json.loads(base64.b64decode(value["snapshots"][0]["chunks"][0]["raw_b64"]))
        body["bids"].pop()
        raw = json.dumps(body, sort_keys=True).encode()
        value["snapshots"][0]["chunks"][0]["raw_b64"] = base64.b64encode(raw).decode()
        result["anchors"][0]["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
        payload = market["canonical"](value)
    elif damage == "crossed":
        result["market"][0]["deltas"][0]["action"] = "UPDATE"
        result["market"][0]["deltas"][0]["order"]["price"] = "102.00000000"
        result["market"][0]["deltas"][0]["order"]["size"] = "1.00000000"
    elif damage == "stale":
        result["market"][0]["deltas"][-1]["ts_event"] -= code.MAX_AGE_NS + 1
    elif damage == "revision":
        result["anchors"][0]["linked_last_update_id"] = 104
    else:
        result["anchors"][0]["snapshot_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="quote_"):
        code.expected_result(payload, lambda _: result, market, snapshot)


def test_root_refuses_native_import(monkeypatch):
    code, market, snapshot, payload, result = evidence()
    monkeypatch.setattr(code.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="quote_native_root_refused"):
        code.validate_native(payload, lambda _: result, market, snapshot)

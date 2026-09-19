"""Repeated native open orders must agree with original account locks."""

import base64
import copy
import json
import os
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_read_sequence import capture_sequence, review
from tests.ops.test_egress_signed_account import selection
from tests.ops.test_egress_tls_receipt import _rechain


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    yield from capture_sequence(tmp_path_factory, orders=True)


def payload(rows):
    raw = b"HTTP/1.1 200 OK\r\n\r\n" + json.dumps(rows).encode()
    clock = {"seq": 1, "utc_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns()}
    return json.dumps(
        {
            "response_b64": base64.b64encode(raw).decode(),
            "tls_sha256": "a" * 64,
            "header_receipt": clock,
            "body_receipt": clock,
        }
    ).encode()


def orders():
    return copy.deepcopy(load("installed_gateway_selftest").FIXTURE_ORDERS)


def test_native_five_read_sequence_preserves_partial_orders_and_locks(captured):
    report = review(captured)
    assert report["status"] == "complete" and report["accepted_steps"] == 5
    assert report["open_order_locks_matched"] and report["repeated_open_orders_equal"]
    assert report["repeated_balances_equal"] and not report["stream_fence_verified"]
    first = report["steps"][2]
    assert first["receipt"]["native_orders_acknowledged"]
    row = next(r for r in first["native_result"]["orders"] if r["orderId"] == 102)
    assert row["status"] == "PARTIALLY_FILLED" and Decimal(row["remainingQty"]) == Decimal("0.1")
    assert first["native_result"] == captured.modules["orders"]["validate_native"](
        captured.payloads[2]
    )
    assert not first["native_result"]["qualified_for_execution"]
    assert first["attempts"]["counts"][0]["documented_weight"] == 80


@pytest.mark.parametrize("end", range(1, 12))
def test_order_sequence_prefix_never_invents_completion(captured, end):
    lines = captured.raw.splitlines(keepends=True)[:end]
    count = sum(json.loads(line)["kind"] == "prepared" for line in lines)
    report = review(captured, b"".join(lines), captured.bundles[:count])
    assert report["status"] == "incomplete_no_resume" and not report["restart_allowed"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("type", "MARKET"),
        ("timeInForce", "IOC"),
        ("status", "FILLED"),
        ("side", "other"),
        ("orderId", True),
        ("symbol", "OTHERUSDT"),
        ("clientOrderId", "bad\nname"),
        ("price", "0"),
        ("origQty", "-1"),
        ("executedQty", "0.001"),
        ("cummulativeQuoteQty", "1"),
        ("stopPrice", "1"),
        ("icebergQty", "0.001"),
        ("origQuoteOrderQty", "1"),
        ("orderListId", 1),
        ("isWorking", False),
        ("updateTime", 2**63),
    ],
)
def test_unsupported_or_conflicting_order_fields_refused(key, value):
    rows = orders()
    rows[0][key] = value
    with pytest.raises(ValueError):
        load("gateway_native_orders").expected_result(payload(rows))


def test_duplicate_and_empty_open_order_sets():
    module = load("gateway_native_orders")
    rows = orders()
    with pytest.raises(ValueError, match="duplicate_order"):
        module.expected_result(payload(rows + [rows[0]]))
    assert module.validate_native(payload([]))["orders"] == []


@pytest.mark.parametrize(
    "key,value",
    [("price", "12500.000000001"), ("origQty", "0.001000001"), ("executedQty", "0.100000001")],
)
def test_native_order_values_never_silently_round(key, value):
    rows = orders()
    rows[1 if key == "executedQty" else 0][key] = value
    with pytest.raises(ValueError, match="rounding_refused"):
        load("gateway_native_orders").validate_native(payload(rows))


@pytest.mark.parametrize(
    "damage", ["swap", "account_in_orders", "missing_receipt", "signature", "native_status"]
)
def test_original_order_steps_cannot_be_replaced_or_acknowledgements_fabricated(captured, damage):
    bundles = copy.deepcopy(captured.bundles)
    if damage == "swap":
        bundles[2], bundles[3] = bundles[3], bundles[2]
    elif damage == "account_in_orders":
        bundles[2] = bundles[1]
    elif damage == "missing_receipt":
        del bundles[2]["receipt"]
    elif damage == "signature":
        value = json.loads(bundles[2]["selection"])
        value["request"]["request"]["params"]["signature"] = base64.b64encode(b"x" * 64).decode()
        bundles[2]["selection"] = captured.code.canonical(value).decode()
    else:
        rows = list(map(json.loads, bundles[2]["receipt"].splitlines()))
        rows[-1]["native_result"]["orders"][0]["status"] = "NEW"
        bundles[2]["receipt"] = _rechain(rows).decode()
    with pytest.raises(ValueError):
        review(captured, bundles=bundles)


@pytest.mark.parametrize(
    "damage", ["quote_lock", "base_lock", "remaining", "missing_order", "changed_id"]
)
def test_order_reconciliation_requires_all_locks_and_equal_open_sets(captured, damage):
    results = copy.deepcopy(review(captured)["steps"])
    if damage in {"quote_lock", "base_lock"}:
        row = next(
            r
            for r in results[1]["native_result"]["balances"]
            if r["currency"] == ("USDT" if damage == "quote_lock" else "BNB")
        )
        row["locked"] = "0"
    elif damage == "remaining":
        for index in (2, 3):
            results[index]["native_result"]["orders"][0]["executedQty"] = "0.15"
    elif damage == "missing_order":
        for index in (2, 3):
            results[index]["native_result"]["orders"].pop()
    else:
        results[3]["native_result"]["orders"][0]["orderId"] += 1
    with pytest.raises(ValueError):
        captured.code.reconcile(results, orders=True)


def test_empty_orders_only_match_zero_locked_balances(captured):
    results = copy.deepcopy(review(captured)["steps"])
    for index in (2, 3):
        results[index]["native_result"]["orders"] = []
    with pytest.raises(ValueError, match="locks_mismatch"):
        captured.code.reconcile(results, orders=True)
    for index in (1, 4):
        for row in results[index]["native_result"]["balances"]:
            row["locked"] = "0"
    assert captured.code.reconcile(results, orders=True)["repeated_balances_equal"]


def test_account_profile_cannot_replay_five_read_order_sequence(captured):
    with pytest.raises(ValueError):
        captured.code.replay(
            captured.raw,
            expected_sha256=captured.code.digest(captured.raw),
            bundles=captured.bundles,
            modules=captured.modules,
        )


def test_fixed_orders_contract_uses_exact_signed_get_selector():
    account = vars(load("gateway_native_account"))
    module = load("gateway_native_orders").view(account)
    requests, value = selection(SimpleNamespace(**module), index=4)
    contract = module["AccountContract"](requests, value)
    assert contract.request.startswith(b"GET /api/v3/openOrders?timestamp=")
    assert contract.SELECTION_FILE == "orders-request.json"
    requests, account_value = selection(SimpleNamespace(**module), index=3)
    with pytest.raises(ValueError):
        module["AccountContract"](requests, account_value)


def test_native_order_import_refuses_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root_refused"):
        load("gateway_native_orders").validate_native(b"not parsed")

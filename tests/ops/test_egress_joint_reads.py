"""Fixed signed selectors and reconciliation of the first ordered account pass."""

import copy
import json
import time

import pytest

from apps.strategies_nautilus import portfolio_rate_evidence
from tests.ops.test_egress_installed_gateway import load


def _selected(module, index):
    requests = load("gateway_native_requests")
    challenge = {
        "index": index,
        "nonce": "a" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
    }
    request = json.loads(requests.native_request(challenge))
    selection = {
        "profile": module["SELECTION_PROFILE"],
        "binding_sha256": "b" * 64,
        "challenge": challenge,
        "request": request,
        "received": [time.time_ns(), time.monotonic_ns()],
    }
    return vars(requests), selection


@pytest.mark.parametrize(
    "index,path",
    [
        (3, "/api/v3/account"),
        (4, "/api/v3/openOrders"),
        (5, "/api/v3/openOrders"),
        (6, "/api/v3/account"),
    ],
)
def test_each_account_pass_selector_uses_its_fixed_native_index(index, path):
    account = load("gateway_native_account")
    module = (
        account.view_for_index(index)
        if index in {3, 6}
        else load("gateway_native_orders").view(vars(account), index=index)
    )
    requests, selection = _selected(module, index)
    contract = module["AccountContract"](requests, selection)
    assert path == contract.PATH
    assert contract.request.startswith(("GET " + path + "?timestamp=").encode())
    selection["challenge"]["index"] = 6 if index != 6 else 5
    with pytest.raises(ValueError):
        module["AccountContract"](requests, selection)


@pytest.mark.parametrize(
    "index,path", [(7, "/api/v3/exchangeInfo"), (8, "/api/v3/ticker/bookTicker")]
)
def test_same_parent_route_selectors_are_exact_unsigned_requests(index, path):
    account = vars(load("gateway_native_account"))
    module = (
        load("gateway_native_receipt").view(account, portfolio_rate_evidence)
        if index == 7
        else load("gateway_book_routes").view(account)
    )
    requests, selection = _selected(module, index)
    contract = module["AccountContract"](requests, selection)
    assert (
        contract.request
        == (
            f"GET {path} HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
        ).encode()
    )
    selection["challenge"]["index"] = 8 if index == 7 else 7
    with pytest.raises(ValueError):
        module["AccountContract"](requests, selection)


@pytest.fixture
def first_pass():
    account = {
        "account_uid": 41001,
        "balances": [
            {"currency": asset, "precision": 8, "total": total, "locked": locked, "free": free}
            for asset, total, locked, free in (
                ("BNB", "1.10000000", "0.10000000", "1.00000000"),
                ("BTC", "0.01100000", "0.00100000", "0.01000000"),
                ("ETH", "0.00000000", "0.00000000", "0.00000000"),
                ("USDT", "512.50000000", "12.50000000", "500.00000000"),
            )
        ],
    }
    fixtures = load("installed_gateway_selftest").FIXTURE_ORDERS
    orders = {
        "account_uid": 41001,
        "orders": [{**row, "remainingQty": row["origQty"]} for row in fixtures],
    }
    return [{"native_result": None} for _ in range(3)] + [
        {"native_result": account},
        {"native_result": orders},
        {"native_result": copy.deepcopy(orders)},
        {"native_result": copy.deepcopy(account)},
    ]


def test_first_pass_requires_both_orders_and_both_balances(first_pass):
    replay = load("gateway_read_sequence")
    for length in range(5, 8):
        replay.reconcile_joint_before(first_pass[:length])


@pytest.mark.parametrize(
    "damage", ["first_uid", "second_uid", "orders", "locked", "last_uid", "last_balance"]
)
def test_account_pass_refuses_reconciled_drift(first_pass, damage):
    results = copy.deepcopy(first_pass)
    if damage == "first_uid":
        results[3]["native_result"]["account_uid"] = 41002
    elif damage == "second_uid":
        results[5]["native_result"]["account_uid"] = 41002
    elif damage == "orders":
        results[5]["native_result"]["orders"][0]["orderId"] = 104
    elif damage == "locked":
        results[3]["native_result"]["balances"][0]["locked"] = "0.00000000"
    elif damage == "last_uid":
        results[6]["native_result"]["account_uid"] = 41002
    else:
        results[6]["native_result"]["balances"][0]["free"] = "2.00000000"
    with pytest.raises(ValueError):
        load("gateway_read_sequence").reconcile_joint_before(results)

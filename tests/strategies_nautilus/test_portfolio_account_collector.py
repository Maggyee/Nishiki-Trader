from __future__ import annotations

import asyncio
import copy
import json
from decimal import Decimal as D

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_account import AccountAnchor
from apps.strategies_nautilus.portfolio_account_collector import BinanceReadOnlyAccountCollector
from apps.strategies_nautilus.portfolio_venue import VenueInputError
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


class SignedClientFixture:
    base_url = "https://api.binance.com"

    def __init__(self):
        self.calls = []
        account = {
            "uid": 123,
            "accountType": "SPOT",
            "canTrade": True,
            "permissions": ["SPOT"],
            "balances": [],
        }
        self.responses = {
            "/sapi/v1/account/apiRestrictions": [
                {"enableReading": True, "enableSpotAndMarginTrading": False}
            ],
            "/api/v3/account": [account, copy.deepcopy(account)],
            "/api/v3/openOrders": [[], []],
            "/api/v3/allOrders": [[]],
            "/api/v3/myTrades": [[]],
        }

    async def sign_request(self, method, path, *, payload):
        assert method == HttpMethod.GET
        assert payload["recvWindow"] == "5000"
        assert int(payload["timestamp"]) == (BASE_NS + 2 * SECOND) // 1_000_000
        self.calls.append((method, path, payload.copy()))
        return json.dumps(self.responses[path].pop(0)).encode()


def collect(client, *, max_pages=32, start_ns=BASE_NS):
    source = BinanceReadOnlyAccountCollector(
        client, clock_ns=lambda: BASE_NS + 2 * SECOND, max_pages=max_pages
    )
    return asyncio.run(source.collect(AccountAnchor("123", "BINANCE-001", start_ns, D("500"))))


def test_signed_gets_only_read_only_key_and_explicit_non_atomic_result():
    client = SignedClientFixture()
    result = collect(client)
    assert len(client.calls) == 7
    assert all(method == HttpMethod.GET for method, _, _ in client.calls)
    assert all(
        "symbol" not in params for _, path, params in client.calls if path.endswith("openOrders")
    )
    assert len(result.wire_sha256) == 7
    assert not result.api_trading_enabled
    assert not result.atomic_revision_verified
    assert result.evidence.account.account_id == "123"
    assert result.evidence.start_ns == BASE_NS


@pytest.mark.parametrize(
    "path,key,cursor",
    [("/api/v3/allOrders", "orderId", "orderId"), ("/api/v3/myTrades", "id", "fromId")],
)
def test_full_pages_require_followup_and_keep_native_wire_hashes(path, key, cursor):
    client = SignedClientFixture()
    client.responses[path] = [[{key: i} for i in range(1000)], [{key: 1000}]]
    result = collect(client)
    calls = [p for _, pth, p in client.calls if pth == path]
    assert calls[0]["startTime"] == str(BASE_NS // 1_000_000)
    assert calls[1][cursor] == "1000"
    assert "startTime" not in calls[1]
    assert len(result.wire_sha256) == 8


def test_full_last_page_never_claims_complete_history():
    client = SignedClientFixture()
    client.responses["/api/v3/allOrders"] = [[{"orderId": i} for i in range(1000)]]
    with pytest.raises(VenueInputError, match="pagination incomplete"):
        collect(client, max_pages=1)


@pytest.mark.parametrize(
    "rows",
    [[{"orderId": 2}, {"orderId": 1}], [{"orderId": 1}, {"orderId": 1}], [{"orderId": True}]],
)
def test_ambiguous_history_page_fails_closed(rows):
    client = SignedClientFixture()
    client.responses["/api/v3/allOrders"] = [rows]
    with pytest.raises(VenueInputError, match="history page"):
        collect(client)


@pytest.mark.parametrize(
    "path,change",
    [
        ("/api/v3/account", {"uid": 999}),
        ("/api/v3/account", {"canTrade": False}),
        ("/api/v3/openOrders", [{"clientOrderId": "new-external-order"}]),
    ],
)
def test_account_changes_during_reads_require_new_collection(path, change):
    client = SignedClientFixture()
    if path.endswith("account"):
        client.responses[path][1].update(change)
    else:
        client.responses[path][1] = change
    with pytest.raises(VenueInputError, match="changed during collection"):
        collect(client)


def test_wrong_signed_account_or_read_permission_fails_before_history():
    client = SignedClientFixture()
    client.responses["/api/v3/account"][0]["uid"] = 999
    with pytest.raises(VenueInputError, match="UID mismatch"):
        collect(client)
    assert not any(path.endswith("allOrders") for _, path, _ in client.calls)
    client = SignedClientFixture()
    client.responses["/sapi/v1/account/apiRestrictions"][0]["enableReading"] = False
    with pytest.raises(VenueInputError, match="reading permission"):
        collect(client)


def test_collector_refuses_unqualified_long_history_and_arbitrary_signed_hosts():
    client = SignedClientFixture()
    with pytest.raises(VenueInputError, match="history archive"):
        collect(client, start_ns=BASE_NS - 86_400 * SECOND)
    assert not client.calls
    client.base_url = "https://untrusted.example"
    with pytest.raises(VenueInputError, match="endpoint"):
        collect(client)


def test_transport_errors_do_not_echo_private_payloads():
    client = SignedClientFixture()

    async def failure(*args, **kwargs):
        raise RuntimeError("secret signed URL should not escape")

    client.sign_request = failure
    with pytest.raises(VenueInputError, match="^signed account read failed$"):
        collect(client)

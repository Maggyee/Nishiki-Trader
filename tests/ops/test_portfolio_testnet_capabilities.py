from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_testnet_capabilities import (
    PATHS,
    PRIVATE,
    PUBLIC,
    TestnetCapabilityHttpClient,
    review_capabilities,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_testnet_session import (
    FIXED,
    VALIDATE_PATH,
    TestnetOrderValidationHttpClient,
    validate_order,
    validation_price,
)
from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    VenueInputError,
    parse_binance_rules,
)

NOW = 1_789_106_400_000_000_000


def fixture_capture():
    account = {
        "uid": 123,
        "accountType": "SPOT",
        "canTrade": True,
        "balances": [
            {"asset": a, "free": q, "locked": "0"}
            for a, q in (("USDT", "100"), ("BTC", "1"), ("UNPRICED", "1000"))
        ],
    }
    symbol = {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "isSpotTradingAllowed": True,
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "baseCommissionPrecision": 8,
        "orderTypes": ["LIMIT"],
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "1000000",
                "tickSize": "0.01",
            },
            {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"},
            {"filterType": "NOTIONAL", "minNotional": "5", "maxNotional": "10000000"},
            {
                "filterType": "PERCENT_PRICE",
                "avgPriceMins": 5,
                "multiplierUp": "5",
                "multiplierDown": "0.2",
            },
        ],
    }
    fees = {
        "symbol": "BTCUSDT",
        "discount": {"enabledForAccount": False, "enabledForSymbol": False, "discountAsset": "BNB"},
        **{
            group: dict.fromkeys(("maker", "taker", "buyer", "seller"), "0")
            for group in ("standardCommission", "specialCommission", "taxCommission")
        },
    }
    fees["standardCommission"].update(maker="0.001", taker="0.001")
    bodies = {
        "/api/v3/account": account,
        "/api/v3/openOrders": [],
        "/api/v3/account/commission": fees,
        "/api/v3/myFilters": {"symbolFilters": [], "exchangeFilters": [], "assetFilters": []},
        "/api/v3/exchangeInfo": {"symbols": [symbol], "exchangeFilters": []},
        "/api/v3/referencePrice": {"code": -2043},
        "/api/v3/avgPrice": {"mins": 5, "price": "70000", "closeTime": NOW // 1_000_000},
        "/api/v3/ticker/bookTicker": {"symbol": "BTCUSDT", "bidPrice": "70000", "bidQty": "1"},
    }
    rows = []
    for i, path in enumerate(PATHS):
        raw = json.dumps(bodies[path])
        rows.append(
            {
                "path": path,
                "params": (PRIVATE | PUBLIC)[path],
                "body": raw,
                "body_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "started_ns": NOW + i * 1_000_000,
                "received_ns": NOW + (i + 1) * 1_000_000,
                "status": 400 if path == "/api/v3/referencePrice" else 200,
            }
        )
    return {"source": {"endpoint": TESTNET_REST, "account_uid": "123"}, "captures": rows}


def change_body(capture, index, change):
    row = capture["captures"][index]
    body = json.loads(row["body"])
    change(body)
    row["body"] = json.dumps(body)
    row["body_sha256"] = hashlib.sha256(row["body"].encode()).hexdigest()


def test_real_shapes_parse_without_manufacturing_permissions_or_full_equity():
    capture = fixture_capture()
    before = copy.deepcopy(capture)
    result = review_capabilities(capture)
    assert capture == before
    assert result["native_rules_parsed"]
    assert result["account_reports_can_trade"]
    assert result["asset_count"] == 3
    assert result["buy_fee_currency"] == "BTC"
    assert result["fee_rate_bound"] == "0.001"
    assert not result["key_trade_permission_verified"]
    assert not result["full_account_baseline_qualified"]
    assert not result["runtime_ready"]


def test_bnb_discount_remains_a_third_asset_fee():
    capture = fixture_capture()
    change_body(
        capture, 2, lambda x: x["discount"].update(enabledForAccount=True, enabledForSymbol=True)
    )
    result = review_capabilities(capture)
    assert result["buy_fee_currency"] == "BNB_OR_BTC"
    assert result["sell_fee_currency"] == "BNB_OR_USDT"
    assert not result["testnet_order_ready"]


@pytest.mark.parametrize(
    "nonzero_group,discount_rate",
    [
        (None, "0"),
        ("standardCommission", "0"),
        ("specialCommission", "0"),
        ("taxCommission", "0"),
        (None, "0.1"),
    ],
)
def test_null_discount_profile_is_limited_to_exact_zero_fees(nonzero_group, discount_rate):
    capture = fixture_capture()

    def update(fees):
        for group in ("standardCommission", "specialCommission", "taxCommission"):
            fees[group] = dict.fromkeys(("maker", "taker", "buyer", "seller"), "0")
        if nonzero_group:
            fees[nonzero_group]["seller"] = "0.001"
        fees["discount"].update(
            enabledForAccount=True,
            enabledForSymbol=True,
            discountAsset=None,
            discount=discount_rate,
        )

    change_body(capture, 2, update)
    result = review_capabilities(capture)
    assert result["native_rules_parsed"] == (nonzero_group is None and discount_rate == "0")

    # The default portfolio parser continues rejecting this testnet-only shape.
    by_path = {r["path"]: r for r in capture["captures"]}
    info = json.loads(by_path["/api/v3/exchangeInfo"]["body"])
    info["symbols"][0]["filters"] = info["symbols"][0]["filters"][:-1]
    with pytest.raises(VenueInputError, match="unsupported commission discount asset"):
        parse_binance_rules(
            CapturedResponse(json.dumps(info), NOW),
            CapturedResponse(by_path["/api/v3/account/commission"]["body"], NOW, "123", "BTCUSDT"),
            CapturedResponse(by_path["/api/v3/myFilters"]["body"], NOW, "123", "BTCUSDT"),
            account_id="123",
            now_ns=NOW,
            max_age_ns=60_000_000_000,
        )


@pytest.mark.parametrize(
    "index,change",
    [
        (6, lambda x: x.update(mins=1)),
        (6, lambda x: x.update(closeTime=1)),
        (5, lambda x: x.update(code=-1002)),
        (4, lambda x: x["symbols"][0]["filters"].append({"filterType": "NEW_UNKNOWN_FILTER"})),
        (3, lambda x: x.pop("assetFilters")),
    ],
)
def test_unqualified_filters_and_price_precedence_fail_closed(index, change):
    capture = fixture_capture()
    change_body(capture, index, change)
    result = review_capabilities(capture)
    assert not result["native_rules_parsed"]
    assert result["native_rules_error"]
    assert not result["testnet_order_ready"]


def test_account_drift_and_unrelated_orders_are_visible():
    capture = fixture_capture()
    change_body(capture, -1, lambda x: x["balances"][-1].update(free="1001"))
    change_body(capture, -2, lambda x: x.append({"symbol": "ETHUSDT", "orderId": 1}))
    result = review_capabilities(capture)
    assert not result["full_balances_unchanged"]
    assert not result["account_wide_open_orders_empty"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["captures"][0].update(body="{}"),
        lambda c: c["captures"][1].update(started_ns=0),
        lambda c: c["captures"][-1].update(received_ns=NOW + 61_000_000_000),
        lambda c: c["source"].update(endpoint="https://api.binance.com"),
        lambda c: c["captures"][2].update(params={"symbol": "ETHUSDT"}),
    ],
)
def test_capture_corruption_rejected(mutate):
    capture = fixture_capture()
    mutate(capture)
    with pytest.raises(VenueInputError):
        review_capabilities(capture)


@pytest.mark.parametrize(
    "method,path,params,host",
    [
        (HttpMethod.POST, "/api/v3/order", {}, TESTNET_REST),
        (HttpMethod.POST, "/api/v3/order/test", {}, TESTNET_REST),
        (HttpMethod.DELETE, "/api/v3/order", {}, TESTNET_REST),
        (HttpMethod.GET, "/sapi/v1/account/apiRestrictions", {}, TESTNET_REST),
        (HttpMethod.GET, "/api/v3/account/commission", {"symbol": "ETHUSDT"}, TESTNET_REST),
        (HttpMethod.GET, "/api/v3/exchangeInfo", {"symbol": "BTCUSDT"}, "https://api.binance.com"),
    ],
)
def test_transport_refuses_mutations_wrong_hosts_and_parameters(method, path, params, host):
    wire = AsyncMock()
    client = SimpleNamespace(base_url=host, _client=SimpleNamespace(request=wire), headers={})
    with pytest.raises(VenueInputError):
        asyncio.run(TestnetCapabilityHttpClient.send_request(client, method, path, params))
    wire.assert_not_awaited()


def test_private_rejections_retained_and_public_reads_do_not_send_key():
    wire = AsyncMock(return_value=SimpleNamespace(status=400, body=b'{"code":-2043}'))
    client = SimpleNamespace(
        base_url=TESTNET_REST,
        _client=SimpleNamespace(request=wire),
        headers={"X-MBX-APIKEY": "synthetic-private-key"},
    )
    status, raw = asyncio.run(
        TestnetCapabilityHttpClient.send_request(
            client, HttpMethod.GET, "/api/v3/referencePrice", {"symbol": "BTCUSDT"}
        )
    )
    assert status == 400 and json.loads(raw)["code"] == -2043
    assert wire.call_args.kwargs["headers"] == {}
    wire.side_effect = RuntimeError("secret-url-with-signature")
    with pytest.raises(VenueInputError, match="^testnet capability GET failed$"):
        asyncio.run(
            TestnetCapabilityHttpClient.send_request(
                client,
                HttpMethod.GET,
                "/api/v3/account/commission",
                {"symbol": "BTCUSDT", "timestamp": "1", "signature": "synthetic"},
            )
        )


def zero_fee_capture():
    capture = fixture_capture()
    change_body(capture, 2, lambda x: x["standardCommission"].update(maker="0", taker="0"))
    capture["source"]["key_sha256"] = hashlib.sha256(b"synthetic-key").hexdigest()
    return capture


@pytest.mark.parametrize(
    "change,index",
    [
        (lambda x: x.update(canTrade=False), -1),
        (lambda x: x["balances"][0].update(free="9"), -1),
        (lambda x: x["standardCommission"].update(taker="0.001"), 2),
        (lambda x: x.append({"symbol": "ETHUSDT", "orderId": 1}), -2),
        (lambda x: x.update(bidPrice="110000"), 7),
        (lambda x: x.update(price="100"), 6),
    ],
)
def test_nonmatching_probe_requires_budget_fees_and_stable_account(change, index):
    capture = zero_fee_capture()
    change_body(capture, index, change)
    with pytest.raises(VenueInputError):
        validation_price(capture, NOW + 20_000_000)


def test_old_capture_cannot_be_used_for_a_later_probe():
    with pytest.raises(VenueInputError, match="fresh capability capture"):
        validation_price(zero_fee_capture(), NOW + 6_000_000_000)


def test_private_asset_limit_is_enforced_before_validation():
    capture = zero_fee_capture()
    change_body(
        capture,
        3,
        lambda x: x["assetFilters"].append(
            {"filterType": "MAX_ASSET", "asset": "USDT", "limit": "6"}
        ),
    )
    review = review_capabilities(capture)
    assert review["native_rules_parsed"]
    assert review["lifecycle_proposal"]["captured_basic_filter_checks_passed"]
    assert not review["buy_within_effective_order_filters"]
    with pytest.raises(VenueInputError, match="prerequisites incomplete"):
        validation_price(capture, NOW + 20_000_000)


@pytest.mark.parametrize(
    "path,method,changes,host",
    [
        ("/api/v3/order", HttpMethod.POST, {}, TESTNET_REST),
        ("/api/v3/order", HttpMethod.DELETE, {}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {"side": "SELL"}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {"quantity": "0.001"}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {"price": "100000.01"}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {"type": "MARKET"}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {"extra": "unknown"}, TESTNET_REST),
        (VALIDATE_PATH, HttpMethod.POST, {}, "https://api.binance.com"),
    ],
)
def test_validation_transport_can_never_submit_matching_orders(path, method, changes, host):
    wire = AsyncMock()
    client = SimpleNamespace(base_url=host, _client=SimpleNamespace(request=wire), headers={})
    params = FIXED | {"price": "70000", "timestamp": "1", "signature": "synthetic"} | changes
    with pytest.raises(VenueInputError):
        asyncio.run(TestnetOrderValidationHttpClient.send_request(client, method, path, params))
    wire.assert_not_awaited()


@pytest.mark.parametrize("status,fee", [(200, "0"), (200, "0.001"), (403, "0")])
def test_probe_acceptance_is_scoped_to_nonmatching_endpoint(status, fee):
    capture = zero_fee_capture()
    body = {
        group: {"maker": fee, "taker": fee}
        for group in (
            "standardCommissionForOrder",
            "taxCommissionForOrder",
            "specialCommissionForOrder",
        )
    }
    body["discount"] = {"enabledForAccount": True, "enabledForSymbol": True}
    sign = AsyncMock(return_value=(status, json.dumps(body).encode()))
    client = SimpleNamespace(base_url=TESTNET_REST, api_key="synthetic-key", sign_request=sign)
    result = asyncio.run(validate_order(client, capture, lambda: NOW + 20_000_000))
    assert result["trade_validation_request_accepted"] == (status == 200)
    assert result["zero_fee_validation_passed"] == (status == 200 and fee == "0")
    assert sign.call_args.args[:2] == (HttpMethod.POST, VALIDATE_PATH)
    assert not result["matching_engine_order_submitted"]
    assert not result["matching_order_permission_proven"]
    assert not result["runtime_ready"]


def test_foreign_key_cannot_consume_a_valid_capture():
    sign = AsyncMock()
    client = SimpleNamespace(base_url=TESTNET_REST, api_key="foreign-key", sign_request=sign)
    with pytest.raises(VenueInputError, match="source mismatch"):
        asyncio.run(validate_order(client, zero_fee_capture(), lambda: NOW + 20_000_000))
    sign.assert_not_awaited()

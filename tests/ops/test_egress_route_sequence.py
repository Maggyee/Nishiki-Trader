"""Same-run account, metadata and book originals select bounded fixture routes."""

import copy
import json
import os
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_order_sequence import payload
from tests.ops.test_egress_read_sequence import capture_sequence, review
from tests.ops.test_egress_signed_account import selection


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    yield from capture_sequence(tmp_path_factory, routes=True)


def inputs(captured):
    report = review(captured)
    code = load("gateway_book_routes")
    _, metadata = code.body(captured.payloads[0])
    return (
        code,
        metadata,
        copy.deepcopy(report["steps"][4]["native_result"]),
        copy.deepcopy(report["steps"][5]["native_result"]),
    )


def test_native_six_reads_select_only_nonzero_market_assets(captured):
    report = review(captured)
    assert report["status"] == "complete" and report["accepted_steps"] == 6
    assert report["repeated_balances_equal"] and report["repeated_open_orders_equal"]
    assert report["routes_derived_from_same_run"]
    routes = report["route_selection"]
    assert routes["symbols"] == ["BNBUSDT", "BTCUSDT"]
    assert [r["status"] for r in routes["assets"]] == [
        "selected",
        "selected",
        "zero_balance",
        "quote_asset",
    ]
    assert not routes["individual_quote_age_verified"] and not routes["dispatch_authorized"]
    step = report["steps"][5]
    assert step["receipt"]["native_books_acknowledged"]
    assert step["attempts"]["counts"][0]["documented_weight"] == 4
    assert (
        captured.modules["books"]["validate_native"](captured.payloads[5]) == step["native_result"]
    )


@pytest.mark.parametrize("end", range(1, 14))
def test_every_route_prefix_preserves_incomplete_no_resume(captured, end):
    lines = captured.raw.splitlines(keepends=True)[:end]
    count = sum(json.loads(line)["kind"] == "prepared" for line in lines)
    report = review(captured, b"".join(lines), captured.bundles[:count])
    assert report["status"] == "incomplete_no_resume" and not report["restart_allowed"]
    assert report["routes_derived_from_same_run"] == (end == 13)


@pytest.mark.parametrize("key", ["bidPrice", "askPrice", "bidQty", "askQty"])
def test_book_native_precision_never_rounds(key):
    rows = copy.deepcopy(load("installed_gateway_selftest").FIXTURE_BOOKS)
    rows[0][key] = "0.000000001"
    with pytest.raises(ValueError, match="rounding_refused"):
        load("gateway_book_routes").validate_native(payload(rows))


@pytest.mark.parametrize("damage", ["duplicate", "unknown", "negative", "nan", "extra", "empty"])
def test_invalid_book_response(damage):
    rows = copy.deepcopy(load("installed_gateway_selftest").FIXTURE_BOOKS)
    if damage == "duplicate":
        rows.append(rows[0])
    elif damage == "unknown":
        rows[0]["symbol"] = "bad/name"
    elif damage in {"negative", "nan"}:
        rows[0]["bidPrice"] = "-1" if damage == "negative" else "NaN"
    elif damage == "extra":
        rows[0]["E"] = 123
    else:
        rows = []
    with pytest.raises(ValueError):
        load("gateway_book_routes").expected_result(payload(rows))


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "crossed",
        "disabled",
        "no_spot",
        "depth",
        "unbound",
        "precision",
        "duplicate_metadata",
    ],
)
def test_route_refusals_preserve_nonzero_assets(captured, damage):
    code, info, account, books = inputs(captured)
    btc = next(r for r in books["books"] if r["symbol"] == "BTCUSDT")
    definition = next(r for r in info["symbols"] if r["symbol"] == "BTCUSDT")
    if damage == "missing":
        books["books"].remove(btc)
    elif damage == "crossed":
        btc["bidPrice"] = "70000"
    elif damage == "disabled":
        definition["status"] = "BREAK"
    elif damage == "no_spot":
        definition["isSpotTradingAllowed"] = False
    elif damage == "depth":
        btc["bidQty"] = "0.01099999"
    elif damage == "unbound":
        btc["symbol"] = "USDCUSDT"
    elif damage == "precision":
        definition["baseAssetPrecision"] = 7
    else:
        info["symbols"].append(definition)
    with pytest.raises(ValueError):
        code.derive(payload(info), account, books)


def test_two_hops_and_inverse_capacity_are_exact(captured):
    code, info, account, books = inputs(captured)
    definition = next(r for r in info["symbols"] if r["symbol"] == "BNBUSDT")
    definition.update(symbol="BTCBNB", baseAsset="BTC", quoteAsset="BNB")
    book = next(r for r in books["books"] if r["symbol"] == "BNBUSDT")
    book.update(symbol="BTCBNB", bidPrice="199", askPrice="200", bidQty="1", askQty="0.0055")
    selected = code.derive(payload(info), account, books)
    assert selected["symbols"] == ["BTCBNB", "BTCUSDT"]
    bnb = selected["assets"][0]
    assert [leg["side"] for leg in bnb["path"]] == ["inverse_ask", "bid"]
    book["askQty"] = "0.00549999"
    with pytest.raises(ValueError, match="top_book_insufficient"):
        code.derive(payload(info), account, books)


def test_permutations_and_decimal_spellings_preserve_route_identity(captured):
    code, info, account, books = inputs(captured)
    original = code.derive(payload(info), account, books)
    info["symbols"].reverse()
    books["books"].reverse()
    for row in books["books"]:
        row["bidQty"] = "10.00000000"
    changed = code.derive(payload(info), account, books)
    assert changed["symbols"] == original["symbols"] and changed["assets"] == original["assets"]


def test_zero_inventory_needs_no_market_route(captured):
    code, info, account, books = inputs(captured)
    for row in account["balances"]:
        row.update(free="0", locked="0")
    books["books"] = []
    assert code.derive(payload(info), account, books)["symbols"] == []


@pytest.mark.parametrize("damage", ["swap", "account", "missing_receipt", "request"])
def test_books_originals_cannot_be_spliced(captured, damage):
    bundles = copy.deepcopy(captured.bundles)
    if damage == "swap":
        bundles[0], bundles[5] = bundles[5], bundles[0]
    elif damage == "account":
        bundles[5] = bundles[4]
    elif damage == "missing_receipt":
        del bundles[5]["receipt"]
    else:
        value = json.loads(bundles[5]["selection"])
        value["request"]["request"]["path"] = "/api/v3/account"
        bundles[5]["selection"] = captured.code.canonical(value).decode()
    with pytest.raises(ValueError):
        review(captured, bundles=bundles)


@pytest.mark.parametrize("damage", ["old", "clock_jump", "midnight"])
def test_route_input_interval_stays_bounded(captured, damage):
    results = copy.deepcopy(review(captured)["steps"])
    first = results[0]["native_result"]["header_receipt"]
    last = results[5]["native_result"]["body_receipt"]
    if damage == "old":
        for key in ("utc_ns", "monotonic_ns"):
            last[key] = first[key] + 60_000_000_001
    elif damage == "clock_jump":
        last["utc_ns"] += 100_000_000
    else:
        first["utc_ns"] = 86_400_000_000_000 - 1
        last["utc_ns"] = 86_400_000_000_000 + 1
        last["monotonic_ns"] = first["monotonic_ns"] + 2
    with pytest.raises(ValueError, match="route_input_interval"):
        captured.code.route_result(results, captured.bundles, captured.modules)


def test_legacy_profiles_cannot_claim_routes(captured):
    for orders in (False, True):
        with pytest.raises(ValueError):
            captured.code.replay(
                captured.raw,
                expected_sha256=captured.code.digest(captured.raw),
                bundles=captured.bundles,
                modules=captured.modules,
                orders=orders,
            )


def test_unsigned_books_contract_is_fixed_and_carries_no_api_key():
    module = load("gateway_book_routes").view(vars(load("gateway_native_account")))
    requests, value = selection(SimpleNamespace(**module), index=8)
    contract = module["AccountContract"](requests, value)
    assert (
        contract.request
        == b"GET /api/v3/ticker/bookTicker HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
    )
    assert contract.SELECTION_FILE == "books-request.json"
    requests, value = selection(SimpleNamespace(**module), index=3)
    with pytest.raises(ValueError):
        module["AccountContract"](requests, value)


def test_native_books_import_refuses_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root_refused"):
        load("gateway_book_routes").validate_native(b"not parsed")


def test_direct_priority_does_not_switch_to_a_better_or_deeper_two_hop(captured):
    code, info, account, books = inputs(captured)
    info["symbols"].append(
        {
            "symbol": "BNBBTC",
            "baseAsset": "BNB",
            "quoteAsset": "BTC",
            "baseAssetPrecision": 8,
            "quoteAssetPrecision": 8,
            "status": "TRADING",
            "isSpotTradingAllowed": True,
        }
    )
    books["books"].append(
        {
            "symbol": "BNBBTC",
            "bidPrice": "0.01",
            "askPrice": "0.011",
            "bidQty": "10",
            "askQty": "10",
        }
    )
    routes = code.derive(payload(info), account, books)
    assert routes["assets"][0]["path"] == [{"symbol": "BNBUSDT", "to_asset": "USDT", "side": "bid"}]
    next(r for r in books["books"] if r["symbol"] == "BNBUSDT")["bidQty"] = "1"
    with pytest.raises(ValueError, match="top_book_insufficient"):
        code.derive(payload(info), account, books)


def test_two_hop_priority_is_lexical_not_price_or_input_order(captured):
    code, info, account, books = inputs(captured)
    next(r for r in info["symbols"] if r["symbol"] == "BNBUSDT")["status"] = "BREAK"
    for quote, price in [("ETH", "1"), ("BTC", "0.004")]:
        info["symbols"].append(
            {
                "symbol": "BNB" + quote,
                "baseAsset": "BNB",
                "quoteAsset": quote,
                "baseAssetPrecision": 8,
                "quoteAssetPrecision": 8,
                "status": "TRADING",
                "isSpotTradingAllowed": True,
            }
        )
        books["books"].append(
            {
                "symbol": "BNB" + quote,
                "bidPrice": price,
                "askPrice": price,
                "bidQty": "10",
                "askQty": "10",
            }
        )
    routes = code.derive(payload(info), account, books)
    assert [leg["symbol"] for leg in routes["assets"][0]["path"]] == ["BNBBTC", "BTCUSDT"]

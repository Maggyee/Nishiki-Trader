from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal as D

import pytest

from apps.ops.portfolio_testnet_admission import DAY_NS, main, review_admission
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_order_plan import lifecycle_test_plan
from apps.strategies_nautilus.portfolio_testnet_valuation import indicative_valuation
from tests.ops.test_portfolio_testnet_account_review import BASE_NS, UNKNOWN, body, capture


def symbol(base, quote="USDT"):
    return {
        "symbol": base + quote,
        "baseAsset": base,
        "quoteAsset": quote,
        "baseAssetPrecision": 8,
        "quoteAssetPrecision": 8,
        "status": "TRADING",
        "isSpotTradingAllowed": True,
        "orderTypes": ["LIMIT"],
        "filters": [
            {
                "filterType": "PRICE_FILTER",
                "minPrice": "0.01",
                "maxPrice": "1000000",
                "tickSize": "0.01",
            },
            {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "10", "stepSize": "0.00001"},
            {"filterType": "NOTIONAL", "minNotional": "5", "maxNotional": "100000"},
        ],
    }


def book(name, bid="10", ask="11", bid_qty="1000000", ask_qty="1000000"):
    return {"symbol": name, "bidPrice": bid, "bidQty": bid_qty, "askPrice": ask, "askQty": ask_qty}


def value(balances, symbols, books):
    return indicative_valuation(
        {asset: (D(free), D(locked)) for asset, (free, locked) in balances.items()},
        {"symbols": symbols},
        books,
    )


def test_bid_marks_include_locked_assets_and_never_assume_stablecoin_pegs():
    r = value(
        {"USDT": ("100", "2"), "BTC": ("1", "1"), "USDC": ("1", "0")},
        [symbol("BTC")],
        [book("BTCUSDT")],
    )
    assert D(r["priced_subtotal_usdt"]) == 122
    assert r["full_indicative_mark_usdt"] is None
    assert r["unpriced_assets"] == ["USDC"]


def test_inverse_path_uses_ask_not_inverse_bid():
    r = value({"X": ("8", "0")}, [symbol("USDT", "X")], [book("USDTX", bid="2", ask="4")])
    assert D(r["full_indicative_mark_usdt"]) == 2
    assert r["assets"][0]["path"][0]["side"] == "inverse_ask"


def test_two_hop_mark_and_fixed_direct_priority_are_not_best_price_search():
    symbols = [symbol("X", "BTC"), symbol("BTC")]
    books = [book("XBTC", bid="2", ask="3"), book("BTCUSDT", bid="10", ask="11")]
    r = value({"X": ("3", "0")}, symbols, books)
    assert D(r["full_indicative_mark_usdt"]) == 60
    symbols.append(symbol("X"))
    books.append(book("XUSDT", bid="5", ask="6"))
    r = value({"X": ("3", "0")}, symbols[::-1], books[::-1])
    assert D(r["full_indicative_mark_usdt"]) == 15
    assert len(r["assets"][0]["path"]) == 1


def test_independent_book_sides_and_depth_limits():
    r = value(
        {"BTC": ("2", "0")}, [symbol("BTC")], [book("BTCUSDT", ask="0", ask_qty="0", bid_qty="1")]
    )
    assert D(r["full_indicative_mark_usdt"]) == 20
    assert r["depth_exceeded_assets"] == ["BTC"]
    assert not r["liquidation_value_verified"] and not r["valuation_qualified"]
    r = value(
        {"X": ("2", "0")}, [symbol("USDT", "X")], [book("USDTX", bid="0", bid_qty="0", ask="4")]
    )
    assert D(r["full_indicative_mark_usdt"]) == D("0.5")


@pytest.mark.parametrize("fault", ["empty", "crossed", "not_trading", "not_spot"])
def test_unusable_quotes_never_become_zero_asset_values(fault):
    s, b = symbol("X"), book("XUSDT")
    if fault == "empty":
        b.update(bidPrice="0", bidQty="0", askPrice="0", askQty="0")
    elif fault == "crossed":
        b["bidPrice"] = "12"
    elif fault == "not_trading":
        s["status"] = "BREAK"
    else:
        s["isSpotTradingAllowed"] = False
    r = value({"X": ("1", "0")}, [s], [b])
    assert r["assets"][0]["mark_usdt"] is None
    assert r["full_indicative_mark_usdt"] is None


def test_unquoted_zero_balance_is_preserved_without_fabricated_price():
    r = value({"X": ("0", "0")}, [symbol("BTC")], [book("BTCUSDT")])
    assert r["assets"][0]["path"] == []
    assert D(r["full_indicative_mark_usdt"]) == 0


@pytest.mark.parametrize(
    "fault", ["duplicate_book", "unknown_book", "duplicate_symbol", "negative", "nan"]
)
def test_bad_market_data_is_rejected(fault):
    s, b = [symbol("BTC")], [book("BTCUSDT")]
    if fault == "duplicate_book":
        b.append(b[0])
    elif fault == "unknown_book":
        b[0]["symbol"] = "FOREIGN"
    elif fault == "duplicate_symbol":
        s.append(s[0])
    else:
        b[0]["bidPrice"] = "-1" if fault == "negative" else "NaN"
    with pytest.raises(ValueError):
        value({"BTC": ("1", "0")}, s, b)


def test_fixed_order_proposal_is_bounded_but_never_authorized():
    r = lifecycle_test_plan(
        {"symbols": [symbol("BTC")]}, [book("BTCUSDT", bid="77166", ask="77166.01")]
    )
    assert r["captured_basic_filter_checks_passed"]
    assert D(r["illustrative_buy_notional_usdt"]) == D("7.716599")
    assert r["fixed_buy_quantity_btc"] == "0.0001"
    assert not r["fee_budget_verified"] and not r["effective_filters_verified"]
    assert not r["runner_wired"] and not r["execution_authorized"] and not r["testnet_order_ready"]
    too_large = lifecycle_test_plan(
        {"symbols": [symbol("BTC")]}, [book("BTCUSDT", bid="110000", ask="110001")]
    )
    assert not too_large["captured_basic_filter_checks_passed"]
    assert too_large["fixed_buy_quantity_btc"] == "0.0001"  # no auto-resizing


@pytest.fixture
def case(tmp_path):
    response = canonical(body()).decode()
    initial = canonical(
        {
            "schema_version": "portfolio.testnet_initial_account_observation.v1",
            "endpoint": "https://testnet.binance.vision",
            "path": "/api/v3/account",
            "key_sha256": hashlib.sha256(b"synthetic-key").hexdigest(),
            "response_body": response,
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        }
    )
    selected = hashlib.sha256(initial).hexdigest()
    raw, digest, collection = capture(tmp_path / "account.jsonl", selection=selected)
    captures = []
    for i, (path, payload) in enumerate(
        [
            ("/api/v3/exchangeInfo", {"symbols": [symbol("BTC"), symbol(UNKNOWN)]}),
            ("/api/v3/ticker/bookTicker", [book("BTCUSDT"), book(UNKNOWN + "USDT")]),
        ]
    ):
        body_raw = canonical(payload).decode()
        captures.append(
            {
                "endpoint": "https://testnet.binance.vision" + path,
                "started_ns": BASE_NS + (i + 1) * 10**9,
                "received_ns": BASE_NS + (i + 1) * 10**9 + 1,
                "response_body": body_raw,
                "response_sha256": hashlib.sha256(body_raw.encode()).hexdigest(),
            }
        )
    market = {
        "schema_version": "portfolio.testnet_market_capture.v1",
        "account_archive_sha256": digest,
        "account_collection_id": collection,
        "captures": captures,
    }
    return (
        raw,
        initial,
        market,
        dict(archive_sha256=digest, collection_id=collection, selection_sha256=selected),
    )


def review(case, **overrides):
    raw, initial, market, params = case
    market_raw = canonical(market)
    return review_admission(
        raw,
        market_raw,
        initial,
        **(params | {"market_sha256": hashlib.sha256(market_raw).hexdigest()} | overrides),
    )


def test_prospective_anchor_never_substitutes_for_utc_risk_baseline(case):
    result = review(case)
    assert result["checks"]["full_native_amount_mapping"]
    assert result["checks"]["all_assets_have_indicative_marks"]
    assert result["checks"]["account_reports_can_trade"]
    assert result["api_trading_enabled"] is None
    assert not result["api_key_restrictions_verified"]
    anchor = result["observation_anchor"]
    assert len(anchor["balances"]) == 3 and D(anchor["initial_indicative_mark_usdt"]) == 540
    assert anchor["day_open_equity_usdt"] is None and anchor["effective_daily_limit_usdt"] is None
    assert not anchor["baseline_qualified"]
    assert not result["testnet_order_ready"] and not result["runtime_ready"]


@pytest.mark.parametrize(
    "fault", ["source", "order", "hash", "binding", "old", "future_span", "rollover"]
)
def test_market_capture_binding_and_time_cannot_be_relabelled(case, fault):
    market = case[2]
    if fault == "source":
        market["captures"][0]["endpoint"] = "https://api.binance.com/api/v3/exchangeInfo"
    elif fault == "order":
        market["captures"].reverse()
    elif fault == "hash":
        market["captures"][0]["response_sha256"] = "0" * 64
    elif fault == "binding":
        market["account_collection_id"] = "wrong"
    elif fault == "old":
        market["captures"][0]["started_ns"] = BASE_NS
    elif fault == "future_span":
        market["captures"][-1]["received_ns"] += 61 * 10**9
    else:
        market["captures"][-1]["received_ns"] += DAY_NS
    with pytest.raises(StreamError):
        review(case)


@pytest.mark.parametrize("field", ["archive_sha256", "market_sha256", "selection_sha256"])
def test_selected_hashes_are_required(case, field):
    with pytest.raises(StreamError):
        review(case, **{field: "0" * 64})


def test_initial_uid_and_key_are_bound_not_inferred_from_new_archive(case, tmp_path):
    raw, digest, collection = capture(
        tmp_path / "other.jsonl", key="other-key", selection=case[3]["selection_sha256"]
    )
    market = copy.deepcopy(case[2])
    market.update(account_archive_sha256=digest, account_collection_id=collection)
    changed = (
        raw,
        case[1],
        market,
        case[3] | {"archive_sha256": digest, "collection_id": collection},
    )
    with pytest.raises(StreamError):
        review(changed)


def test_cli_retains_private_report_and_cannot_overwrite(case, tmp_path, capsys):
    raw, initial, market, params = case
    (tmp_path / "initial.json").write_bytes(initial)
    market_raw = canonical(market)
    (tmp_path / "market.json").write_bytes(market_raw)
    output = tmp_path / "review.json"
    args = [
        "--archive",
        str(tmp_path / "account.jsonl"),
        "--archive-sha256",
        params["archive_sha256"],
        "--collection",
        params["collection_id"],
        "--initial",
        str(tmp_path / "initial.json"),
        "--selection-sha256",
        params["selection_sha256"],
        "--market",
        str(tmp_path / "market.json"),
        "--market-sha256",
        hashlib.sha256(market_raw).hexdigest(),
        "--output",
        str(output),
    ]
    assert main(args) == 0
    stdout = capsys.readouterr().out
    assert UNKNOWN not in stdout and '"balances"' not in stdout
    assert not json.loads(stdout)["testnet_order_ready"]
    saved = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    assert main(args) == 2 and output.read_bytes() == saved
    assert (tmp_path / "account.jsonl").read_bytes() == raw

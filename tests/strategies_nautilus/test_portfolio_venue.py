from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal as D
from itertools import permutations

import pytest

from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_preflight import (
    AccountSnapshot,
    AdmissionCandidate,
    PendingOrder,
    ProposedOrder,
    check_batch,
    select_funded_batch,
)
from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    PriceReference,
    VenueInputError,
    parse_binance_rules,
)

NOW = 1_767_225_600_000_000_000
AGE = 60_000_000_000
ACCOUNT = "synthetic-account"


def bodies():
    # Invented test values in official response shape, not current exchange data.
    symbol = {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "isSpotTradingAllowed": True,
        "orderTypes": ["LIMIT", "MARKET"],
        "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "0", "maxPrice": "0", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "10", "stepSize": "0.00001"},
            {
                "filterType": "MIN_NOTIONAL",
                "minNotional": "5",
                "applyToMarket": True,
                "avgPriceMins": 5,
            },
            {"filterType": "MAX_NUM_ORDERS", "maxNumOrders": 10},
        ],
    }
    info = {
        "symbols": [symbol],
        "exchangeFilters": [{"filterType": "EXCHANGE_MAX_NUM_ORDERS", "maxNumOrders": 100}],
    }
    fees = {
        "symbol": "BTCUSDT",
        "discount": {"enabledForAccount": False, "enabledForSymbol": False, "discountAsset": "BNB"},
    }
    for group in ("standardCommission", "taxCommission", "specialCommission"):
        fees[group] = dict.fromkeys(("maker", "taker", "buyer", "seller"), "0")
    fees["standardCommission"].update(maker="0.001", taker="0.0015")
    private = {"exchangeFilters": [], "symbolFilters": [], "assetFilters": []}
    return info, fees, private


def parse(info=None, fees=None, private=None, references=(), **kwargs):
    originals = bodies()
    responses = [
        CapturedResponse(
            json.dumps(body if body is not None else originals[i]),
            NOW,
            None if i == 0 else ACCOUNT,
            None if i == 0 else "BTCUSDT",
        )
        for i, body in enumerate((info, fees, private))
    ]
    return parse_binance_rules(
        *responses, account_id=ACCOUNT, now_ns=NOW, max_age_ns=AGE, references=references, **kwargs
    )


def zero_fees():
    fees = bodies()[1]
    fees["standardCommission"].update(maker="0", taker="0")
    return fees


def snapshot(**kwargs):
    return replace(
        AccountSnapshot(
            "BTCUSDT.BINANCE",
            NOW,
            NOW,
            True,
            D("500"),
            D("500"),
            D("0"),
            D("0"),
            tuple((s, D("0")) for s in SLEEVES),
            (),
            frozenset(),
            D("100000"),
            D("500"),
            D("500"),
        ),
        **kwargs,
    )


def candidates():
    return tuple(
        AdmissionCandidate(
            ProposedOrder(f"order-{s}", s, "BUY", D("0.001"), D("100000")),
            f"signal-{s}",
            NOW,
            NOW + AGE,
        )
        for s in SLEEVES
    )


def test_received_asset_commission_blocks_buys_without_mislabeling_as_quote_fee():
    evidence = parse()
    assert evidence.rules.fee_rate == D("0.0015")
    assert evidence.rules.buy_fee_currency == "BTC"
    assert evidence.rules.sell_fee_currency == "USDT"
    result = select_funded_batch(
        snapshot(), evidence.rules, preflight_limits(), candidates(), now_ns=NOW
    )
    assert not result.selected
    assert all("unsupported_order_fee_currency" in skipped.reasons for skipped in result.skipped)
    assert len(evidence.response_sha256) == 3
    assert evidence.rules.price_max == 0
    assert evidence.rules.notional_max is None


def test_received_quote_sell_remains_supported_and_bnb_discount_is_not_assumed():
    qty = D("0.001")
    account = snapshot(
        total_base=qty,
        venue_free_base=qty,
        total_quote=D("400"),
        venue_free_quote=D("400"),
        holdings=tuple((s, qty if s == "v16" else D("0")) for s in SLEEVES),
    )
    sell = replace(candidates()[0].order, side="SELL")
    assert check_batch(
        account, parse().rules, preflight_limits(), (sell,), now_ns=NOW
    ).checks_passed
    fees = bodies()[1]
    fees["discount"].update(enabledForAccount=True, enabledForSymbol=True)
    rules = parse(fees=fees).rules
    assert rules.buy_fee_currency == "BNB_OR_BTC"
    assert (
        "unsupported_order_fee_currency"
        in check_batch(account, rules, preflight_limits(), (sell,), now_ns=NOW).reasons
    )


def test_fee_bound_includes_buyer_seller_tax_special_and_maker_taker():
    fees = bodies()[1]
    fees["taxCommission"].update(taker="0.0002", buyer="0.0003")
    fees["specialCommission"].update(maker="0.005", seller="0.002")
    assert parse(fees=fees).rules.fee_rate == D("0.008")


def test_order_count_gate_applies_during_greedy_selection_and_final_batch():
    info, fees, private = bodies()
    fees = zero_fees()
    info["exchangeFilters"][0]["maxNumOrders"] = 2
    rules = parse(info, fees, private).rules
    for batch in permutations(candidates()):
        result = select_funded_batch(snapshot(), rules, preflight_limits(), batch, now_ns=NOW)
        assert [c.order.sleeve for c in result.selected] == ["v16", "v18"]
        assert all("venue_open_order_limit" in c.reasons for c in result.skipped)
    pending = PendingOrder("old", "v16", "BUY", D("0.0005"), D("100000"), "pending_cancel")
    account = snapshot(pending=(pending,), used_order_ids=frozenset({"old"}))
    result = select_funded_batch(account, rules, preflight_limits(), candidates()[1:], now_ns=NOW)
    assert len(result.selected) == 1
    account = replace(account, pending=(replace(pending, status="canceled", remaining=D("0")),))
    assert (
        len(
            select_funded_batch(
                account, rules, preflight_limits(), candidates()[1:], now_ns=NOW
            ).selected
        )
        == 2
    )


def test_private_asset_limits_and_public_notional_intersect():
    info, _, private = bodies()
    info["symbols"][0]["filters"].append(
        {"filterType": "NOTIONAL", "minNotional": "10", "maxNotional": "500"}
    )
    private["assetFilters"] = [
        {"filterType": "MAX_ASSET", "asset": "BTC", "limit": "0.0008"},
        {"filterType": "MAX_ASSET", "asset": "USDT", "limit": "90"},
    ]
    rules = parse(info=info, fees=zero_fees(), private=private).rules
    assert (rules.quantity_max, rules.notional_min, rules.notional_max) == (
        D("0.0008"),
        D("10"),
        D("90"),
    )
    result = check_batch(
        snapshot(), rules, preflight_limits(), (candidates()[0].order,), now_ns=NOW
    )
    assert "quantity_bounds" in result.reasons and "notional_bounds" in result.reasons


def test_max_position_counts_partial_buy_remainder_without_unfilled_sell_credit():
    info, _, _ = bodies()
    info["symbols"][0]["filters"].append({"filterType": "MAX_POSITION", "maxPosition": "0.0015"})
    rules = parse(info=info, fees=zero_fees()).rules
    pending = PendingOrder("old", "v16", "BUY", D("0.0005"), D("100000"), "partially_filled")
    account = snapshot(
        total_base=D("0.0005"),
        venue_free_base=D("0.0005"),
        holdings=tuple((s, D("0.0005") if s == "v16" else D("0")) for s in SLEEVES),
        total_quote=D("450"),
        venue_free_quote=D("400"),
        pending=(pending,),
        used_order_ids=frozenset({"old"}),
    )
    assert (
        "venue_position_limit"
        in check_batch(
            account, rules, preflight_limits(), (candidates()[1].order,), now_ns=NOW
        ).reasons
    )
    sell = replace(pending, side="SELL", status="pending_cancel")
    account = replace(account, pending=(sell,))
    # Two fresh buys plus a pending sell still exceed the venue base ceiling.
    assert (
        "venue_position_limit"
        in check_batch(
            account,
            rules,
            preflight_limits(),
            tuple(c.order for c in candidates()[1:3]),
            now_ns=NOW,
        ).reasons
    )


def with_percent_filter():
    info, _, _ = bodies()
    info["symbols"][0]["filters"].append(
        {
            "filterType": "PERCENT_PRICE_BY_SIDE",
            "avgPriceMins": 5,
            "bidMultiplierDown": "0.9",
            "bidMultiplierUp": "1.1",
            "askMultiplierDown": "0.95",
            "askMultiplierUp": "1.05",
        }
    )
    ref = PriceReference("PERCENT_PRICE_BY_SIDE", D("100000"), NOW, 5, "weighted_average", True)
    return info, ref


@pytest.mark.parametrize(
    "side,price,passes",
    [
        ("BUY", "90000", True),
        ("BUY", "110000", True),
        ("BUY", "110000.01", False),
        ("SELL", "95000", True),
        ("SELL", "105000", True),
        ("SELL", "94999.99", False),
    ],
)
def test_side_specific_bands_include_boundaries(side, price, passes):
    info, ref = with_percent_filter()
    rules = parse(info=info, fees=zero_fees(), references=(ref,)).rules
    account = snapshot(
        total_quote=D("400"),
        venue_free_quote=D("400"),
        total_base=D("0.001"),
        venue_free_base=D("0.001"),
        holdings=tuple((s, D("0.001") if s == "v16" else D("0")) for s in SLEEVES),
    )
    order = replace(candidates()[1 if side == "BUY" else 0].order, side=side, limit_price=D(price))
    result = check_batch(account, rules, preflight_limits(), (order,), now_ns=NOW)
    assert ("venue_price_band" not in result.reasons) == passes


@pytest.mark.parametrize(
    "changes",
    [
        {"ts_ns": NOW - AGE - 1},
        {"ts_ns": NOW + 1},
        {"average_minutes": 0},
        {"kind": "bid"},
        {"reference_price_known_absent": False},
        {"price": D("NaN")},
    ],
)
def test_invalid_reference_never_substitutes_bid_or_24h_average(changes):
    info, ref = with_percent_filter()
    with pytest.raises(VenueInputError):
        parse(info=info, references=(replace(ref, **changes),))


def test_reference_precedence_and_two_independent_percent_filters():
    info, ref = with_percent_filter()
    info["symbols"][0]["filters"].append(
        {
            "filterType": "PERCENT_PRICE",
            "avgPriceMins": 0,
            "multiplierDown": "0.8",
            "multiplierUp": "1.2",
        }
    )
    last = PriceReference("PERCENT_PRICE", D("100000"), NOW - 100, 0, "last_price", True)
    ref = replace(ref, kind="reference_price", reference_price_known_absent=False)
    rules = parse(info=info, references=(ref, last)).rules
    assert len(rules.price_bands) == 4
    assert rules.ts_ns == NOW - 100  # never re-stamp older inputs with evaluation time
    with pytest.raises(VenueInputError, match="missing effective"):
        parse(info=info, references=(ref,))


@pytest.mark.parametrize("which", range(3))
@pytest.mark.parametrize("time", [NOW - AGE - 1, NOW + 1, True])
def test_every_response_has_independent_freshness(which, time):
    responses = [CapturedResponse(json.dumps(body), NOW, ACCOUNT, "BTCUSDT") for body in bodies()]
    responses[which] = replace(responses[which], received_ns=time)
    with pytest.raises(VenueInputError):
        parse_binance_rules(*responses, account_id=ACCOUNT, now_ns=NOW, max_age_ns=AGE)


def test_account_mismatch_and_conflicting_filters_fail_closed():
    responses = [CapturedResponse(json.dumps(body), NOW, ACCOUNT, "BTCUSDT") for body in bodies()]
    responses[1] = replace(responses[1], account_id="other")
    with pytest.raises(VenueInputError, match="account mismatch"):
        parse_binance_rules(*responses, account_id=ACCOUNT, now_ns=NOW, max_age_ns=AGE)
    private = bodies()[2]
    private["symbolFilters"] = [{"filterType": "MAX_NUM_ORDERS", "maxNumOrders": 5}]
    with pytest.raises(VenueInputError, match="conflicting"):
        parse(private=private)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i, f, p: i["symbols"][0].update(status="HALT"),
        lambda i, f, p: i["symbols"][0].update(isSpotTradingAllowed="true"),
        lambda i, f, p: i["symbols"].append(i["symbols"][0]),
        lambda i, f, p: i["symbols"][0]["filters"].append({"filterType": "FUTURE_FILTER"}),
        lambda i, f, p: i["symbols"][0]["filters"].append(i["symbols"][0]["filters"][0]),
        lambda i, f, p: i["symbols"][0]["filters"][0].update(tickSize="NaN"),
        lambda i, f, p: i["symbols"][0]["filters"][0].update(minPrice=0.1),
        lambda i, f, p: f.pop("taxCommission"),
        lambda i, f, p: f["discount"].update(enabledForAccount="false"),
        lambda i, f, p: f["standardCommission"].update(maker="-0.001"),
        lambda i, f, p: p.pop("assetFilters"),
        lambda i, f, p: p["assetFilters"].append(
            {"filterType": "MAX_ASSET", "asset": "BNB", "limit": "10"}
        ),
    ],
)
def test_malformed_missing_unknown_and_ambiguous_inputs(mutate):
    info, fees, private = bodies()
    mutate(info, fees, private)
    with pytest.raises(VenueInputError):
        parse(info, fees, private)


def test_zero_disabled_price_rules_do_not_disable_notional_or_quantity_rules():
    info, _, _ = bodies()
    info["symbols"][0]["filters"][0].update(minPrice="0", maxPrice="0", tickSize="0")
    rules = parse(info=info, fees=zero_fees()).rules
    valid = replace(candidates()[0].order, limit_price=D("100000.00001"))
    assert check_batch(snapshot(), rules, preflight_limits(), (valid,), now_ns=NOW).checks_passed
    tiny = replace(valid, quantity=D("0.000001"))
    result = check_batch(snapshot(), rules, preflight_limits(), (tiny,), now_ns=NOW)
    assert "quantity_bounds" in result.reasons and "notional_bounds" in result.reasons


def test_native_strategy_consumes_parsed_rules_and_refuses_base_fee_before_submit(
    tmp_path, monkeypatch
):
    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
        advance,
        build_simulation,
        fixture_signal,
    )

    engine, strategy, instrument = build_simulation(tmp_path / "checkpoint.json")
    try:
        advance(engine, instrument, NOW)
        monkeypatch.setattr(strategy, "rules", lambda: parse().rules)
        result = strategy.process_signals(tuple(fixture_signal(s, "venue", NOW) for s in SLEEVES))
        assert not result.selected
        assert not engine.cache.orders()
        assert all(
            "unsupported_order_fee_currency" in skipped.reasons for skipped in result.skipped
        )
    finally:
        engine.end()
        engine.dispose()


def test_private_request_symbol_is_required_even_when_response_does_not_echo_it():
    responses = [CapturedResponse(json.dumps(body), NOW, ACCOUNT, "BTCUSDT") for body in bodies()]
    responses[2] = replace(responses[2], requested_symbol="ETHUSDT")
    with pytest.raises(VenueInputError, match="request symbol"):
        parse_binance_rules(*responses, account_id=ACCOUNT, now_ns=NOW, max_age_ns=AGE)


def test_rules_are_not_refreshed_by_later_evaluation():
    evidence = parse(fees=zero_fees())
    result = select_funded_batch(
        replace(snapshot(), ts_ns=NOW + AGE + 1),
        evidence.rules,
        preflight_limits(),
        candidates(),
        now_ns=NOW + AGE + 1,
    )
    assert not result.selected
    assert any("stale or future instrument rules" in reason for reason in result.preflight.reasons)


def test_inapplicable_filters_are_explicit_and_unknown_exchange_filters_block():
    info, _, private = bodies()
    info["symbols"][0]["filters"].append(
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0", "maxQty": "10", "stepSize": "0"}
    )
    private["exchangeFilters"].append(
        {"filterType": "EXCHANGE_MAX_NUM_ALGO_ORDERS", "maxNumAlgoOrders": 5}
    )
    evidence = parse(info=info, private=private)
    assert evidence.inapplicable_filters == ("EXCHANGE_MAX_NUM_ALGO_ORDERS", "MARKET_LOT_SIZE")
    private["exchangeFilters"].append({"filterType": "NEW_EXCHANGE_FILTER"})
    with pytest.raises(VenueInputError, match="unsupported venue filter"):
        parse(info=info, private=private)


def test_pending_non_quote_fee_order_blocks_even_reduction_preflight():
    pending = PendingOrder("old", "v16", "BUY", D("0.001"), D("100000"), "pending_cancel")
    account = snapshot(pending=(pending,), used_order_ids=frozenset({"old"}))
    result = check_batch(account, parse().rules, preflight_limits(), (), now_ns=NOW)
    assert not result.checks_passed
    assert "pending order has unsupported fee currency" in result.reasons[0]


def test_cli_reports_fee_block_without_raw_private_data(tmp_path, capsys):
    from dataclasses import asdict

    from apps.ops.portfolio_venue_check import main

    bundle = {
        "schema_version": "portfolio.venue_inputs.v1",
        "account_id": ACCOUNT,
        "references": [],
    }
    for name, body in zip(("exchange_info", "commission", "my_filters"), bodies(), strict=True):
        bundle[name] = asdict(CapturedResponse(json.dumps(body), NOW, ACCOUNT, "BTCUSDT"))
    path = tmp_path / "captured.json"
    path.write_text(json.dumps(bundle))
    assert main([str(path), "--now-ns", str(NOW)]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["unsupported_fee_sides"] == ["BUY"]
    assert report["runtime_ready"] is False and report["account_reconciled"] is False
    assert ACCOUNT not in output and "standardCommission" not in output
    bundle["commission"]["body"] = json.dumps(zero_fees())
    path.write_text(json.dumps(bundle))
    assert main([str(path), "--now-ns", str(NOW)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "parsed_offline_only"
    assert main([str(path), "--now-ns", str(NOW + AGE + 1)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_duplicate_json_keys_are_rejected():
    responses = [CapturedResponse(json.dumps(body), NOW, ACCOUNT, "BTCUSDT") for body in bodies()]
    responses[1] = replace(responses[1], body='{"symbol":"BTCUSDT","symbol":"BTCUSDT"}')
    with pytest.raises(VenueInputError, match="duplicate JSON key"):
        parse_binance_rules(*responses, account_id=ACCOUNT, now_ns=NOW, max_age_ns=AGE)


def test_native_order_cap_reserves_slots_and_cash_for_the_selected_set(tmp_path, monkeypatch):
    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import (
        advance,
        build_simulation,
        fixture_signal,
    )

    info, _, _ = bodies()
    info["exchangeFilters"][0]["maxNumOrders"] = 2
    fees = zero_fees()
    # Synthetic schedule yields a conservative .0015 quote bound; no base fees.
    fees["standardCommission"]["seller"] = "0.0015"
    rules = parse(info=info, fees=fees).rules
    engine, strategy, instrument = build_simulation(tmp_path / "checkpoint.json")
    try:
        advance(engine, instrument, NOW)
        monkeypatch.setattr(strategy, "rules", lambda: rules)
        result = strategy.process_signals(tuple(fixture_signal(s, "slots", NOW) for s in SLEEVES))
        assert [c.order.sleeve for c in result.selected] == ["v16", "v18"]
        assert result.preflight.required_quote == D("200.30")
        assert len(engine.cache.orders()) == 2
        assert all("venue_open_order_limit" in skipped.reasons for skipped in result.skipped)
    finally:
        engine.end()
        engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_open_orders", True),
        ("max_open_orders", -1),
        ("max_position", D("NaN")),
        ("price_bands", ({},)),
    ],
)
def test_malformed_extended_preflight_rules_fail_closed(field, value):
    rules = replace(parse(fees=zero_fees()).rules, **{field: value})
    assert not check_batch(snapshot(), rules, preflight_limits(), (), now_ns=NOW).checks_passed


def test_explicit_base_commission_precision_is_retained_without_enabling_base_fees():
    info, _, _ = bodies()
    info["symbols"][0]["baseCommissionPrecision"] = 8
    evidence = parse(info=info)
    assert evidence.rules.base_fee_quantum == D("0.00000001")
    result = check_batch(
        snapshot(), evidence.rules, preflight_limits(), (candidates()[0].order,), now_ns=NOW
    )
    assert "unsupported_order_fee_currency" in result.reasons
    info["symbols"][0]["baseCommissionPrecision"] = 9
    with pytest.raises(VenueInputError, match="commission precision"):
        parse(info=info)

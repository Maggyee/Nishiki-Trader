from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest

from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_preflight import (
    AccountSnapshot,
    InstrumentRules,
    PendingOrder,
    ProposedOrder,
    check_batch,
)

NOW = 1_789_000_000_000_000_000
DAY = NOW // 86_400_000_000_000 * 86_400_000_000_000


def limits():
    return preflight_limits()


def rules(**kwargs):
    # SYNTHETIC effective LIMIT filters, never represented as current exchangeInfo.
    return replace(
        InstrumentRules(
            "BTCUSDT.BINANCE",
            NOW,
            D("0.00001"),
            D("1"),
            D("0.00001"),
            D("1"),
            D("1000000"),
            D("0.01"),
            D("5"),
            D("100000"),
            D("0.0015"),
        ),
        **kwargs,
    )


def account(**kwargs):
    return replace(
        AccountSnapshot(
            "BTCUSDT.BINANCE",
            NOW,
            DAY,
            True,
            D("500"),
            D("500"),
            D("0"),
            D("0"),
            tuple((p, D("0")) for p in SLEEVES),
            (),
            frozenset(),
            D("100000"),
            D("500"),
            D("500"),
        ),
        **kwargs,
    )


def order(sleeve="v16", side="BUY", quantity="0.001", price="100000", **kwargs):
    return replace(ProposedOrder(f"new-{sleeve}", sleeve, side, D(quantity), D(price)), **kwargs)


def check(a=None, orders=None, **kwargs):
    return check_batch(
        a or account(),
        kwargs.pop("r", rules()),
        kwargs.pop("l", limits()),
        orders if orders is not None else (order(),),
        now_ns=NOW,
        **kwargs,
    )


def held_account(quantity="0.001", **kwargs):
    qty = D(quantity)
    return account(
        total_quote=D("500") - qty * D("100000"),
        venue_free_quote=D("500") - qty * D("100000"),
        total_base=qty,
        venue_free_base=qty,
        holdings=tuple((p, qty if p == "v16" else D("0")) for p in SLEEVES),
        **kwargs,
    )


def pending_account(status="accepted", remaining="0.001", **kwargs):
    p = PendingOrder("old", "v16", "BUY", D(remaining), D("100000"), status)
    return account(pending=(p,), used_order_ids=frozenset({"old"}), **kwargs)


def test_batch_includes_fee_and_cannot_spend_same_cash_five_times():
    assert all(check(orders=(order(s),)).checks_passed for s in SLEEVES)
    result = check(orders=tuple(order(s) for s in SLEEVES))
    assert not result.checks_passed
    assert result.required_quote == D("500.75")
    assert result.available_quote == D("500")
    assert result.reasons == ("insufficient_unreserved_quote",)


def test_exact_cash_boundary():
    a = account(
        total_quote=D("100.15"),
        venue_free_quote=D("100.15"),
        day_open_equity=D("100.15"),
        peak_equity=D("100.15"),
    )
    assert check(a).checks_passed
    assert not check(replace(a, venue_free_quote=D("100.149999"))).checks_passed


@pytest.mark.parametrize("status", ["submitted", "accepted", "partially_filled", "pending_cancel"])
def test_active_reservations_are_kept_and_sleeve_cannot_replace(status):
    a = pending_account(status)
    assert "sleeve_has_pending_order" in check(a).reasons
    result = check(a, (order("v18"),))
    assert result.checks_passed
    assert result.available_quote == D("399.85")


def test_partial_fill_counts_remaining_only_without_double_counting_settlement():
    a = held_account("0.0004")
    p = PendingOrder("old", "v16", "BUY", D("0.0006"), D("100000"), "partially_filled")
    a = replace(a, pending=(p,), used_order_ids=frozenset({"old"}))
    result = check(a, (order("v18"),))
    assert result.available_quote == D("399.91")
    assert result.checks_passed


@pytest.mark.parametrize("status", ["filled", "canceled", "rejected", "expired"])
def test_only_confirmed_terminal_releases_reservation(status):
    assert check(pending_account(status, "0")).checks_passed
    assert not check(pending_account(status)).checks_passed


def test_venue_free_cash_not_double_subtracted_but_can_tighten_limit():
    a = pending_account(venue_free_quote=D("400"))
    assert check(a, (order("v18"),)).available_quote == D("399.85")
    assert check(replace(a, venue_free_quote=D("80")), (order("v18"),)).available_quote == D("80")


def test_unfilled_sell_never_finances_buy_and_cannot_sell_another_sleeve():
    a = held_account("0.001")
    a = replace(a, total_quote=D("0"), venue_free_quote=D("0"), day_open_equity=D("100"))
    result = check(a, (order(side="SELL"), order("v18")))
    assert "insufficient_unreserved_quote" in result.reasons
    assert "insufficient_unreserved_base" in check(a, (order("v18", "SELL"),)).reasons


def test_pending_sell_reserves_base_until_cancel_ack():
    p = PendingOrder("old", "v16", "SELL", D("0.0005"), D("100000"), "pending_cancel")
    a = replace(held_account(), pending=(p,), used_order_ids=frozenset({"old"}))
    result = check(a, (order(side="SELL"),))
    assert result.available_base == D("0.0005")
    assert "insufficient_unreserved_base" in result.reasons


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"day_open_equity": D("550"), "peak_equity": D("550")}, "daily_loss_limit"),
        ({"peak_equity": D("750")}, "drawdown_limit"),
        ({"risk_latched": True}, "risk_latched"),
    ],
)
def test_inclusive_risk_limits_block_buys_but_allow_owned_reductions(kwargs, reason):
    a = held_account(**kwargs)
    assert reason in check(a, (order("v18"),)).reasons
    assert check(a, (order(side="SELL"),)).checks_passed


def test_buy_cannot_net_away_pending_sell_exposure():
    a = held_account()
    result = check(
        a, (order(side="SELL"), order("v18")), l=replace(limits(), total_quantity=D("0.001"))
    )
    assert "portfolio_exposure_limit" in result.reasons


def test_sleeve_cap_includes_existing_inventory():
    assert "sleeve_exposure_limit" in check(held_account()).reasons


def test_known_entry_fees_cannot_cross_daily_or_peak_limit():
    a = account(day_open_equity=D("549.90"), peak_equity=D("749.90"))
    result = check(a)
    assert "projected_daily_loss_limit" in result.reasons
    assert "projected_drawdown_limit" in result.reasons


def test_pending_buy_fees_also_count_toward_projected_daily_limit():
    a = pending_account(day_open_equity=D("549.75"), peak_equity=D("549.75"))
    result = check(a, (order("v18"),))
    assert "projected_daily_loss_limit" in result.reasons


def test_snapshot_checks_are_deterministic_and_do_not_mutate_state():
    a = pending_account()
    assert check(a, (order("v18"),)) == check(a, (order("v18"),))
    assert a.total_quote == D("500")
    assert a.pending[0].remaining == D("0.001")


@pytest.mark.parametrize(
    "proposal,reason",
    [
        (order(quantity="0.000011"), "quantity_step"),
        (order(quantity="0.00001"), "notional_bounds"),
        (order(quantity="1.1"), "quantity_bounds"),
        (order(price="100000.001"), "price_tick"),
        (order(price="0.5"), "price_bounds"),
    ],
)
def test_effective_limit_filters(proposal, reason):
    assert reason in check(orders=(proposal,)).reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": D("NaN")},
        {"quantity": D("Infinity")},
        {"quantity": D("-1")},
        {"quantity": 0.001},
        {"order_type": "MARKET"},
        {"sleeve": "v40"},
        {"side": "SHORT"},
        {"order_id": ""},
    ],
)
def test_invalid_or_unsupported_orders_fail_closed(changes):
    assert not check(orders=(replace(order(), **changes),)).checks_passed


@pytest.mark.parametrize(
    "changes",
    [
        {"ts_ns": NOW - 60_000_000_001},
        {"ts_ns": NOW + 1},
        {"utc_day_start_ns": DAY - 86_400_000_000_000},
        {"reconciled": False},
        {"total_base": D("0.1")},
        {"total_quote": D("NaN")},
        {"venue_free_quote": D("501")},
        {"peak_equity": D("499")},
        {"instrument_id": "ETHUSDT.BINANCE"},
        {"holdings": ()},
    ],
)
def test_invalid_snapshot_rejects_even_sells(changes):
    assert not check(account(**changes), (order(side="SELL"),)).checks_passed


def test_duplicate_ids_in_batch_and_across_restart_fail_closed():
    assert not check(orders=(order(), order())).checks_passed
    assert not check(account(used_order_ids=frozenset({"new-v16"}))).checks_passed


def test_unknown_pending_order_blocks_not_ignored():
    assert not check(pending_account("unknown")).checks_passed
    a = pending_account()
    assert not check(replace(a, pending=a.pending * 2)).checks_passed
    assert not check(replace(a, used_order_ids=frozenset())).checks_passed


@pytest.mark.parametrize(
    "changes",
    [
        {"fee_currency": "BNB"},
        {"fee_rate": D("NaN")},
        {"quantity_step": D("0")},
        {"ts_ns": NOW - 60_000_000_001},
        {"ts_ns": NOW + 1},
    ],
)
def test_unknown_or_stale_rules_fail_closed(changes):
    assert not check(r=rules(**changes)).checks_passed

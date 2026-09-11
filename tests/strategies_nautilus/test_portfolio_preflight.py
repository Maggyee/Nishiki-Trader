from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
from itertools import permutations

import pytest

from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_preflight import (
    AccountSnapshot,
    AdmissionCandidate,
    InstrumentRules,
    PendingOrder,
    ProposedOrder,
    check_batch,
    select_funded_batch,
)

NOW = 1_789_000_000_000_000_000
DAY = NOW // 86_400_000_000_000 * 86_400_000_000_000


def limits():
    return preflight_limits()


@pytest.mark.parametrize(
    "day_open,threshold", [("100", "5"), ("400", "20"), ("500", "25"), ("1000", "25")]
)
@pytest.mark.parametrize("offset", ["-0.01", "0", "0.01"])
def test_current_daily_rule_tracks_equity_and_keeps_fixed_cap(day_open, threshold, offset):
    opening, loss = D(day_open), D(threshold) + D(offset)
    equity = opening - loss
    a = account(
        total_quote=equity, venue_free_quote=equity, day_open_equity=opening, peak_equity=opening
    )
    # Zero fee isolates the inclusive observed-loss boundary; fee accumulation
    # is independently exercised by the funded-subset and pending-order tests.
    result = check(a, (order(quantity="0.0001"),), r=rules(fee_rate=D("0")))
    assert limits().effective_daily_loss(opening) == D(threshold)
    assert result.checks_passed == (D(offset) < 0)
    assert ("daily_loss_limit" in result.reasons) == (D(offset) >= 0)


@pytest.mark.parametrize("fraction", [D("0"), D("0.0501"), D("NaN"), D("Infinity"), 0.05])
def test_invalid_or_weakened_percentage_fails_closed(fraction):
    result = check(l=replace(limits(), daily_fraction=fraction))
    assert not result.checks_passed
    assert result.reasons[0].startswith("invalid_input:")


def test_legacy_50_usdt_replay_is_explicit():
    a = account(total_quote=D("474"), venue_free_quote=D("474"))
    assert check(a, l=preflight_limits(revision=2)).checks_passed
    assert "daily_loss_limit" in check(a).reasons


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


def candidate(sleeve="v16", *, proposal=None, **kwargs):
    return replace(
        AdmissionCandidate(
            proposal or order(sleeve), f"signal-{sleeve}", NOW - 1_000_000_000, NOW + 30_000_000_000
        ),
        **kwargs,
    )


def select(candidates=None, a=None, **kwargs):
    return select_funded_batch(
        a or account(),
        kwargs.pop("r", rules()),
        kwargs.pop("l", limits()),
        candidates if candidates is not None else tuple(candidate(s) for s in SLEEVES),
        now_ns=kwargs.pop("now_ns", NOW),
        **kwargs,
    )


def test_funded_subset_preserves_sizes_and_has_exact_headroom():
    result = select()
    assert [c.order.sleeve for c in result.selected] == list(SLEEVES[:4])
    assert all(c.order.quantity == D("0.001") for c in result.selected)
    assert result.preflight.checks_passed
    assert result.preflight.required_quote == D("400.60")
    assert result.preflight.available_quote - result.preflight.required_quote == D("99.40")
    assert result.skipped[0].order_id == "new-v36"
    assert result.skipped[0].signal_id == "signal-v36"
    assert result.skipped[0].reasons == ("insufficient_unreserved_quote",)
    assert result.snapshot_ts_ns == result.evaluated_at_ns == NOW


def test_all_input_permutations_produce_same_admission_and_audit():
    expected = select()
    for items in permutations(tuple(candidate(s) for s in SLEEVES)):
        assert select(items) == expected


def test_earlier_event_time_precedes_sleeve_tie_break():
    items = tuple(
        candidate(s, ts_event_ns=NOW - (2_000_000_000 if s == "v36" else 1_000_000_000))
        for s in SLEEVES
    )
    result = select(items)
    assert result.selected[0].order.sleeve == "v36"
    assert result.skipped[0].order_id == "new-v34"


def test_skipping_expensive_first_order_does_not_stop_later_affordable_orders():
    items = (candidate(proposal=order(price="1000000")), candidate("v18"))
    result = select(items)
    assert [c.order.sleeve for c in result.selected] == ["v18"]
    assert "insufficient_unreserved_quote" in result.skipped[0].reasons


def test_selector_accounts_for_pending_cancel_and_never_replaces_it():
    result = select(a=pending_account("pending_cancel"))
    assert [c.order.sleeve for c in result.selected] == ["v18", "v22", "v34"]
    assert result.preflight.available_quote == D("399.85")
    assert result.preflight.required_quote == D("300.45")
    assert result.skipped[0].reasons == ("sleeve_has_pending_order", "sleeve_exposure_limit")
    assert result.skipped[-1].reasons == ("insufficient_unreserved_quote",)


def test_reductions_first_without_crediting_unsettled_proceeds():
    a = held_account()
    a = replace(a, total_quote=D("0"), venue_free_quote=D("0"), day_open_equity=D("100"))
    items = (
        candidate("v18", ts_event_ns=NOW - 2_000_000_000),
        candidate(proposal=order(side="SELL")),
    )
    result = select(items, a)
    assert [c.order.side for c in result.selected] == ["SELL"]
    assert "insufficient_unreserved_quote" in result.skipped[0].reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"risk_latched": True}, "risk_latched"),
        ({"day_open_equity": D("550"), "peak_equity": D("550")}, "daily_loss_limit"),
        ({"peak_equity": D("750")}, "drawdown_limit"),
    ],
)
def test_selector_preserves_entry_risk_blocks_and_owned_reductions(changes, reason):
    result = select(
        (candidate("v18"), candidate(proposal=order(side="SELL"))), held_account(**changes)
    )
    assert [c.order.side for c in result.selected] == ["SELL"]
    assert reason in result.skipped[0].reasons


def test_selector_accumulates_fees_and_exposure_for_whole_selected_set():
    result = select(a=account(day_open_equity=D("524.60"), peak_equity=D("524.60")))
    assert len(result.selected) == 2  # 0.30 fees fit; 0.45 would cross 25 loss
    assert all("projected_daily_loss_limit" in s.reasons for s in result.skipped)
    capped = select(l=replace(limits(), total_quantity=D("0.002")))
    assert len(capped.selected) == 2
    assert all("portfolio_exposure_limit" in s.reasons for s in capped.skipped)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"expires_at_ns": NOW}, "expired_signal"),
        ({"ts_event_ns": NOW + 1}, "future_signal"),
    ],
)
def test_selector_skips_invalid_time_without_blocking_other_candidates(changes, reason):
    result = select((candidate(**changes), candidate("v18")))
    assert [c.order.sleeve for c in result.selected] == ["v18"]
    assert result.skipped[0].reasons == (reason,)


def test_no_queued_retry_and_fresh_reconsideration_checks_expiry():
    original = select()
    later = NOW + 30_000_000_000
    a = account(
        ts_ns=later,
        total_quote=D("1000"),
        venue_free_quote=D("1000"),
        day_open_equity=D("1000"),
        peak_equity=D("1000"),
    )
    result = select((candidate("v36"),), a, r=rules(ts_ns=later), now_ns=later)
    assert not result.selected
    assert result.skipped[0].reasons == ("expired_signal",)
    assert len(original.selected) == 4


@pytest.mark.parametrize(
    "changes", [{"reconciled": False}, {"ts_ns": NOW + 1}, {"ts_ns": NOW - 60_000_000_001}]
)
def test_invalid_snapshot_rejects_all_before_selection(changes):
    result = select(a=account(**changes))
    assert not result.selected and not result.preflight.checks_passed
    assert len(result.skipped) == 5


@pytest.mark.parametrize("fault", ["signal", "sleeve", "order", "timestamp"])
def test_ambiguous_or_malformed_candidate_batch_fails_closed(fault):
    left, right = candidate(), candidate("v18")
    if fault == "signal":
        right = replace(right, signal_id=left.signal_id)
    elif fault == "sleeve":
        right = replace(right, order=replace(right.order, sleeve="v16"))
    elif fault == "order":
        right = replace(right, order=replace(right.order, order_id=left.order.order_id))
    else:
        right = replace(right, ts_event_ns=float(NOW))
    result = select((left, right))
    assert not result.selected and not result.preflight.checks_passed
    assert len(result.skipped) == 2


def test_empty_input_never_selects_an_order():
    result = select(())
    assert not result.selected and not result.skipped
    assert result.preflight.checks_passed


def test_selector_keeps_filters_id_replay_and_unknown_sleeve_checks():
    items = (
        candidate(proposal=order(quantity="0.000011")),
        candidate("v18"),
        candidate("v22"),
        candidate("v40"),
    )
    result = select(items, account(used_order_ids=frozenset({"new-v22"})))
    assert [c.order.sleeve for c in result.selected] == ["v18"]
    assert "quantity_step" in result.skipped[0].reasons
    assert "reused" in result.skipped[1].reasons[0]
    assert "unknown/repeated proposed sleeve" in result.skipped[2].reasons[0]


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
    a = account(day_open_equity=D("524.90"), peak_equity=D("749.90"))
    result = check(a)
    assert "projected_daily_loss_limit" in result.reasons
    assert "projected_drawdown_limit" in result.reasons


def test_pending_buy_fees_also_count_toward_projected_daily_limit():
    a = pending_account(day_open_equity=D("524.75"), peak_equity=D("524.75"))
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

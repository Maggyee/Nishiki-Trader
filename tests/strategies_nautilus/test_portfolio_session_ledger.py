from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import replace
from decimal import Decimal as D

import pytest
from nautilus_trader.model.currencies import BTC, ETH, USDT
from nautilus_trader.model.objects import AccountBalance, Money
from nautilus_trader.test_kit.stubs.events import TestEventStubs

from apps.strategies_nautilus.portfolio_adapter_recovery import (
    AdapterRecoveryError,
    prepare_binance_reports,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.portfolio_session_ledger import (
    SessionLedger,
    SessionLedgerError,
    native_view,
    read_session,
)
from apps.strategies_nautilus.portfolio_session_recovery import recover_session
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.runners.portfolio_session_acceptance import (
    BASE,
    BINDING,
    SECOND,
    SID,
    fixture_context,
    install_submitted,
    native_order,
    recovery_evidence,
    row,
    rules,
    run_acceptance,
    signal,
    trade,
)


@pytest.fixture
def session(tmp_path):
    loop = asyncio.new_event_loop()
    owner = fixture_context(loop)
    ledger = SessionLedger(tmp_path / "session.json").create(owner, session_id=SID, source=BINDING)
    owner.clock.set_time(BASE + SECOND)
    try:
        yield owner, ledger, loop
    finally:
        ledger.close()
        owner.engine.dispose()
        loop.close()


def prepare(owner, ledger, *, side="buy", quantity="0.00010000", price="70000.00", suffix="entry"):
    sig = signal(owner.clock.timestamp_ns(), side=side, suffix=suffix)
    order = native_order(owner, sig, quantity=quantity, price=price)
    ledger.prepare(owner, signal=sig, order=order, rules=rules(owner.clock.timestamp_ns()))
    return order


def settle(owner, ledger, *, status="FILLED", quantity="0.00010000"):
    order = prepare(owner, ledger)
    install_submitted(owner, order)
    owner.clock.set_time(BASE + 6 * SECOND)
    orders = [row(status, quantity)]
    trades = [trade(201, quantity, offset=6)] if D(quantity) else []
    reconcile_binance_reports(
        owner.engine,
        owner.cache,
        account_id=owner.cache.accounts()[0].id,
        orders=orders,
        trades=trades,
        now_ns=owner.clock.timestamp_ns(),
    )
    ledger.observe(owner)
    return order, orders, trades


def recover(raw, evidence, loop):
    return recover_session(
        raw,
        evidence,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        evidence_sha256=hashlib.sha256(evidence).hexdigest(),
        now_ns=BASE + 8 * SECOND,
        loop=loop,
    )


def test_prepared_intent_is_durable_before_native_order_exists_and_survives_reload(session):
    owner, ledger, _ = session
    order = prepare(owner, ledger)
    assert owner.cache.orders() == []
    saved = read_session(ledger.path.read_bytes())["state"]
    assert saved["view"]["buy_allowance_consumed"]
    assert D(saved["view"]["buy_reserved_usdt"]) == 7
    assert saved["view"]["uncertain_order_ids"] == [str(order.client_order_id)]
    assert saved["view"]["owned_btc"] == "0"
    assert D(saved["baseline"]["BTC"][0]) == 2
    digest = ledger.sha256
    ledger.close()
    ledger.load(expected_sha256=digest)
    with pytest.raises(SessionLedgerError, match="outstanding or uncertain"):
        prepare(owner, ledger, suffix="second")
    assert ledger.sha256 == digest


def test_existing_checkpoint_and_concurrent_writer_cannot_reset_budget(session):
    owner, ledger, _ = session
    other = SessionLedger(ledger.path)
    with pytest.raises(BlockingIOError):
        other.load(expected_sha256=ledger.sha256)
    ledger.close()
    with pytest.raises(SessionLedgerError, match="cannot be reset"):
        other.create(owner, session_id=SID, source=BINDING)


def test_changed_checkpoint_hash_and_public_file_permissions_are_refused(session):
    _, ledger, _ = session
    digest = ledger.sha256
    ledger.close()
    with pytest.raises(SessionLedgerError, match="selected session checkpoint changed"):
        ledger.load(expected_sha256="0" * 64)
    ledger.path.chmod(0o644)
    with pytest.raises(SessionLedgerError, match="private bounded checkpoint"):
        ledger.load(expected_sha256=digest)
    ledger.path.chmod(0o600)
    ledger.load(expected_sha256=digest)


def test_external_checkpoint_replacement_poisoned_writer_cannot_publish(session):
    owner, ledger, _ = session
    ledger.path.write_bytes(ledger.path.read_bytes() + b" ")
    with pytest.raises(SessionLedgerError, match="outside writer"):
        prepare(owner, ledger)
    with pytest.raises(SessionLedgerError, match="healthy owning"):
        ledger.observe(owner)


@pytest.mark.parametrize(
    "quantity,price",
    [
        ("0.00020000", "70000.00"),
        ("0.00010000", "100000.01"),
        ("0.00010000", "40000.00"),
        ("0.00010100", "70000.00"),
    ],
)
def test_fixed_size_budget_step_and_minimum_notional(session, quantity, price):
    owner, ledger, _ = session
    before = ledger.path.read_bytes()
    with pytest.raises(SessionLedgerError):
        prepare(owner, ledger, quantity=quantity, price=price)
    assert ledger.path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        {"source": "llm_advice"},
        {"model_version": "foreign-model"},
        {"symbol": "ETHUSDT"},
        {"venue": "OTHER"},
        {"ts_event": BASE + 2 * SECOND},
        {"ts_event": BASE - 61 * SECOND},
        {"confidence": 0.1},
        {"side": "sell"},
    ],
)
def test_fixture_consumer_refuses_unauthorized_stale_or_foreign_signals(session, change):
    owner, ledger, _ = session
    sig = signal(owner.clock.timestamp_ns()).model_copy(update=change)
    order = native_order(owner, sig)
    with pytest.raises((SessionLedgerError, ValueError)):
        ledger.prepare(owner, signal=sig, order=order, rules=rules(owner.clock.timestamp_ns()))
    assert ledger.state["intents"] == {}


@pytest.mark.parametrize(
    "overrides",
    [
        {"fee_rate": D("0.001")},
        {"ts_ns": BASE - 10 * SECOND},
        {"max_position": D("2")},
        {"notional_max": D("6")},
        {"max_open_orders": 0},
    ],
)
def test_effective_filters_include_the_whole_account(session, overrides):
    owner, ledger, _ = session
    sig = signal(owner.clock.timestamp_ns())
    with pytest.raises(ValueError):
        ledger.prepare(
            owner,
            signal=sig,
            order=native_order(owner, sig),
            rules=replace(rules(owner.clock.timestamp_ns()), **overrides),
        )


def test_owned_cleanup_never_sells_preexisting_btc_or_recycles_proceeds(session):
    owner, ledger, _ = session
    _, orders, trades = settle(owner, ledger)
    assert ledger.state["view"]["owned_btc"] == "0.0001"
    owner.clock.set_time(BASE + 7 * SECOND)
    with pytest.raises(SessionLedgerError):
        prepare(owner, ledger, side="flat", quantity="2.00010000", price="71000.00", suffix="sweep")
    sell = prepare(owner, ledger, side="flat", price="71000.00", suffix="exit")
    install_submitted(owner, sell)
    owner.clock.set_time(BASE + 8 * SECOND)
    orders += [
        row("FILLED", "0.00010000", side="SELL", price="71000.00", time_offset=7, update_offset=8)
    ]
    trades += [trade(202, "0.00010000", side="SELL", price="71000.00", offset=8)]
    reconcile_binance_reports(
        owner.engine,
        owner.cache,
        account_id=owner.cache.accounts()[0].id,
        orders=orders,
        trades=trades,
        now_ns=owner.clock.timestamp_ns(),
    )
    view = ledger.observe(owner)
    assert D(view["owned_btc"]) == 0
    assert D(view["buy_spent_usdt"]) == 7
    assert D(view["sell_proceeds_usdt"]) == D("7.1")
    assert owner.cache.accounts()[0].balance_total(BTC).as_decimal() == 2
    assert owner.cache.accounts()[0].balance_total(USDT).as_decimal() == D("100.1")
    owner.clock.set_time(BASE + 9 * SECOND)
    with pytest.raises(SessionLedgerError, match="one fixed BUY"):
        prepare(owner, ledger, suffix="recycle")


def test_below_minimum_partial_fill_is_retained_as_owned_inventory(session):
    owner, ledger, _ = session
    settle(owner, ledger, status="CANCELED", quantity="0.00003500")
    owner.clock.set_time(BASE + 7 * SECOND)
    with pytest.raises(SessionLedgerError):
        prepare(owner, ledger, side="flat", quantity="0.00003000", suffix="dust")
    assert D(ledger.state["view"]["owned_btc"]) == D("0.000035")
    assert not ledger.state["view"]["sell_allowance_consumed"]


def test_whole_step_cleanup_preserves_exact_native_dust(session):
    owner, ledger, _ = session
    _, orders, trades = settle(owner, ledger, status="CANCELED", quantity="0.00007500")
    owner.clock.set_time(BASE + 7 * SECOND)
    sell = prepare(
        owner, ledger, side="flat", quantity="0.00007000", price="80000.00", suffix="exit"
    )
    install_submitted(owner, sell)
    owner.clock.set_time(BASE + 8 * SECOND)
    orders += [
        row(
            "FILLED",
            "0.00007000",
            side="SELL",
            original="0.00007000",
            price="80000.00",
            time_offset=7,
            update_offset=8,
        )
    ]
    trades += [trade(202, "0.00007000", side="SELL", price="80000.00", offset=8)]
    reconcile_binance_reports(
        owner.engine,
        owner.cache,
        account_id=owner.cache.accounts()[0].id,
        orders=orders,
        trades=trades,
        now_ns=owner.clock.timestamp_ns(),
    )
    view = ledger.observe(owner)
    assert D(view["owned_btc"]) == D("0.000005")
    assert owner.cache.accounts()[0].balance_total(BTC).as_decimal() == D("2.000005")
    assert view["sell_allowance_consumed"]


def test_unexpected_fee_is_accounted_and_persistently_halts_the_zero_fee_session(session):
    owner, ledger, _ = session
    order = prepare(owner, ledger)
    install_submitted(owner, order)
    owner.clock.set_time(BASE + 6 * SECOND)
    fill = trade(201, "0.0001", offset=6)
    fill["commission"] = "0.00001000"
    reconcile_binance_reports(
        owner.engine,
        owner.cache,
        account_id=owner.cache.accounts()[0].id,
        orders=[row("FILLED", "0.0001")],
        trades=[fill],
        now_ns=owner.clock.timestamp_ns(),
    )
    view = ledger.observe(owner)
    assert D(view["buy_spent_usdt"]) == D("7.00001")
    assert owner.cache.accounts()[0].balance_total(USDT).as_decimal() == D("92.99999")
    digest = ledger.sha256
    ledger.close()
    ledger.load(expected_sha256=digest)
    assert ledger.state["halt_reasons"] == ["unexpected_nonzero_commission"]
    owner.clock.set_time(BASE + 7 * SECOND)
    with pytest.raises(SessionLedgerError, match="halted"):
        prepare(owner, ledger, side="flat", suffix="exit")


def test_partial_buy_free_and_locked_balances_use_remaining_native_quantity(session):
    owner, ledger, _ = session
    settle(owner, ledger, status="PARTIALLY_FILLED", quantity="0.00004000")
    account = owner.cache.accounts()[0]
    assert account.balance_total(USDT).as_decimal() == D("97.2")
    assert account.balance_locked(USDT).as_decimal() == D("4.2")
    assert account.balance_free(USDT).as_decimal() == D("93")


def test_active_partial_order_recovery_preserves_native_locks(session):
    owner, ledger, loop = session
    order = prepare(owner, ledger)
    install_submitted(owner, order)
    ledger.observe(owner)
    raw = ledger.path.read_bytes()
    evidence = json.loads(recovery_evidence(scenario="prepared"))
    evidence["orders"] = [row("PARTIALLY_FILLED", "0.00004")]
    evidence["trades"] = [trade(201, "0.00004", offset=6)]
    evidence["open_orders"] = evidence["orders"]
    evidence["account"]["balances"][0].update(free="93", locked="4.2")
    evidence["account"]["balances"][1].update(free="2.00004")
    result = recover(raw, canonical(evidence), loop)
    assert result["full_account_reconciled"]
    assert D(result["view"]["buy_reserved_usdt"]) == D("4.2")


def test_active_order_without_submitted_receipt_stays_blocked_without_inference(session):
    owner, ledger, loop = session
    prepare(owner, ledger)
    raw = ledger.path.read_bytes()
    evidence = json.loads(recovery_evidence(scenario="prepared"))
    evidence["orders"] = [row("PARTIALLY_FILLED", "0.00004")]
    evidence["trades"] = [trade(201, "0.00004", offset=6)]
    evidence["open_orders"] = evidence["orders"]
    evidence["account"]["balances"][0].update(free="93", locked="4.2")
    evidence["account"]["balances"][1].update(free="2.00004")
    with pytest.raises(SessionLedgerError, match="persisted native submit receipt"):
        recover(raw, canonical(evidence), loop)
    assert ledger.path.read_bytes() == raw


def test_canceled_empty_buy_still_spends_the_buy_allowance(session):
    owner, ledger, _ = session
    settle(owner, ledger, status="CANCELED", quantity="0")
    owner.clock.set_time(BASE + 7 * SECOND)
    with pytest.raises(SessionLedgerError, match="one fixed BUY"):
        prepare(owner, ledger, suffix="retry")


def test_cancel_intent_is_durable_and_not_repeated(session):
    owner, ledger, _ = session
    order, _, _ = settle(owner, ledger, status="PARTIALLY_FILLED", quantity="0.00004000")
    with pytest.raises(SessionLedgerError, match="acknowledged"):
        ledger.prepare_cancel(owner, order)
    owner.clock.set_time(BASE + 8 * SECOND)
    ledger.prepare_cancel(owner, order)
    order.apply(TestEventStubs.order_pending_cancel(order, ts_event=owner.clock.timestamp_ns()))
    owner.cache.update_order(order)
    view = ledger.observe(owner)
    assert str(order.client_order_id) in view["uncertain_order_ids"]
    with pytest.raises(SessionLedgerError):
        ledger.prepare_cancel(owner, order)
    assert (
        str(order.client_order_id)
        in read_session(ledger.path.read_bytes())["state"]["cancel_intents"]
    )


@pytest.mark.parametrize("failure_call", [1, 2])
def test_file_or_directory_fsync_failure_never_returns_a_submission_permit(
    session, monkeypatch, failure_call
):
    owner, ledger, _ = session
    before = ledger.path.read_bytes()
    real_fsync = os.fsync
    calls = 0

    def fail(fd):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("synthetic persistence failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        prepare(owner, ledger)
    with pytest.raises(SessionLedgerError, match="healthy owning"):
        ledger.observe(owner)
    saved = ledger.path.read_bytes()
    if failure_call == 1:
        assert saved == before
    else:
        assert read_session(saved)["state"]["view"]["buy_allowance_consumed"]


def test_timeout_and_clock_rollback_do_not_reset_session(session):
    owner, ledger, _ = session
    owner.clock.set_time(BASE + 180 * SECOND)
    with pytest.raises(SessionLedgerError, match="expired"):
        prepare(owner, ledger)
    ledger.observe(owner)
    owner.clock.set_time(BASE + 179 * SECOND)
    with pytest.raises(SessionLedgerError, match="regressed"):
        prepare(owner, ledger)


def test_unrelated_balance_drift_is_never_repaired(session):
    owner, ledger, _ = session
    account = owner.cache.accounts()[0]
    account.update_balances([AccountBalance(Money(6, ETH), Money(0, ETH), Money(6, ETH))])
    with pytest.raises(SessionLedgerError, match="conservation"):
        native_view(ledger.state, owner)


def test_prepared_native_initialization_recovery_uses_real_native_accepted_and_fill(session):
    owner, ledger, loop = session
    prepare(owner, ledger)
    raw = ledger.path.read_bytes()
    result = recover(raw, recovery_evidence(scenario="prepared"), loop)
    wrapped = read_session(result["checkpoint"])
    events = [json.loads(e)["type"] for e in wrapped["native"]["orders"][0]["events"]]
    assert events == ["OrderInitialized", "OrderAccepted", "OrderFilled"]
    assert result["view"]["buy_allowance_consumed"]
    assert result["view"]["owned_btc"] == "0.0001"
    assert not result["runtime_ready"]
    assert ledger.path.read_bytes() == raw


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e.update(orders=[]),
        lambda e: e.update(trades=[]),
        lambda e: e["trades"].append(e["trades"][0]),
        lambda e: e["source"].update(account_uid="999"),
        lambda e: e["source"].update(endpoint="https://api.binance.com"),
        lambda e: e.update(history_start_ns=BASE + SECOND),
        lambda e: e["account"]["balances"][2].update(free="6"),
        lambda e: e["account"]["balances"][0].update(free="92", locked="1"),
        lambda e: e["open_orders"].append({"symbol": "ETHUSDT", "orderId": 777}),
        lambda e: e["orders"][0].update(origQty="0.0002"),
    ],
)
def test_recovery_refuses_missing_conflicting_or_foreign_evidence(session, mutation):
    owner, ledger, loop = session
    prepare(owner, ledger)
    raw = ledger.path.read_bytes()
    evidence = json.loads(recovery_evidence(scenario="prepared"))
    mutation(evidence)
    with pytest.raises(ValueError):
        recover(raw, canonical(evidence), loop)
    assert ledger.path.read_bytes() == raw


def test_default_adapter_does_not_adopt_initialized_orders(session):
    owner, ledger, _ = session
    order = prepare(owner, ledger)
    from nautilus_trader.model.identifiers import PositionId

    owner.cache.add_order(order, position_id=PositionId(ledger.state["position_id"]))
    with pytest.raises(AdapterRecoveryError, match="lineage mismatch"):
        prepare_binance_reports(
            owner.cache,
            account_id=owner.cache.accounts()[0].id,
            orders=[row("FILLED", "0.0001")],
            trades=[trade(201, "0.0001", offset=6)],
            now_ns=BASE + 8 * SECOND,
        )


def test_actual_abrupt_exit_and_replay_in_six_processes_preserve_all_502_assets():
    result = run_acceptance()
    assert all(row["full_assets_preserved"] == 502 for row in result["scenarios"].values())
    assert result["matching_requests_made"] == 0
    assert not result["runtime_ready"]

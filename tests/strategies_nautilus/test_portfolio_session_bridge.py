from __future__ import annotations

import asyncio
import hashlib
import os
from decimal import Decimal as D
from types import SimpleNamespace

import msgspec
import pytest
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.model.identifiers import PositionId

from apps.strategies_nautilus.portfolio_session_bridge import SessionBridge
from apps.strategies_nautilus.portfolio_session_ledger import (
    SessionLedger,
    SessionLedgerError,
    read_session,
)
from apps.strategies_nautilus.portfolio_session_recovery import recover_session
from apps.strategies_nautilus.runners.portfolio_session_acceptance import (
    BASE,
    BINDING,
    SECOND,
    SID,
    recovery_evidence,
    rules,
    signal,
)
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import (
    build_bridge,
    close_bridge,
    drain,
    execution_report,
    run_acceptance,
    run_crash_acceptance,
)


@pytest.fixture
def session(tmp_path):
    loop = asyncio.new_event_loop()

    async def build():
        return build_bridge(tmp_path / "session.json")

    owner = loop.run_until_complete(build())
    owner.loop = loop
    try:
        yield owner
    finally:
        loop.run_until_complete(close_bridge(owner))
        loop.close()


def flush(owner):
    owner.loop.run_until_complete(drain(owner))


def submit(owner):
    return owner.strategy.consume(
        signal(owner.clock.timestamp_ns()),
        rules=rules(owner.clock.timestamp_ns()),
        price="70000.00",
    )


def acknowledge(owner):
    order = submit(owner)
    flush(owner)
    owner.clock.set_time(BASE + 2 * SECOND)
    report(owner, order)
    return order


def report(owner, order, **kwargs):
    raw = execution_report(owner, order, **kwargs)
    owner.client._handle_user_ws_message(raw)
    flush(owner)
    return raw


def saved(owner):
    return read_session(owner.ledger.path.read_bytes())["state"]


def test_full_queued_native_partial_cancel_late_duplicate_acceptance():
    result = asyncio.run(run_acceptance())
    assert result["fixture_dispatches"] == 2
    assert result["assets_retained"] == 502
    assert result["network_requests"] == 0 and not result["runtime_ready"]


def test_queued_submitted_and_dispatch_are_durable_before_http(session):
    owner = session
    observed = []

    async def check():
        state = saved(owner)
        observed.append(state["view"]["statuses"][f"ts-{SID}-b"])
        assert state["dispatches"][f"submit:ts-{SID}-b"]["event_id"]
        assert state["view"]["buy_allowance_consumed"]

    owner.client.sink.before_response = check
    order = submit(owner)
    assert owner.client.sink.calls == [] and order.status.name == "INITIALIZED"
    flush(owner)
    assert observed == ["SUBMITTED"]
    assert order.status.name == "SUBMITTED"  # HTTP ACK is not native Accepted.
    assert owner.risk.command_count == 1


def test_risk_engine_denial_never_reaches_adapter(session):
    owner = session
    owner.risk.set_max_notional_per_order(owner.cache.instruments()[0].id, D("6"))
    order = submit(owner)
    flush(owner)
    assert order.status.name == "DENIED"
    assert owner.client.sink.calls == []
    assert saved(owner)["view"]["buy_allowance_consumed"]
    assert saved(owner)["view"]["statuses"][str(order.client_order_id)] == "DENIED"


@pytest.mark.parametrize(
    "stage", ["prepare", "submitted", "dispatch", "pending_cancel", "cancel_dispatch"]
)
def test_disk_failure_prevents_outbound_attempt(session, monkeypatch, stage):
    owner = session
    if stage in {"pending_cancel", "cancel_dispatch"}:
        order = acknowledge(owner)
        owner.clock.set_time(BASE + 4 * SECOND)
    original_fsync = os.fsync

    def fail_at_stage(fd):
        orders = owner.cache.orders()
        status = orders[0].status.name if orders else "PREPARE"
        dispatches = owner.ledger.state.get("dispatches", {})
        fail = (
            stage == "prepare"
            or (stage == "submitted" and status == "SUBMITTED")
            or (stage == "dispatch" and f"submit:ts-{SID}-b" in dispatches)
            or (stage == "pending_cancel" and status == "PENDING_CANCEL")
            or (stage == "cancel_dispatch" and f"cancel:ts-{SID}-b" in dispatches)
        )
        if fail:
            raise OSError("fixture fsync failed")
        return original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_at_stage)
    if stage == "prepare":
        with pytest.raises(OSError):
            submit(owner)
    elif stage in {"pending_cancel", "cancel_dispatch"}:
        owner.strategy.request_cancel(order)
    else:
        submit(owner)
    flush(owner)
    assert len(owner.client.sink.calls) == (1 if "cancel" in stage else 0)
    assert owner.ledger._poisoned
    with pytest.raises(SessionLedgerError):
        owner.bridge.require_healthy()


@pytest.mark.parametrize("kind", ["submit", "cancel"])
def test_unknown_timeout_never_becomes_rejected_or_retries(session, kind):
    owner = session
    if kind == "cancel":
        order = acknowledge(owner)
        owner.clock.set_time(BASE + 4 * SECOND)
    owner.client.sink.failure = TimeoutError("unknown fixture response")
    if kind == "submit":
        order = submit(owner)
    else:
        owner.strategy.request_cancel(order)
    flush(owner)
    assert owner.bridge.failed
    assert order.status.name == ("SUBMITTED" if kind == "submit" else "PENDING_CANCEL")
    assert saved(owner)["dispatches"][f"{kind}:{order.client_order_id}"]
    assert len(owner.client.sink.calls) == (1 if kind == "submit" else 2)
    assert not any(
        type(e).__name__ in {"OrderRejected", "OrderCancelRejected"} for e in order.events
    )
    with pytest.raises(SessionLedgerError):
        submit(owner)
    # Late business events still settle under native accounting after the halt.
    owner.clock.set_time(BASE + 5 * SECOND)
    if kind == "submit":
        report(owner, order)
    report(owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201)
    assert D(saved(owner)["view"]["owned_btc"]) == D("0.00004")
    assert saved(owner)["halt_reasons"]


def test_cancel_receipt_persists_before_native_http_and_waits_two_seconds(session):
    owner = session
    order = acknowledge(owner)
    with pytest.raises(SessionLedgerError):
        owner.strategy.request_cancel(order)
    owner.clock.set_time(BASE + 4 * SECOND)
    owner.strategy.request_cancel(order)
    assert order.status.name == "PENDING_CANCEL"
    assert saved(owner)["view"]["statuses"][str(order.client_order_id)] == "PENDING_CANCEL"
    assert len(owner.client.sink.calls) == 1
    flush(owner)
    assert f"cancel:{order.client_order_id}" in saved(owner)["dispatches"]
    assert len(owner.client.sink.calls) == 2
    with pytest.raises(SessionLedgerError):
        owner.strategy.request_cancel(order)


def test_native_full_fill_then_only_owned_cleanup(session):
    owner = session
    order = acknowledge(owner)
    owner.clock.set_time(BASE + 3 * SECOND)
    report(owner, order, kind="TRADE", quantity="0.00010000", total="0.00010000", tid=201)
    owner.clock.set_time(BASE + 4 * SECOND)
    cleanup = owner.strategy.consume(
        signal(owner.clock.timestamp_ns(), side="flat", suffix="exit"),
        rules=rules(owner.clock.timestamp_ns()),
        price="70000.00",
    )
    flush(owner)
    assert cleanup.quantity.as_decimal() == D("0.0001")
    owner.clock.set_time(BASE + 5 * SECOND)
    report(owner, cleanup)
    report(owner, cleanup, kind="TRADE", quantity="0.00010000", total="0.00010000", tid=202)
    assert not owner.bridge.failed
    state = saved(owner)
    assert D(state["view"]["owned_btc"]) == 0
    assert D(state["view"]["expected_totals"]["BTC"]) == 2
    assert len(owner.client.sink.calls) == 2
    owner.clock.set_time(BASE + 6 * SECOND)
    with pytest.raises(SessionLedgerError):
        submit(owner)


def test_changed_duplicate_trade_halts_without_double_settlement(session):
    owner = session
    order = acknowledge(owner)
    owner.clock.set_time(BASE + 3 * SECOND)
    raw = report(owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201)
    changed = msgspec.json.decode(raw)
    changed["n"] = "0.00000001"
    owner.client._handle_user_ws_message(msgspec.json.encode(changed))
    flush(owner)
    assert owner.bridge.failed
    assert D(saved(owner)["view"]["owned_btc"]) == D("0.00004")
    assert len(saved(owner)["view"]["fills"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"s": "ETHUSDT"},
        {"c": "foreign"},
        {"S": "SELL"},
        {"i": 999},
        {"p": "70000.01"},
        {"z": "0.00008"},
        {"n": None},
        {"n": "0.000000001"},
        {"N": "BNB"},
        {"L": "0"},
        {"l": "0.000000001"},
        {"E": 9999999999999},
        {"X": "FILLED"},
    ],
)
def test_invalid_or_missing_stream_evidence_halts_before_fill(session, change):
    owner = session
    order = acknowledge(owner)
    owner.clock.set_time(BASE + 3 * SECOND)
    raw = msgspec.json.decode(
        execution_report(
            owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201
        )
    )
    raw.update(change)
    owner.client._handle_user_ws_message(msgspec.json.encode(raw))
    flush(owner)
    assert owner.bridge.failed
    assert order.filled_qty.as_decimal() == 0


@pytest.mark.parametrize("asset", ["USDT", "BTC"])
def test_positive_supported_fee_settles_then_persistently_halts(session, asset):
    owner = session
    order = acknowledge(owner)
    owner.clock.set_time(BASE + 3 * SECOND)
    raw = msgspec.json.decode(
        execution_report(
            owner, order, kind="TRADE", quantity="0.00010000", total="0.00010000", tid=201
        )
    )
    raw["n"] = "0.00000001"
    raw["N"] = asset
    owner.client._handle_user_ws_message(msgspec.json.encode(raw))
    flush(owner)
    assert "unexpected_nonzero_commission" in saved(owner)["halt_reasons"]
    assert D(saved(owner)["view"]["buy_spent_usdt"]) == D("7.00000001" if asset == "USDT" else "7")
    assert D(saved(owner)["view"]["owned_btc"]) == D("0.00009999" if asset == "BTC" else "0.0001")
    with pytest.raises(SessionLedgerError):
        owner.bridge.require_healthy()


def test_account_update_is_not_applied_to_repair_native_balances(session):
    owner = session
    before = owner.ledger.state["baseline"]
    owner.client._handle_user_ws_message(
        msgspec.json.encode(
            {
                "e": "outboundAccountPosition",
                "E": owner.clock.timestamp_ms(),
                "u": owner.clock.timestamp_ms(),
                "B": [{"a": "USDT", "f": "999", "l": "0"}],
            }
        )
    )
    assert owner.bridge.failed and saved(owner)["baseline"] == before


def test_live_clock_and_network_operations_rejected(session):
    owner = session
    with pytest.raises(SessionLedgerError):
        SessionBridge(SimpleNamespace(clock=LiveClock()), owner.ledger)
    with pytest.raises(SessionLedgerError):
        owner.loop.run_until_complete(
            owner.client.sink.send_request(HttpMethod.POST, "/api/v3/order")
        )
    with pytest.raises(SessionLedgerError):
        owner.loop.run_until_complete(owner.client._connect())
    assert owner.client.sink.calls == []


@pytest.mark.parametrize(
    "method,path",
    [
        (HttpMethod.GET, "/api/v3/order"),
        (HttpMethod.POST, "/api/v3/order/test"),
        (HttpMethod.DELETE, "/api/v3/openOrders"),
        (HttpMethod.POST, "https://api.binance.com/api/v3/order"),
    ],
)
def test_fixture_transport_denies_other_routes(session, method, path):
    with pytest.raises(SessionLedgerError):
        session.loop.run_until_complete(session.client.sink.sign_request(method, path, {}))
    assert session.client.sink.calls == []


def test_queue_delay_invalidates_prepared_filter_freshness(session):
    owner = session
    submit(owner)
    owner.clock.set_time(BASE + 7 * SECOND)
    flush(owner)
    assert owner.client.sink.calls == [] and owner.bridge.failed
    assert saved(owner)["view"]["buy_allowance_consumed"]


def test_duplicate_adapter_command_never_resubmits(session):
    owner = session
    order = submit(owner)
    flush(owner)
    command = SubmitOrder(
        trader_id=order.trader_id,
        strategy_id=order.strategy_id,
        order=order,
        position_id=PositionId(f"session-{SID}"),
        command_id=UUID4(),
        ts_init=owner.clock.timestamp_ns(),
    )
    owner.loop.run_until_complete(owner.client._submit_order(command))
    assert len(owner.client.sink.calls) == 1 and owner.bridge.failed


def test_submitted_crash_gap_native_recovery_preserves_dispatch_and_allowance(session):
    owner = session
    submit(owner)
    flush(owner)
    raw = owner.ledger.path.read_bytes()
    evidence = recovery_evidence(scenario="fill")
    result = recover_session(
        raw,
        evidence,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        evidence_sha256=hashlib.sha256(evidence).hexdigest(),
        now_ns=BASE + 8 * SECOND,
        loop=owner.loop,
    )
    state = read_session(result["checkpoint"])["state"]
    assert state["dispatches"] == saved(owner)["dispatches"]
    assert state["view"]["buy_allowance_consumed"]
    assert D(state["view"]["owned_btc"]) == D("0.0001")


def test_fixed_fixture_checkpoint_cannot_create_new_session(session):
    owner = session
    submit(owner)
    flush(owner)
    path, selected = owner.ledger.path, owner.ledger.sha256
    owner.ledger.close()
    with pytest.raises(SessionLedgerError):
        SessionLedger(path).create(owner, session_id="another01", source=BINDING)
    restored = SessionLedger(path).load(expected_sha256=selected)
    try:
        assert restored.state["view"]["buy_allowance_consumed"]
        assert len(restored.state["dispatches"]) == 1
    finally:
        restored.close()


def test_native_adapter_abrupt_exit_and_fresh_process_recovery():
    result = run_crash_acceptance()
    assert D(result["submit"]["owned_btc"]) == D("0.0001")
    assert D(result["cancel"]["owned_btc"]) == D("0.00008")
    assert result["submit"]["dispatches_preserved"] == 1
    assert result["cancel"]["dispatches_preserved"] == 2


def test_missing_native_event_receipt_times_out_without_http(session, monkeypatch):
    owner = session
    monkeypatch.setattr(owner.engine, "_handle_event_with_tracking", lambda event: None)
    submit(owner)
    owner.loop.run_until_complete(asyncio.sleep(2.1))
    assert owner.bridge.failed and owner.client.sink.calls == []
    assert saved(owner)["view"]["buy_allowance_consumed"]


def test_cancelled_http_task_keeps_uncertain_submit_and_consumed_attempt(session):
    owner = session

    async def pending():
        await asyncio.Event().wait()

    owner.client.sink.before_response = pending
    order = submit(owner)
    flush(owner)
    assert len(owner.client.sink.calls) == 1
    for task in owner.client._tasks:
        if not task.done():
            task.cancel()
    flush(owner)
    assert owner.bridge.failed and order.status.name == "SUBMITTED"
    assert saved(owner)["dispatches"]


def test_fill_disk_failure_preserves_last_complete_checkpoint(session, monkeypatch):
    owner = session
    order = acknowledge(owner)
    previous = owner.ledger.path.read_bytes()

    def fail(_fd):
        raise OSError("fixture disk lost")

    monkeypatch.setattr(os, "fsync", fail)
    owner.clock.set_time(BASE + 3 * SECOND)
    report(owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201)
    assert owner.ledger.path.read_bytes() == previous
    assert order.filled_qty.as_decimal() == D("0.00004")
    assert owner.bridge.failed and owner.ledger._poisoned
    with pytest.raises(SessionLedgerError):
        owner.strategy.request_cancel(order)


def test_strategy_cannot_reenter_during_native_fill_transaction(session, monkeypatch):
    owner = session
    order = acknowledge(owner)
    blocked = []

    def callback(event):
        with pytest.raises(SessionLedgerError, match="transaction"):
            owner.bridge.require_healthy()
        blocked.append(True)

    monkeypatch.setattr(owner.strategy, "on_order_filled", callback)
    owner.clock.set_time(BASE + 3 * SECOND)
    report(owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201)
    assert blocked == [True] and not owner.bridge.failed


def test_back_to_back_trade_callbacks_preserve_cumulative_fills(session):
    owner = session
    order = acknowledge(owner)
    owner.clock.set_time(BASE + 3 * SECOND)
    first = execution_report(
        owner, order, kind="TRADE", quantity="0.00004000", total="0.00004000", tid=201
    )
    second = execution_report(
        owner, order, kind="TRADE", quantity="0.00004000", total="0.00008000", tid=202
    )
    for raw in (first, second, first):
        owner.client._handle_user_ws_message(raw)
    flush(owner)
    assert not owner.bridge.failed
    assert D(saved(owner)["view"]["owned_btc"]) == D("0.00008")
    assert len(saved(owner)["view"]["fills"]) == 2

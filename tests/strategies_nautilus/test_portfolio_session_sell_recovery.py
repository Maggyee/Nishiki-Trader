"""Interrupted owned SELL acceptance with native engines and synthetic signed I/O."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.model.identifiers import ClientOrderId

from apps.strategies_nautilus.portfolio_session_bootstrap import reconcile_collected
from apps.strategies_nautilus.portfolio_session_ledger import SessionLedgerError, read_session
from apps.strategies_nautilus.portfolio_session_runtime import await_terminal, stop_matching
from apps.strategies_nautilus.portfolio_session_transport import (
    SessionJournal,
    SessionLease,
    SessionReadHttpClient,
    collect_session,
    write_private_new,
)
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.runners.portfolio_session_acceptance import BINDING, row, trade
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import (
    drain,
    execution_report,
)
from tests.strategies_nautilus.test_portfolio_session_cancel_recovery import close, restore
from tests.strategies_nautilus.test_portfolio_session_runtime import arm, create_owner, emit, submit
from tests.strategies_nautilus.test_portfolio_session_transport import PEM


def wire_reads(ctx):
    async def request(method, *, url, **kwargs):
        assert method == HttpMethod.GET
        parsed, params = urlsplit(url), parse_qs(urlsplit(url).query)
        ctx.gets.append((parsed.path, params))
        if parsed.path == "/api/v3/account":
            body = ctx.account
        elif parsed.path == "/api/v3/openOrders":
            body = [r for r in ctx.orders.values() if r["status"] in {"NEW", "PARTIALLY_FILLED"}]
        elif parsed.path == "/api/v3/order":
            body = ctx.orders[params["origClientOrderId"][0]]
        else:
            assert parsed.path == "/api/v3/myTrades"
            body = [t for t in ctx.trades if str(t["orderId"]) == params["orderId"][0]]
        return SimpleNamespace(status=200, body=canonical(body))
    ctx.http._client = SimpleNamespace(request=request)


def fresh_reader(root, lease, raw, *, account, orders, trades):
    clock = LiveClock()
    state = read_session(raw)["state"]
    journal = SessionJournal(root / f"reader-{os.getpid()}-{clock.timestamp_ns()}.jsonl", BINDING,
                             clock_ns=clock.timestamp_ns)
    journal.subscribed(8, BINDING)
    http = SessionReadHttpClient(clock, "offline-session-key", None, TESTNET_REST,
                                ed25519_private_key=PEM, client_order_ids=state["intents"])
    ctx = SimpleNamespace(lease=lease, raw=raw, clock=clock, journal=journal, http=http,
        account=account, orders=orders, trades=trades, owner=None, calls=[], gets=[],
        credentials=SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM))
    ctx.oid = next(oid for oid in orders if oid.endswith("-s"))
    ctx.order = orders[ctx.oid]
    wire_reads(ctx)
    return ctx


async def interrupted_sell(root, *, partial=True, missed=False, acknowledged=True):
    owner = create_owner(root)
    buy = submit(owner)
    await drain(owner)
    emit(owner, buy)
    buy_raw = execution_report(owner, buy, kind="TRADE", quantity="0.00010000",
                               total="0.00010000", tid=201)
    owner.client.receive(buy_raw)
    await drain(owner)
    arm(owner)
    # A fresh effective step change leaves original-session dust, never swept.
    owner.rules = replace(owner.rules, quantity_step=D("0.00003"))
    owner.bridge.arm(owner.bridge.admission[0], owner.rules)
    sell = submit(owner, "flat")
    await drain(owner)
    assert sell.quantity.as_decimal() == D("0.00009")
    if acknowledged:
        emit(owner, sell)
        await drain(owner)
    sell_raw = execution_report(owner, sell, kind="TRADE", quantity="0.00003000",
                                total="0.00003000", tid=202)
    if partial and not missed:
        owner.client.receive(sell_raw)
        await drain(owner)
    owner.ledger.halt(owner, "matching_runner_aborted_requires_reconciliation")
    raw = owner.ledger.path.read_bytes()
    assert len(owner.calls) == 2  # Original BUY and owned SELL, both native POSTs.
    await stop_matching(owner)
    owner.journal.close()
    orders, trades = {}, []
    for order, fill_raw, qty, status in (
        (buy, buy_raw, "0.00010000", "FILLED"),
        (sell, sell_raw, "0.00003000" if partial else "0.00000000",
         "PARTIALLY_FILLED" if partial else "NEW"),
    ):
        event = json.loads(fill_raw)
        oid = str(order.client_order_id)
        r = row(status, qty, side=order.side.name, original=str(order.quantity))
        r.update(clientOrderId=oid, time=order.ts_init // 1_000_000, updateTime=event["T"])
        orders[oid] = r
        if D(qty):
            t = trade(event["t"], qty, side=order.side.name)
            t["time"] = event["T"]
            trades.append(t)
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": "BTC", "free": "2.00001000", "locked": "0.00006000" if partial else "0.00009000"},
        {"asset": "USDT", "free": "95.1" if partial else "93", "locked": "0"},
        {"asset": "ETH", "free": "5", "locked": "0"}]}
    ctx = fresh_reader(root, owner.lease, raw, account=account, orders=orders, trades=trades)
    ctx.duplicates = [buy_raw] + ([sell_raw] if partial else [])
    return ctx


def observe(ctx, raw):
    ctx.journal.observe(canonical({"subscriptionId": 8, "event": json.loads(raw)}))


def sell_fill(ctx, *, total="0.00006000", fee="0", deliver=True):
    order = ctx.owner.cache.order(ClientOrderId(ctx.oid))
    quantity = D(total) - D(ctx.order["executedQty"])
    raw = execution_report(ctx.owner, order, kind="TRADE", quantity=f"{quantity:.8f}",
                           total=total, tid=203)
    event = json.loads(raw)
    event["n"] = fee
    raw = canonical(event)
    if deliver:
        observe(ctx, raw)
    t = trade(203, str(quantity), side="SELL")
    t.update(time=event["T"], commission=fee)
    ctx.trades.append(t)
    ctx.order.update(status=event["X"], executedQty=total,
                     cummulativeQuoteQty=str(D(total) * 70000), updateTime=event["T"])
    update_balances(ctx)
    return raw


def update_balances(ctx):
    sold = D(ctx.order["executedQty"])
    locked = D("0.00009") - sold if ctx.order["status"] in {"NEW", "PARTIALLY_FILLED"} else D(0)
    fees = sum((D(t["commission"]) for t in ctx.trades), D(0))
    ctx.account["balances"][0].update(free=str(D("2.0001") - sold - locked), locked=str(locked))
    ctx.account["balances"][1]["free"] = str(D(93) + sold * 70000 - fees)


def terminal_sink(ctx, *, late=True, fee="0", timeout=False):
    async def request(method, *, url, **kwargs):
        assert method == HttpMethod.DELETE
        params = parse_qs(urlsplit(url).query)
        assert params["origClientOrderId"] == [ctx.oid] and params["orderId"] == ["102"]
        state = read_session(ctx.lease.checkpoint_path.read_bytes())["state"]
        assert state["view"]["statuses"][ctx.oid] == "PENDING_CANCEL"
        assert f"cancel:{ctx.oid}" in state["dispatches"]
        assert len(state["dispatches"]) == 3 and state["recovery_cancel_only"]
        ctx.calls.append(method)
        if timeout:
            raise TimeoutError("synthetic uncertain SELL cancel")
        for raw in ctx.duplicates:
            observe(ctx, raw)
        if late:
            sell_fill(ctx, fee=fee)
        order = ctx.owner.cache.order(ClientOrderId(ctx.oid))
        raw = execution_report(ctx.owner, order, kind="CANCELED", total=ctx.order["executedQty"])
        observe(ctx, raw)
        ctx.order.update(status="CANCELED", updateTime=json.loads(raw)["T"])
        update_balances(ctx)
        event = {"e": "outboundAccountPosition", "E": ctx.clock.timestamp_ms(),
                 "u": ctx.clock.timestamp_ms(), "B": [
                     {"a": r["asset"], "f": r["free"], "l": r["locked"]} for r in ctx.account["balances"]]}
        observe(ctx, canonical(event))
        return SimpleNamespace(status=200, body=canonical({"symbol": "BTCUSDT", "orderId": 102,
            "clientOrderId": ctx.oid, "transactTime": ctx.clock.timestamp_ms()}))
    ctx.owner.http._client = SimpleNamespace(request=request)


async def reconcile(ctx):
    raw = ctx.lease.checkpoint_path.read_bytes()
    receipt = await collect_session(ctx.http, ctx.journal, read_session(raw)["state"], hashlib.sha256(raw).hexdigest())
    return reconcile_collected(raw, receipt, ctx.journal, loop=asyncio.get_running_loop())


@pytest.mark.parametrize("partial,missed,acknowledged", [
    (False, False, True), (True, False, True), (True, True, True), (False, False, False),
])
def test_recovered_sell_cancel_keeps_owned_residual_and_original_allowances(tmp_path, partial, missed, acknowledged):
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope", partial=partial, missed=missed, acknowledged=acknowledged)
        try:
            before = read_session(ctx.raw)["state"]
            await restore(ctx)
            owner = ctx.owner
            view = owner.ledger.state["view"]
            assert view["buy_allowance_consumed"] and view["sell_allowance_consumed"]
            assert D(view["expected_locked"]["BTC"]) == D("0.00006" if partial else "0.00009")
            assert owner.ledger.state["deadline_ns"] == before["deadline_ns"]
            terminal_sink(ctx, late=partial)
            assert await await_terminal(owner, owner.cache.order(ClientOrderId(ctx.oid))) == "CANCELED"
            result = await reconcile(ctx)
            assert result["view"] == owner.ledger.state["view"]
            assert D(result["view"]["owned_btc"]) == D("0.00004" if partial else "0.0001")
            assert D(result["view"]["expected_locked"]["BTC"]) == 0
            assert D(result["view"]["expected_totals"]["ETH"]) == 5
            assert len(result["view"]["fills"]) == (3 if partial else 1)
            assert owner.ledger.state["halt_reasons"] == before["halt_reasons"]
            assert ctx.calls == [HttpMethod.DELETE]
            for action in (lambda: owner.strategy.consume(None), lambda: owner.ledger.prepare(owner)):
                with pytest.raises(SessionLedgerError):
                    action()
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_sell_finishes_before_cancel_retains_only_original_dust(tmp_path):
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            sell_fill(ctx, total="0.00009000")
            await drain(ctx.owner)
            order = ctx.owner.cache.order(ClientOrderId(ctx.oid))
            assert await await_terminal(ctx.owner, order) == "FILLED"
            result = await reconcile(ctx)
            assert D(result["view"]["owned_btc"]) == D("0.00001")
            assert ctx.calls == [] and not ctx.owner.ledger.state["cancel_intents"]
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_late_sell_fee_settles_and_halts_without_new_cleanup(tmp_path):
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx, fee="0.00000001")
            with pytest.raises(SessionLedgerError):
                await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
            result = await reconcile(ctx)
            assert D(result["view"]["owned_btc"]) == D("0.00004")
            assert D(result["view"]["sell_proceeds_usdt"]) == D("4.19999999")
            assert "unexpected_nonzero_commission" in read_session(result["checkpoint"])["state"]["halt_reasons"]
            assert ctx.calls == [HttpMethod.DELETE]
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["buy_trade", "sell_trade", "base_lock", "unrelated_balance", "sell_dispatch", "cancel_intent"])
def test_missing_buy_or_sell_evidence_never_publishes_recovery(tmp_path, change):
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            if change in {"buy_trade", "sell_trade"}:
                ctx.trades = [t for t in ctx.trades if t["id"] != (201 if change == "buy_trade" else 202)]
            elif change == "base_lock":
                ctx.account["balances"][0].update(free="2.00002000", locked="0.00005000")
            elif change == "unrelated_balance":
                ctx.account["balances"][2]["free"] = "6"
            else:
                from apps.strategies_nautilus.portfolio_adapter_checkpoint import checkpoint_bytes
                wrapped = read_session(ctx.raw)
                if change == "sell_dispatch":
                    wrapped["state"]["dispatches"].pop(f"submit:{ctx.oid}")
                else:
                    wrapped["state"]["cancel_intents"][ctx.oid] = ctx.clock.timestamp_ns()
                ctx.raw = checkpoint_bytes(wrapped["state"], wrapped["native"])
                ctx.lease.checkpoint_path.write_bytes(ctx.raw)
            with pytest.raises((ValueError, AssertionError)):
                await restore(ctx)
            assert ctx.owner is None and not ctx.calls
            assert ctx.lease.checkpoint_path.read_bytes() == ctx.raw
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_uncertain_sell_cancel_cannot_be_retried_after_recovery(tmp_path):
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx, timeout=True)
            with pytest.raises(SessionLedgerError):
                await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
            raw = ctx.lease.checkpoint_path.read_bytes()
            state = read_session(raw)["state"]
            assert state["view"]["statuses"][ctx.oid] == "PENDING_CANCEL"
            assert f"cancel:{ctx.oid}" in state["dispatches"]
            assert len(state["dispatches"]) == 3
            await stop_matching(ctx.owner)
            ctx.owner = None
            ctx.journal.close()
            again = fresh_reader(ctx.lease.root, ctx.lease, raw, account=ctx.account,
                                 orders=ctx.orders, trades=ctx.trades)
            try:
                # PendingCancel cannot be reconciled back into an executable partial order.
                with pytest.raises(ValueError):
                    await restore(again)
                assert ctx.lease.checkpoint_path.read_bytes() == raw
                assert again.owner is None and not again.calls
            finally:
                again.journal.close()
            assert ctx.calls == [HttpMethod.DELETE]
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["pending_cancel", "dispatch"])
def test_sell_cancel_durability_failure_blocks_adapter_send(tmp_path, monkeypatch, stage):
    from apps.strategies_nautilus.portfolio_session_cancel_recovery import CancelRecoveryLedger
    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx)
            original = CancelRecoveryLedger._persist
            def persist(ledger, owner):
                order = owner.cache.order(ClientOrderId(ctx.oid))
                fail = (order.status.name == "PENDING_CANCEL" if stage == "pending_cancel"
                        else f"cancel:{ctx.oid}" in ledger.state["dispatches"])
                if fail:
                    with monkeypatch.context() as patch:
                        patch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("synthetic disk failure")))
                        return original(ledger, owner)
                return original(ledger, owner)
            monkeypatch.setattr(CancelRecoveryLedger, "_persist", persist)
            with pytest.raises(SessionLedgerError):
                await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
            assert ctx.owner.ledger._poisoned and ctx.calls == []
        finally:
            await close(ctx)
    asyncio.run(scenario())


async def crash_sell_cancel(root):
    ctx = await interrupted_sell(root, missed=True)
    await restore(ctx)
    async def crash(method, *, url, **kwargs):
        assert method == HttpMethod.DELETE
        assert parse_qs(urlsplit(url).query)["origClientOrderId"] == [ctx.oid]
        state = read_session(ctx.lease.checkpoint_path.read_bytes())["state"]
        assert state["view"]["statuses"][ctx.oid] == "PENDING_CANCEL"
        assert f"cancel:{ctx.oid}" in state["dispatches"]
        sell_fill(ctx, deliver=False)  # Venue filled during the now-lost cancellation reply.
        ctx.order.update(status="CANCELED", updateTime=ctx.clock.timestamp_ms())
        update_balances(ctx)
        write_private_new(root / "fixture-sell-venue.json", canonical({
            "account": ctx.account, "orders": ctx.orders, "trades": ctx.trades}))
        os._exit(27)
    ctx.owner.http._client = SimpleNamespace(request=crash)
    await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
    raise AssertionError("crash boundary was not reached")


async def consume_sell_crash(root):
    lease = SessionLease(BINDING, "a" * 64, root=root)
    raw = lease.checkpoint_path.read_bytes()
    venue = json.loads((root / "fixture-sell-venue.json").read_bytes())
    ctx = fresh_reader(root, lease, raw, **venue)
    try:
        result = await restore(ctx)
        assert ctx.owner is None and ctx.calls == []
        assert lease.checkpoint_path.read_bytes() == raw
        before, after = read_session(raw)["state"], read_session(result["checkpoint"])["state"]
        for key in ("intents", "signals", "dispatches", "cancel_intents", "halt_reasons", "deadline_ns"):
            assert before[key] == after[key]
        assert after["view"]["buy_allowance_consumed"] and after["view"]["sell_allowance_consumed"]
        assert after["view"]["open_order_ids"] == []
        assert len(after["view"]["fills"]) == 3
        assert D(after["view"]["owned_btc"]) == D("0.00004")
        assert D(after["view"]["expected_totals"]["BTC"]) == D("2.00004")
        assert D(after["view"]["expected_totals"]["USDT"]) == D("97.2")
        return {"pid": os.getpid(), "view": after["view"], "dispatches": len(after["dispatches"])}
    finally:
        await close(ctx)


def test_sell_cancel_crash_and_two_fresh_process_reconciliations(tmp_path):
    import subprocess
    import sys
    root = tmp_path / "scope"
    prelude = "import asyncio,json,sys; from pathlib import Path; from tests.strategies_nautilus.test_portfolio_session_sell_recovery import "
    producer = subprocess.run([sys.executable, "-c", prelude +
        "crash_sell_cancel; asyncio.run(crash_sell_cancel(Path(sys.argv[1])))", str(root)],
        capture_output=True, text=True, timeout=30)
    assert producer.returncode == 27, producer.stderr
    consumers = []
    for _ in range(2):
        process = subprocess.run([sys.executable, "-c", prelude +
            "consume_sell_crash; print(json.dumps(asyncio.run(consume_sell_crash(Path(sys.argv[1])))))", str(root)],
            capture_output=True, text=True, timeout=30)
        assert process.returncode == 0, process.stderr
        consumers.append(json.loads(process.stdout.splitlines()[-1]))
    assert consumers[0]["pid"] != consumers[1]["pid"]
    assert consumers[0]["view"] == consumers[1]["view"]
    assert consumers[0]["dispatches"] == consumers[1]["dispatches"] == 3

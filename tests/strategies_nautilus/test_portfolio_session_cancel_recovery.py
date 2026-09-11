from __future__ import annotations

import asyncio
import hashlib
import json
import os
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_session_cancel_recovery import (
    CancelRecoveryLedger,
    restore_cancel_runtime,
)
from apps.strategies_nautilus.portfolio_session_ledger import SessionLedgerError, read_session
from apps.strategies_nautilus.portfolio_session_runtime import await_terminal, stop_matching
from apps.strategies_nautilus.portfolio_session_transport import (
    SessionJournal,
    SessionReadHttpClient,
    collect_session,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.runners.portfolio_session_acceptance import BINDING, row, trade
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import (
    drain,
    execution_report,
)
from tests.strategies_nautilus.test_portfolio_session_runtime import create_owner, emit, submit
from tests.strategies_nautilus.test_portfolio_session_transport import PEM


async def interrupted(root, *, partial=True, missed=False, halt=True, acknowledged=True):
    owner = create_owner(root)
    buy = submit(owner)
    await drain(owner)
    if acknowledged:
        emit(owner, buy)
        await drain(owner)
    fill_raw = execution_report(owner, buy, kind="TRADE", quantity="0.00004000",
                                total="0.00004000", tid=201)
    if partial and not missed:
        owner.client.receive(fill_raw)
        await drain(owner)
    if halt:
        owner.ledger.halt(owner, "matching_runner_aborted_requires_reconciliation")
    raw = owner.ledger.path.read_bytes()
    await stop_matching(owner)
    owner.journal.close()
    # Independent fixed account/trade responses; never generated from native balances.
    r = row("PARTIALLY_FILLED" if partial else "NEW", "0.00004000" if partial else "0.00000000")
    now_ms = owner.clock.timestamp_ms()
    r.update(clientOrderId=str(buy.client_order_id), time=buy.ts_init // 1_000_000,
             updateTime=now_ms)
    t = trade(201, "0.00004000")
    t["time"] = json.loads(fill_raw)["T"]
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": "BTC", "free": "2.00004000" if partial else "2", "locked": "0"},
        {"asset": "USDT", "free": "93", "locked": "4.2" if partial else "7"},
        {"asset": "ETH", "free": "5", "locked": "0"}]}
    clock = LiveClock()
    journal = SessionJournal(root / "fresh-stream.jsonl", BINDING, clock_ns=clock.timestamp_ns)
    journal.subscribed(8, BINDING)
    http = SessionReadHttpClient(clock, "offline-session-key", None, TESTNET_REST,
        ed25519_private_key=PEM, client_order_ids=[str(buy.client_order_id)])
    ctx = SimpleNamespace(lease=owner.lease, raw=raw, clock=clock, journal=journal,
        http=http, account=account, order=r, trades=[t] if partial else [], fill_raw=fill_raw,
        owner=None, calls=[], gets=[], failure=None,
        credentials=SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM))

    async def request(method, *, url, **kwargs):
        assert method == HttpMethod.GET
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        ctx.gets.append(parsed.path)
        if parsed.path == "/api/v3/account":
            body = ctx.account
        elif parsed.path == "/api/v3/order":
            assert params["origClientOrderId"] == [ctx.order["clientOrderId"]]
            body = ctx.order
        elif parsed.path == "/api/v3/openOrders":
            body = [ctx.order] if ctx.order["status"] in {"NEW", "PARTIALLY_FILLED"} else []
        else:
            assert parsed.path == "/api/v3/myTrades"
            body = ctx.trades
        return SimpleNamespace(status=200, body=canonical(body))
    http._client = SimpleNamespace(request=request)
    return ctx


async def restore(ctx):
    state = read_session(ctx.raw)["state"]
    ctx.receipt = await collect_session(ctx.http, ctx.journal, state, hashlib.sha256(ctx.raw).hexdigest())
    ctx.owner, result = await restore_cancel_runtime(raw=ctx.raw, receipt=ctx.receipt,
        journal=ctx.journal, lease=ctx.lease, clock=ctx.clock, http=ctx.http, credentials=ctx.credentials)
    return result


async def close(ctx):
    await stop_matching(ctx.owner)
    ctx.journal.close()
    ctx.lease.close()


def terminal_sink(ctx, *, late=False, duplicate=False):
    async def request(method, *, url, **kwargs):
        assert method == HttpMethod.DELETE
        params = parse_qs(urlsplit(url).query)
        state = read_session(ctx.lease.checkpoint_path.read_bytes())["state"]
        oid = ctx.order["clientOrderId"]
        assert params["origClientOrderId"] == [oid] and params["orderId"] == ["101"]
        assert state["view"]["statuses"][oid] == "PENDING_CANCEL"
        assert state["dispatches"][f"cancel:{oid}"]
        assert state["recovery_cancel_only"]
        ctx.calls.append(method)
        if ctx.failure:
            raise ctx.failure
        order = ctx.owner.cache.orders()[0]
        def observe(raw):
            ctx.journal.observe(canonical({"subscriptionId": 8, "event": json.loads(raw)}))
        if duplicate:
            observe(ctx.fill_raw)
        if late:
            raw = execution_report(ctx.owner, order, kind="TRADE", quantity="0.00004000",
                                   total="0.00008000", tid=202)
            observe(raw)
            t = trade(202, "0.00004000")
            t["time"] = json.loads(raw)["T"]
            ctx.trades.append(t)
            ctx.order.update(executedQty="0.00008000", cummulativeQuoteQty="5.6")
            ctx.account["balances"][0]["free"] = "2.00008000"
        raw = execution_report(ctx.owner, order, kind="CANCELED", total=ctx.order["executedQty"])
        observe(raw)
        ctx.order.update(status="CANCELED", updateTime=json.loads(raw)["T"])
        ctx.account["balances"][1].update(free=str(D("100") - D(ctx.order["cummulativeQuoteQty"])), locked="0")
        return SimpleNamespace(status=200, body=canonical({"symbol": "BTCUSDT", "orderId": 101,
            "clientOrderId": oid, "transactTime": ctx.owner.clock.timestamp_ms()}))
    ctx.owner.http._client = SimpleNamespace(request=request)


@pytest.mark.parametrize("partial,missed,acknowledged", [(False, False, True),
    (True, False, True), (True, True, True), (False, False, False)])
def test_restore_original_native_order_cancel_and_late_fill(tmp_path, partial, missed, acknowledged):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope", partial=partial, missed=missed, acknowledged=acknowledged)
        try:
            original = read_session(ctx.raw)["state"]
            result = await restore(ctx)
            state = ctx.owner.ledger.state
            assert state["halt_reasons"] == original["halt_reasons"]
            assert state["dispatches"] == original["dispatches"]
            assert state["view"] == result["view"]
            terminal_sink(ctx, late=partial, duplicate=partial)
            order = ctx.owner.cache.orders()[0]
            await await_terminal(ctx.owner, order)
            assert order.status.name == "CANCELED" and ctx.calls == [HttpMethod.DELETE]
            assert ctx.owner.ledger.state["view"]["owned_btc"] == ("0.00008" if partial else "0")
            assert ctx.owner.ledger.state["halt_reasons"] == original["halt_reasons"]
            raw = ctx.lease.checkpoint_path.read_bytes()
            receipt = await collect_session(ctx.http, ctx.journal, read_session(raw)["state"], hashlib.sha256(raw).hexdigest())
            from apps.strategies_nautilus.portfolio_session_bootstrap import reconcile_collected
            reconciled = reconcile_collected(raw, receipt, ctx.journal, loop=asyncio.get_running_loop())
            assert reconciled["view"] == ctx.owner.ledger.state["view"]
            assert len(reconciled["view"]["fills"]) == (2 if partial else 0)
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["balance", "missing_trade", "foreign_order", "old_cancel", "halt", "dispatch"])
def test_unqualified_recovery_never_publishes_or_sends(tmp_path, change):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            if change == "balance":
                ctx.account["balances"][2]["free"] = "6"
            elif change == "missing_trade":
                ctx.trades = []
            elif change == "foreign_order":
                ctx.order["clientOrderId"] = "foreign"
            else:
                # Preserve a plausible interrupted state with a consumed intent or unknown halt.
                ledger = CancelRecoveryLedger(ctx.lease.checkpoint_path).load(expected_sha256=hashlib.sha256(ctx.raw).hexdigest())
                state = ledger.state
                if change == "old_cancel":
                    state["cancel_intents"][ctx.order["clientOrderId"]] = ctx.clock.timestamp_ns()
                elif change == "halt":
                    state["halt_reasons"].append("unexplained_unrelated_asset_delta")
                else:
                    state["dispatches"] = {}
                from apps.strategies_nautilus.portfolio_adapter_checkpoint import checkpoint_bytes
                wrapped = read_session(ctx.raw)
                updated = checkpoint_bytes(state, wrapped["native"])
                ledger.close()
                ctx.lease.checkpoint_path.write_bytes(updated)
                ctx.raw = updated
            with pytest.raises((StreamError, SessionLedgerError, ValueError, AssertionError)):
                await restore(ctx)
            assert ctx.lease.checkpoint_path.read_bytes() == ctx.raw
            assert ctx.calls == []
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_new_order_paths_are_forbidden_after_recovery(tmp_path):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            await restore(ctx)
            owner = ctx.owner
            for action in (lambda: owner.strategy.consume(None),
                           lambda: owner.ledger.prepare(owner),
                           lambda: owner.engine.execute(None),
                           lambda: owner.bridge.assert_admission(None),
                           lambda: owner.ledger.create(owner)):
                with pytest.raises(SessionLedgerError):
                    action()
            with pytest.raises(StreamError):
                await owner.http.sign_request(HttpMethod.POST, "/api/v3/order", {})
            with pytest.raises(StreamError):
                await owner.http.send_request(HttpMethod.POST, "/api/v3/order", {})
            with pytest.raises(SessionLedgerError):
                await owner.client._submit_order(None)
            assert ctx.calls == []
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["disk", "source", "expired"])
def test_failed_publication_or_expired_receipt_blocks_cancellation(tmp_path, monkeypatch, change):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            if change == "disk":
                from apps.strategies_nautilus import portfolio_session_cancel_recovery as module
                original = module.restore_session_objects
                def fail_after_restore(raw):
                    result = original(raw)
                    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fixture disk failed")))
                    return result
                monkeypatch.setattr(module, "restore_session_objects", fail_after_restore)
                with pytest.raises((OSError, StreamError)):
                    await restore(ctx)
                assert ctx.lease.checkpoint_path.read_bytes() == ctx.raw
            else:
                await restore(ctx)
                if change == "source":
                    ctx.journal.disconnect("fixture lost")
                else:
                    ctx.owner.bridge.receipt.evidence["received_ns"] = 1
                with pytest.raises(StreamError):
                    ctx.owner.strategy.request_cancel(ctx.owner.cache.orders()[0])
            assert ctx.calls == []
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_cancel_timeout_survives_second_recovery_without_retry(tmp_path):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx)
            ctx.failure = TimeoutError("fixture uncertain DELETE response")
            with pytest.raises(SessionLedgerError):
                await await_terminal(ctx.owner, ctx.owner.cache.orders()[0])
            assert ctx.calls == [HttpMethod.DELETE]
            ctx.raw = ctx.lease.checkpoint_path.read_bytes()
            state = read_session(ctx.raw)["state"]
            assert state["dispatches"][f"cancel:{ctx.order['clientOrderId']}"]
            assert state["view"]["statuses"][ctx.order["clientOrderId"]] == "PENDING_CANCEL"
            await stop_matching(ctx.owner)
            ctx.owner = None
            ctx.journal.close()
            ctx.journal = SessionJournal(ctx.lease.root / "again-stream.jsonl", BINDING,
                                         clock_ns=ctx.clock.timestamp_ns)
            ctx.journal.subscribed(9, BINDING)
            with pytest.raises(ValueError):
                await restore(ctx)
            assert ctx.lease.checkpoint_path.read_bytes() == ctx.raw
            assert ctx.calls == [HttpMethod.DELETE]
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_fill_finishes_order_before_cancel_never_sends_delete(tmp_path):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx)
            order = ctx.owner.cache.orders()[0]
            raw = execution_report(ctx.owner, order, kind="TRADE", quantity="0.00006000",
                                   total="0.00010000", tid=202)
            ctx.journal.observe(canonical({"subscriptionId": 8, "event": json.loads(raw)}))
            await drain(ctx.owner)
            assert await await_terminal(ctx.owner, order) == "FILLED"
            assert ctx.calls == []
            assert D(ctx.owner.ledger.state["view"]["owned_btc"]) == D("0.0001")
            assert not ctx.owner.ledger.state["cancel_intents"]
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["checkpoint", "pending_cancel", "dispatch"])
def test_native_checkpoint_failure_blocks_recovery_delete(tmp_path, monkeypatch, stage):
    async def scenario():
        ctx = await interrupted(tmp_path / "scope")
        try:
            original = CancelRecoveryLedger._persist
            def persist(ledger, owner):
                state = ledger.state
                if ((stage == "checkpoint" and state.get("cancel_recovery"))
                    or (stage == "pending_cancel" and owner.cache.orders()[0].status.name == "PENDING_CANCEL")
                    or (stage == "dispatch" and any(k.startswith("cancel:") for k in state.get("dispatches", {})))):
                    # Fail the real atomic writer's fsync, not a fake successful write.
                    with monkeypatch.context() as patch:
                        patch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fixture failed durability")))
                        return original(ledger, owner)
                return original(ledger, owner)
            monkeypatch.setattr(CancelRecoveryLedger, "_persist", persist)
            if stage == "checkpoint":
                with pytest.raises(OSError):
                    await restore(ctx)
                assert ctx.lease.checkpoint_path.read_bytes() == ctx.raw
            else:
                await restore(ctx)
                terminal_sink(ctx)
                with pytest.raises(SessionLedgerError):
                    await await_terminal(ctx.owner, ctx.owner.cache.orders()[0])
                assert ctx.owner.ledger._poisoned
            assert ctx.calls == []
        finally:
            await close(ctx)
    asyncio.run(scenario())


async def crash_at_delete(root):
    """Subprocess-only fixture; no real network or credentials."""
    ctx = await interrupted(root)
    await restore(ctx)
    async def crash(method, **kwargs):
        assert method == HttpMethod.DELETE
        state = read_session(ctx.lease.checkpoint_path.read_bytes())["state"]
        assert state["dispatches"][f"cancel:{ctx.order['clientOrderId']}"]
        ctx.order.update(status="CANCELED", updateTime=ctx.clock.timestamp_ms())
        ctx.account["balances"][1].update(free="97.2", locked="0")
        from apps.strategies_nautilus.portfolio_session_transport import write_private_new
        write_private_new(root / "fixture-venue.json", canonical({"account": ctx.account,
            "order": ctx.order, "trades": ctx.trades}))
        os._exit(27)  # After one durable attempt; no engine/ledger cleanup.
    ctx.owner.http._client = SimpleNamespace(request=crash)
    await await_terminal(ctx.owner, ctx.owner.cache.orders()[0])
    raise AssertionError("crash boundary was not reached")


async def consume_crash(root):
    from apps.strategies_nautilus.portfolio_session_transport import SessionLease, private_read
    lease = SessionLease(BINDING, "a" * 64, root=root)
    raw = private_read(lease.checkpoint_path)
    state = read_session(raw)["state"]
    clock = LiveClock()
    journal = SessionJournal(root / f"consumer-{os.getpid()}.jsonl", BINDING,
                             clock_ns=clock.timestamp_ns)
    journal.subscribed(10, BINDING)
    http = SessionReadHttpClient(clock, "offline-session-key", None, TESTNET_REST,
        ed25519_private_key=PEM, client_order_ids=state["intents"])
    venue = json.loads(private_read(root / "fixture-venue.json"))
    async def request(method, *, url, **kwargs):
        assert method == HttpMethod.GET
        path = urlsplit(url).path
        body = {"/api/v3/account": venue["account"], "/api/v3/openOrders": [],
                "/api/v3/order": venue["order"], "/api/v3/myTrades": venue["trades"]}[path]
        return SimpleNamespace(status=200, body=canonical(body))
    http._client = SimpleNamespace(request=request)
    try:
        receipt = await collect_session(http, journal, state, hashlib.sha256(raw).hexdigest())
        owner, result = await restore_cancel_runtime(raw=raw, receipt=receipt, journal=journal,
            lease=lease, clock=clock, http=http,
            credentials=SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM))
        assert owner is None
        assert private_read(lease.checkpoint_path) == raw
        recovered = read_session(result["checkpoint"])["state"]
        assert recovered["dispatches"] == state["dispatches"]
        assert recovered["halt_reasons"] == state["halt_reasons"]
        return {"pid": os.getpid(), "view": result["view"], "dispatches": len(recovered["dispatches"])}
    finally:
        journal.close()
        lease.close()


def test_abrupt_exit_during_recovered_cancel_then_two_fresh_processes(tmp_path):
    import subprocess
    import sys
    root = tmp_path / "scope"
    prelude = "import asyncio,json,sys; from pathlib import Path; from tests.strategies_nautilus.test_portfolio_session_cancel_recovery import "
    producer = subprocess.run([sys.executable, "-c", prelude + "crash_at_delete; asyncio.run(crash_at_delete(Path(sys.argv[1])))", str(root)],
                              capture_output=True, text=True, timeout=30)
    assert producer.returncode == 27, producer.stderr
    consumers = []
    for _ in range(2):
        process = subprocess.run([sys.executable, "-c", prelude + "consume_crash; print(json.dumps(asyncio.run(consume_crash(Path(sys.argv[1])))))", str(root)],
                                 capture_output=True, text=True, timeout=30)
        assert process.returncode == 0, process.stderr
        consumers.append(json.loads(process.stdout.splitlines()[-1]))
    assert consumers[0]["pid"] != consumers[1]["pid"]
    assert consumers[0]["view"] == consumers[1]["view"]
    assert consumers[0]["dispatches"] == consumers[1]["dispatches"] == 2
    assert D(consumers[0]["view"]["owned_btc"]) == D("0.00004")

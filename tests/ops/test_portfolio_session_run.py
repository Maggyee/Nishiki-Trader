"""Whole one-shot CLI orchestration with native engines and stubbed exchange I/O."""
import asyncio
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.ops import portfolio_session_run as module
from apps.strategies_nautilus import portfolio_session_runtime as runtime
from apps.strategies_nautilus import portfolio_user_stream
from apps.strategies_nautilus.portfolio_session_ledger import SessionLedgerError, read_session
from apps.strategies_nautilus.portfolio_session_transport import SessionLease, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.runners.portfolio_session_acceptance import BINDING, row, trade
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import execution_report
from tests.ops.test_portfolio_testnet_admission import symbol
from tests.ops.test_portfolio_testnet_capabilities import NOW, change_body, zero_fee_capture
from tests.strategies_nautilus.test_portfolio_session_transport import PEM


@pytest.mark.parametrize("buy_qty,sell_qty,cash,fee_side,fee_asset", [
    ("0", "0", "100", None, None),
    ("0.0001", "0.0001", "100", None, None),
    ("0.0001", "0.0001", "10", None, None),
    ("0.00008", "0.00008", "10", None, None),
    ("0.000085", "0.00008", "10", None, None),
    ("0.00004", "0", "10", None, None),
    ("0.000005", "0", "10", None, None),
    ("0.0001", "0.00004", "10", None, None),
    ("0.0001", "0", "10", "BUY", "BTC"),
    ("0.0001", "0", "10", "BUY", "USDT"),
    ("0.0001", "0.0001", "10", "SELL", "USDT"),
])
def test_full_cli_native_matching_and_separate_get_recovery(tmp_path, monkeypatch, buy_qty, sell_qty, cash, fee_side, fee_asset):
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": a, "free": q, "locked": "0"} for a, q in (("BTC", "2"), ("USDT", cash), ("ETH", "5"))]}
    context = SimpleNamespace(owner=None, rows={}, trades=[], sends=[])
    root = tmp_path / "private"
    initial_path = tmp_path / "data/spot-testnet-initial-account-20260911T014024Z.json"
    initial_path.parent.mkdir()
    write_private_new(initial_path, b"{}")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "clean_revision", lambda: "a" * 40)
    monkeypatch.setattr(module, "select_initial_observation", lambda *args: BINDING)
    monkeypatch.setattr(module, "SessionLease", lambda binding, selection: SessionLease(binding, selection, root=root))
    monkeypatch.setattr(module, "load_testnet_ed25519_credentials", lambda *args:
                        SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM))

    async def metadata(clock):
        symbols = [symbol("BTC"), symbol("ETH")]
        for s in symbols:
            s.update(quotePrecision=8, icebergAllowed=True, ocoAllowed=True,
                     quoteOrderQtyMarketAllowed=True, allowTrailingStop=True,
                     isMarginTradingAllowed=False, permissions=["SPOT"])
        body = canonical({"symbols": symbols})
        return canonical({"schema_version": "portfolio.testnet_exchange_info_observation.v1",
            "endpoint": module.TESTNET_REST + "/api/v3/exchangeInfo", "started_ns": clock.timestamp_ns(),
            "received_ns": clock.timestamp_ns(), "response_body": body.decode(),
            "response_sha256": hashlib.sha256(body).hexdigest()})
    monkeypatch.setattr(module, "metadata_capture", metadata)

    async def capabilities(http, initial, selection, clock_ns):
        # Exercise the actual fresh_terms + BUY/SELL gates, including low quote cash.
        capture = zero_fee_capture()
        shift = clock_ns() - NOW - 20_000_000
        for entry in capture["captures"]:
            entry["started_ns"] += shift
            entry["received_ns"] += shift
        for index in (0, -1):
            change_body(capture, index, lambda body: (body.clear(), body.update(account)))
        change_body(capture, 6, lambda body: body.update(closeTime=capture["captures"][6]["received_ns"] // 1_000_000))
        return capture
    monkeypatch.setattr(module, "collect_capabilities", capabilities)

    class Stream:
        def __init__(self, http, *, journal, clock, **kwargs):
            self.journal, self.clock = journal, clock
            async def request(method, *, url, **kw):
                assert method == HttpMethod.GET
                parsed = urlsplit(url)
                params = parse_qs(parsed.query)
                if parsed.path == "/api/v3/account":
                    body = account
                elif parsed.path == "/api/v3/openOrders":
                    body = [r for r in context.rows.values() if r["status"] in {"NEW", "PARTIALLY_FILLED"}]
                elif parsed.path == "/api/v3/order":
                    body = context.rows[params["origClientOrderId"][0]]
                else:
                    body = [t for t in context.trades if str(t["orderId"]) == params["orderId"][0]]
                return SimpleNamespace(status=200, body=canonical(body))
            http._client = SimpleNamespace(request=request)
        async def start(self):
            self.journal.subscribed(7, BINDING)
        async def ping(self):
            self.journal.last_transport_ns = self.clock.timestamp_ns()
        async def disconnect(self):
            self.journal.disconnect("fixture completed")
    monkeypatch.setattr(portfolio_user_stream, "ReadOnlyBinanceUserStream", Stream)

    original = runtime.start_matching
    def start(owner, provider, **kwargs):
        original(owner, provider, **kwargs)
        context.owner = owner
        async def request(method, *, url, **kw):
            context.sends.append(method)
            params = parse_qs(urlsplit(url).query)
            oid = params["newClientOrderId" if method == HttpMethod.POST else "origClientOrderId"][0]
            order = next(o for o in owner.cache.orders() if str(o.client_order_id) == oid)
            def emit(kind, quantity="0.00000000", total="0.00000000", tid=-1):
                event = json.loads(execution_report(owner, order, kind=kind, quantity=quantity, total=total, tid=tid))
                if kind == "TRADE" and order.side.name == fee_side:
                    event.update(n="0.00000001", N=fee_asset)
                owner.bridge.journal.observe(canonical({"subscriptionId": 7, "event": event}))
                return event
            if method == HttpMethod.POST:
                event = emit("NEW")
                r = row("NEW", "0.00000000", side=order.side.name,
                        original=str(order.quantity), price=str(order.price))
                r.update(clientOrderId=oid, time=event["T"], updateTime=event["T"])
                context.rows[oid] = r
                quantity = D(buy_qty if order.side.name == "BUY" else sell_qty)
                if quantity:
                    tid = 201 if order.side.name == "BUY" else 202
                    q = f"{quantity:.8f}"
                    event = emit("TRADE", q, q, tid)
                    r.update(status=event["X"], executedQty=q,
                             cummulativeQuoteQty=str(quantity * order.price.as_decimal()), updateTime=event["T"])
                    t = trade(tid, q, side=order.side.name, price=str(order.price))
                    t.update(time=event["T"], commission=event["n"], commissionAsset=event["N"])
                    context.trades.append(t)
                    direction = 1 if order.side.name == "BUY" else -1
                    for a in account["balances"]:
                        if a["asset"] == "BTC":
                            a["free"] = str(D(a["free"]) + direction * quantity)
                        elif a["asset"] == "USDT":
                            a["free"] = str(D(a["free"]) - direction * quantity * order.price.as_decimal())
                        if order.side.name == fee_side and a["asset"] == fee_asset:
                            a["free"] = str(D(a["free"]) - D("0.00000001"))
            else:
                event = emit("CANCELED", total=context.rows[oid]["executedQty"])
                context.rows[oid].update(status="CANCELED", updateTime=event["T"])
            return SimpleNamespace(status=200, body=canonical({"symbol": "BTCUSDT", "clientOrderId": oid,
                "orderId": context.rows[oid]["orderId"], "transactTime": event["T"]}))
        owner.http._client = SimpleNamespace(request=request)
        return owner
    monkeypatch.setattr(module, "start_matching", start)
    if fee_side:
        with pytest.raises(SessionLedgerError):
            asyncio.run(module.run(SimpleNamespace(execute=True, credentials=tmp_path / "unused")))
        state = read_session((root / "native.json").read_bytes())["state"]
        assert "unexpected_nonzero_commission" in state["halt_reasons"]
        view = state["view"]
        failures = list(root.glob("matching-*-failure.json"))
        assert len(failures) == 1
        assert json.loads(failures[0].read_bytes())["status"] == "halted_no_retry"
    else:
        result = asyncio.run(module.run(SimpleNamespace(execute=True, credentials=tmp_path / "unused")))
        view = result["view"]
        assert result["full_account_reconciled"] and result["account_wide_open_orders"] == 0
        assert result["known_trades"] == int(D(buy_qty) > 0) + int(D(sell_qty) > 0)
        assert result["known_orders"] == 1 + int(D(sell_qty) > 0)
        if D(buy_qty) and not D(sell_qty):
            assert result["cleanup"] == "owned_residual_below_minimum_retained"
    owned = D(buy_qty) - D(sell_qty) - (D("0.00000001") if fee_asset == "BTC" else 0)
    spent = D(buy_qty) * D("69999.99") + (
        D("0.00000001") if fee_side == "BUY" and fee_asset == "USDT" else 0)
    proceeds = D(sell_qty) * 70000 - (D("0.00000001") if fee_side == "SELL" else 0)
    assert D(view["owned_btc"]) == owned
    assert D(view["expected_totals"]["BTC"]) == 2 + owned
    assert D(view["expected_totals"]["ETH"]) == 5
    assert D(view["expected_totals"]["USDT"]) == D(cash) - spent + proceeds
    assert D(view["buy_spent_usdt"]) == spent
    assert D(view["sell_proceeds_usdt"]) == proceeds
    has_sell = D(sell_qty) > 0
    assert view["sell_allowance_consumed"] == has_sell
    sends = list(context.sends)
    assert sends.count(HttpMethod.POST) == 1 + int(has_sell)
    assert sends.count(HttpMethod.DELETE) == int(D(buy_qty) < D("0.0001")) + int(
        has_sell and D(sell_qty) < (D(buy_qty) // D("0.00001")) * D("0.00001"))
    before = (root / "native.json").read_bytes()
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kw: "a" * 40)
    recovered = asyncio.run(module.run(SimpleNamespace(execute=False, credentials=tmp_path / "unused")))
    assert recovered["view"] == view
    if fee_side:
        report_path = Path(recovered["report"])
        recovered_path = report_path.with_name(report_path.name.replace("report.json", "recovered.json"))
        recovered_state = read_session(recovered_path.read_bytes())["state"]
        assert recovered_state["halt_reasons"] == state["halt_reasons"]
    if fee_side or owned:
        terminal = asyncio.run(module.run(SimpleNamespace(
            execute=False, recover_cancel=True, credentials=tmp_path / "unused")))
        assert terminal["cleanup"] == "terminal_session_no_action"
        assert terminal["view"] == view
    assert (root / "native.json").read_bytes() == before
    assert context.sends == sends  # Recovery never submits or cancels.
    with pytest.raises(ValueError):
        asyncio.run(module.run(SimpleNamespace(execute=True, credentials=tmp_path / "unused")))
    assert context.sends == sends


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_recover_cancel_cli_handles_interrupted_native_order(tmp_path, monkeypatch, side):
    from tests.strategies_nautilus.test_portfolio_session_cancel_recovery import (
        interrupted,
        terminal_sink,
    )
    if side == "SELL":
        from tests.strategies_nautilus.test_portfolio_session_sell_recovery import (
            interrupted_sell as interrupted,
        )
        from tests.strategies_nautilus.test_portfolio_session_sell_recovery import (
            terminal_sink,
        )
    ctx = asyncio.run(interrupted(tmp_path / "private"))
    ctx.journal.close()
    ctx.lease.close()
    initial = tmp_path / "data/spot-testnet-initial-account-20260911T014024Z.json"
    initial.parent.mkdir()
    write_private_new(initial, b"{}")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "clean_revision", lambda: "a" * 40)
    monkeypatch.setattr(module, "select_initial_observation", lambda *args: BINDING)
    monkeypatch.setattr(module, "SessionLease", lambda binding, selection:
                        SessionLease(binding, "a" * 64, root=ctx.lease.root))
    monkeypatch.setattr(module, "load_testnet_ed25519_credentials", lambda *args: ctx.credentials)
    original = module.restore_cancel_runtime
    async def restore(**kwargs):
        owner, result = await original(**kwargs)
        if owner is not None:
            ctx.owner, ctx.journal = owner, kwargs["journal"]
            if side == "SELL":
                terminal_sink(ctx, late=True)
            else:
                terminal_sink(ctx, late=True, duplicate=True)
        return owner, result
    monkeypatch.setattr(module, "restore_cancel_runtime", restore)
    class Stream:
        def __init__(self, http, *, journal, clock, **kwargs):
            self.journal, self.clock = journal, clock
            http._client = ctx.http._client
        async def start(self):
            self.journal.subscribed(8, BINDING)
        async def ping(self):
            self.journal.last_transport_ns = self.clock.timestamp_ns()
        async def disconnect(self):
            self.journal.disconnect("fixture finished")
    monkeypatch.setattr(portfolio_user_stream, "ReadOnlyBinanceUserStream", Stream)
    args = SimpleNamespace(execute=False, recover_cancel=True, credentials=tmp_path / "unused")
    result = asyncio.run(module.run(args))
    assert result["run_kind"] == "cancel_only_recovery"
    assert result["cleanup"] == "one_recovered_original_order_cancellation"
    assert result["full_account_reconciled"] and result["account_wide_open_orders"] == 0
    assert D(result["view"]["owned_btc"]) == D("0.00004" if side == "SELL" else "0.00008")
    assert ctx.calls == [HttpMethod.DELETE]
    before = ctx.lease.checkpoint_path.read_bytes()
    again = asyncio.run(module.run(args))
    assert again["cleanup"] == "terminal_session_no_action"
    assert ctx.lease.checkpoint_path.read_bytes() == before
    assert ctx.calls == [HttpMethod.DELETE]

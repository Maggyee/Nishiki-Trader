"""Whole one-shot CLI orchestration with native engines and stubbed exchange I/O."""
import asyncio
import hashlib
import json
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.ops import portfolio_session_run as module
from apps.strategies_nautilus import portfolio_session_runtime as runtime
from apps.strategies_nautilus import portfolio_user_stream
from apps.strategies_nautilus.portfolio_session_transport import SessionLease, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.runners.portfolio_session_acceptance import BINDING, row, rules, trade
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import execution_report
from tests.ops.test_portfolio_testnet_admission import symbol
from tests.strategies_nautilus.test_portfolio_session_transport import PEM


@pytest.mark.parametrize("filled", [False, True])
def test_full_cli_native_matching_and_separate_get_recovery(tmp_path, monkeypatch, filled):
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": a, "free": q, "locked": "0"} for a, q in (("BTC", "2"), ("USDT", "100"), ("ETH", "5"))]}
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

    async def terms(http, initial, selection, clock, journal, path):
        capture = {"captures": [{"path": "/api/v3/ticker/bookTicker", "body": '{"bidPrice":"70000"}'},
                                {"body": json.dumps(account)}]}
        write_private_new(path, canonical(capture))
        return capture, rules(clock.timestamp_ns()), D("70000")
    monkeypatch.setattr(module, "fresh_terms", terms)

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
                    body = [r for r in context.rows.values() if r["status"] == "NEW"]
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
                owner.bridge.journal.observe(canonical({"subscriptionId": 7, "event": event}))
                return event
            if method == HttpMethod.POST:
                event = emit("NEW")
                r = row("NEW", "0.00000000", side=order.side.name)
                r.update(clientOrderId=oid, time=event["T"], updateTime=event["T"])
                context.rows[oid] = r
                if filled:
                    tid = 201 if order.side.name == "BUY" else 202
                    event = emit("TRADE", "0.00010000", "0.00010000", tid)
                    r.update(status="FILLED", executedQty="0.00010000", cummulativeQuoteQty="7", updateTime=event["T"])
                    t = trade(tid, "0.00010000", side=order.side.name)
                    t["time"] = event["T"]
                    context.trades.append(t)
                    for a in account["balances"]:
                        if a["asset"] == "BTC":
                            a["free"] = "2.0001" if order.side.name == "BUY" else "2"
                        elif a["asset"] == "USDT":
                            a["free"] = "93" if order.side.name == "BUY" else "100"
            else:
                event = emit("CANCELED")
                context.rows[oid].update(status="CANCELED", updateTime=event["T"])
            return SimpleNamespace(status=200, body=canonical({"symbol": "BTCUSDT", "clientOrderId": oid,
                "orderId": context.rows[oid]["orderId"], "transactTime": event["T"]}))
        owner.http._client = SimpleNamespace(request=request)
        return owner
    monkeypatch.setattr(module, "start_matching", start)
    result = asyncio.run(module.run(SimpleNamespace(execute=True, credentials=tmp_path / "unused")))
    assert result["full_account_reconciled"] and result["account_wide_open_orders"] == 0
    assert result["known_trades"] == (2 if filled else 0)
    assert result["known_orders"] == (2 if filled else 1)
    assert D(result["view"]["owned_btc"]) == 0
    assert len(context.sends) == 2
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kw: "a" * 40)
    recovered = asyncio.run(module.run(SimpleNamespace(execute=False, credentials=tmp_path / "unused")))
    assert recovered["view"] == result["view"]
    assert len(context.sends) == 2  # Recovery never submits or cancels.
    with pytest.raises(ValueError):
        asyncio.run(module.run(SimpleNamespace(execute=True, credentials=tmp_path / "unused")))
    assert len(context.sends) == 2

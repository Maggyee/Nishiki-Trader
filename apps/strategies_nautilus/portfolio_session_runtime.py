"""Explicit ADR-017 LiveClock matching profile, fixed lease and one-attempt I/O.

No production route, reconnect, resubmission, inferred fill or remote balance patch.
The command path remains SignalEvent -> native Strategy -> RiskEngine -> adapter.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
from urllib.parse import urlencode

from nautilus_trader.common.component import LiveClock
from nautilus_trader.config import LiveExecEngineConfig, RiskEngineConfig
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.live.execution_engine import LiveExecutionEngine
from nautilus_trader.model.events import OrderAccepted
from nautilus_trader.model.identifiers import ClientOrderId, TraderId
from nautilus_trader.risk.engine import RiskEngine

from apps.bridge.signal_event import SignalEvent
from apps.strategies_nautilus.portfolio_session_bootstrap import (
    ReadOnlyRuntimeBridge,
    SessionEventReceiver,
    build_observed_account,
)
from apps.strategies_nautilus.portfolio_session_bridge import SessionBridge, SessionStrategy
from apps.strategies_nautilus.portfolio_session_ledger import (
    MODEL,
    SOURCE,
    SessionLedger,
    SessionLedgerError,
    balances,
)
from apps.strategies_nautilus.portfolio_stream import StreamError
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    Ed25519TestnetReadOnlyHttpClient,
)

RUNTIME_PROFILE = "testnet_liveclock_bounded_matching_v1"


class MatchingRuntimeLedger(SessionLedger):
    def _owner(self, owner):
        if (
            self._fd is None or self._poisoned
            or threading.get_ident() != self._thread
            or not isinstance(owner.clock, LiveClock)
        ):
            raise SessionLedgerError("healthy owning LiveClock matching writer required")
        if self.state is not None and owner.clock.timestamp_ns() < self.state["updated_ns"]:
            raise SessionLedgerError("matching clock regressed")

    def _started_ns(self, owner):
        started = owner.cache.accounts()[0].events[0].ts_event
        if not 0 <= owner.clock.timestamp_ns() - started <= 5_000_000_000:
            raise SessionLedgerError("fresh complete matching baseline required")
        return started

    def _order_time_valid(self, order, now):
        # Native order construction and validation are separate wall-clock reads.
        return self.state["started_ns"] <= order.ts_init <= now <= order.ts_init + 1_000_000_000

    def _persist(self, owner):
        if self.state.get("runtime_profile", RUNTIME_PROFILE) != RUNTIME_PROFILE:
            raise SessionLedgerError("matching cannot convert another runtime profile")
        self.state["runtime_profile"] = RUNTIME_PROFILE
        super()._persist(owner)

    def prepare(self, owner, *, signal, order, rules):
        if self.state.get("recovery_cancel_only"):
            raise SessionLedgerError("recovered cancellation scope cannot admit new orders")
        owner.bridge.assert_admission(rules)
        return super().prepare(owner, signal=signal, order=order, rules=rules)


class MatchingRuntimeBridge(ReadOnlyRuntimeBridge):
    def __init__(self, owner, ledger, lease, journal):
        if type(ledger) is not MatchingRuntimeLedger:
            raise SessionLedgerError("explicit matching ledger required")
        ledger._owner(owner)
        self.owner, self.ledger, self.lease, self.journal = owner, ledger, lease, journal
        self.failed = self.processing = False
        self.waiters = {}
        self.account_updates = []
        self.balance_history = [balances(owner.cache.accounts()[0])]
        self.admission = None

    def require_healthy(self):
        SessionBridge.require_healthy(self)
        try:
            self.lease.assert_active()
            if self.ledger.state["session_id"] != self.lease.state["session_id"]:
                raise StreamError("fixed session changed")
            self.journal.fence()  # Checks the current actual subscription/socket.
        except Exception:
            self.fail("matching_source_or_lease_lost")
            raise

    def arm(self, receipt, rules):
        self.require_healthy()
        self.assert_account_correlated()
        receipt.assert_current(self.journal, self.ledger.sha256)
        self.admission = (receipt, rules)

    def assert_admission(self, rules):
        self.require_healthy()
        if self.admission is None or self.admission[1] is not rules:
            raise SessionLedgerError("current signed reconciliation and exact rules required")
        receipt, _ = self.admission
        receipt.assert_current(self.journal, self.ledger.sha256)
        self.assert_account_correlated()

    def assert_submit_fresh(self):
        self.require_healthy()
        if self.admission is None:
            raise SessionLedgerError("matching admission absent")
        receipt, rules = self.admission
        # Preparation/Submitted changed the local hash, not the external receipt.
        receipt.assert_current(self.journal, receipt.checkpoint_sha256)
        if not 0 <= self.owner.clock.timestamp_ns() - rules.ts_ns <= 5_000_000_000:
            raise SessionLedgerError("effective rules expired before dispatch")


class MatchingRuntimeEngine(LiveExecutionEngine):
    def __init__(self, owner, bridge, loop):
        if not isinstance(owner.clock, LiveClock) or type(bridge) is not MatchingRuntimeBridge:
            raise SessionLedgerError("explicit owning matching runtime required")
        self.bridge = bridge
        super().__init__(loop=loop, msgbus=owner.msgbus, cache=owner.cache, clock=owner.clock,
                         config=LiveExecEngineConfig(reconciliation=False,
                            generate_missing_orders=False, inflight_check_interval_ms=0))

    def register_client(self, client):
        if type(client) is not MatchingBinanceClient or client.bridge is not self.bridge:
            raise SessionLedgerError("only owning bounded matching adapter permitted")
        super().register_client(client)

    def _handle_event_with_tracking(self, event):
        self.bridge.processing = True
        try:
            super()._handle_event_with_tracking(event)
            self.bridge.checkpoint()
        except Exception:
            self.bridge.fail("native_matching_event_or_persistence_failure")
        finally:
            self.bridge.processing = False


class MatchingHttpClient(Ed25519TestnetReadOnlyHttpClient):
    """Only durable native intent can authorize one exact signed POST/DELETE."""
    def __init__(self, bridge, credentials):
        super().__init__(bridge.owner.clock, credentials.api_key, None, TESTNET_REST,
                         ed25519_private_key=credentials.private_key_pem)
        self.bridge = bridge
        self._pending_request = None
        if hashlib.sha256(self.api_key.encode()).hexdigest() != bridge.journal.binding.key_sha256:
            raise StreamError("matching key differs from selected account source")

    async def sign_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        self.bridge.require_healthy()
        params = {k: str(v) for k, v in dict(payload or {}).items()}
        if self.base_url != TESTNET_REST or url_path != "/api/v3/order" or http_method not in (
            HttpMethod.POST, HttpMethod.DELETE
        ) or self._pending_request is not None:
            raise StreamError("only single exact native matching order route permitted")
        kind = "submit" if http_method == HttpMethod.POST else "cancel"
        oid = params.get("newClientOrderId" if kind == "submit" else "origClientOrderId")
        order = self.bridge.owner.cache.order(ClientOrderId(oid)) if oid else None
        if order is None or oid not in self.bridge.ledger.state["intents"]:
            raise StreamError("matching order not owned by fixed session")
        timestamp = params.get("timestamp", "")
        if not timestamp.isdecimal() or not 0 <= (
            self.bridge.owner.clock.timestamp_ms() - int(timestamp)
        ) <= 1000:
            raise StreamError("fresh native request timestamp required")
        expected = {"symbol": "BTCUSDT", "timestamp": timestamp}
        if kind == "submit":
            self.bridge.assert_submit_fresh()
            expected.update(side=order.side.name, type="LIMIT", timeInForce="GTC",
                            quantity=str(order.quantity), price=str(order.price),
                            newClientOrderId=oid, recvWindow="5000")
        else:
            if order.venue_order_id is None:
                raise StreamError("known original venue ID required for cancellation")
            expected.update(origClientOrderId=oid, orderId=str(order.venue_order_id))
        if params != expected:
            raise StreamError("matching parameters differ from exact native intent")
        self.bridge.ledger.record_dispatch(self.bridge.owner, order, kind=kind)
        self.bridge.journal._append("matching_attempt", operation=kind, path=url_path, params=params,
                                    checkpoint_sha256=self.bridge.ledger.sha256)
        self._pending_request = (http_method, url_path, params)
        try:
            return await super().sign_request(http_method, url_path, dict(params), ratelimiter_keys)
        finally:
            self._pending_request = None

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        params = dict(payload or {})
        unsigned = {k: v for k, v in params.items() if k != "signature"}
        if self._pending_request != (http_method, url_path, unsigned) or not params.get("signature"):
            raise StreamError("direct matching transport calls forbidden")
        self._pending_request = None  # Consume before entering native network I/O.
        self.bridge.require_healthy()
        if http_method == HttpMethod.POST:
            self.bridge.assert_submit_fresh()
        try:
            async with asyncio.timeout(10):
                response = await self._client.request(
                    http_method, url=TESTNET_REST + url_path + "?" + urlencode(params),
                    headers=self.headers, body=None, keys=ratelimiter_keys)
            if len(response.body) > 65_536:
                raise StreamError("matching response exceeded archive bound")
            self.bridge.journal._append("matching_response", method=str(http_method),
                path=url_path, status=response.status, raw=response.body.decode(),
                response_sha256=hashlib.sha256(response.body).hexdigest())
            if response.status != 200:
                raise StreamError("matching request rejected; original ID requires reconciliation")
            return response.body
        except BaseException:
            # Never expose a signed URL in a transport exception or native logger.
            raise StreamError("matching outcome uncertain; no automatic retry") from None


class MatchingBinanceClient(SessionEventReceiver):
    """Native serializer and guarded callbacks; unused native WS never connects."""
    def receive(self, raw):
        super().receive(raw)


def start_matching(owner, provider, *, lease, journal, credentials, loop):
    """Activate only after the caller has validated fresh complete bootstrap evidence."""
    lease.activate()
    owner.ledger = MatchingRuntimeLedger(lease.checkpoint_path).create(
        owner, session_id=lease.state["session_id"], source=lease.binding)
    owner.bridge = MatchingRuntimeBridge(owner, owner.ledger, lease, journal)
    owner.engine = MatchingRuntimeEngine(owner, owner.bridge, loop)
    owner.risk = RiskEngine(portfolio=owner.portfolio, msgbus=owner.msgbus,
        cache=owner.cache, clock=owner.clock,
        config=RiskEngineConfig(max_notional_per_order={"BTCUSDT.BINANCE": 10}))
    owner.strategy = SessionStrategy(owner.bridge)
    owner.strategy.register(trader_id=TraderId("BACKTESTER-001"), portfolio=owner.portfolio,
        msgbus=owner.msgbus, cache=owner.cache, clock=owner.clock)
    owner.engine.register_oms_type(owner.strategy)
    owner.http = MatchingHttpClient(owner.bridge, credentials)
    provider.add(owner.cache.instruments()[0])
    owner.client = MatchingBinanceClient(owner, owner.bridge, owner.http, credentials, provider, loop)
    owner.engine.register_client(owner.client)
    journal.execution_handler = owner.client.receive
    journal.account_handler = owner.bridge.account_update
    owner.portfolio.initialize_orders()
    owner.portfolio.initialize_positions()
    owner.risk.start()
    owner.engine.start()
    owner.strategy.start()
    return owner


def matching_account(**kwargs):
    return build_observed_account(**kwargs, profile=RUNTIME_PROFILE)


def fixture_signal(owner, side):
    sid = owner.ledger.state["session_id"]
    return SignalEvent(schema_version="signal.v1", signal_id=f"session:{sid}:{side}",
        source=SOURCE, model_version=MODEL, symbol="BTCUSDT", venue="BINANCE",
        ts_event=owner.clock.timestamp_ns(), horizon="1m", side=side,
        score=0.8 if side == "buy" else 0.0, confidence=0.9, ttl_seconds=60,
        metadata={"engineering_fixture": True})


async def await_terminal(owner, order):
    """One cancellation at native acknowledgement +2s; unknown outcomes halt."""
    loop = asyncio.get_running_loop()
    timeout = loop.time() + 20
    while not order.is_closed:
        owner.bridge.require_healthy()
        if loop.time() >= timeout:
            owner.bridge.fail("order_ack_or_cancel_confirmation_timeout")
            raise StreamError("original order outcome requires signed recovery")
        accepted = [e for e in order.events if isinstance(e, OrderAccepted)]
        if (accepted and owner.clock.timestamp_ns() >= accepted[0].ts_init + 2_000_000_000
                and str(order.client_order_id) not in owner.ledger.state["cancel_intents"]):
            owner.strategy.request_cancel(order)
        await asyncio.sleep(0.01)
    # Wait for queued client HTTP tasks as well as native terminal settlement.
    tasks = list(owner.client._tasks)
    if tasks:
        async with asyncio.timeout(12):
            await asyncio.gather(*tasks)
    owner.bridge.require_healthy()
    owner.bridge.assert_account_correlated()
    return order.status.name


async def stop_matching(owner):
    if owner is None:
        return
    try:
        if hasattr(owner, "client"):
            tasks = list(owner.client._tasks)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if hasattr(owner, "strategy") and owner.strategy.is_running:
            owner.strategy.stop()
        if hasattr(owner, "risk") and owner.risk.is_running:
            owner.risk.stop()
        if hasattr(owner, "engine"):
            if owner.engine.is_running:
                owner.engine.stop()
                await asyncio.gather(owner.engine.get_cmd_queue_task(),
                                     owner.engine.get_evt_queue_task())
            owner.engine.dispose()
    finally:
        if hasattr(owner, "ledger"):
            owner.ledger.close()

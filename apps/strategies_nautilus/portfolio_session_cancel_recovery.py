"""Signed recovery into a cancellation-only native runtime for the fixed ADR-017 scope.

No new BUY/SELL, activation, cancel retry or halt reset. Terminal sessions stay read-only.
"""
from __future__ import annotations

import asyncio
import hashlib
from decimal import Decimal as D
from types import SimpleNamespace

from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.spot.providers import BinanceSpotInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import LiveExecEngineConfig, RiskEngineConfig
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.execution.messages import CancelOrder
from nautilus_trader.live.execution_engine import LiveExecutionEngine
from nautilus_trader.model.enums import OmsType, TradingState
from nautilus_trader.model.events import OrderFilled, OrderSubmitted
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.risk.engine import RiskEngine

from apps.strategies_nautilus.portfolio_session_account import restore_session_cash_account
from apps.strategies_nautilus.portfolio_session_bootstrap import (
    ReadOnlyRuntimeBridge,
    SessionEventReceiver,
    reconcile_collected,
)
from apps.strategies_nautilus.portfolio_session_bridge import SessionStrategy
from apps.strategies_nautilus.portfolio_session_ledger import (
    SessionLedgerError,
    balances,
    native_view,
    read_session,
)
from apps.strategies_nautilus.portfolio_session_recovery import restore_session_objects
from apps.strategies_nautilus.portfolio_session_runtime import (
    RUNTIME_PROFILE,
    MatchingHttpClient,
    MatchingRuntimeEngine,
    MatchingRuntimeLedger,
    stop_matching,
)
from apps.strategies_nautilus.portfolio_session_transport import private_read
from apps.strategies_nautilus.portfolio_stream import StreamError

# These history entries can coexist with a newly verified cancellation. They are
# never removed. Unknown/economic/persistence incidents require separate review.
RECOVERABLE_HALTS = frozenset({
    "submit_attempt_failed_or_unknown",
    "matching_runner_aborted_requires_reconciliation",
    "matching_source_or_lease_lost",
    "order_ack_or_cancel_confirmation_timeout",
    "cancel_recovery_interrupted",
})


class CancelRecoveryLedger(MatchingRuntimeLedger):
    def create(self, *args, **kwargs):
        raise SessionLedgerError("cancel recovery cannot create a session")

    def prepare(self, *args, **kwargs):
        raise SessionLedgerError("cancel recovery cannot prepare new orders")

    def prepare_cancel(self, owner, order):
        owner.bridge.assert_cancel_source()
        super().prepare_cancel(owner, order)

    def record_dispatch(self, owner, order, *, kind):
        if kind != "cancel":
            raise SessionLedgerError("cancel recovery cannot dispatch a new order")
        owner.bridge.assert_cancel_source()
        super().record_dispatch(owner, order, kind=kind)


class CancelRecoveryBridge(ReadOnlyRuntimeBridge):
    def __init__(self, owner, ledger, lease, journal, receipt):
        if type(ledger) is not CancelRecoveryLedger or not isinstance(owner.clock, LiveClock):
            raise SessionLedgerError("explicit LiveClock cancellation recovery required")
        ledger._owner(owner)
        self.owner, self.ledger, self.lease, self.journal = owner, ledger, lease, journal
        self.receipt = receipt
        self.failed = self.processing = False
        self.waiters = {}
        self.account_updates = []
        self.balance_history = [balances(owner.cache.accounts()[0])]

    def require_healthy(self):
        self.ledger._owner(self.owner)
        if (self.failed or self.processing
                or set(self.ledger.state["halt_reasons"]) - RECOVERABLE_HALTS):
            raise SessionLedgerError("cancellation recovery halted or transaction incomplete")
        self.lease.assert_active()
        if self.ledger.state["session_id"] != self.lease.state["session_id"]:
            raise StreamError("fixed cancellation recovery session changed")
        self.journal.fence()

    def assert_cancel_source(self):
        self.require_healthy()
        self.receipt.assert_current(self.journal, self.receipt.checkpoint_sha256)
        if self.ledger.state.get("cancel_recovery", {}).get("evidence_sha256") != self.receipt.evidence_sha256:
            raise StreamError("cancellation recovery receipt changed")
        self.assert_account_correlated()

    def assert_account_correlated(self):
        self._correlate()
        self.require_healthy()
        if self.account_updates:
            raise StreamError("unexplained account updates block recovered cancellation")

    def assert_admission(self, *args, **kwargs):
        raise SessionLedgerError("cancel recovery forbids new order admission")

    assert_submit_fresh = assert_admission


class CancelRecoveryStrategy(SessionStrategy):
    def consume(self, *args, **kwargs):
        raise SessionLedgerError("cancel recovery consumes no new signals")


class CancelRecoveryHttpClient(MatchingHttpClient):
    async def sign_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        if http_method != HttpMethod.DELETE:
            raise StreamError("cancel recovery HTTP permits only original-order DELETE")
        self.bridge.assert_cancel_source()
        return await super().sign_request(http_method, url_path, payload, ratelimiter_keys)

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        if http_method != HttpMethod.DELETE:
            raise StreamError("cancel recovery HTTP permits only original-order DELETE")
        self.bridge.assert_cancel_source()
        return await super().send_request(http_method, url_path, payload, ratelimiter_keys)


class CancelRecoveryClient(SessionEventReceiver):
    _submit_order = SessionEventReceiver._blocked

    def seed_fill_history(self, trades):
        """Preserve cumulative receipt checks/dedup across the process boundary."""
        reported = {t["id"]: t for t in trades}
        if len(reported) != len(trades):
            raise StreamError("ambiguous recovered trade IDs")
        for order in self._cache.orders():
            oid = str(order.client_order_id)
            if order.venue_order_id is None:
                raise StreamError("recovered original venue order ID required")
            venue_id = int(str(order.venue_order_id))
            self._received_venue_ids[oid] = venue_id
            quantity = quote = D(0)
            for event in order.events:
                if not isinstance(event, OrderFilled):
                    continue
                q, p = event.last_qty.as_decimal(), event.last_px.as_decimal()
                quantity += q
                quote += q * p
                tid = int(str(event.trade_id))
                original = reported.get(tid)
                if (original is None or original["orderId"] != venue_id
                        or event.ts_event != millis_to_nanos(original["time"])
                        or (q, p, event.commission.as_decimal(), event.commission.currency.code)
                        != (D(original["qty"]), D(original["price"]),
                            D(original["commission"]), original["commissionAsset"])):
                    raise StreamError("native fill differs from signed original trade")
                identity = (oid, venue_id, q, p, event.commission.as_decimal(),
                            event.commission.currency.code, original["time"],
                            quantity, quote)
                if tid in self._received_trades:
                    raise StreamError("ambiguous recovered Binance fill identity/time")
                self._received_trades[tid] = identity
            self._received_totals[oid] = (quantity, quote)
        if set(self._received_trades) != set(reported):
            raise StreamError("recovered native and signed trade coverage differ")


class CancelRecoveryEngine(MatchingRuntimeEngine):
    def __init__(self, owner, bridge, loop):
        if type(bridge) is not CancelRecoveryBridge or not isinstance(owner.clock, LiveClock):
            raise SessionLedgerError("explicit cancellation-only engine required")
        self.bridge = bridge
        LiveExecutionEngine.__init__(self, loop=loop, msgbus=owner.msgbus,
            cache=owner.cache, clock=owner.clock,
            config=LiveExecEngineConfig(reconciliation=False, generate_missing_orders=False,
                                        inflight_check_interval_ms=0))

    def register_client(self, client):
        if type(client) is not CancelRecoveryClient or client.bridge is not self.bridge:
            raise SessionLedgerError("only the owning cancellation recovery client is allowed")
        LiveExecutionEngine.register_client(self, client)

    def execute(self, command):
        state = self.bridge.ledger.state
        if (type(command) is not CancelOrder
                or str(command.client_order_id) != state["cancel_recovery"]["client_order_id"]
                or command.params):
            raise SessionLedgerError("only the original recovered order cancellation is allowed")
        order = self.bridge.owner.cache.order(command.client_order_id)
        if (order is None or command.instrument_id != order.instrument_id
                or command.venue_order_id != order.venue_order_id
                or command.strategy_id != order.strategy_id):
            raise SessionLedgerError("recovered cancellation command identity changed")
        self.bridge.assert_cancel_source()
        LiveExecutionEngine.execute(self, command)


def cancellation_candidate(state):
    """No-op terminal sessions; never renew already prepared/attempted cancellation."""
    if state.get("runtime_profile") != RUNTIME_PROFILE:
        raise SessionLedgerError("only the existing matching profile can recover cancellation")
    active = state["view"]["open_order_ids"]
    if not active:
        return None
    if len(active) != 1 or set(state["halt_reasons"]) - RECOVERABLE_HALTS:
        raise SessionLedgerError("active cancellation requires complete qualified native state")
    oid = active[0]
    if (state["view"]["statuses"][oid] not in {"ACCEPTED", "PARTIALLY_FILLED"}
            or oid in state["cancel_intents"]
            or f"cancel:{oid}" in state.get("dispatches", {})
            or f"submit:{oid}" not in state.get("dispatches", {})):
        raise SessionLedgerError("original submit receipt and unused cancellation required; no retry")
    return oid


async def restore_cancel_runtime(*, raw, receipt, journal, lease, clock, http, credentials):
    """Reconcile under source fence, then publish native state before any cancellation.

    The fixed checkpoint is changed only for a qualified active order. Source
    changes, disk failure or an old cancel intent fail closed without replenishment.
    """
    selected = hashlib.sha256(raw).hexdigest()
    lease.assert_active()
    before = read_session(raw)["state"]
    if (before.get("runtime_profile") != RUNTIME_PROFILE
            or before["session_id"] != lease.state["session_id"]
            or before["source"] != lease.state["source"]
            or private_read(lease.checkpoint_path) != raw
            or not isinstance(clock, LiveClock) or journal.clock_ns() > clock.timestamp_ns()):
        raise StreamError("fixed matching checkpoint and owning real clock required")
    result = reconcile_collected(raw, receipt, journal, loop=asyncio.get_running_loop())
    candidate_raw = result["checkpoint"]
    state = read_session(candidate_raw)["state"]
    oid = cancellation_candidate(state)
    if oid is None:
        return None, result  # Preserve terminal native.json byte-for-byte.
    ledger = CancelRecoveryLedger(lease.checkpoint_path).load(expected_sha256=selected)
    owner = None
    try:
        _, instrument, account, orders, positions = restore_session_objects(candidate_raw)
        cache = Cache()
        cache.add_instrument(instrument)
        cache.add_account(restore_session_cash_account(account, cache))
        for order, pid in orders:
            cache.add_order(order, position_id=pid)
        for position in positions:
            cache.add_position(position, OmsType.HEDGING)
        cache.build_index()
        owning_order = next(order for order, _ in orders if str(order.client_order_id) == oid)
        if not any(isinstance(event, OrderSubmitted) for event in owning_order.events):
            raise StreamError("recovered original native Submitted event required")
        bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
        owner = SimpleNamespace(cache=cache, clock=clock, msgbus=bus, ledger=ledger)
        owner.portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
        if native_view(state, owner) != result["view"]:
            raise StreamError("restored cancellation account differs from reconciled native state")
        for key in ("session_id", "source", "baseline", "instrument", "started_ns", "deadline_ns",
                    "intents", "signals", "cancel_intents", "dispatches", "halt_reasons"):
            if state.get(key) != before.get(key):
                raise StreamError("recovery changed fixed scope, allowance or historical halt")
        state["recovery_cancel_only"] = True
        state["cancel_recovery"] = {
            "input_sha256": selected, "evidence_sha256": receipt.evidence_sha256,
            "reconciled_sha256": result["output_sha256"], "client_order_id": oid,
            "stream_epoch": receipt.fence.epoch, "ts_ns": clock.timestamp_ns(),
        }
        ledger.state = state
        owner.bridge = CancelRecoveryBridge(owner, ledger, lease, journal, receipt)
        owner.engine = CancelRecoveryEngine(owner, owner.bridge, asyncio.get_running_loop())
        owner.risk = RiskEngine(portfolio=owner.portfolio, msgbus=bus, cache=cache, clock=clock,
                               config=RiskEngineConfig(max_notional_per_order={str(instrument.id): 10}))
        owner.strategy = CancelRecoveryStrategy(owner.bridge)
        owner.strategy.register(trader_id=TraderId("BACKTESTER-001"), portfolio=owner.portfolio,
                                msgbus=bus, cache=cache, clock=clock)
        owner.engine.register_oms_type(owner.strategy)
        owner.http = CancelRecoveryHttpClient(owner.bridge, credentials)
        provider = BinanceSpotInstrumentProvider(client=http, clock=clock,
                                                 environment=BinanceEnvironment.TESTNET)
        provider.add(instrument)
        owner.client = CancelRecoveryClient(owner, owner.bridge, owner.http, credentials,
                                           provider, asyncio.get_running_loop())
        owner.client.seed_fill_history(receipt.evidence["trades"])
        owner.engine.register_client(owner.client)
        owner.portfolio.initialize_orders()
        owner.portfolio.initialize_positions()
        owner.bridge.assert_cancel_source()
        journal._append("cancel_recovery_prepared", **state["cancel_recovery"])
        ledger._persist(owner)  # Atomic replacement under the original file lock.
        receipt.assert_current(journal, selected)
        journal.execution_handler = owner.client.receive
        journal.account_handler = owner.bridge.account_update
        owner.risk.start()
        owner.risk.set_trading_state(TradingState.HALTED)
        owner.engine.start()
        owner.strategy.start()
        return owner, result
    except BaseException:
        await stop_matching(owner)
        ledger.close()
        raise

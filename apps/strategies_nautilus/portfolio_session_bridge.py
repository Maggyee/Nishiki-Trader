"""Offline ADR-017 Strategy -> RiskEngine -> queued native Binance adapter bridge.

Only TestClock and the built-in in-memory HTTP sink are accepted. No credentials,
connections or live-clock bootstrap exist here. Native objects alone settle fills.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from decimal import ROUND_FLOOR
from decimal import Decimal as D

import msgspec
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.config import BinanceExecClientConfig
from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
from nautilus_trader.adapters.binance.spot.execution import BinanceSpotExecutionClient
from nautilus_trader.adapters.binance.spot.providers import BinanceSpotInstrumentProvider
from nautilus_trader.common.component import TestClock
from nautilus_trader.config import LiveExecEngineConfig, StrategyConfig
from nautilus_trader.live.execution_engine import LiveExecutionEngine
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderSubmitted
from nautilus_trader.model.identifiers import ClientOrderId, PositionId
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_session_ledger import (
    INSTRUMENT,
    SessionLedgerError,
    native_view,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST


class SessionBridge:
    """Receipt barrier owned by the same event loop as the native engines."""

    def __init__(self, owner, ledger):
        if not isinstance(owner.clock, TestClock):
            raise SessionLedgerError("offline bridge requires TestClock")
        ledger._owner(owner)
        self.owner, self.ledger = owner, ledger
        self.failed = False
        self.processing = False
        self.waiters = {}

    def require_healthy(self):
        self.ledger._owner(self.owner)
        if self.failed or self.processing or self.ledger.state["halt_reasons"]:
            raise SessionLedgerError("session bridge halted or event transaction in progress")

    def fail(self, reason):
        self.failed = True
        # A poisoned writer must never overwrite its last acknowledged bytes.
        with suppress(Exception):
            self.ledger.halt(self.owner, reason)
        for future in self.waiters.values():
            if not future.done():
                future.set_result(False)

    def checkpoint(self):
        self.ledger.observe(self.owner)
        for (oid, event_type), future in self.waiters.items():
            order = self.owner.cache.order(ClientOrderId(oid))
            if (
                order
                and not future.done()
                and any(type(e).__name__ == event_type for e in order.events)
            ):
                future.set_result(True)

    async def submitted(self, client, order):
        self.require_healthy()
        key = (str(order.client_order_id), "OrderSubmitted")
        if key in self.waiters or any(isinstance(e, OrderSubmitted) for e in order.events):
            raise SessionLedgerError("duplicate submit attempt")
        future = asyncio.get_running_loop().create_future()
        self.waiters[key] = future
        try:
            client.generate_order_submitted(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                ts_event=self.owner.clock.timestamp_ns(),
            )
            # generate_order_submitted only enqueues; native processing + fsync
            # must complete before the adapter may enter its HTTP method.
            if not await asyncio.wait_for(future, timeout=2):
                raise SessionLedgerError("native Submitted persistence failed")
            self.require_healthy()
        finally:
            self.waiters.pop(key, None)


class SessionExecutionEngine(LiveExecutionEngine):
    """Native live queues with post-settlement persistence, strictly offline."""

    def __init__(self, *, bridge, loop, msgbus, cache, clock):
        if not isinstance(clock, TestClock) or clock is not bridge.owner.clock:
            raise SessionLedgerError("offline engine requires owning TestClock")
        self.bridge = bridge
        super().__init__(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=LiveExecEngineConfig(
                reconciliation=False,
                generate_missing_orders=False,
                inflight_check_interval_ms=0,
            ),
        )

    def _handle_event_with_tracking(self, event):
        self.bridge.processing = True
        try:
            super()._handle_event_with_tracking(event)
            # Order callbacks run before all position notifications have finished.
            # Capture only after the entire native transaction has returned.
            self.bridge.checkpoint()
        except Exception:
            self.bridge.fail("native_event_or_persistence_failure")
        finally:
            self.bridge.processing = False

    def register_client(self, client):
        if type(client) is not SessionBinanceFixtureClient or client.bridge is not self.bridge:
            raise SessionLedgerError("only the owning offline session adapter is allowed")
        super().register_client(client)


class SessionStrategy(Strategy):
    """Fixed fixture policy; no live source store or autonomous signal producer."""

    def __init__(self, bridge):
        super().__init__(
            StrategyConfig(
                strategy_id="TESTNET-SESSION",
                order_id_tag="TS",
                oms_type="HEDGING",
            )
        )
        self.bridge = bridge

    def consume(self, signal, *, rules, price):
        self.bridge.require_healthy()
        ledger = self.bridge.ledger
        state = ledger.state
        instrument = self.cache.instrument(INSTRUMENT)
        side = OrderSide.BUY if signal.side == "buy" else OrderSide.SELL
        quantity = D("0.0001")
        if side == OrderSide.SELL:
            owned = D(native_view(state, self)["owned_btc"])
            quantity = (owned / rules.quantity_step).to_integral_value(
                rounding=ROUND_FLOOR,
            ) * rules.quantity_step
        order = self.order_factory.limit(
            instrument_id=INSTRUMENT,
            order_side=side,
            quantity=instrument.make_qty(quantity),
            price=instrument.make_price(price),
            time_in_force=TimeInForce.GTC,
            client_order_id=ClientOrderId(
                f"ts-{state['session_id']}-{'b' if side == OrderSide.BUY else 's'}"
            ),
            tags=[f"signal_id:{signal.signal_id}", f"session_id:{state['session_id']}"],
        )
        ledger.prepare(self, signal=signal, order=order, rules=rules)
        self.submit_order(order, position_id=PositionId(state["position_id"]))
        # Includes a synchronous RiskEngine denial (which never reaches adapter).
        ledger.observe(self)
        return order

    def request_cancel(self, order):
        self.bridge.require_healthy()
        self.bridge.ledger.prepare_cancel(self, order)
        self.cancel_order(order)

    def on_order_pending_cancel(self, event):
        # Strategy creates/applies this event directly, outside ExecEngine.process.
        try:
            self.bridge.checkpoint()
        except Exception:
            self.bridge.fail("pending_cancel_persistence_failure")


class SessionFixtureHttpClient(BinanceHttpClient):
    """In-memory sink behind native HTTP parameter serialization; never signs/dials."""

    def __init__(self, bridge):
        super().__init__(
            clock=bridge.owner.clock,
            api_key="offline-fixture-key",
            api_secret="offline-fixture-secret",
            base_url=TESTNET_REST,
        )
        self.bridge = bridge
        self.calls = []
        self.failure = None
        self.before_response = None

    async def send_request(self, *args, **kwargs):
        raise SessionLedgerError("network transport is unavailable in the offline bridge")

    async def sign_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        self.bridge.require_healthy()
        payload = dict(payload or {})
        method = str(http_method).removeprefix("HttpMethod.")
        if (
            self.base_url != TESTNET_REST
            or url_path != "/api/v3/order"
            or method not in {"POST", "DELETE"}
        ):
            raise SessionLedgerError("unsupported fixture route")
        kind = "submit" if method == "POST" else "cancel"
        oid = payload.get("newClientOrderId" if kind == "submit" else "origClientOrderId")
        order = self.bridge.owner.cache.order(ClientOrderId(oid)) if oid else None
        if order is None:
            raise SessionLedgerError("unknown fixture order")
        expected = {
            "symbol": "BTCUSDT",
            "timestamp": str(self.bridge.owner.clock.timestamp_ms()),
        }
        if kind == "submit":
            expected.update(
                side=order.side.name,
                type="LIMIT",
                timeInForce="GTC",
                quantity=str(order.quantity),
                price=str(order.price),
                newClientOrderId=oid,
                recvWindow="5000",
            )
        else:
            expected.update(origClientOrderId=oid, orderId=str(order.venue_order_id))
        if {k: str(v) for k, v in payload.items()} != expected:
            raise SessionLedgerError("fixture request differs from exact native intent")
        self.bridge.ledger.record_dispatch(self.bridge.owner, order, kind=kind)
        self.calls.append((method, url_path, payload))
        if self.before_response is not None:
            await self.before_response()
        if self.failure is not None:
            raise self.failure
        # Native BinanceOrder response decoder is exercised; the adapter relies
        # on stream reports for acknowledgement and never fabricates a fill here.
        return msgspec.json.encode(
            {
                "symbol": "BTCUSDT",
                "orderId": 101 if order.side == OrderSide.BUY else 102,
                "clientOrderId": oid,
                "transactTime": self.bridge.owner.clock.timestamp_ms(),
            }
        )


class SessionBinanceFixtureClient(BinanceSpotExecutionClient):
    """Native Binance serializer/callbacks with durable single-attempt dispatch."""

    def __init__(self, *, bridge, loop, msgbus):
        self.bridge = bridge
        sink = SessionFixtureHttpClient(bridge)
        provider = BinanceSpotInstrumentProvider(
            client=sink,
            clock=bridge.owner.clock,
            environment=BinanceEnvironment.TESTNET,
        )
        provider.add(bridge.owner.cache.instrument(INSTRUMENT))
        super().__init__(
            loop=loop,
            client=sink,
            msgbus=msgbus,
            cache=bridge.owner.cache,
            clock=bridge.owner.clock,
            instrument_provider=provider,
            base_url_ws="wss://ws-api.testnet.binance.vision/ws-api/v3",
            config=BinanceExecClientConfig(max_retries=0, use_position_ids=True),
            environment=BinanceEnvironment.TESTNET,
            api_key="offline-fixture-key",
            api_secret="offline-fixture-secret",
        )
        self._set_account_id(bridge.owner.cache.accounts()[0].id)
        self.sink = sink
        self._received_trades = {}
        self._received_totals = {}
        self._received_venue_ids = {}

    async def _submit_order(self, command):
        try:
            self.bridge.require_healthy()
            order = command.order
            state = self.bridge.ledger.state
            if (
                str(order.client_order_id) not in state["intents"]
                or order.status.name != "INITIALIZED"
                or command.params
                or str(command.position_id) != state["position_id"]
            ):
                raise SessionLedgerError("unprepared or repeated adapter command")
            native_view(state, self.bridge.owner)
            await self.bridge.submitted(self, order)
            # Use native LIMIT serializer without the common adapter retry and
            # exception-to-Rejected path. Any failure retains uncertain Submitted.
            await self._submit_limit_order(order, None, None, False)
        except BaseException:
            self.bridge.fail("submit_attempt_failed_or_unknown")

    async def _cancel_order(self, command):
        try:
            self.bridge.require_healthy()
            await self._cancel_order_single(
                command.instrument_id,
                command.client_order_id,
                command.venue_order_id,
            )
        except BaseException:
            self.bridge.fail("cancel_attempt_failed_or_unknown")

    async def _blocked(self, *args, **kwargs):
        self.bridge.fail("unsupported_adapter_operation")
        raise SessionLedgerError(
            "offline session forbids connections, queries, batches and amendments"
        )

    _connect = _blocked
    _query_account = _blocked
    _query_order = _blocked
    _submit_order_list = _blocked
    _modify_order = _blocked
    _batch_cancel_orders = _blocked
    _cancel_all_orders = _blocked
    _reconcile_after_resubscribe = _blocked

    def _handle_user_ws_message(self, raw):
        # No native catch-and-log continuation or balance replacement. Only known
        # execution reports enter this increment. Account streams require a later
        # source-bound collector/fence integration.
        try:
            report = self._decoder_spot_order_update.decode(raw)
            oid = report.C if report.x.value == "CANCELED" and report.C else report.c
            order = self._cache.order(ClientOrderId(oid))
            state = self.bridge.ledger.state
            if (
                report.e.value != "executionReport"
                or report.s != "BTCUSDT"
                or order is None
                or oid not in state["intents"]
                or report.S.value != order.side.name
                or report.o.value != "LIMIT"
                or report.f.value != "GTC"
                or D(report.q) != order.quantity.as_decimal()
                or D(report.p) != order.price.as_decimal()
                or (order.venue_order_id is not None and str(report.i) != str(order.venue_order_id))
                or report.i < 0
                or report.i != self._received_venue_ids.get(oid, report.i)
                or not state["started_ns"] <= report.T * 1_000_000 <= self._clock.timestamp_ns()
                or not state["started_ns"] <= report.E * 1_000_000 <= self._clock.timestamp_ns()
                or report.x.value not in {"NEW", "TRADE", "CANCELED", "EXPIRED", "REJECTED"}
                or (
                    report.x.value == "TRADE"
                    and (
                        D(report.l) <= 0
                        or D(report.L) <= 0
                        or report.t < 0
                        or report.n is None
                        or report.N not in {"BTC", "USDT"}
                        or D(report.n) < 0
                    )
                )
            ):
                raise SessionLedgerError("unsupported or conflicting session execution report")
            self._validate_received_fill(report, order)
            self._received_venue_ids[oid] = report.i
            super()._handle_execution_report(raw)
        except Exception:
            self.bridge.fail("execution_report_invalid_or_incomplete")

    def _validate_received_fill(self, report, order):
        """Reject missing/conflicting stream history before native dedup can hide it."""
        oid = str(order.client_order_id)
        quantity, quote = self._received_totals.get(oid, (D(0), D(0)))
        cumulative, cumulative_quote = D(report.z), D(report.Z)
        if not cumulative.is_finite() or not cumulative_quote.is_finite():
            raise SessionLedgerError("nonfinite stream cumulative quantities")
        if report.x.value == "TRADE":
            q, p, fee = D(report.l), D(report.L), D(report.n)
            instrument = self._cache.instrument(INSTRUMENT)
            if (
                not all(v.is_finite() for v in (q, p, fee))
                or q % instrument.size_increment.as_decimal()
                or p % instrument.price_increment.as_decimal()
                or fee % D("0.00000001")
                or D(report.Y) != q * p
                or (report.S.value == "SELL" and report.N != "USDT")
            ):
                raise SessionLedgerError("invalid stream fill precision, notional or fee")
            identity = (oid, report.i, q, p, fee, report.N, report.T, cumulative, cumulative_quote)
            previous = self._received_trades.get(report.t)
            if previous is not None:
                if identity != previous:
                    raise SessionLedgerError("historical stream trade changed")
                return  # Native engine still receives and deduplicates exact fills.
            quantity += q
            quote += q * p
            if report.X.value != (
                "FILLED" if quantity == order.quantity.as_decimal() else "PARTIALLY_FILLED"
            ):
                raise SessionLedgerError("stream fill status differs from complete history")
            self._received_trades[report.t] = identity
        elif report.X.value != report.x.value:
            raise SessionLedgerError("stream status differs from execution type")
        if (
            cumulative != quantity
            or cumulative_quote != quote
            or quantity > order.quantity.as_decimal()
        ):
            raise SessionLedgerError("stream cumulative fills missing or conflicting")
        self._received_totals[oid] = (quantity, quote)

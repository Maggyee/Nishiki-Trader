"""Synthetic-only Nautilus portfolio acceptance strategy.

Nautilus owns orders, fills, positions and balances. The checkpoint holds intent,
audit and risk state, plus optional native events for detached native restoration.
It never derives or applies replacement fills or maintains a second ledger.
Not imported by paper/testnet/live runners; only fixture identities are accepted.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from dataclasses import asdict
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from nautilus_trader.common.component import TestClock
from nautilus_trader.model.currencies import BTC, USDT
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, PositionId
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization
from apps.ops.portfolio_execution_plan import SLEEVES, preflight_limits
from apps.strategies_nautilus.portfolio_inventory import EXIT_POLICIES, size_exit
from apps.strategies_nautilus.portfolio_preflight import (
    AccountSnapshot,
    AdmissionCandidate,
    InstrumentRules,
    PendingOrder,
    ProposedOrder,
    select_funded_batch,
)
from apps.strategies_nautilus.portfolio_risk_policy import POLICY_ID
from apps.strategies_nautilus.signal_consumer import ConsumerConfig, evaluate

D = Decimal
INSTRUMENT = InstrumentId.from_str("BTCUSDT.BINANCE")
MODEL = "portfolio-lifecycle-fixture-v1"
IDENTITIES = {f"rule_fixture_{s}": s for s in SLEEVES}
DAY_NS = 86_400_000_000_000
CHECKPOINT_VERSION = "portfolio.simulation_checkpoint.v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class SimulationBlocked(RuntimeError):
    pass


class PortfolioSimulationStrategy(Strategy):
    """A single-writer, non-yielding admission section on Nautilus TestClock.

    Every selected native order is durably PREPARED before the first submit.
    Until native cache acknowledges its state it consumes the full reservation.
    Exceptions halt admission and preserve all uncertain reservations. A missing
    native cache fails closed. The separate recovery gate may restore native
    events into a fresh cache after account verification; intents alone cannot.
    """

    def __init__(
        self,
        checkpoint: Path,
        *,
        fee_mode: str = "quote",
        exit_policy: str = "exact_v1",
        persist_native: bool = False,
    ):
        if fee_mode not in {"quote", "received_asset"}:
            raise ValueError("unknown synthetic fee mode")
        if exit_policy not in EXIT_POLICIES:
            raise ValueError("unknown offline exit policy")
        self.fee_mode = fee_mode
        self.exit_policy = exit_policy
        self.persist_native = persist_native
        self.restored_checkpoint_bytes = None
        self.recovery_validator = None
        super().__init__(
            StrategyConfig(
                strategy_id="PORTFOLIO-FIXTURE", order_id_tag="PF", oms_type=OmsType.HEDGING
            )
        )
        self.checkpoint = checkpoint
        self.limits = preflight_limits()
        self.quote = None
        self._admitting = False
        self._owner_thread = None
        self._lock_file = None
        self._restored = False
        self._restored_order_ids = frozenset()
        self.state_data = {
            "version": CHECKPOINT_VERSION,
            "fingerprint": self._fingerprint(),
            "orders": {},
            "signals": {},
            "watermarks": {},
            "events": [],
            "day_ns": None,
            "day_open": None,
            "peak": None,
            "risk_latched": False,
            "halt_reason": None,
        }
        self.auth = ConsumerConfig(
            "BINANCE", Authorization(frozenset(IDENTITIES), frozenset({MODEL})), 0.5
        )

    def _fingerprint(self):
        return hashlib.sha256(
            canonical(
                {
                    "identities": IDENTITIES,
                    "model": MODEL,
                    "risk_policy_id": POLICY_ID,
                    "instrument": str(INSTRUMENT),
                    "limits": {k: str(v) for k, v in asdict(self.limits).items()},
                    "limit_price": "100000",
                    "fee_bound": "0.0015",
                    "fee_mode": self.fee_mode,
                    "exit_policy": self.exit_policy,
                    **({"native_recovery": "native_uuid_v1"} if self.persist_native else {}),
                }
            )
        ).hexdigest()

    def on_start(self):
        if not isinstance(self.clock, TestClock):
            raise SimulationBlocked("synthetic strategy requires Nautilus TestClock")
        self._owner_thread = threading.get_ident()
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = self.checkpoint.with_suffix(".lock").open("a+b")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.checkpoint.exists():
                raw = self.checkpoint.read_bytes()
                if (
                    self.restored_checkpoint_bytes is not None
                    and raw != self.restored_checkpoint_bytes
                ):
                    raise SimulationBlocked("checkpoint changed during native restore")
                self.on_load({"checkpoint": raw})
            self._reconcile_orders()
            instrument = self.cache.instrument(INSTRUMENT)
            expected_native_fee = D("0") if self.fee_mode == "received_asset" else D("0.0015")
            if (
                instrument is None
                or instrument.maker_fee != expected_native_fee
                or instrument.taker_fee != expected_native_fee
                or (
                    self.fee_mode == "received_asset" and instrument.size_precision != BTC.precision
                )
            ):
                raise SimulationBlocked("synthetic instrument fee configuration mismatch")
            account = self.portfolio.account(INSTRUMENT.venue)
            if account is None or account.type != AccountType.CASH:
                raise SimulationBlocked("dedicated simulated CASH account required")
            if not self._restored and (
                self.cache.orders()
                or self.cache.positions_open()
                or account.balance_total(USDT).as_decimal() != D("500")
                or (account.balance_total(BTC) and account.balance_total(BTC).as_decimal() != 0)
            ):
                raise SimulationBlocked("new acceptance session must start flat with 500 USDT")
            if self.recovery_validator is not None:
                self.recovery_validator(self)
            self.subscribe_quote_ticks(INSTRUMENT)
            self._persist()
        except Exception:
            self._release_lock()
            raise

    def on_stop(self):
        # Preserve outstanding native orders for strategy-restart acceptance.
        self.unsubscribe_quote_ticks(INSTRUMENT)
        self._release_lock()

    def _release_lock(self):
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    def on_save(self):
        raw = canonical(self.state_data)
        wrapped = {"state": self.state_data, "sha256": hashlib.sha256(raw).hexdigest()}
        if self.persist_native:
            from apps.strategies_nautilus.portfolio_recovery import capture_native

            wrapped["native"] = capture_native(self)
            wrapped["native_sha256"] = hashlib.sha256(canonical(wrapped["native"])).hexdigest()
            wrapped["generation_sha256"] = hashlib.sha256(
                canonical({"state": wrapped["state"], "native": wrapped["native"]})
            ).hexdigest()
        return {"checkpoint": canonical(wrapped)}

    def on_load(self, state):
        wrapped = json.loads(state["checkpoint"])
        if self.persist_native:
            from apps.strategies_nautilus.portfolio_recovery import verify_checkpoint

            verify_checkpoint(state["checkpoint"])
        saved = wrapped["state"]
        if (
            hashlib.sha256(canonical(saved)).hexdigest() != wrapped["sha256"]
            or saved["version"] != CHECKPOINT_VERSION
            or saved["fingerprint"] != self._fingerprint()
            or set(saved) != set(self.state_data)
            or type(saved["risk_latched"]) is not bool
        ):
            raise SimulationBlocked("checkpoint integrity/config mismatch")
        self.state_data = saved
        self._restored = True
        self._restored_order_ids = frozenset(saved["orders"])

    def _persist(self):
        if self._lock_file is None:
            raise SimulationBlocked("checkpoint writer lock not held")
        raw = self.on_save()["checkpoint"]
        # Atomic durable replace, never truncate the last valid checkpoint.
        with tempfile.NamedTemporaryFile(dir=self.checkpoint.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, self.checkpoint)
            fd = os.open(self.checkpoint.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _audit(self, kind, **fields):
        self.state_data["events"].append(
            {
                "seq": len(self.state_data["events"]),
                "ts_ns": self.clock.timestamp_ns(),
                "kind": kind,
                **fields,
            }
        )

    def _reconcile_orders(self):
        known = self.state_data["orders"]
        for order in self.cache.orders():
            oid = str(order.client_order_id)
            if (
                oid not in known
                or order.instrument_id != INSTRUMENT
                or order.strategy_id != self.id
            ):
                raise SimulationBlocked("unknown native order / account contamination")
            expected = known[oid]
            if (
                str(order.quantity) != expected["quantity"]
                or str(order.price) != expected["price"]
                or order.side.name != expected["side"]
                or order.tags
                != [f"signal_id:{expected['signal_id']}", f"sleeve:{expected['sleeve']}"]
                or str(self.cache.position_id(order.client_order_id)) != expected["position_id"]
            ):
                raise SimulationBlocked("native order differs from prepared intent")
        if self._restored:
            for oid in self._restored_order_ids:
                if self.cache.order(ClientOrderId(oid)) is None:
                    raise SimulationBlocked(
                        "restored intent missing from native cache; do not resubmit"
                    )

    def _assert_owner(self):
        if (
            threading.get_ident() != self._owner_thread
            or not isinstance(self.clock, TestClock)
            or self._lock_file is None
        ):
            raise SimulationBlocked(
                "admission must run on owning simulation thread with writer lock"
            )

    def snapshot(self):
        self._assert_owner()
        if self.quote is None:
            raise SimulationBlocked("no current native quote")
        now = self.clock.timestamp_ns()
        if not 0 <= now - self.quote.ts_event <= self.limits.max_age_ns:
            raise SimulationBlocked("stale or future native quote")
        self._reconcile_orders()
        account = self.portfolio.account(INSTRUMENT.venue)
        if set(account.balances_total()) - {BTC, USDT}:
            raise SimulationBlocked("unexpected account assets")
        total_quote = account.balance_total(USDT).as_decimal()
        total_base = account.balance_total(BTC)
        total_base = total_base.as_decimal() if total_base else D("0")
        holdings = dict.fromkeys(SLEEVES, D("0"))
        pos_sleeves = {v["position_id"]: v["sleeve"] for v in self.state_data["orders"].values()}
        for pos in self.cache.positions_open():
            if str(pos.id) not in pos_sleeves or pos.instrument_id != INSTRUMENT or not pos.is_long:
                raise SimulationBlocked("unattributed or short native position")
            holdings[pos_sleeves[str(pos.id)]] += pos.quantity.as_decimal()
        if self.fee_mode == "received_asset":
            self._check_native_net_inventory(holdings)
        if sum(holdings.values(), D("0")) != total_base:
            raise SimulationBlocked("native positions and settled BTC disagree")
        pending = []
        for oid, intent in self.state_data["orders"].items():
            order = self.cache.order(ClientOrderId(oid))
            if order is None:
                # Write-ahead intent not yet visible to native cache.
                remaining, status = D(intent["quantity"]), "submitted"
            else:
                remaining = order.leaves_qty.as_decimal()
                status = {
                    "INITIALIZED": "submitted",
                    "SUBMITTED": "submitted",
                    "ACCEPTED": "accepted",
                    "PARTIALLY_FILLED": "partially_filled",
                    "PENDING_CANCEL": "pending_cancel",
                    "FILLED": "filled",
                    "CANCELED": "canceled",
                    "REJECTED": "rejected",
                    "DENIED": "rejected",
                    "EXPIRED": "expired",
                }.get(order.status.name)
                if status is None:
                    raise SimulationBlocked("unknown native order state")
                if order.is_closed:
                    remaining = D("0")  # native terminal acknowledgement, not cancel request
            pending.append(
                PendingOrder(
                    oid, intent["sleeve"], intent["side"], remaining, D(intent["price"]), status
                )
            )
        mark = self.quote.bid_price.as_decimal()
        equity = total_quote + total_base * mark
        day = now // DAY_NS * DAY_NS
        if self.state_data["day_ns"] != day:
            self.state_data.update(day_ns=day, day_open=str(equity))
        peak = max(D(self.state_data["peak"] or equity), equity)
        self.state_data["peak"] = str(peak)
        if (
            D(self.state_data["day_open"]) - equity
            >= self.limits.effective_daily_loss(D(self.state_data["day_open"]))
            or peak - equity >= self.limits.drawdown_loss
        ):
            self.state_data["risk_latched"] = True
        free_base = account.balance_free(BTC)
        return AccountSnapshot(
            str(INSTRUMENT),
            self.quote.ts_event,
            day,
            True,
            total_quote,
            account.balance_free(USDT).as_decimal(),
            total_base,
            free_base.as_decimal() if free_base else D("0"),
            tuple(holdings.items()),
            tuple(pending),
            frozenset(self.state_data["orders"]),
            mark,
            D(self.state_data["day_open"]),
            peak,
            self.state_data["risk_latched"],
        )

    def _check_native_net_inventory(self, holdings):
        # Independent reconciliation of native fill evidence, not another ledger:
        # never apply balances/positions or persist a derived inventory here.
        expected = dict.fromkeys(SLEEVES, D("0"))
        instrument = self.cache.instrument(INSTRUMENT)
        quantum = D("0.00000001")
        for oid, intent in self.state_data["orders"].items():
            order = self.cache.order(ClientOrderId(oid))
            if order is None:
                continue  # full prepared reservation still applies
            seen, filled = set(), D("0")
            for event in order.events:
                if not isinstance(event, OrderFilled):
                    continue
                key = str(event.trade_id)
                if key in seen:
                    raise SimulationBlocked("duplicate native trade evidence")
                seen.add(key)
                quantity = event.last_qty.as_decimal()
                if quantity <= 0 or quantity % instrument.size_increment.as_decimal():
                    raise SimulationBlocked("native fill outside supported quantity grid")
                filled += quantity
                fee = event.commission.as_decimal()
                currency = event.commission.currency
                is_buy = event.order_side == OrderSide.BUY
                if fee < 0 or currency != (BTC if is_buy else USDT):
                    raise SimulationBlocked("unexpected native commission currency/value")
                amount = quantity if is_buy else quantity * event.last_px.as_decimal()
                ceiling = (amount * D("0.0015") / quantum).to_integral_value(
                    rounding=ROUND_CEILING
                ) * quantum
                if fee > ceiling or (is_buy and (fee > quantity or fee % quantum)):
                    raise SimulationBlocked("native commission exceeds supported fee bound")
                expected[intent["sleeve"]] += quantity if is_buy else -quantity
                if is_buy:
                    expected[intent["sleeve"]] -= fee
            if filled != order.filled_qty.as_decimal():
                raise SimulationBlocked("native filled quantity lacks complete event evidence")
        if expected != holdings:
            raise SimulationBlocked("native net inventory and fill commissions disagree")

    def inventory_diagnostics(self):
        from apps.strategies_nautilus.portfolio_inventory import inventory_diagnostics

        return inventory_diagnostics(self.snapshot(), self.rules(), limit_price=D("100000"))

    def rules(self):
        instrument = self.cache.instrument(INSTRUMENT)
        return InstrumentRules(
            str(INSTRUMENT),
            self.quote.ts_event,
            instrument.min_quantity.as_decimal(),
            instrument.max_quantity.as_decimal(),
            instrument.size_increment.as_decimal(),
            instrument.min_price.as_decimal(),
            instrument.max_price.as_decimal(),
            instrument.price_increment.as_decimal(),
            instrument.min_notional.as_decimal(),
            D("100000"),
            D("0.0015"),
            buy_fee_currency="BTC" if self.fee_mode == "received_asset" else "USDT",
            base_fee_quantum=D("0.00000001") if self.fee_mode == "received_asset" else None,
        )

    def on_quote_tick(self, quote):
        self.quote = quote
        try:
            self.snapshot()  # update and persist risk even with no signals
            self._persist()
        except Exception as exc:
            self.state_data["halt_reason"] = str(exc)
            self._persist()
            raise

    def process_signals(self, signals: tuple[SignalEvent, ...]):
        self._assert_owner()
        if self._admitting:
            raise SimulationBlocked("reentrant admission blocked")
        self._admitting = True
        try:
            if self.state_data["halt_reason"]:
                raise SimulationBlocked(self.state_data["halt_reason"])
            snapshot = self.snapshot()
            rules = self.rules()
            now = self.clock.timestamp_ns()
            holdings = dict(snapshot.holdings)
            candidates = []
            # Revalidate at the boundary, including model_construct/model_copy inputs.
            signals = tuple(SignalEvent.model_validate(s.model_dump()) for s in signals)
            if len({s.signal_id for s in signals}) != len(signals):
                raise SimulationBlocked("ambiguous duplicate signal IDs in batch")
            effective = {}
            for signal in sorted(signals, key=lambda s: (s.ts_event, s.signal_id)):
                if signal.signal_id in self.state_data["signals"]:
                    self._audit("duplicate_signal", signal_id=signal.signal_id)
                    continue
                row = {
                    "signal": json.loads(signal.model_dump_json()),
                    "decision": "skipped",
                    "reasons": [],
                    "order_ids": [],
                }
                self.state_data["signals"][signal.signal_id] = row
                outcome = evaluate(signal, self.auth, now_ns=now)
                sleeve = IDENTITIES.get(signal.source)
                if outcome.decision != "accept":
                    row["reasons"] = [outcome.decision]
                elif signal.symbol != "BTCUSDT" or signal.side not in {"buy", "flat"}:
                    row["reasons"] = ["unsupported_instrument_or_direction"]
                elif (
                    signal.ts_event > now
                    or now >= signal.ts_event + signal.ttl_seconds * 1_000_000_000
                ):
                    row["reasons"] = ["future_or_expired_signal"]
                elif signal.ts_event <= self.state_data["watermarks"].get(sleeve, 0):
                    row["reasons"] = ["superseded_or_out_of_order_signal"]
                else:
                    effective.setdefault(sleeve, []).append(signal)
            for sleeve, eligible in effective.items():
                latest_ns = max(s.ts_event for s in eligible)
                latest = [s for s in eligible if s.ts_event == latest_ns]
                self.state_data["watermarks"][sleeve] = latest_ns
                for signal in eligible:
                    row = self.state_data["signals"][signal.signal_id]
                    if signal.ts_event < latest_ns:
                        row["reasons"] = ["superseded_or_out_of_order_signal"]
                    elif len(latest) != 1:
                        row["reasons"] = ["ambiguous_same_time_sleeve_signals"]
                if len(latest) != 1:
                    continue
                signal = latest[0]
                row = self.state_data["signals"][signal.signal_id]
                quantity = self.limits.sleeve_quantity if signal.side == "buy" else holdings[sleeve]
                if signal.side == "flat":
                    sizing = size_exit(quantity, rules.quantity_step, policy=self.exit_policy)
                    row["exit_sizing"] = {k: str(v) for k, v in asdict(sizing).items()}
                    row["exit_sizing"]["prepared_quantity"] = "0"
                    quantity = sizing.proposed_quantity
                if quantity == 0:
                    row["reasons"] = ["residual_below_step" if holdings[sleeve] else "already_flat"]
                    continue
                oid = "PF-" + hashlib.sha256(signal.signal_id.encode()).hexdigest()[:24]
                candidates.append(
                    AdmissionCandidate(
                        ProposedOrder(
                            oid,
                            sleeve,
                            "BUY" if signal.side == "buy" else "SELL",
                            quantity,
                            D("100000"),
                        ),
                        signal.signal_id,
                        signal.ts_event,
                        signal.ts_event + signal.ttl_seconds * 1_000_000_000,
                    )
                )
            result = select_funded_batch(
                snapshot,
                rules,
                self.limits,
                tuple(candidates),
                now_ns=now,
                allow_base_buy_fees=self.fee_mode == "received_asset",
            )
            for skipped in result.skipped:
                self.state_data["signals"][skipped.signal_id]["reasons"] = list(skipped.reasons)
            native = []
            for candidate in result.selected:
                p = candidate.order
                existing = [
                    pos
                    for pos in self.cache.positions_open()
                    if any(
                        v["position_id"] == str(pos.id) and v["sleeve"] == p.sleeve
                        for v in self.state_data["orders"].values()
                    )
                ]
                position_id = existing[0].id if existing else PositionId(f"{p.sleeve}-{p.order_id}")
                instrument = self.cache.instrument(INSTRUMENT)
                order = self.order_factory.limit(
                    INSTRUMENT,
                    OrderSide.BUY if p.side == "BUY" else OrderSide.SELL,
                    instrument.make_qty(p.quantity),
                    instrument.make_price(p.limit_price),
                    client_order_id=ClientOrderId(p.order_id),
                    tags=[f"signal_id:{candidate.signal_id}", f"sleeve:{p.sleeve}"],
                )
                self.state_data["orders"][p.order_id] = {
                    "sleeve": p.sleeve,
                    "signal_id": candidate.signal_id,
                    "quantity": str(order.quantity),
                    "price": str(order.price),
                    "side": p.side,
                    "position_id": str(position_id),
                }
                row = self.state_data["signals"][candidate.signal_id]
                row.update(decision="prepared", order_ids=[p.order_id])
                if p.side == "SELL":
                    row["exit_sizing"]["prepared_quantity"] = str(order.quantity)
                native.append((order, position_id))
            self._audit(
                "admission",
                selected=[c.order.order_id for c in result.selected],
                required_quote=str(result.preflight.required_quote),
                available_quote=str(result.preflight.available_quote),
                skipped=[asdict(s) for s in result.skipped],
            )
            self._persist()  # all reservations + consumed signals durable BEFORE any submit
            for order, position_id in native:
                if self.state_data["halt_reason"]:
                    raise SimulationBlocked(self.state_data["halt_reason"])
                self._submit_native(order, position_id)
            return result
        except Exception as exc:
            self.state_data["halt_reason"] = str(exc)
            self._persist()
            raise
        finally:
            self._admitting = False

    def _submit_native(self, order, position_id):
        self.submit_order(order, position_id=position_id)  # native RiskEngine -> ExecutionEngine

    def request_cancel(self, order_id: str):
        self._assert_owner()
        order = self.cache.order(ClientOrderId(order_id))
        if order_id not in self.state_data["orders"] or order is None or order.is_closed:
            raise SimulationBlocked("cancel requires known active native order")
        self._audit("cancel_requested", order_id=order_id)
        self._persist()  # no release on request or exception
        self.cancel_order(order)

    def on_order_event(self, event):
        self._assert_owner()
        oid = str(event.client_order_id)
        if oid not in self.state_data["orders"]:
            self.state_data["halt_reason"] = "unknown order event"
            self._audit("unknown_order_event", order_id=oid, event_id=str(event.id))
            self._persist()
            return
        # Event callbacks are observational; cumulative fills/balances come from
        # native cache only. Repeated/late callbacks cannot apply cash twice.
        event_id = str(event.id)
        if any(e.get("event_id") == event_id for e in self.state_data["events"]):
            return
        self._audit(
            type(event).__name__,
            event_id=event_id,
            order_id=oid,
            signal_id=self.state_data["orders"].get(oid, {}).get("signal_id"),
        )
        self._persist()

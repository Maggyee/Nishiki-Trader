"""ADR-017 single-session intent journal over native balances/orders/fills.

Offline TestClock only. Durable preparation is not submission permission. Native
objects own settlement; this journal derives ownership and checks conservation.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import os
import stat
import tempfile
import threading
from dataclasses import asdict
from decimal import ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path

from nautilus_trader.common.component import TestClock
from nautilus_trader.model.events import OrderAccepted, OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair

from apps.bridge.signal_event import SignalEvent
from apps.bridge.validators import Authorization
from apps.strategies_nautilus.portfolio_account import AccountAnchor
from apps.strategies_nautilus.portfolio_adapter_checkpoint import checkpoint_bytes
from apps.strategies_nautilus.portfolio_recovery import capture_native, encode, verify_checkpoint
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_testnet_session import session_contract
from apps.strategies_nautilus.portfolio_venue import _decimal, _fresh
from apps.strategies_nautilus.signal_consumer import ConsumerConfig, evaluate

VERSION = "portfolio.testnet_session_ledger.v1"
MODE = "binance_numeric_offline_v1"
STRATEGY = "TESTNET-SESSION-TS"
SOURCE = "rule_testnet_engineering_fixture"
MODEL = "testnet-engineering-lifecycle-v1"
INSTRUMENT = InstrumentId.from_str("BTCUSDT.BINANCE")
AUTH = ConsumerConfig("BINANCE", Authorization(frozenset({SOURCE}), frozenset({MODEL})))
TERMINAL = {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "DENIED"}
UNCERTAIN = {"INITIALIZED", "SUBMITTED", "PENDING_CANCEL", "PENDING_UPDATE"}


class SessionLedgerError(ValueError):
    pass


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def balances(account):
    return {
        c.code: [str(b.free.as_decimal()), str(b.locked.as_decimal())]
        for c, b in account.balances().items()
    }


def _time(now):
    if type(now) is not int or now <= 0:
        raise SessionLedgerError("positive integer session time required")


def native_view(state, owner):
    """Derive ownership from complete native fills; preserve all unrelated assets."""
    now = owner.clock.timestamp_ns()
    _time(now)
    cache = owner.cache
    accounts = cache.accounts()
    if len(accounts) != 1 or str(accounts[0].id) != state["native_account_id"]:
        raise SessionLedgerError("session native account mismatch")
    actual = balances(accounts[0])
    expected = {
        a: sum((_decimal(q) for q in values), D(0)) for a, values in state["baseline"].items()
    }
    if set(actual) != set(expected):
        raise SessionLedgerError("full native asset set changed")
    known = state["intents"]
    native = {str(o.client_order_id): o for o in cache.orders()}
    if set(native) - set(known):
        raise SessionLedgerError("unowned native order")
    owned, spent, sale_proceeds, reserved = D(0), D(0), D(0), D(0)
    trade_ids, fills, statuses, open_ids, uncertain, incidents = set(), {}, {}, [], [], []
    locked = dict.fromkeys(expected, D(0))
    for oid, intent in known.items():
        order = native.get(oid)
        if order is None:
            statuses[oid] = "PREPARED"
            open_ids.append(oid)
            uncertain.append(oid)
            if intent["side"] == "BUY":
                reserved += _decimal(intent["quantity"]) * _decimal(intent["price"])
            continue
        if (
            str(order.strategy_id) != STRATEGY
            or order.instrument_id != INSTRUMENT
            or order.order_type.name != "LIMIT"
            or order.time_in_force.name != "GTC"
            or order.side.name != intent["side"]
            or order.quantity.as_decimal() != _decimal(intent["quantity"])
            or order.price.as_decimal() != _decimal(intent["price"])
            or str(cache.position_id(order.client_order_id)) != state["position_id"]
            or order.tags
            != [f"signal_id:{intent['signal_id']}", f"session_id:{state['session_id']}"]
            or encode(order.events[0]) != intent["native_init"]
            or (
                order.account_id is not None and str(order.account_id) != state["native_account_id"]
            )
            or any(
                str(e.account_id) != state["native_account_id"]
                for e in order.events
                if getattr(e, "account_id", None) is not None
            )
        ):
            raise SessionLedgerError("native order/intent lineage differs")
        status = order.status.name
        if status not in TERMINAL | UNCERTAIN | {"ACCEPTED", "PARTIALLY_FILLED"}:
            raise SessionLedgerError("unsupported native order state")
        statuses[oid] = status
        if status not in TERMINAL:
            open_ids.append(oid)
        if status in UNCERTAIN:
            uncertain.append(oid)
        quantity = D(0)
        for event in order.events:
            if not isinstance(event, OrderFilled):
                continue
            tid = str(event.trade_id)
            q, price, fee = (
                event.last_qty.as_decimal(),
                event.last_px.as_decimal(),
                event.commission.as_decimal(),
            )
            asset = event.commission.currency.code
            if (
                tid in trade_ids
                or q <= 0
                or price <= 0
                or fee < 0
                or asset not in expected
                or str(event.position_id) != state["position_id"]
                or not state["started_ns"] <= event.ts_event <= now
                or event.ts_init > now
            ):
                raise SessionLedgerError("invalid/duplicate native fill")
            trade_ids.add(tid)
            fills[tid] = {
                "client_order_id": oid,
                "quantity": str(q),
                "price": str(price),
                "commission": str(fee),
                "commission_asset": asset,
                "ts_event": event.ts_event,
            }
            direction = D(1) if intent["side"] == "BUY" else D(-1)
            expected["BTC"] += direction * q
            expected["USDT"] -= direction * q * price
            expected[asset] -= fee
            owned += direction * q - (fee if asset == "BTC" else 0)
            if direction == 1:
                spent += q * price + (fee if asset == "USDT" else 0)
            else:
                sale_proceeds += q * price - (fee if asset == "USDT" else 0)
            quantity += q
            if fee:
                incidents.append("unexpected_nonzero_commission")
            if (direction == 1 and price > order.price.as_decimal()) or (
                direction == -1 and price < order.price.as_decimal()
            ):
                incidents.append("execution_outside_limit")
        if quantity != order.filled_qty.as_decimal() or quantity > order.quantity.as_decimal():
            raise SessionLedgerError("incomplete native fill coverage")
        if status not in TERMINAL:
            remaining = order.quantity.as_decimal() - quantity
            if intent["side"] == "BUY":
                reserved += remaining * order.price.as_decimal()
                locked["USDT"] += remaining * order.price.as_decimal()
            else:
                locked["BTC"] += remaining
    for tid, historical in state.get("view", {}).get("fills", {}).items():
        if fills.get(tid) != historical:
            raise SessionLedgerError("historical native fill changed or disappeared")
    positions = cache.positions()
    if (
        any(
            str(p.id) != state["position_id"]
            or p.instrument_id != INSTRUMENT
            or str(p.strategy_id) != STRATEGY
            or p.signed_qty < 0
            for p in positions
        )
        or sum((p.quantity.as_decimal() for p in positions), D(0)) != owned
        or owned < 0
    ):
        raise SessionLedgerError("native position differs from owned net fills")
    for asset, values in actual.items():
        if sum((_decimal(v) for v in values), D(0)) != expected[asset]:
            raise SessionLedgerError("native full-account conservation failed")
        if (not uncertain or asset not in {"BTC", "USDT"}) and _decimal(values[1]) != locked[asset]:
            raise SessionLedgerError("native full-account lock attribution failed")
    if spent + reserved > 10:
        incidents.append("session_debit_cap_exceeded")
    if len(open_ids) > 1:
        raise SessionLedgerError("multiple outstanding session orders")
    return {
        "owned_btc": str(owned),
        "buy_spent_usdt": str(spent),
        "buy_reserved_usdt": str(reserved),
        "sell_proceeds_usdt": str(sale_proceeds),
        "buy_allowance_consumed": any(i["side"] == "BUY" for i in known.values()),
        "sell_allowance_consumed": any(i["side"] == "SELL" for i in known.values()),
        "statuses": statuses,
        "open_order_ids": open_ids,
        "uncertain_order_ids": uncertain,
        "fills": fills,
        "expected_totals": {a: str(q) for a, q in expected.items()},
        "expected_locked": {a: str(q) for a, q in locked.items()},
        "incidents": sorted(set(incidents)),
        "runtime_ready": False,
    }


def snapshot(state, owner):
    state = copy.deepcopy(state)
    state["view"] = native_view(state, owner)
    if state["view"]["incidents"]:
        state["halt_reasons"] = sorted(set(state["halt_reasons"] + state["view"]["incidents"]))
    state["updated_ns"] = owner.clock.timestamp_ns()
    anchor = AccountAnchor(
        state["source"]["account_uid"],
        state["native_account_id"],
        state["started_ns"],
        sum(map(_decimal, state["baseline"]["USDT"])),
        sum(map(_decimal, state["baseline"]["BTC"])),
    )
    native = capture_native(owner, venue_id_mode=MODE, anchor=anchor)
    # Explicit precision for serializer reconstruction of every full-account asset.
    native["session_currencies"] = {
        c.code: {
            "precision": c.precision,
            "iso4217": c.iso4217,
            "name": c.name,
            "currency_type": c.currency_type.name,
        }
        for c in owner.cache.accounts()[0].balances()
    }
    return checkpoint_bytes(state, native)


def read_session(raw):
    wrapped = verify_checkpoint(raw)
    state, native = wrapped["state"], wrapped["native"]
    if (
        state["version"] != VERSION
        or state["contract_sha256"] != _hash(canonical(session_contract()))
        or state["source"]["endpoint"] != TESTNET_REST
        or native["venue_id_mode"] != MODE
        or state["updated_ns"] != native["ts_ns"]
        or state["deadline_ns"] != state["started_ns"] + 180_000_000_000
        or not isinstance(state["halt_reasons"], list)
        or not 0 < state["started_ns"] <= state["updated_ns"]
    ):
        raise SessionLedgerError("session checkpoint policy/source/time mismatch")
    return wrapped


class SessionLedger:
    """Single-writer atomic checkpoint, poisoned after any unacknowledged write.

    A PREPARED intent consumes its allowance even when no native order exists yet.
    A missing file is never interpreted as an existing session reset.
    """

    def __init__(self, path: Path):
        self.path = path
        self._fd = None
        self._thread = threading.get_ident()
        self._poisoned = False
        self._raw = None
        self.state = None

    def _lock(self):
        if self._fd is not None:
            raise SessionLedgerError("session writer already open")
        self._fd = os.open(
            self.path.with_suffix(self.path.suffix + ".lock"),
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        try:
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise SessionLedgerError("private session writer lock required")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def _owner(self, owner):
        if (
            self._fd is None
            or self._poisoned
            or threading.get_ident() != self._thread
            or not isinstance(owner.clock, TestClock)
        ):
            raise SessionLedgerError("healthy owning offline writer required")
        if self.state is not None and owner.clock.timestamp_ns() < self.state["updated_ns"]:
            raise SessionLedgerError("session clock regressed")

    def create(self, owner, *, session_id, source):
        self._lock()
        try:
            self._owner(owner)
            if self.path.exists():
                raise SessionLedgerError("existing session cannot be reset")
            if (
                not isinstance(session_id, str)
                or not session_id.isascii()
                or not session_id.isalnum()
                or not 8 <= len(session_id) <= 20
            ):
                raise SessionLedgerError("bounded alphanumeric session ID required")
            if (
                source.endpoint != TESTNET_REST
                or not source.account_uid.isdecimal()
                or len(source.key_sha256) != 64
                or any(c not in "0123456789abcdef" for c in source.key_sha256)
            ):
                raise SessionLedgerError("selected testnet source required")
            accounts = owner.cache.accounts()
            if len(accounts) != 1 or accounts[0].type.name != "CASH":
                raise SessionLedgerError("one full native cash account required")
            baseline = balances(accounts[0])
            if (
                owner.cache.orders()
                or owner.cache.positions()
                or "BTC" not in baseline
                or "USDT" not in baseline
                or _decimal(baseline["USDT"][0]) < 10
                or any(_decimal(q[1]) != 0 for q in baseline.values())
            ):
                raise SessionLedgerError(
                    "empty native orders/positions and unreserved funds required"
                )
            now = owner.clock.timestamp_ns()
            self.state = {
                "version": VERSION,
                "contract_sha256": _hash(canonical(session_contract())),
                "session_id": session_id,
                "source": asdict(source),
                "native_account_id": str(accounts[0].id),
                "position_id": f"session-{session_id}",
                "started_ns": now,
                "deadline_ns": now + 180_000_000_000,
                "updated_ns": now,
                "baseline": baseline,
                "instrument": CurrencyPair.to_dict(owner.cache.instrument(INSTRUMENT)),
                "intents": {},
                "signals": {},
                "cancel_intents": {},
                "halt_reasons": [],
                "generation": 0,
                "previous_sha256": None,
            }
            self._persist(owner)
            return self
        except BaseException:
            self.close()
            raise

    def load(self, *, expected_sha256):
        self._lock()
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                    or info.st_size > 32 * 1024 * 1024
                ):
                    raise SessionLedgerError("private bounded checkpoint required")
                raw = source.read()
            if _hash(raw) != expected_sha256:
                raise SessionLedgerError("selected session checkpoint changed")
            self.state = read_session(raw)["state"]
            self._raw = raw
            return self
        except BaseException:
            self.close()
            raise

    def _persist(self, owner):
        self._owner(owner)
        temporary = None
        try:
            if self._raw is not None and self.path.read_bytes() != self._raw:
                raise SessionLedgerError("session changed outside writer")
            state = copy.deepcopy(self.state)
            state["generation"] += 1
            state["previous_sha256"] = _hash(self._raw) if self._raw is not None else None
            raw = snapshot(state, owner)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            if self._raw is None:
                os.link(temporary, self.path)
            else:
                os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self._raw, self.state = raw, read_session(raw)["state"]
        except BaseException:
            self._poisoned = True
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def observe(self, owner):
        self._persist(owner)
        return copy.deepcopy(self.state["view"])

    def prepare(self, owner, *, signal, order, rules):
        self._owner(owner)
        state = self.state
        now = owner.clock.timestamp_ns()
        view = native_view(state, owner)
        if (
            now >= state["deadline_ns"]
            or state["halt_reasons"]
            or view["incidents"]
            or view["open_order_ids"]
        ):
            raise SessionLedgerError("session expired, halted, outstanding or uncertain")
        signal = SignalEvent.model_validate(signal.model_dump())
        if (
            evaluate(signal, AUTH, now_ns=now).decision != "accept"
            or signal.symbol != "BTCUSDT"
            or signal.ts_event > now
            or now >= signal.ts_event + signal.ttl_seconds * 1_000_000_000
            or signal.signal_id in state["signals"]
            or (state["signals"] and signal.ts_event <= max(state["signals"].values()))
        ):
            raise SessionLedgerError("fixture signal rejected or replayed")
        _fresh(rules.ts_ns, now, 5_000_000_000)
        side, quantity, price = (
            order.side.name,
            order.quantity.as_decimal(),
            order.price.as_decimal(),
        )
        oid = str(order.client_order_id)
        expected_side = "BUY" if signal.side == "buy" else "SELL" if signal.side == "flat" else None
        if (
            side != expected_side
            or str(order.strategy_id) != STRATEGY
            or order.instrument_id != INSTRUMENT
            or rules.instrument_id != str(INSTRUMENT)
            or order.order_type.name != "LIMIT"
            or order.time_in_force.name != "GTC"
            or order.status.name != "INITIALIZED"
            or order.ts_init != now
            or oid != f"ts-{state['session_id']}-{'b' if side == 'BUY' else 's'}"
            or order.tags != [f"signal_id:{signal.signal_id}", f"session_id:{state['session_id']}"]
            or rules.fee_rate != 0
            or not price.is_finite()
            or price <= 0
            or not rules.quantity_min <= quantity <= rules.quantity_max
            or rules.quantity_step <= 0
            or quantity % rules.quantity_step
            or price < rules.price_min
            or (rules.price_max and price > rules.price_max)
            or (rules.price_tick and price % rules.price_tick)
            or quantity * price < rules.notional_min
            or (rules.notional_max is not None and quantity * price > rules.notional_max)
            or any(not b.minimum <= price <= b.maximum for b in rules.price_bands if b.side == side)
            or (rules.max_open_orders is not None and rules.max_open_orders < 1)
        ):
            raise SessionLedgerError("session order or effective zero-fee filters rejected")
        if side == "BUY":
            if view["buy_allowance_consumed"] or quantity != D("0.0001") or quantity * price > 10:
                raise SessionLedgerError("one fixed BUY / 10 test-USDT ceiling exceeded")
            if (
                rules.max_position is not None
                and _decimal(view["expected_totals"]["BTC"]) + quantity > rules.max_position
            ):
                raise SessionLedgerError("full-account base position filter exceeded")
        else:
            owned = _decimal(view["owned_btc"])
            whole_steps = (owned / rules.quantity_step).to_integral_value(
                rounding=ROUND_FLOOR
            ) * rules.quantity_step
            if (
                view["sell_allowance_consumed"]
                or not view["buy_allowance_consumed"]
                or quantity <= 0
                or quantity != whole_steps
            ):
                raise SessionLedgerError("one cleanup of owned whole steps required")
        self.state["signals"][signal.signal_id] = signal.ts_event
        self.state["intents"][oid] = {
            "side": side,
            "quantity": str(quantity),
            "price": str(price),
            "signal_id": signal.signal_id,
            "prepared_ns": now,
            "native_init": encode(order.events[0]),
        }
        self._persist(owner)  # must succeed before a future strategy can submit
        return oid

    def prepare_cancel(self, owner, order):
        self._owner(owner)
        oid = str(order.client_order_id)
        native_view(self.state, owner)
        accepted = [e for e in order.events if isinstance(e, OrderAccepted)]
        if (
            oid not in self.state["intents"]
            or oid in self.state["cancel_intents"]
            or owner.cache.order(order.client_order_id) is not order
            or order.is_closed
            or not accepted
            or owner.clock.timestamp_ns() < accepted[0].ts_init + 2_000_000_000
        ):
            raise SessionLedgerError("known acknowledged order and unused cancellation required")
        self.state["cancel_intents"][oid] = owner.clock.timestamp_ns()
        self._persist(owner)

    def record_dispatch(self, owner, order, *, kind):
        """Consume one adapter attempt after its native event has been persisted.

        A receipt records permission to attempt I/O, never exchange acceptance.
        No retry is permitted even when the process dies before the actual send.
        """
        self._owner(owner)
        oid = str(order.client_order_id)
        expected = {"submit": "SUBMITTED", "cancel": "PENDING_CANCEL"}.get(kind)
        event_type = {"submit": "OrderSubmitted", "cancel": "OrderPendingCancel"}.get(kind)
        key = f"{kind}:{oid}"
        dispatches = self.state.get("dispatches", {})
        if (
            expected is None
            or oid not in self.state["intents"]
            or owner.cache.order(order.client_order_id) is not order
            or order.status.name != expected
            or self.state["view"]["statuses"].get(oid) != expected
            or type(order.events[-1]).__name__ != event_type
            or key in dispatches
            or (kind == "cancel" and oid not in self.state["cancel_intents"])
            or (kind == "submit" and (
                self.state["halt_reasons"]
                or owner.clock.timestamp_ns() >= self.state["deadline_ns"]
                or owner.clock.timestamp_ns() > self.state["intents"][oid]["prepared_ns"] + 5_000_000_000
            ))
        ):
            raise SessionLedgerError("durable native event and unused adapter attempt required")
        # The previous successful snapshot must contain this exact native event.
        saved = read_session(self._raw)["native"]
        if encode(order.events[-1]) not in [
            e for item in saved["orders"] for e in item["events"]
        ]:
            raise SessionLedgerError("native dispatch event not durably captured")
        self.state.setdefault("dispatches", {})[key] = {
            "event_id": str(order.events[-1].id), "ts_ns": owner.clock.timestamp_ns(),
        }
        self._persist(owner)

    def halt(self, owner, reason):
        self._owner(owner)
        if reason not in self.state["halt_reasons"]:
            self.state["halt_reasons"].append(reason)
        self._persist(owner)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def sha256(self):
        return _hash(self._raw) if self._raw else None

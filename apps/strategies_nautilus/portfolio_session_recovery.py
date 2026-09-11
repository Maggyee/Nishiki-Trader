"""Offline full-account ADR-017 reconstruction through native Binance reports.

No sockets, credentials, clients, runtime bootstrap or inferred fills. Original
native initial events can be adopted only with complete matching venue reports.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import LiveExecEngineConfig, StrategyConfig
from nautilus_trader.model.enums import CurrencyType, OmsType
from nautilus_trader.model.events import OrderInitialized
from nautilus_trader.model.identifiers import PositionId, TraderId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.orders import OrderUnpacker
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.trading.strategy import Strategy

from apps.strategies_nautilus.portfolio_adapter_recovery import (
    EvidenceOnlyExecutionEngine,
    reconcile_binance_reports,
)
from apps.strategies_nautilus.portfolio_recovery import SERIALIZER, reconstruct_native
from apps.strategies_nautilus.portfolio_session_account import restore_session_cash_account
from apps.strategies_nautilus.portfolio_session_ledger import (
    MODE,
    SessionLedgerError,
    balances,
    native_view,
    read_session,
    snapshot,
)
from apps.strategies_nautilus.portfolio_testnet_observation import _open_orders, account_balances
from apps.strategies_nautilus.portfolio_venue import _decimal, _unique_object


def restore_session_objects(raw):
    """Call only in an isolated process: CashAccount registers currency metadata."""
    wrapped = read_session(raw)
    native, state = wrapped["native"], wrapped["state"]
    if set(native["session_currencies"]) != set(state["baseline"]):
        raise SessionLedgerError("complete persisted currency metadata required")
    for code, row in native["session_currencies"].items():
        currency = Currency(
            code, row["precision"], row["iso4217"], row["name"], CurrencyType[row["currency_type"]]
        )
        existing = Currency.from_internal_map(code)
        if existing is not None and existing.precision != currency.precision:
            raise SessionLedgerError("native currency precision conflict")
        if existing is None:
            Currency.register(currency)
    instrument, account, orders, positions = reconstruct_native(
        native, venue_id_mode=MODE, calculate_account_state=True
    )
    if CurrencyPair.to_dict(instrument) != state["instrument"]:
        raise SessionLedgerError("session instrument changed")
    # Recover exact persisted initialization, never fabricate a submitted or filled event.
    indexed = {str(o.client_order_id) for o, _ in orders}
    for oid, intent in state["intents"].items():
        if oid not in indexed:
            event = SERIALIZER.deserialize(intent["native_init"].encode())
            if not isinstance(event, OrderInitialized) or str(event.client_order_id) != oid:
                raise SessionLedgerError("persisted native initialization mismatch")
            orders.append((OrderUnpacker.from_init(event), PositionId(state["position_id"])))
    if {str(o.client_order_id) for o, _ in orders} != set(state["intents"]):
        raise SessionLedgerError("native/intent order coverage mismatch")
    return wrapped, instrument, account, orders, positions


def recover_session(raw, evidence_raw, *, expected_sha256, evidence_sha256, now_ns, loop):
    """Reconcile fixed original evidence in a disposable native process/cache.

    Hashes bind selected bytes, not exchange authenticity. A future transport must
    qualify source/fences and current market state before any execution bootstrap.
    """
    if (
        not 0 < len(raw) <= 32 * 1024 * 1024
        or not 0 < len(evidence_raw) <= 32 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != expected_sha256
        or hashlib.sha256(evidence_raw).hexdigest() != evidence_sha256
    ):
        raise SessionLedgerError("selected recovery bytes changed")
    state = read_session(raw)["state"]
    evidence = json.loads(evidence_raw, object_pairs_hook=_unique_object)
    if (
        evidence["profile"] != "offline_testnet_session_recovery_v1"
        or evidence["source"] != state["source"]
        or evidence["history_start_ns"] != state["started_ns"]
        or type(now_ns) is not int
        or type(evidence["received_ns"]) is not int
        or not state["updated_ns"] < evidence["received_ns"] <= now_ns
        or now_ns - evidence["received_ns"] > 5_000_000_000
    ):
        raise SessionLedgerError("session recovery source/history/time mismatch")
    remote_balances = account_balances(evidence["account"], state["source"]["account_uid"])
    _open_orders(evidence["open_orders"])
    rows, trades = evidence["orders"], evidence["trades"]
    if len(rows) != len(state["intents"]) or {r["clientOrderId"] for r in rows} != set(
        state["intents"]
    ):
        raise SessionLedgerError(
            "every prepared order requires an authoritative report; do not resubmit"
        )
    active = {r["orderId"]: r for r in rows if r["status"] in {"NEW", "PARTIALLY_FILLED"}}
    if len(active) != len(evidence["open_orders"]):
        raise SessionLedgerError("account-wide open-order coverage mismatch")
    for row in evidence["open_orders"]:
        if row != active.get(row["orderId"]):
            raise SessionLedgerError("foreign or conflicting account-wide order")
    wrapped, instrument, account, orders, positions = restore_session_objects(raw)
    remote = {r["clientOrderId"]: r for r in rows}
    if any(
        o.account_id is None
        and remote[str(o.client_order_id)]["status"] in {"NEW", "PARTIALLY_FILLED"}
        for o, _ in orders
    ):
        raise SessionLedgerError(
            "active prepared order lacks a persisted native submit receipt; hold without resubmission"
        )
    clock = TestClock()
    clock.set_time(now_ns)
    cache = Cache()
    account = restore_session_cash_account(account, cache)
    cache.add_instrument(instrument)
    cache.add_account(account)
    for order, pid in orders:
        cache.add_order(order, position_id=pid)
    for position in positions:
        cache.add_position(position, OmsType.HEDGING)
    cache.build_index()
    owner = SimpleNamespace(cache=cache, clock=clock)
    native_view(state, owner)  # reject corrupt lineage/economics before native mutation
    bus = MessageBus(trader_id=TraderId("BACKTESTER-001"), clock=clock)
    portfolio = Portfolio(msgbus=bus, cache=cache, clock=clock)
    engine = EvidenceOnlyExecutionEngine(
        loop=loop,
        msgbus=bus,
        cache=cache,
        clock=clock,
        config=LiveExecEngineConfig(filter_unclaimed_external_orders=False),
    )
    try:
        engine.register_oms_type(
            Strategy(
                StrategyConfig(strategy_id="TESTNET-SESSION", order_id_tag="TS", oms_type="HEDGING")
            )
        )
        portfolio.initialize_orders()
        portfolio.initialize_positions()
        reconcile_binance_reports(
            engine,
            cache,
            account_id=account.id,
            orders=rows,
            trades=trades,
            now_ns=now_ns,
            allow_initialized=True,
        )
        view = native_view(state, owner)
        native_balances = {a: tuple(map(_decimal, q)) for a, q in balances(account).items()}
        if native_balances != remote_balances:
            raise SessionLedgerError("native and reported full-account balances/locks differ")
        for asset, (free, locked) in remote_balances.items():
            if free + locked != _decimal(view["expected_totals"][asset]) or locked != _decimal(
                view["expected_locked"][asset]
            ):
                raise SessionLedgerError(
                    "reported full-account funds differ from owned native events"
                )
        state["generation"] += 1
        state["previous_sha256"] = expected_sha256
        state["last_recovery_evidence_sha256"] = evidence_sha256
        checkpoint = snapshot(state, owner)
        return {
            "checkpoint": checkpoint,
            "view": read_session(checkpoint)["state"]["view"],
            "input_sha256": expected_sha256,
            "evidence_sha256": evidence_sha256,
            "output_sha256": hashlib.sha256(checkpoint).hexdigest(),
            "full_account_assets": len(remote_balances),
            "full_account_reconciled": True,
            "native_reports_reconciled": True,
            "matching_requests_made": 0,
            "source_authenticated": False,
            "runtime_ready": False,
        }
    finally:
        engine.dispose()

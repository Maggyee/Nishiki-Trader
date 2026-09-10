"""Durable native-event snapshots for the isolated portfolio simulation.

Uses Nautilus serializers, order state machines, account and position replay.
Never infers fills from intents or resubmits an uncertain order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import msgspec
import nautilus_trader
from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.accounting.factory import AccountFactory
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.events import AccountState, OrderFilled, OrderInitialized
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.orders import OrderUnpacker
from nautilus_trader.model.position import Position
from nautilus_trader.serialization.serializer import MsgSpecSerializer

SERIALIZER = MsgSpecSerializer(msgspec.json)
VERSION = "portfolio.native_events.v1"


class RecoveryError(ValueError):
    pass


def encode(event):
    return SERIALIZER.serialize(event).decode()


def capture_native(strategy, *, venue_id_mode="native_uuid", anchor=None):
    from apps.strategies_nautilus.portfolio_simulation import INSTRUMENT

    cache = strategy.cache
    account = cache.accounts()[0]
    initial = account.events[0]
    initial_balances = {
        balance.currency.code: balance.total.as_decimal() for balance in initial.balances
    }
    if venue_id_mode not in {"native_uuid", "binance_numeric_offline_v1"}:
        raise RecoveryError("unsupported native venue ID mode")
    account_anchor = {
        "venue_uid": "synthetic-authority",
        "native_account_id": str(account.id),
        "start_ns": initial.ts_event,
        "quote": str(initial_balances["USDT"]),
        "base": str(initial_balances["BTC"]),
    }
    if venue_id_mode == "binance_numeric_offline_v1":
        if anchor is None:
            raise RecoveryError("explicit numeric-venue account anchor required")
        supplied = {**asdict(anchor), "quote": str(anchor.quote), "base": str(anchor.base)}
        if {**supplied, "venue_uid": "synthetic-authority"} != account_anchor:
            raise RecoveryError("numeric-venue native baseline mismatch")
        account_anchor = supplied
    elif anchor is not None:
        raise RecoveryError("simulation anchor is fixed")
    if any(
        adjustment.adjustment_type.name != "COMMISSION"
        for position in cache.positions()
        for adjustment in position.adjustments
    ):
        raise RecoveryError("unsupported native position adjustment")
    return {
        "version": VERSION,
        "nautilus_version": nautilus_trader.__version__,
        "venue_id_mode": venue_id_mode,
        "ts_ns": strategy.clock.timestamp_ns(),
        "anchor": account_anchor,
        "instrument": CurrencyPair.to_dict(cache.instrument(INSTRUMENT)),
        "accounts": [[encode(e) for e in a.events] for a in cache.accounts()],
        "orders": [
            {
                "position_id": str(cache.position_id(o.client_order_id)),
                "events": [encode(e) for e in o.events],
            }
            for o in sorted(cache.orders(), key=lambda o: str(o.client_order_id))
        ],
        "positions": [
            [encode(e) for e in p.events]
            for p in sorted(cache.positions(), key=lambda p: str(p.id))
        ],
    }


def decode_events(rows, first_type, *, max_ts_ns=None):
    events = [SERIALIZER.deserialize(row.encode()) for row in rows]
    if not events or not isinstance(events[0], first_type):
        raise RecoveryError("missing native initial event")
    if len({str(e.id) for e in events}) != len(events):
        raise RecoveryError("duplicate native event")
    if max_ts_ns is not None and any(
        not 0 <= e.ts_event <= max_ts_ns or not 0 <= e.ts_init <= max_ts_ns for e in events
    ):
        raise RecoveryError("native event exceeds checkpoint cursor")
    return events


def reconstruct_native(bundle, *, venue_id_mode="native_uuid", calculate_account_state=False):
    """Reconstruct detached native objects; do not mutate a running cache."""
    if (
        venue_id_mode not in {"native_uuid", "binance_numeric_offline_v1"}
        or bundle["version"] != VERSION
        or bundle["nautilus_version"] != nautilus_trader.__version__
        or bundle["venue_id_mode"] != venue_id_mode
    ):
        raise RecoveryError("native serialization version mismatch")
    instrument = CurrencyPair.from_dict(bundle["instrument"])
    max_ts_ns = bundle["ts_ns"] if venue_id_mode == "binance_numeric_offline_v1" else None
    accounts, orders, positions = [], [], []
    for rows in bundle["accounts"]:
        events = decode_events(rows, AccountState, max_ts_ns=max_ts_ns)
        if calculate_account_state:
            if (
                venue_id_mode != "binance_numeric_offline_v1"
                or events[0].account_type.name != "CASH"
            ):
                raise RecoveryError("calculated account recovery is isolated numeric CASH only")
            account = CashAccount(events[0], calculate_account_state=True)
        else:
            account = AccountFactory.create(events[0])
        for event in events[1:]:
            account.apply(event)
        accounts.append(account)
    for row in bundle["orders"]:
        events = decode_events(row["events"], OrderInitialized, max_ts_ns=max_ts_ns)
        order = OrderUnpacker.from_init(events[0])
        for event in events[1:]:
            order.apply(event)
        orders.append((order, PositionId(row["position_id"])))
    for rows in bundle["positions"]:
        events = decode_events(rows, OrderFilled, max_ts_ns=max_ts_ns)
        if any(not isinstance(e, OrderFilled) for e in events):
            raise RecoveryError("unsupported position event")
        position = Position(instrument, events[0])
        for event in events[1:]:
            position.apply(event)
        positions.append(position)
    if len(accounts) != 1:
        raise RecoveryError("one dedicated native account required")
    if len({str(o.client_order_id) for o, _ in orders}) != len(orders):
        raise RecoveryError("duplicate native order")
    if len({str(p.id) for p in positions}) != len(positions):
        raise RecoveryError("duplicate native position")
    return instrument, accounts[0], orders, positions


def verify_checkpoint(raw):
    from apps.strategies_nautilus.portfolio_simulation import canonical
    from apps.strategies_nautilus.portfolio_venue import _unique_object

    wrapped = json.loads(raw, object_pairs_hook=_unique_object)
    for key, digest in (("state", "sha256"), ("native", "native_sha256")):
        if hashlib.sha256(canonical(wrapped[key])).hexdigest() != wrapped[digest]:
            raise RecoveryError("checkpoint integrity mismatch")
    if (
        hashlib.sha256(
            canonical({"state": wrapped["state"], "native": wrapped["native"]})
        ).hexdigest()
        != wrapped["generation_sha256"]
    ):
        raise RecoveryError("checkpoint generation mismatch")
    return wrapped


def restore_cache(engine, bundle):
    """Install native objects before engine startup; native startup restores orders."""
    instrument, account, orders, positions = reconstruct_native(bundle)
    if engine.cache.orders() or engine.cache.positions() or engine.cache.accounts():
        raise RecoveryError("restore requires an empty native cache")
    engine.cache.add_account(account)
    for order, position_id in orders:
        engine.cache.add_order(order, position_id=position_id)
    for position in positions:
        engine.cache.add_position(position, OmsType.HEDGING)
    engine.cache.build_index()
    return instrument


def recover_simulation(
    checkpoint,
    *,
    evidence,
    anchor,
    now_ns,
    max_age_ns=60_000_000_000,
    fee_mode="received_asset",
    exit_policy="whole_steps_v1",
    venue=None,
):
    """Gate a fresh simulation process on complete, fresh independent account evidence.

    This is not a live bootstrap: no adapters/credentials, no synthesized execution
    events, no replacement submission and no reset of persistent risk state.
    """
    from apps.strategies_nautilus.portfolio_account import reconcile_account
    from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import build_simulation

    raw = checkpoint.read_bytes()
    wrapped = verify_checkpoint(raw)
    anchor_fields = asdict(anchor)
    anchor_fields.update(quote=str(anchor.quote), base=str(anchor.base))
    if anchor_fields != wrapped["native"]["anchor"]:
        raise RecoveryError("checkpoint account anchor mismatch")
    instrument, account, orders, positions = reconstruct_native(wrapped["native"])
    if wrapped["native"]["ts_ns"] >= now_ns:
        raise RecoveryError("resume must advance beyond the native checkpoint cursor")
    if wrapped["state"]["halt_reason"]:
        raise RecoveryError("persisted halt requires explicit incident resolution")
    result = reconcile_account(
        evidence,
        anchor=anchor,
        native=(account, orders, positions),
        intents=wrapped["state"]["orders"],
        now_ns=now_ns,
        max_age_ns=max_age_ns,
        venue=venue,
    )
    if not result.checks_passed:
        raise RecoveryError("; ".join(result.reasons))
    engine, strategy, fixture = build_simulation(
        checkpoint,
        fee_mode=fee_mode,
        exit_policy=exit_policy,
        persist_native=True,
        recovery_bundle=wrapped["native"],
    )
    try:
        if CurrencyPair.to_dict(instrument) != CurrencyPair.to_dict(fixture):
            raise RecoveryError("native instrument/config mismatch")
        strategy.on_load({"checkpoint": raw})  # validate policy before native startup
        strategy.restored_checkpoint_bytes = raw  # check again under writer lock

        def validate_started(restored):
            if restored.clock.timestamp_ns() <= wrapped["native"]["ts_ns"]:
                raise RecoveryError("replayed market cursor on native recovery")
            cache = restored.cache
            checked = reconcile_account(
                evidence,
                anchor=anchor,
                native=(
                    cache.accounts()[0],
                    [(o, cache.position_id(o.client_order_id)) for o in cache.orders()],
                    cache.positions(),
                ),
                intents=restored.state_data["orders"],
                now_ns=restored.clock.timestamp_ns(),
                max_age_ns=max_age_ns,
                venue=venue,
            )
            if not checked.checks_passed:
                raise RecoveryError("; ".join(checked.reasons))
            restored._audit(
                "native_process_recovered",
                evidence_sha256=checked.response_sha256,
                evidence_ts_ns=checked.evidence_ts_ns,
            )

        strategy.recovery_validator = validate_started
        return engine, strategy, fixture, result
    except Exception:
        engine.dispose()
        raise

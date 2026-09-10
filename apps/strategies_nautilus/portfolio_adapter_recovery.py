"""Offline qualification of Binance's native report conversion/reconciliation.

Runs real Nautilus adapter schemas and LiveExecutionEngine reconciliation with a
TestClock and no execution clients. It cannot connect to or submit to an exchange.
"""

from __future__ import annotations

from decimal import ROUND_CEILING
from decimal import Decimal as D

import msgspec
from nautilus_trader.adapters.binance.common.schemas.account import BinanceOrder, BinanceUserTrade
from nautilus_trader.adapters.binance.spot.enums import BinanceSpotEnumParser
from nautilus_trader.common.component import TestClock
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.reports import ExecutionMassStatus
from nautilus_trader.live.execution_engine import LiveExecutionEngine
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import ClientId, ClientOrderId, InstrumentId, Venue

from apps.strategies_nautilus.portfolio_venue import _decimal


class AdapterRecoveryError(ValueError):
    pass


def prepare_binance_reports(cache, *, account_id, orders, trades, now_ns):
    """Validate complete original fills before allowing native state mutation.

    Account/source/stream qualification is separate. These are captured fixture
    bodies, not authenticated wire responses or an authorization artifact.
    """
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")
    instrument = cache.instrument(instrument_id)
    if instrument is None or instrument.size_precision != 8:
        raise AdapterRecoveryError("qualified native BTC precision required")
    known = {str(o.client_order_id) for o in cache.orders()}
    if len(orders) != len(known) or {o["clientOrderId"] for o in orders} != known:
        raise AdapterRecoveryError("complete known order coverage required")
    venue_ids = {o["orderId"] for o in orders}
    if len(venue_ids) != len(orders) or any(type(i) is not int or i < 0 for i in venue_ids):
        raise AdapterRecoveryError("unique Binance venue order IDs required")
    grouped = {vid: [] for vid in venue_ids}
    seen = set()
    for trade in trades:
        if (
            type(trade["id"]) is not int
            or trade["id"] < 0
            or trade["id"] in seen
            or trade["orderId"] not in grouped
        ):
            raise AdapterRecoveryError("unknown or duplicate trade")
        seen.add(trade["id"])
        if (
            trade["symbol"] != "BTCUSDT"
            or type(trade["isBuyer"]) is not bool
            or type(trade["isMaker"]) is not bool
        ):
            raise AdapterRecoveryError("invalid trade identity/side")
        q, p, fee = (_decimal(trade[k]) for k in ("qty", "price", "commission"))
        currency = trade["commissionAsset"]
        if (
            q <= 0
            or p <= 0
            or q % instrument.size_increment.as_decimal()
            or p % instrument.price_increment.as_decimal()
            or _decimal(trade["quoteQty"]) != q * p
        ):
            raise AdapterRecoveryError("invalid trade quantity/price/notional")
        if currency not in ({"BTC", "USDT"} if trade["isBuyer"] else {"USDT"}):
            raise AdapterRecoveryError("unsupported actual commission currency")
        bound = (
            (q if currency == "BTC" else q * p) * D("0.0015") / D("0.00000001")
        ).to_integral_value(rounding=ROUND_CEILING) * D("0.00000001")
        if fee > bound or fee % D("0.00000001"):
            raise AdapterRecoveryError("actual commission exceeds qualified bound")
        if type(trade["time"]) is not int or not 0 < trade["time"] * 1_000_000 <= now_ns:
            raise AdapterRecoveryError("invalid trade timestamp")
        grouped[trade["orderId"]].append(trade)
    mass = ExecutionMassStatus(
        client_id=ClientId("BINANCE"),
        account_id=account_id,
        venue=Venue("BINANCE"),
        report_id=UUID4(),
        ts_init=now_ns,
    )
    order_reports, fills = [], []
    for row in orders:
        native = cache.order(ClientOrderId(row["clientOrderId"]))
        if (
            str(native.account_id) != str(account_id)
            or native.instrument_id != instrument_id
            or cache.position_id(native.client_order_id) is None
        ):
            raise AdapterRecoveryError("native account/instrument/position lineage mismatch")
        if (
            row["symbol"] != "BTCUSDT"
            or row["type"] != "LIMIT"
            or row["timeInForce"] != "GTC"
            or row.get("orderListId", -1) != -1
        ):
            raise AdapterRecoveryError("unsupported order instruction")
        if (
            row["side"] != native.side.name
            or _decimal(row["origQty"]) != native.quantity.as_decimal()
            or _decimal(row["price"]) != native.price.as_decimal()
        ):
            raise AdapterRecoveryError("original order differs from native intent")
        if native.venue_order_id is not None and str(native.venue_order_id) != str(row["orderId"]):
            raise AdapterRecoveryError("venue order ID changed")
        if row["status"] not in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED"}:
            raise AdapterRecoveryError("unsupported authoritative terminal state")
        if native.is_closed and native.status.name != row["status"]:
            raise AdapterRecoveryError("terminal native order cannot change state")
        for key in ("time", "updateTime"):
            if type(row[key]) is not int or not 0 < row[key] * 1_000_000 <= now_ns:
                raise AdapterRecoveryError("invalid order timestamp")
        history = sorted(grouped[row["orderId"]], key=lambda t: (t["time"], t["id"]))
        qty = sum((_decimal(t["qty"]) for t in history), D("0"))
        notional = sum((_decimal(t["quoteQty"]) for t in history), D("0"))
        if (
            qty != _decimal(row["executedQty"])
            or notional != _decimal(row["cummulativeQuoteQty"])
            or qty > native.quantity.as_decimal()
            or qty < native.filled_qty.as_decimal()
        ):
            raise AdapterRecoveryError("complete fill history required; inference forbidden")
        if (
            (row["status"] == "FILLED" and qty != native.quantity.as_decimal())
            or (row["status"] == "NEW" and qty)
            or (row["status"] == "PARTIALLY_FILLED" and not 0 < qty < native.quantity.as_decimal())
        ):
            raise AdapterRecoveryError("order status/fill quantity conflict")
        for trade in history:
            if (
                trade["isBuyer"] != (row["side"] == "BUY")
                or not row["time"] <= trade["time"] <= row["updateTime"]
            ):
                raise AdapterRecoveryError("trade side/time conflicts with order")
        indexed = {str(t["id"]): t for t in history}
        for event in native.events:
            if not isinstance(event, OrderFilled):
                continue
            t = indexed.get(str(event.trade_id))
            if t is None or (
                _decimal(t["qty"]),
                _decimal(t["price"]),
                _decimal(t["commission"]),
                t["commissionAsset"],
            ) != (
                event.last_qty.as_decimal(),
                event.last_px.as_decimal(),
                event.commission.as_decimal(),
                event.commission.currency.code,
            ):
                raise AdapterRecoveryError("historical native fill conflict")
        parsed = msgspec.convert(row, type=BinanceOrder)
        order_reports.append(
            parsed.parse_to_order_status_report(
                account_id=account_id,
                instrument_id=instrument_id,
                report_id=UUID4(),
                enum_parser=BinanceSpotEnumParser(),
                treat_expired_as_canceled=False,
                ts_init=now_ns,
            )
        )
        fills.extend(
            msgspec.convert(t, type=BinanceUserTrade).parse_to_fill_report(
                account_id=account_id,
                instrument_id=instrument_id,
                report_id=UUID4(),
                ts_init=now_ns,
            )
            for t in history
        )
    mass.add_order_reports(order_reports)
    mass.add_fill_reports(fills)
    return mass


def reconcile_binance_reports(engine, cache, *, account_id, orders, trades, now_ns):
    """Offline native mutation with exact order/fill postconditions.

    On any failure discard the isolated cache; reconciliation is not transactional.
    Account balances, locks and risk history still require independent qualification.
    """
    if not isinstance(engine, EvidenceOnlyExecutionEngine):
        raise AdapterRecoveryError("isolated evidence engine required")
    reports = prepare_binance_reports(
        cache,
        account_id=account_id,
        orders=orders,
        trades=trades,
        now_ns=now_ns,
    )
    if not engine._reconcile_execution_mass_status(reports):
        raise AdapterRecoveryError("native reconciliation failed; discard isolated cache")
    for row in orders:
        order = cache.order(ClientOrderId(row["clientOrderId"]))
        expected_status = "ACCEPTED" if row["status"] == "NEW" else row["status"]
        if order.status.name != expected_status or order.filled_qty.as_decimal() != _decimal(
            row["executedQty"]
        ):
            raise AdapterRecoveryError("native order postcondition failed; discard isolated cache")
        actual = [event for event in order.events if isinstance(event, OrderFilled)]
        expected = {str(t["id"]): t for t in trades if t["orderId"] == row["orderId"]}
        if len(actual) != len(expected) or {str(e.trade_id) for e in actual} != set(expected):
            raise AdapterRecoveryError("native fill coverage failed; discard isolated cache")
        for event in actual:
            t = expected[str(event.trade_id)]
            if (
                event.last_qty.as_decimal(),
                event.last_px.as_decimal(),
                event.commission.as_decimal(),
                event.commission.currency.code,
            ) != (
                _decimal(t["qty"]),
                _decimal(t["price"]),
                _decimal(t["commission"]),
                t["commissionAsset"],
            ):
                raise AdapterRecoveryError(
                    "native fill postcondition failed; discard isolated cache"
                )


class EvidenceOnlyExecutionEngine(LiveExecutionEngine):
    """Native reconciliation only; no clients, live clock or inferred fills."""

    def __init__(self, *args, **kwargs):
        if not isinstance(kwargs.get("clock"), TestClock):
            raise AdapterRecoveryError("offline native reconciliation requires TestClock")
        super().__init__(*args, **kwargs)

    def register_client(self, client):
        raise AdapterRecoveryError("execution clients forbidden in offline reconciliation")

    def register_default_client(self, client):
        raise AdapterRecoveryError("execution clients forbidden in offline reconciliation")

    def register_venue_routing(self, client, venue=None):
        raise AdapterRecoveryError("execution clients forbidden in offline reconciliation")

    def execute(self, command):
        raise AdapterRecoveryError("trading commands forbidden in offline reconciliation")

    def _generate_inferred_fill(self, *args, **kwargs):
        raise AdapterRecoveryError("inferred fills forbidden")

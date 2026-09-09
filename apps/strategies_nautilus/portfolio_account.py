"""Read-only Binance account evidence and exact native-state reconciliation.

Captured JSON can prove agreement, not authentication or an atomic exchange cut.
The signed collector below is opt-in and never submits/cancels orders. Deployment
still requires a synchronized user-stream barrier and runtime policy approval.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal as D

from nautilus_trader.model.events import OrderFilled

from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    VenueInputError,
    VenueRulesEvidence,
    _decimal,
    _fresh,
    _unique_object,
)


@dataclass(frozen=True)
class AccountAnchor:
    """Explicit dedicated-account baseline; never inferred from today's balance."""

    venue_uid: str
    native_account_id: str
    start_ns: int
    quote: D
    base: D = D("0")


@dataclass(frozen=True)
class AccountEvidence:
    account: CapturedResponse
    orders: CapturedResponse  # complete allOrders since anchor, including terminal orders
    trades: CapturedResponse  # complete myTrades since anchor, including commissions
    open_orders: CapturedResponse  # account-wide, not symbol-filtered
    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class AccountReconciliation:
    checks_passed: bool
    reasons: tuple[str, ...]
    response_sha256: tuple[tuple[str, str], ...]
    evidence_ts_ns: int
    runtime_ready: bool = False  # REST agreement is not an atomic live admission permit


def native_account_view(account, orders, positions, intents, anchor):
    """Normalize native evidence and verify lineage/fees/position/cash conservation."""
    if (
        str(account.id) != anchor.native_account_id
        or anchor.base != 0
        or account.type.name != "CASH"
    ):
        raise VenueInputError("dedicated native account / flat baseline mismatch")
    if not anchor.quote.is_finite() or anchor.quote <= 0:
        raise VenueInputError("invalid account anchor")
    native_orders = {str(o.client_order_id): o for o, _ in orders}
    if len(native_orders) != len(orders) or set(native_orders) != set(intents):
        raise VenueInputError("unknown native order or uncertain prepared submission")
    balances = {
        c.code: (v.total.as_decimal(), v.free.as_decimal(), v.locked.as_decimal())
        for c, v in account.balances().items()
    }
    if set(balances) != {"BTC", "USDT"}:
        raise VenueInputError("dedicated BTC/USDT balances required")
    quantities, expected, order_rows, trades = (
        {},
        {"BTC": anchor.base, "USDT": anchor.quote},
        {},
        {},
    )
    position_sleeves = {}
    trade_ids = set()
    venue_order_ids = set()
    for order, position_id in orders:
        oid = str(order.client_order_id)
        intent = intents[oid]
        if (
            str(order.instrument_id) != "BTCUSDT.BINANCE"
            or str(order.account_id) != anchor.native_account_id
            or str(position_id) != intent["position_id"]
            or order.side.name != intent["side"]
            or str(order.strategy_id) != "PORTFOLIO-FIXTURE-PF"
            or order.order_type.name != "LIMIT"
            or order.time_in_force.name != "GTC"
            or order.quantity.as_decimal() != D(intent["quantity"])
            or order.price.as_decimal() != D(intent["price"])
            or order.tags != [f"signal_id:{intent['signal_id']}", f"sleeve:{intent['sleeve']}"]
        ):
            raise VenueInputError("native order lineage mismatch")
        if order.status.name not in {
            "ACCEPTED",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "EXPIRED",
            "REJECTED",
        }:
            raise VenueInputError("uncertain native submission/cancellation")
        if not order.venue_order_id:
            raise VenueInputError("missing authoritative venue order ID")
        if str(order.venue_order_id) in venue_order_ids:
            raise VenueInputError("duplicate native venue order ID")
        venue_order_ids.add(str(order.venue_order_id))
        pid = str(position_id)
        if pid in position_sleeves and position_sleeves[pid] != intent["sleeve"]:
            raise VenueInputError("ambiguous native sleeve ownership")
        position_sleeves[pid] = intent["sleeve"]
        qty, notional = D("0"), D("0")
        for event in order.events:
            if not isinstance(event, OrderFilled):
                continue
            if event.ts_event < anchor.start_ns or str(event.position_id) != pid:
                raise VenueInputError("fill outside anchor or native position")
            q, p, fee = (
                event.last_qty.as_decimal(),
                event.last_px.as_decimal(),
                event.commission.as_decimal(),
            )
            currency = event.commission.currency.code
            if q <= 0 or p <= 0 or fee < 0 or currency not in {"BTC", "USDT"}:
                raise VenueInputError("unsupported fill or fee")
            if order.side.name == "SELL" and currency != "USDT":
                raise VenueInputError("unsupported SELL fee currency")
            key = (str(order.venue_order_id), str(event.trade_id))
            if key[1] in trade_ids:
                raise VenueInputError("duplicate native trade")
            trade_ids.add(key[1])
            trades[key] = (q, p, q * p, fee, currency, order.side.name == "BUY")
            direction = D("1") if order.side.name == "BUY" else D("-1")
            quantities[pid] = (
                quantities.get(pid, D("0")) + direction * q - (fee if currency == "BTC" else 0)
            )
            expected["BTC"] += direction * q
            expected["USDT"] -= direction * q * p
            expected[currency] -= fee
            qty += q
            notional += q * p
        if qty != order.filled_qty.as_decimal():
            raise VenueInputError("incomplete native fill history")
        status = "NEW" if order.status.name == "ACCEPTED" else order.status.name
        order_rows[oid] = (
            str(order.venue_order_id),
            order.side.name,
            order.quantity.as_decimal(),
            qty,
            order.price.as_decimal(),
            notional,
            status,
        )
    actual = {str(p.id): p.quantity.as_decimal() for p in positions}
    if len(actual) != len(positions) or actual != quantities:
        raise VenueInputError("native position and commission evidence mismatch")
    if (
        any(q < 0 for q in quantities.values())
        or sum(quantities.values(), D("0")) != balances["BTC"][0]
    ):
        raise VenueInputError("unattributed native base inventory")
    if any(expected[c] != balances[c][0] for c in expected):
        raise VenueInputError("native balances disagree with anchor and fills")
    return balances, order_rows, trades


def reconcile_account(
    evidence,
    *,
    anchor,
    native,
    intents,
    now_ns,
    max_age_ns,
    venue: VenueRulesEvidence | None = None,
):
    """Require exact native/venue agreement; no tolerance, state repair or orders."""
    hashes, timestamps = [], []
    try:
        if evidence.start_ns != anchor.start_ns or not anchor.start_ns <= evidence.end_ns <= now_ns:
            raise VenueInputError("account history coverage mismatch")
        if type(now_ns) is not int or type(max_age_ns) is not int or max_age_ns <= 0:
            raise VenueInputError("invalid account evaluation time")
        payloads = {}
        for name in ("account", "orders", "trades", "open_orders"):
            response = getattr(evidence, name)
            _fresh(response.received_ns, now_ns, max_age_ns)
            if response.account_id != anchor.venue_uid:
                raise VenueInputError("private account identity mismatch")
            if name in {"orders", "trades"} and response.requested_symbol != "BTCUSDT":
                raise VenueInputError("account history symbol mismatch")
            if name == "open_orders" and response.requested_symbol is not None:
                raise VenueInputError("account-wide open orders required")
            hashes.append((name, hashlib.sha256(response.body.encode()).hexdigest()))
            timestamps.append(response.received_ns)
            payloads[name] = json.loads(response.body, object_pairs_hook=_unique_object)
        _fresh(evidence.end_ns, now_ns, max_age_ns)
        timestamps.append(evidence.end_ns)
        if venue is not None:
            if (
                venue.account_id != anchor.venue_uid
                or venue.rules.instrument_id != "BTCUSDT.BINANCE"
            ):
                raise VenueInputError("venue/account attachment mismatch")
            _fresh(venue.rules.ts_ns, now_ns, max_age_ns)
            timestamps.append(venue.rules.ts_ns)
            hashes.extend(venue.response_sha256)
        account = payloads["account"]
        if str(account["uid"]) != anchor.venue_uid or account["accountType"] != "SPOT":
            raise VenueInputError("venue account UID/type mismatch")
        if account["canTrade"] is not True or "SPOT" not in account["permissions"]:
            raise VenueInputError("account trading permission absent")
        balances = {}
        for row in account["balances"]:
            asset = row["asset"]
            if asset in balances:
                raise VenueInputError("duplicate account asset")
            free, locked = _decimal(row["free"]), _decimal(row["locked"])
            balances[asset] = (free + locked, free, locked)
        if any(total for asset, (total, _, _) in balances.items() if asset not in {"BTC", "USDT"}):
            raise VenueInputError("unexpected funded account asset")
        balances = {c: balances[c] for c in ("BTC", "USDT")}
        order_rows, venue_ids = {}, set()
        for row in payloads["orders"]:
            oid, vid = row["clientOrderId"], str(row["orderId"])
            if oid in order_rows or vid in venue_ids:
                raise VenueInputError("duplicate venue order")
            venue_ids.add(vid)
            if row["symbol"] != "BTCUSDT" or row["type"] != "LIMIT" or row["timeInForce"] != "GTC":
                raise VenueInputError("unsupported venue order")
            if not anchor.start_ns <= row["time"] * 1_000_000 <= evidence.end_ns:
                raise VenueInputError("venue order outside history coverage")
            order_rows[oid] = (
                vid,
                row["side"],
                _decimal(row["origQty"]),
                _decimal(row["executedQty"]),
                _decimal(row["price"]),
                _decimal(row["cummulativeQuoteQty"]),
                row["status"],
            )
        open_ids = set()
        for row in payloads["open_orders"]:
            oid = row["clientOrderId"]
            if oid in open_ids or row not in payloads["orders"]:
                raise VenueInputError("unknown/duplicate/drifting account-wide open order")
            open_ids.add(oid)
        if open_ids != {
            oid for oid, row in order_rows.items() if row[-1] in {"NEW", "PARTIALLY_FILLED"}
        }:
            raise VenueInputError("incomplete open-order coverage")
        trades = {}
        trade_ids = set()
        for row in payloads["trades"]:
            key = (str(row["orderId"]), str(row["id"]))
            if key[1] in trade_ids or key[0] not in venue_ids or row["symbol"] != "BTCUSDT":
                raise VenueInputError("unknown or duplicate venue trade")
            trade_ids.add(key[1])
            if (
                type(row["isBuyer"]) is not bool
                or not anchor.start_ns <= row["time"] * 1_000_000 <= evidence.end_ns
            ):
                raise VenueInputError("invalid venue trade coverage/side")
            trades[key] = (
                _decimal(row["qty"]),
                _decimal(row["price"]),
                _decimal(row["quoteQty"]),
                _decimal(row["commission"]),
                row["commissionAsset"],
                row["isBuyer"],
            )
        actual = native_account_view(*native, intents, anchor)
        for label, local, remote in zip(
            ("balances", "orders", "trades"), actual, (balances, order_rows, trades), strict=True
        ):
            if local != remote:
                raise VenueInputError(f"native/venue {label} mismatch")
        return AccountReconciliation(True, (), tuple(hashes), min(timestamps))
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, VenueInputError) else "malformed account evidence"
        return AccountReconciliation(False, (reason,), tuple(hashes), min(timestamps, default=0))

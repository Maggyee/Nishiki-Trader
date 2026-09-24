"""Fixed signed openOrders fixture and exact native order-status receipts."""

from __future__ import annotations

import base64
import json
import os
import re
from decimal import Decimal

PROFILE = "portfolio.installed_native_orders_receipt.v1"
SELECTION_PROFILE = "portfolio.installed_signed_orders_request.v1"
TLS_PROFILE = "portfolio.installed_signed_orders_tls.v1"
ENDPOINT = "https://rest.fixture.invalid:23456/api/v3/openOrders"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT")
FIELDS = {
    "symbol",
    "orderId",
    "clientOrderId",
    "price",
    "origQty",
    "executedQty",
    "cummulativeQuoteQty",
    "status",
    "timeInForce",
    "type",
    "side",
    "time",
    "updateTime",
    "isWorking",
    "icebergQty",
    "stopPrice",
    "orderListId",
    "origQuoteOrderQty",
}


def amount(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", value) is None:
        raise ValueError("orders_decimal_required")
    return Decimal(value)


def expected_result(payload):
    value = json.loads(payload)
    raw = base64.b64decode(value["response_b64"], validate=True)
    orders = json.loads(raw.split(b"\r\n\r\n", 1)[1])
    if not isinstance(orders, list) or len(orders) > 16:
        raise ValueError("fixture_open_orders_required")
    seen, clients, result = set(), set(), []
    for row in orders:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("fixture_order_fields")
        if (
            row["symbol"] not in SYMBOLS
            or type(row["orderId"]) is not int
            or not 0 < row["orderId"] < 2**63
            or not isinstance(row["clientOrderId"], str)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,36}", row["clientOrderId"]) is None
            or row["type"] != "LIMIT"
            or row["timeInForce"] != "GTC"
            or row["side"] not in {"BUY", "SELL"}
            or row["status"] not in {"NEW", "PARTIALLY_FILLED"}
            or row["isWorking"] is not True
            or type(row["orderListId"]) is not int
            or row["orderListId"] != -1
            or any(type(row[k]) is not int for k in ("time", "updateTime"))
            or not 0
            < row["time"]
            <= row["updateTime"]
            <= value["body_receipt"]["utc_ns"] // 1_000_000
        ):
            raise ValueError("fixture_order_identity_type_or_time")
        key = row["symbol"], row["orderId"]
        if key in seen or row["clientOrderId"] in clients:
            raise ValueError("fixture_duplicate_order")
        seen.add(key)
        clients.add(row["clientOrderId"])
        price, quantity, filled, quote = (
            amount(row[k]) for k in ("price", "origQty", "executedQty", "cummulativeQuoteQty")
        )
        if (
            price <= 0
            or quantity <= 0
            or not 0 <= filled < quantity
            or (row["status"] == "NEW" and (filled != 0 or quote != 0))
            or (row["status"] == "PARTIALLY_FILLED" and (filled <= 0 or quote <= 0))
            or any(amount(row[k]) != 0 for k in ("icebergQty", "stopPrice", "origQuoteOrderQty"))
        ):
            raise ValueError("fixture_order_quantity_or_status")
        # Retain every selected exchange field; no trade/fill history is inferred.
        result.append({**row, "remainingQty": format(quantity - filled, "f")})
    return {
        "profile": PROFILE,
        "native_version": "1.226.0",
        "account_uid": 41001,
        "orders": sorted(result, key=lambda r: (r["symbol"], r["orderId"])),
        "tls_sha256": value["tls_sha256"],
        "header_receipt": value["header_receipt"],
        "body_receipt": value["body_receipt"],
        "qualified_for_execution": False,
    }


def validate_native(payload):
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core import nautilus_pyo3 as native

    if native.NAUTILUS_VERSION != "1.226.0":
        raise ValueError("native_version_changed")
    result = expected_result(payload)
    for row in result["orders"]:
        quantity = native.Quantity(Decimal(row["origQty"]), 8)
        filled = native.Quantity(Decimal(row["executedQty"]), 8)
        price = native.Price(Decimal(row["price"]), 8)
        if any(
            actual.as_decimal() != Decimal(row[key])
            for actual, key in ((quantity, "origQty"), (filled, "executedQty"), (price, "price"))
        ):
            raise ValueError("native_orders_rounding_refused")
        report = native.OrderStatusReport(
            account_id=native.AccountId("BINANCE-41001"),
            instrument_id=native.InstrumentId.from_str(row["symbol"] + ".BINANCE"),
            venue_order_id=native.VenueOrderId(str(row["orderId"])),
            client_order_id=native.ClientOrderId(row["clientOrderId"]),
            order_side=native.OrderSide.BUY if row["side"] == "BUY" else native.OrderSide.SELL,
            order_type=native.OrderType.LIMIT,
            time_in_force=native.TimeInForce.GTC,
            order_status=native.OrderStatus.ACCEPTED
            if row["status"] == "NEW"
            else native.OrderStatus.PARTIALLY_FILLED,
            quantity=quantity,
            filled_qty=filled,
            price=price,
            ts_accepted=row["time"] * 1_000_000,
            ts_last=row["updateTime"] * 1_000_000,
            ts_init=result["body_receipt"]["utc_ns"],
        )
        mapped = report.to_dict()
        expected = {
            "account_id": "BINANCE-41001",
            "instrument_id": row["symbol"] + ".BINANCE",
            "venue_order_id": str(row["orderId"]),
            "client_order_id": row["clientOrderId"],
            "order_side": row["side"],
            "order_type": "LIMIT",
            "time_in_force": "GTC",
            "order_status": "ACCEPTED" if row["status"] == "NEW" else "PARTIALLY_FILLED",
            "ts_accepted": row["time"] * 1_000_000,
            "ts_last": row["updateTime"] * 1_000_000,
            "ts_init": result["body_receipt"]["utc_ns"],
        }
        if (
            not report.is_open
            or any(mapped[k] != v for k, v in expected.items())
            or any(
                Decimal(mapped[k]) != Decimal(row[source])
                for k, source in (
                    ("quantity", "origQty"),
                    ("filled_qty", "executedQty"),
                    ("price", "price"),
                )
            )
        ):
            raise ValueError("native_orders_mapping_changed")
    return result


def view(account, *, index=4):
    """Closed internal specialization; no caller-selected URL, method or operation."""
    if index not in {4, 5}:
        raise ValueError("signed_orders_fixed_index")

    class OrdersContract(account["AccountContract"]):
        SELECTION_PROFILE = SELECTION_PROFILE
        TLS_PROFILE = TLS_PROFILE
        ENDPOINT = ENDPOINT
        LEDGER_PROFILE = "portfolio.fixture_signed_orders_tls_ledger.v1"
        CHALLENGE_INDEX = index
        PATH = "/api/v3/openOrders"
        SELECTION_FILE = "orders-request.json"

    def ledger_view(module):
        return account["ledger_view"](
            module, profile=module.ORDERS_PROFILE, scope=module.ORDERS_SCOPE
        )

    def authorize(collector, ledger, authority, requests):
        return account["authorize"](
            collector, ledger, authority, requests, contract_type=OrdersContract
        )

    def launch(authority, sources, launcher, runtime):
        return account["launch"](
            authority,
            sources,
            launcher,
            runtime,
            orders=True,
            **({"request_index": index} if index == 5 else {}),
        )

    return {
        "PROFILE": PROFILE,
        "SELECTION_PROFILE": SELECTION_PROFILE,
        "AccountContract": OrdersContract,
        "ledger_view": ledger_view,
        "rates_view": account["rates_view"],
        "transport_view": account["transport_view"],
        "authorize": authorize,
        "launch": launch,
        "expected_result": expected_result,
        "validate_native": validate_native,
    }


def child_loop(fd, parent):
    globals()["ACCOUNT"]["child_loop"](fd, parent, index=4, native=validate_native)

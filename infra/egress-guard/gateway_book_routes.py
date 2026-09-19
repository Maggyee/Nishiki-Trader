"""Fixed bookTicker receipt and same-run fixture routes; no event-time or equity claim."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from decimal import Decimal
from fractions import Fraction

PROFILE = "portfolio.installed_native_books_receipt.v1"
SELECTION_PROFILE = "portfolio.installed_books_request.v1"
TLS_PROFILE = "portfolio.installed_books_tls.v1"
ENDPOINT = "https://rest.fixture.invalid:23456/api/v3/ticker/bookTicker"
ASSETS = ("BNB", "BTC", "ETH", "USDT")
FIELDS = {"symbol", "bidPrice", "bidQty", "askPrice", "askQty"}


def amount(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", value) is None:
        raise ValueError("books_decimal_required")
    return Decimal(value)


def body(payload):
    value = json.loads(payload)
    raw = base64.b64decode(value["response_b64"], validate=True)
    return value, json.loads(raw.split(b"\r\n\r\n", 1)[1])


def expected_result(payload):
    value, books = body(payload)
    if not isinstance(books, list) or not 1 <= len(books) <= 16:
        raise ValueError("fixture_books_required")
    seen = set()
    for row in books:
        if (
            not isinstance(row, dict)
            or set(row) != FIELDS
            or not isinstance(row["symbol"], str)
            or re.fullmatch(r"[A-Z0-9]{2,32}", row["symbol"]) is None
            or row["symbol"] in seen
        ):
            raise ValueError("fixture_book_identity")
        seen.add(row["symbol"])
        for key in FIELDS - {"symbol"}:
            amount(row[key])
    return {
        "profile": PROFILE,
        "native_version": "1.226.0",
        "books": sorted(books, key=lambda row: row["symbol"]),
        "tls_sha256": value["tls_sha256"],
        "header_receipt": value["header_receipt"],
        "body_receipt": value["body_receipt"],
        "individual_quote_age_verified": False,
        "qualified_for_execution": False,
    }


def validate_native(payload):
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core import nautilus_pyo3 as native

    if native.NAUTILUS_VERSION != "1.226.0":
        raise ValueError("native_version_changed")
    result = expected_result(payload)
    for row in result["books"]:
        for key in FIELDS - {"symbol"}:
            value = amount(row[key])
            mapped = (native.Price if key.endswith("Price") else native.Quantity)(value, 8)
            if mapped.as_decimal() != value:
                raise ValueError("native_books_rounding_refused")
    # REST bookTicker has no event timestamp; never fabricate a QuoteTick.
    return result


def derive(metadata_payload, account, books):
    """Bounded direct-then-two-hop routes from originals; rational capacity arithmetic."""
    _, info = body(metadata_payload)
    definitions, graph, unavailable = {}, {asset: [] for asset in ASSETS}, []
    symbols = info.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 16:
        raise ValueError("route_metadata_required")
    for row in symbols:
        if (
            row.get("baseAsset") not in ASSETS
            or row.get("quoteAsset") not in ASSETS
            or row["baseAsset"] == row["quoteAsset"]
            or row.get("symbol") != row["baseAsset"] + row["quoteAsset"]
            or row["symbol"] in definitions
            or row.get("baseAssetPrecision") != 8
            or row.get("quoteAssetPrecision") != 8
            or not isinstance(row.get("status"), str)
            or type(row.get("isSpotTradingAllowed")) is not bool
        ):
            raise ValueError("route_symbol_definition")
        definitions[row["symbol"]] = row
    seen = set()
    for book in books["books"]:
        name = book["symbol"]
        if name not in definitions or name in seen:
            raise ValueError("route_unbound_or_duplicate_book")
        seen.add(name)
        row = definitions[name]
        bid, bqty, ask, aqty = (
            Fraction(amount(book[k])) for k in ("bidPrice", "bidQty", "askPrice", "askQty")
        )
        if row["status"] != "TRADING" or not row["isSpotTradingAllowed"]:
            unavailable.append({"symbol": name, "reason": "not_spot_trading"})
            continue
        if bid > 0 and ask > 0 and bid > ask:
            unavailable.append({"symbol": name, "reason": "crossed_book"})
            continue
        if bid > 0 and bqty > 0:
            graph[row["baseAsset"]].append((row["quoteAsset"], name, "bid", bid, bqty))
        else:
            unavailable.append({"symbol": name, "reason": "empty_bid"})
        if ask > 0 and aqty > 0:
            graph[row["quoteAsset"]].append(
                (row["baseAsset"], name, "inverse_ask", 1 / ask, aqty * ask)
            )
        else:
            unavailable.append({"symbol": name, "reason": "empty_ask"})
    unavailable.extend(
        {"symbol": name, "reason": "missing_book"} for name in sorted(set(definitions) - seen)
    )
    rows, selected = [], set()
    if account["account_uid"] != 41001 or [r["currency"] for r in account["balances"]] != list(
        ASSETS
    ):
        raise ValueError("route_account_required")
    for balance in account["balances"]:
        asset = balance["currency"]
        quantity = Fraction(amount(balance["free"])) + Fraction(amount(balance["locked"]))
        paths = [(e,) for e in graph[asset] if e[0] == "USDT"]
        if not paths:
            paths = [
                (e, last)
                for e in graph[asset]
                if e[0] in ASSETS and e[0] not in {asset, "USDT"}
                for last in graph[e[0]]
                if last[0] == "USDT"
            ]
        path = ()
        status = (
            "quote_asset" if asset == "USDT" else "zero_balance" if quantity == 0 else "selected"
        )
        if status == "selected":
            if not paths:
                raise ValueError("route_nonzero_asset_unpriced")
            path = min(paths, key=lambda p: (len(p), tuple(e[:3] for e in p)))
        converted, audit = quantity, []
        for destination, name, side, rate, capacity in path:
            if converted > capacity:
                raise ValueError("route_top_book_insufficient")
            audit.append({"symbol": name, "to_asset": destination, "side": side})
            converted *= rate
            selected.add(name)
        rows.append(
            {
                "asset": asset,
                "free": balance["free"],
                "locked": balance["locked"],
                "status": status,
                "path": audit,
            }
        )
    if len(selected) > 3:
        raise ValueError("route_union_exceeds_cap")
    return {
        "policy": "fixture_direct_then_two_hops_v1",
        "assets": rows,
        "symbols": sorted(selected),
        "unavailable_books": sorted(unavailable, key=lambda row: (row["symbol"], row["reason"])),
        "metadata_tls_sha256": json.loads(metadata_payload)["tls_sha256"],
        "account_tls_sha256": account["tls_sha256"],
        "books_tls_sha256": books["tls_sha256"],
        "metadata_payload_sha256": hashlib.sha256(metadata_payload).hexdigest(),
        "fixed_at": books["body_receipt"],
        "individual_quote_age_verified": False,
        "valuation_qualified": False,
        "dispatch_authorized": False,
    }


def view(account):
    class BooksContract(account["AccountContract"]):
        SELECTION_PROFILE = SELECTION_PROFILE
        TLS_PROFILE = TLS_PROFILE
        ENDPOINT = ENDPOINT
        LEDGER_PROFILE = "portfolio.fixture_books_tls_ledger.v1"
        CHALLENGE_INDEX = 8
        PATH = "/api/v3/ticker/bookTicker"
        SELECTION_FILE = "books-request.json"

    def ledger_view(module):
        return account["ledger_view"](
            module, profile=module.BOOKS_PROFILE, scope=module.BOOKS_SCOPE
        )

    def authorize(collector, ledger, authority, requests):
        return account["authorize"](
            collector, ledger, authority, requests, contract_type=BooksContract
        )

    def launch(authority, sources, launcher, runtime):
        return account["launch"](authority, sources, launcher, runtime, books=True)

    return {
        "PROFILE": PROFILE,
        "SELECTION_PROFILE": SELECTION_PROFILE,
        "AccountContract": BooksContract,
        "ledger_view": ledger_view,
        "rates_view": account["rates_view"],
        "transport_view": account["transport_view"],
        "authorize": authorize,
        "launch": launch,
        "expected_result": expected_result,
        "validate_native": validate_native,
        "derive": derive,
    }


def child_loop(fd, parent):
    globals()["ACCOUNT"]["child_loop"](fd, parent, index=8, native=validate_native)

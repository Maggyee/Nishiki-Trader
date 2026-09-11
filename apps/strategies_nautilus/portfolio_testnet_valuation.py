"""Deterministic full-account indicative marks from selected testnet books.

No orders, assumed stablecoin pegs, historical prices or guessed missing marks.
Top-of-book marks do not establish liquidation value or tick freshness.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext

from apps.strategies_nautilus.portfolio_stream import StreamError
from apps.strategies_nautilus.portfolio_testnet_observation import _name
from apps.strategies_nautilus.portfolio_venue import _decimal

PIVOTS = ("BTC", "ETH", "BNB", "USDC", "FDUSD")


def indicative_valuation(balances, exchange_info, books):
    with localcontext() as context:
        context.prec = 50
        return _value(balances, exchange_info, books)


def _value(balances, info, books):
    symbols = info["symbols"]
    if not isinstance(symbols, list) or not 0 < len(symbols) <= 10000:
        raise StreamError("bounded symbol metadata required")
    if not isinstance(books, list) or not 0 < len(books) <= 10000:
        raise StreamError("bounded book snapshot required")
    definitions, seen_books, unavailable, graph = {}, set(), [], defaultdict(list)
    for row in symbols:
        symbol = _name(row["symbol"])
        if symbol in definitions:
            raise StreamError("duplicate symbol metadata")
        base, quote = _name(row["baseAsset"]), _name(row["quoteAsset"])
        if base == quote or type(row["isSpotTradingAllowed"]) is not bool:
            raise StreamError("invalid spot symbol definition")
        definitions[symbol] = row
    for book in books:
        symbol = _name(book["symbol"])
        if symbol in seen_books or symbol not in definitions:
            raise StreamError("duplicate or unbound book symbol")
        seen_books.add(symbol)
        row = definitions[symbol]
        bid, bid_qty, ask, ask_qty = (
            _decimal(book[k]) for k in ("bidPrice", "bidQty", "askPrice", "askQty")
        )
        if row["status"] != "TRADING" or not row["isSpotTradingAllowed"]:
            unavailable.append({"symbol": symbol, "reason": "not_spot_trading"})
            continue
        if bid > 0 and ask > 0 and bid > ask:
            unavailable.append({"symbol": symbol, "reason": "crossed_book"})
            continue
        base, quote = row["baseAsset"], row["quoteAsset"]
        if bid > 0 and bid_qty > 0:
            graph[base].append((quote, symbol, "bid", bid, bid_qty))
        else:
            unavailable.append({"symbol": symbol, "reason": "empty_bid"})
        if ask > 0 and ask_qty > 0:
            graph[quote].append((base, symbol, "inverse_ask", Decimal(1) / ask, ask_qty * ask))
        else:
            unavailable.append({"symbol": symbol, "reason": "empty_ask"})
    for symbol in sorted(definitions.keys() - seen_books):
        unavailable.append({"symbol": symbol, "reason": "missing_book"})
    rows, unpriced, depth_exceeded = [], [], []
    subtotal = Decimal(0)
    for asset, (free, locked) in sorted(balances.items()):
        quantity = free + locked
        row = {"asset": asset, "free": str(free), "locked": str(locked), "total": str(quantity)}
        if asset == "USDT" or quantity == 0:
            value = quantity if asset == "USDT" else Decimal(0)
            rows.append(
                row | {"mark_usdt": str(value), "path": [], "whole_balance_within_top_book": True}
            )
            subtotal += value
            continue
        paths = [(edge,) for edge in graph[asset] if edge[0] == "USDT"]
        if not paths:
            for edge in graph[asset]:
                if edge[0] in PIVOTS and edge[0] != asset:
                    paths.extend((edge, last) for last in graph[edge[0]] if last[0] == "USDT")
        if not paths:
            unpriced.append(asset)
            rows.append(row | {"mark_usdt": None, "path": [], "reason": "no_supported_quote_path"})
            continue
        # Fixed shortest-path/lexical identity priority, never the best price.
        path = min(paths, key=lambda p: (len(p), tuple((e[0], e[1], e[2]) for e in p)))
        converted, depth_ok, audit = quantity, True, []
        for destination, symbol, side, rate, capacity in path:
            depth_ok = depth_ok and converted <= capacity
            audit.append(
                {
                    "symbol": symbol,
                    "to_asset": destination,
                    "side": side,
                    "rate": str(rate),
                    "source_capacity": str(capacity),
                }
            )
            converted *= rate
        if not depth_ok:
            depth_exceeded.append(asset)
        subtotal += converted
        rows.append(
            row
            | {
                "mark_usdt": str(converted),
                "path": audit,
                "whole_balance_within_top_book": depth_ok,
            }
        )
    return {
        "method": "direct_then_two_hops_v1",
        "pivots": list(PIVOTS),
        "assets": rows,
        "assets_recorded": len(rows),
        "priced_assets": len(rows) - len(unpriced),
        "unpriced_assets": unpriced,
        "depth_exceeded_assets": depth_exceeded,
        "unavailable_books": sorted(unavailable, key=lambda row: row["symbol"]),
        "priced_subtotal_usdt": str(subtotal),
        "full_indicative_mark_usdt": None if unpriced else str(subtotal),
        "all_assets_priced": not unpriced,
        "individual_quote_age_verified": False,
        "liquidation_value_verified": False,
        "valuation_qualified": False,
    }

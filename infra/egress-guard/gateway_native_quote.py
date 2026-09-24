"""Fixture snapshot book and native QuoteTick receipts after socket revocation.

The root-side expected result uses stdlib only. The dedicated UID constructs
Nautilus L2 books and quotes from the same validated original snapshot/deltas.
Neither result establishes a stream fence or a live price.
"""

from __future__ import annotations

import base64
import os
from decimal import Decimal

MAX_AGE_NS = 5_000_000_000


def books(payload, result, market, snapshot):
    value = market["decode"](payload)
    output = []
    for anchor, item in zip(result["anchors"], value["snapshots"], strict=True):
        raw = b"".join(base64.b64decode(row["raw_b64"], validate=True) for row in item["chunks"])
        depth = snapshot["response"](raw, market)
        symbol = anchor["symbol"]
        if (
            item["symbol"] != symbol
            or market["digest"](raw) != anchor["snapshot_sha256"]
            or depth["lastUpdateId"] != anchor["snapshot_last_update_id"]
        ):
            raise ValueError("quote_snapshot_original_changed")
        bids = {Decimal(price): Decimal(size) for price, size in depth["bids"]}
        asks = {Decimal(price): Decimal(size) for price, size in depth["asks"]}
        bid_floor = min(bids) if len(bids) == 100 else None
        ask_ceiling = max(asks) if len(asks) == 100 else None
        active = [
            event
            for event in result["market"]
            if event["symbol"] == symbol and event["last_update_id"] > depth["lastUpdateId"]
        ]
        if [row["original_sha256"] for row in active] != anchor["linked_event_sha256"]:
            raise ValueError("quote_linked_originals_changed")
        previous = depth["lastUpdateId"]
        final = None
        for event in active:
            if not event["first_update_id"] <= previous + 1 <= event["last_update_id"]:
                raise ValueError("quote_increment_gap")
            available = max(anchor["snapshot_receipt"]["utc_ns"], event["receipt"]["utc_ns"])
            event_ns = event["deltas"][-1]["ts_event"]
            if (
                not 0 <= available - event_ns <= MAX_AGE_NS
                or not 0 <= available - anchor["snapshot_receipt"]["utc_ns"] <= MAX_AGE_NS
            ):
                raise ValueError("quote_fixture_age")
            for delta in event["deltas"]:
                order = delta["order"]
                levels = bids if order["side"] == "BUY" else asks
                price, size = Decimal(order["price"]), Decimal(order["size"])
                if delta["action"] == "DELETE":
                    levels.pop(price, None)
                else:
                    levels[price] = size
            if not bids or not asks:
                raise ValueError("quote_empty_book_side")
            bid, ask = max(bids), min(asks)
            if (
                bid >= ask
                or (bid_floor is not None and bid < bid_floor)
                or (ask_ceiling is not None and ask > ask_ceiling)
            ):
                raise ValueError("quote_crossed_or_uncovered_book")
            final = {
                "type": "QuoteTick",
                "instrument_id": symbol + ".BINANCE",
                "bid_price": format(bid, ".8f"),
                "ask_price": format(ask, ".8f"),
                "bid_size": format(bids[bid], ".8f"),
                "ask_size": format(asks[ask], ".8f"),
                "ts_event": event_ns,
                "ts_init": available,
            }
            previous = event["last_update_id"]
        if final is None or previous != anchor["linked_last_update_id"]:
            raise ValueError("quote_final_revision_missing")
        output.append(
            {
                "symbol": symbol,
                "snapshot": depth,
                "anchor": anchor,
                "events": active,
                "quote": final,
            }
        )
    return output


def expected_result(payload, snapshot_result, market, snapshot):
    result = snapshot_result(payload)
    rows = books(payload, result, market, snapshot)
    return {
        **result,
        "profile": snapshot["QUOTE_RECEIPT"],
        "quotes": [row["quote"] for row in rows],
        "bounded_order_book_reconstructed": True,
        "quote_ticks_created": True,
        "stream_fence_verified": False,
        "qualified_for_execution": False,
    }


def validate_native(payload, snapshot_native, market, snapshot):
    if os.geteuid() == 0:
        raise ValueError("quote_native_root_refused")
    from nautilus_trader.core import nautilus_pyo3 as native

    if native.NAUTILUS_VERSION != "1.226.0":
        raise ValueError("quote_native_version_changed")
    expected = expected_result(payload, lambda raw: snapshot_native(raw), market, snapshot)
    rows = books(payload, expected, market, snapshot)
    quotes = []
    for row in rows:
        symbol, depth, anchor = row["symbol"], row["snapshot"], row["anchor"]
        instrument = native.InstrumentId.from_str(symbol + ".BINANCE")
        book = native.OrderBook(instrument, native.BookType.L2_MBP)
        for key, side in (("bids", native.OrderSide.BUY), ("asks", native.OrderSide.SELL)):
            for price, size in depth[key]:
                order = native.BookOrder(
                    side, native.Price(Decimal(price), 8), native.Quantity(Decimal(size), 8), 0
                )
                if order.price.as_decimal() != Decimal(price) or order.size.as_decimal() != Decimal(
                    size
                ):
                    raise ValueError("quote_native_snapshot_rounding")
                book.add(order, 0, depth["lastUpdateId"], anchor["snapshot_receipt"]["utc_ns"])
        for event in row["events"]:
            for source in event["deltas"]:
                values = source["order"]
                order = native.BookOrder(
                    getattr(native.OrderSide, values["side"]),
                    native.Price(Decimal(values["price"]), 8),
                    native.Quantity(Decimal(values["size"]), 8),
                    values["order_id"],
                )
                delta = native.OrderBookDelta(
                    instrument,
                    getattr(native.BookAction, source["action"]),
                    order,
                    source["flags"],
                    source["sequence"],
                    source["ts_event"],
                    source["ts_init"],
                )
                if delta.to_dict() != source:
                    raise ValueError("quote_native_delta_changed")
                book.apply_delta(delta)
        book.check_integrity()
        claim = row["quote"]
        quote = native.QuoteTick(
            instrument,
            book.best_bid_price(),
            book.best_ask_price(),
            book.best_bid_size(),
            book.best_ask_size(),
            claim["ts_event"],
            claim["ts_init"],
        ).to_dict()
        if quote != claim:
            raise ValueError("quote_native_book_or_tick_changed")
        quotes.append(quote)
    if quotes != expected["quotes"]:
        raise ValueError("quote_native_receipt_changed")
    return expected

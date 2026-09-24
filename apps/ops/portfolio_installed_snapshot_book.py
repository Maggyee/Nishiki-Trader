"""Rebuild bounded historical native L2 books from verified installed originals.

This runs in an ordinary project process, never in the installed root controller.
It does not restore a stream fence, certify live freshness or dispatch a request.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from decimal import Decimal
from pathlib import Path

PROFILE = "portfolio.installed_snapshot_book_review.v1"
MAX_AGE_NS = 5_000_000_000


def exact_native(native, kind, value):
    amount = Decimal(value)
    result = kind(amount, 8)
    if result.as_decimal() != amount:
        raise ValueError("snapshot_book_native_rounding")
    return result


def segment(symbol, snapshot, anchor, events, native):
    """Apply only original-linked events; return blockers rather than a partial quote."""
    if (
        anchor["symbol"] != symbol
        or snapshot["lastUpdateId"] != anchor["snapshot_last_update_id"]
        or not anchor["linked_event_sha256"]
    ):
        raise ValueError("snapshot_book_anchor_changed")
    active = [
        row
        for row in events
        if row["symbol"] == symbol and row["last_update_id"] > snapshot["lastUpdateId"]
    ]
    if [row["original_sha256"] for row in active] != anchor["linked_event_sha256"]:
        raise ValueError("snapshot_book_events_changed")
    instrument = native.InstrumentId.from_str(symbol + ".BINANCE")
    book = native.OrderBook(instrument, native.BookType.L2_MBP)
    snapshot_clock = anchor["snapshot_receipt"]["utc_ns"]
    for key, side in (("bids", native.OrderSide.BUY), ("asks", native.OrderSide.SELL)):
        for price, size in snapshot[key]:
            book.add(
                native.BookOrder(
                    side,
                    exact_native(native, native.Price, price),
                    exact_native(native, native.Quantity, size),
                    0,
                ),
                0,
                snapshot["lastUpdateId"],
                snapshot_clock,
            )
    bid_floor = Decimal(snapshot["bids"][-1][0]) if len(snapshot["bids"]) == 100 else None
    ask_ceiling = Decimal(snapshot["asks"][-1][0]) if len(snapshot["asks"]) == 100 else None
    previous = snapshot["lastUpdateId"]
    blockers = set()
    latest_age = None
    availability_ns = snapshot_clock
    bid = ask = None
    for event in active:
        if not event["first_update_id"] <= previous + 1 <= event["last_update_id"]:
            raise ValueError("snapshot_book_revision_gap")
        receipt_ns = event["receipt"]["utc_ns"]
        availability_ns = max(availability_ns, receipt_ns)
        if availability_ns - snapshot_clock > MAX_AGE_NS:
            blockers.add("snapshot_too_old")
        for row in event["deltas"]:
            if (
                row["type"] != "OrderBookDelta"
                or row["instrument_id"] != str(instrument)
                or row["sequence"] != event["last_update_id"]
                or row["ts_init"] != receipt_ns
            ):
                raise ValueError("snapshot_book_delta_identity")
            values = row["order"]
            order = native.BookOrder(
                getattr(native.OrderSide, values["side"]),
                exact_native(native, native.Price, values["price"]),
                exact_native(native, native.Quantity, values["size"]),
                values["order_id"],
            )
            delta = native.OrderBookDelta(
                instrument,
                getattr(native.BookAction, row["action"]),
                order,
                row["flags"],
                row["sequence"],
                row["ts_event"],
                row["ts_init"],
            )
            if delta.to_dict() != row:
                raise ValueError("snapshot_book_native_delta_changed")
            book.apply_delta(delta)
        latest_age = availability_ns - event["deltas"][-1]["ts_event"]
        if not 0 <= latest_age <= MAX_AGE_NS:
            blockers.add("event_time_outside_five_seconds")
        bid, ask = book.best_bid_price(), book.best_ask_price()
        if bid is None:
            blockers.add("empty_bid")
        if ask is None:
            blockers.add("empty_ask")
        if bid is not None and ask is not None:
            if bid.as_decimal() >= ask.as_decimal():
                blockers.add("crossed_book")
            if bid_floor is not None and bid.as_decimal() < bid_floor:
                blockers.add("bid_snapshot_coverage_exhausted")
            if ask_ceiling is not None and ask.as_decimal() > ask_ceiling:
                blockers.add("ask_snapshot_coverage_exhausted")
        previous = event["last_update_id"]
    if previous != anchor["linked_last_update_id"]:
        raise ValueError("snapshot_book_final_revision_changed")
    quote = None
    if not blockers:
        book.check_integrity()
        quote = native.QuoteTick(
            instrument,
            bid,
            ask,
            book.best_bid_size(),
            book.best_ask_size(),
            active[-1]["deltas"][-1]["ts_event"],
            availability_ns,
        ).to_dict()
    return {
        "symbol": symbol,
        "snapshot_last_update_id": snapshot["lastUpdateId"],
        "linked_last_update_id": previous,
        "linked_event_sha256": anchor["linked_event_sha256"],
        "best_bid": str(bid) if bid is not None else None,
        "best_ask": str(ask) if ask is not None else None,
        "last_event_age_at_availability_ns": latest_age,
        "blockers": sorted(blockers),
    }, quote


def review(raw, *, expected_sha256, scenario="snapshot_success"):
    if os.geteuid() == 0:
        raise ValueError("snapshot_book_ordinary_process_required")
    from apps.ops import portfolio_installed_joint_handoff as handoff

    verified = handoff.review(raw, expected_sha256=expected_sha256, scenario=scenario)
    report = handoff.unique_json(raw)
    entry = next(s for s in report["scenarios"] if s["scenario"] == scenario)
    loader, sources = handoff.selected_sources({**entry, "source_sha256": report["source_sha256"]})
    snapshot = loader["load"](sources["gateway_snapshot_ws.py"])
    market = loader["load"](sources["gateway_market_ws.py"])
    native_result = entry["ws_replay"]["native_result"]
    from nautilus_trader.core import nautilus_pyo3 as native

    if native_result["native_version"] != native.NAUTILUS_VERSION:
        raise ValueError("snapshot_book_native_version_changed")
    chunks = {symbol: [] for symbol in verified["symbols"]}
    for line in entry["ws_archive"].splitlines():
        row = json.loads(line)
        if row["kind"] == "snapshot_chunk":
            chunks[row["payload"]["symbol"]].append(row)
    anchors = {row["symbol"]: row for row in native_result["anchors"]}
    if set(anchors) != set(chunks) or any(not rows for rows in chunks.values()):
        raise ValueError("snapshot_book_selected_originals_required")
    results, quotes = [], []
    for symbol, rows in chunks.items():
        anchor = anchors[symbol]
        response_raw = b"".join(base64.b64decode(r["payload"]["raw_b64"]) for r in rows)
        if (
            handoff.digest(response_raw) != anchor["snapshot_sha256"]
            or {key: rows[-1][key] for key in ("utc_ns", "monotonic_ns")}
            != anchor["snapshot_receipt"]
        ):
            raise ValueError("snapshot_book_original_changed")
        depth = snapshot["response"](response_raw, market)
        result, quote = segment(symbol, depth, anchor, native_result["market"], native)
        results.append(result)
        if quote is not None:
            quotes.append(quote)
    complete = len(quotes) == len(results)
    return {
        "schema_version": PROFILE,
        "status": "historical_native_quotes_only" if complete else "blocked_snapshot_book",
        "selected_report_sha256": verified["selected_report_sha256"],
        "snapshot_ws_archive_sha256": verified["snapshot_ws_archive_sha256"],
        "symbols": results,
        "historical_native_quote_ticks": quotes if complete else [],
        "installed_native_quote_receipt": False,
        "stream_fence_verified": False,
        "full_joint_collector_integrated": False,
        "network_admitted": False,
        "trading_admitted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument(
        "--scenario", choices=("snapshot_success", "snapshot_two_hops"), default="snapshot_success"
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            review(
                args.report.read_bytes(), expected_sha256=args.report_sha256, scenario=args.scenario
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

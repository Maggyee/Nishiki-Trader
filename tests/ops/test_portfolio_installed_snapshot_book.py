"""Historical native book reconstruction and fail-closed quote boundaries."""

import copy

import pytest
from nautilus_trader.core import nautilus_pyo3 as native

from apps.ops import portfolio_installed_snapshot_book as book

SYMBOL = "BTCUSDT"
EVENT_NS = 1_800_000_000_000_000_000
RECEIPT_NS = EVENT_NS + 100_000_000
SNAPSHOT_NS = EVENT_NS + 300_000_000


def delta(side, action, price, size, *, sequence=103, ts_event=EVENT_NS):
    order = native.BookOrder(
        getattr(native.OrderSide, side),
        native.Price.from_str(price),
        native.Quantity.from_str(size),
        0,
    )
    return native.OrderBookDelta(
        native.InstrumentId.from_str(SYMBOL + ".BINANCE"),
        getattr(native.BookAction, action),
        order,
        128,
        sequence,
        ts_event,
        RECEIPT_NS,
    ).to_dict()


def evidence(*, two_bids=True):
    snapshot = {
        "lastUpdateId": 101,
        "bids": [["100.00000000", "1.00000000"]]
        + ([["99.00000000", "3.00000000"]] if two_bids else []),
        "asks": [["101.00000000", "2.00000000"]],
    }
    anchor = {
        "symbol": SYMBOL,
        "snapshot_last_update_id": 101,
        "linked_last_update_id": 103,
        "linked_event_sha256": ["a" * 64],
        "snapshot_receipt": {"utc_ns": SNAPSHOT_NS, "monotonic_ns": 100},
    }
    events = [
        {
            "symbol": SYMBOL,
            "first_update_id": 102,
            "last_update_id": 103,
            "original_sha256": "a" * 64,
            "receipt": {"utc_ns": RECEIPT_NS, "monotonic_ns": 90},
            "deltas": [
                delta("BUY", "DELETE", "100.00000000", "0.00000000"),
                delta("SELL", "UPDATE", "101.00000000", "2.00000000"),
            ],
        }
    ]
    return snapshot, anchor, events


def test_fresh_two_sided_l2_constructs_exact_native_quote_after_snapshot_receipt():
    result, quote = book.segment(SYMBOL, *evidence(), native)
    assert result["blockers"] == []
    assert result["best_bid"] == "99.00000000"
    assert result["best_ask"] == "101.00000000"
    assert result["last_event_age_at_availability_ns"] == 300_000_000
    assert quote == {
        "type": "QuoteTick",
        "instrument_id": "BTCUSDT.BINANCE",
        "bid_price": "99.00000000",
        "ask_price": "101.00000000",
        "bid_size": "3.00000000",
        "ask_size": "2.00000000",
        "ts_event": EVENT_NS,
        "ts_init": SNAPSHOT_NS,
    }


def test_deleting_only_bid_blocks_quote():
    result, quote = book.segment(SYMBOL, *evidence(two_bids=False), native)
    assert result["blockers"] == ["empty_bid"]
    assert result["best_bid"] is None and quote is None


def test_old_event_blocks_quote_even_with_two_sided_book():
    snapshot, anchor, events = evidence()
    events[0]["deltas"] = [
        delta("BUY", "DELETE", "100.00000000", "0.00000000", ts_event=EVENT_NS - 6_000_000_000)
    ]
    result, quote = book.segment(SYMBOL, snapshot, anchor, events, native)
    assert result["blockers"] == ["event_time_outside_five_seconds"]
    assert quote is None


def test_crossed_book_blocks_native_quote():
    snapshot, anchor, events = evidence()
    events[0]["deltas"] = [delta("BUY", "UPDATE", "102.00000000", "1.00000000")]
    result, quote = book.segment(SYMBOL, snapshot, anchor, events, native)
    assert result["blockers"] == ["crossed_book"] and quote is None


def test_empty_intermediate_book_stays_blocked_after_next_update():
    snapshot, anchor, events = evidence(two_bids=False)
    anchor["linked_last_update_id"] = 105
    anchor["linked_event_sha256"].append("b" * 64)
    later = copy.deepcopy(events[0])
    later.update(first_update_id=104, last_update_id=105, original_sha256="b" * 64)
    later["deltas"] = [delta("BUY", "UPDATE", "99.00000000", "3.00000000", sequence=105)]
    events.append(later)
    result, quote = book.segment(SYMBOL, snapshot, anchor, events, native)
    assert result["best_bid"] == "99.00000000"
    assert result["blockers"] == ["empty_bid"] and quote is None


def test_snapshot_older_than_five_seconds_blocks_quote():
    snapshot, anchor, events = evidence()
    events[0]["receipt"]["utc_ns"] = SNAPSHOT_NS + 6_000_000_000
    for row in events[0]["deltas"]:
        row["ts_init"] = events[0]["receipt"]["utc_ns"]
    result, quote = book.segment(SYMBOL, snapshot, anchor, events, native)
    assert "snapshot_too_old" in result["blockers"] and quote is None


def test_root_cannot_start_project_native_review(monkeypatch):
    monkeypatch.setattr(book.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="snapshot_book_ordinary_process_required"):
        book.review(b"", expected_sha256="0" * 64)


@pytest.mark.parametrize("damage", ["symbol", "original", "gap", "revision", "delta"])
def test_changed_link_or_delta_refused(damage):
    snapshot, anchor, events = copy.deepcopy(evidence())
    if damage == "symbol":
        anchor["symbol"] = "ETHUSDT"
    elif damage == "original":
        events[0]["original_sha256"] = "b" * 64
    elif damage == "gap":
        events[0]["first_update_id"] = 104
    elif damage == "revision":
        anchor["linked_last_update_id"] = 104
    else:
        events[0]["deltas"][0]["ts_init"] += 1
    with pytest.raises(ValueError):
        book.segment(SYMBOL, snapshot, anchor, events, native)

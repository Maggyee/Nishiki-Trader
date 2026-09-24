"""Original-derived fixture depth increments and native deltas, without a snapshot.

This profile records a bounded unanchored segment per selected symbol. It never
constructs an OrderBook, QuoteTick, stream fence or executable price observation.
"""

from __future__ import annotations

import base64
import json
import os
import re
from decimal import Decimal

PROFILE = "portfolio.installed_market_ws.v1"
SCOPE = "account-market-ws-v1"
RECEIPT = "portfolio.native_account_market_ws.v1"
MAX_PAYLOAD = 8192
MAX_U64 = 2**64 - 1
EVENTS_PER_SYMBOL = 2


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("market_ws_duplicate_key")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=pairs)


def definitions(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise ValueError("market_ws_symbol_selection")
    names = []
    for row in value:
        if (
            not isinstance(row, dict)
            or set(row) != {"symbol", "price_precision", "size_precision"}
            or not isinstance(row["symbol"], str)
            or re.fullmatch("[A-Z0-9]{2,20}", row["symbol"]) is None
            or any(
                type(row[k]) is not int or row[k] != 8
                for k in ("price_precision", "size_precision")
            )
        ):
            raise ValueError("market_ws_fixture_precision")
        names.append(row["symbol"])
    if names != sorted(set(names)):
        raise ValueError("market_ws_symbol_order")
    return {row["symbol"]: row for row in value}


def selection(selected, bundles):
    # The caller first replays every route original. Reconstruct metadata bytes,
    # never obtain precision or symbols from a caller's saved summary alone.
    archive = bundles[0]["tls"].encode()
    raw = b"".join(
        base64.b64decode(r["raw_b64"], validate=True)
        for r in map(json.loads, archive.splitlines())
        if r["kind"] == "response_chunk"
    )
    metadata = decode(raw.split(b"\r\n\r\n", 1)[1])
    result = []
    for symbol in selected["symbols"]:
        rows = [row for row in metadata["symbols"] if row["symbol"] == symbol]
        if (
            len(rows) != 1
            or rows[0]["status"] != "TRADING"
            or rows[0]["isSpotTradingAllowed"] is not True
            or any(
                type(rows[0][k]) is not int or rows[0][k] != 8
                for k in ("baseAssetPrecision", "quoteAssetPrecision")
            )
        ):
            raise ValueError("market_ws_original_metadata")
        # Asset accounting precision is a bounded representation for this fixture;
        # it does not establish PRICE_FILTER/LOT_SIZE validity.
        result.append({"symbol": symbol, "price_precision": 8, "size_precision": 8})
    definitions(result)
    return {**selected, "market_definitions": result, "market_metadata_tls_sha256": digest(archive)}


def amount(value, *, positive=False):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", value) is None:
        raise ValueError("market_ws_decimal")
    number = Decimal(value)
    if (positive and number <= 0) or number != number.quantize(Decimal("0.00000001")):
        raise ValueError("market_ws_precision_or_price")
    return number


def event(raw, selected):
    value = decode(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"stream", "data"}
        or not isinstance(value["data"], dict)
    ):
        raise ValueError("market_ws_combined_envelope")
    row = value["data"]
    if (
        set(row) != {"e", "E", "s", "U", "u", "b", "a"}
        or row["e"] != "depthUpdate"
        or not isinstance(row["s"], str)
        or row["s"] not in definitions(selected)
        or value["stream"] != row["s"].lower() + "@depth@100ms"
        or any(type(row[k]) is not int or not 0 < row[k] <= MAX_U64 for k in ("E", "U", "u"))
        or row["E"] > MAX_U64 // 1_000_000
        or row["U"] > row["u"]
    ):
        raise ValueError("market_ws_symbol_or_update_range")
    levels = []
    for key, side in (("b", "BUY"), ("a", "SELL")):
        if not isinstance(row[key], list) or len(row[key]) > 4:
            raise ValueError("market_ws_bounded_levels")
        seen = set()
        for pair in row[key]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("market_ws_level")
            price, size = amount(pair[0], positive=True), amount(pair[1])
            if price in seen:
                raise ValueError("market_ws_duplicate_level")
            seen.add(price)
            levels.append(
                {
                    "side": side,
                    "price": format(price, ".8f"),
                    "size": format(size, ".8f"),
                    "order_id": 0,
                }
            )
    if not levels:
        raise ValueError("market_ws_nonempty_increment")
    return row, levels


def stamp(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"utc_ns", "monotonic_ns"}
        or any(type(v) is not int or not 0 < v <= MAX_U64 for v in value.values())
    ):
        raise ValueError("market_ws_original_clock")
    return value


def increments(items, selected, *, complete):
    symbols = definitions(selected)
    if not isinstance(items, list) or len(items) > len(symbols) * EVENTS_PER_SYMBOL:
        raise ValueError("market_ws_event_limit")
    previous, counts, output = {}, dict.fromkeys(symbols, 0), []
    last = None
    for item in items:
        if not isinstance(item, dict) or set(item) != {"raw_b64", "raw_sha256", "receipt"}:
            raise ValueError("market_ws_original_event")
        raw = base64.b64decode(item["raw_b64"], validate=True)
        if base64.b64encode(raw).decode() != item["raw_b64"] or digest(raw) != item["raw_sha256"]:
            raise ValueError("market_ws_original_digest")
        receipt = stamp(item["receipt"])
        if last:
            delta = [receipt[k] - last[k] for k in ("utc_ns", "monotonic_ns")]
            if any(n < 0 for n in delta) or abs(delta[0] - delta[1]) > 50_000_000:
                raise ValueError("market_ws_receipt_order")
        last = receipt
        row, levels = event(raw, selected)
        symbol = row["s"]
        if symbol in previous:
            prior = previous[symbol]
            if not row["U"] <= prior["u"] + 1 <= row["u"] or row["E"] < prior["E"]:
                raise ValueError("market_ws_gap_duplicate_or_event_clock")
        previous[symbol] = row
        counts[symbol] += 1
        if counts[symbol] > EVENTS_PER_SYMBOL:
            raise ValueError("market_ws_symbol_event_limit")
        deltas = [
            {
                "type": "OrderBookDelta",
                "instrument_id": symbol + ".BINANCE",
                "action": "DELETE" if Decimal(level["size"]) == 0 else "UPDATE",
                "order": level,
                "flags": 128 if index == len(levels) - 1 else 0,
                "sequence": row["u"],
                "ts_event": row["E"] * 1_000_000,
                "ts_init": receipt["utc_ns"],
            }
            for index, level in enumerate(levels)
        ]
        output.append(
            {
                "symbol": symbol,
                "first_update_id": row["U"],
                "last_update_id": row["u"],
                "receipt": receipt,
                "original_sha256": digest(raw),
                "deltas": deltas,
            }
        )
    if complete and any(n != EVENTS_PER_SYMBOL for n in counts.values()):
        raise ValueError("market_ws_all_selected_symbols_required")
    return output


def expected_result(payload, account_result):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError("market_ws_receipt_size")
    value = decode(payload)
    if (
        not isinstance(value, dict)
        or canonical(value) != payload
        or set(value) != {"profile", "account_b64", "definitions", "metadata_tls_sha256", "events"}
        or value["profile"] != RECEIPT
        or not isinstance(value["metadata_tls_sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", value["metadata_tls_sha256"]) is None
    ):
        raise ValueError("market_ws_receipt_schema")
    account_raw = base64.b64decode(value["account_b64"], validate=True)
    if base64.b64encode(account_raw).decode() != value["account_b64"]:
        raise ValueError("market_ws_account_encoding")
    return {
        "profile": RECEIPT,
        "native_version": "1.226.0",
        "payload_sha256": digest(payload),
        "metadata_tls_sha256": value["metadata_tls_sha256"],
        "definitions": value["definitions"],
        "account": account_result(account_raw),
        "market": increments(value["events"], value["definitions"], complete=True),
        "unanchored_depth_segment": True,
        "snapshot_linked": False,
        "order_book_synchronized": False,
        "quote_ticks_created": False,
        "tick_size_validated": False,
        "stream_fence_verified": False,
        "qualified_for_execution": False,
    }


def validate_native(payload, account_native):
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core import nautilus_pyo3 as native

    if native.NAUTILUS_VERSION != "1.226.0":
        raise ValueError("native_version_changed")
    result = expected_result(payload, account_native)
    for item in result["market"]:
        deltas = []
        for row in item["deltas"]:
            values = row["order"]
            price, size = (
                native.Price(Decimal(values["price"]), 8),
                native.Quantity(Decimal(values["size"]), 8),
            )
            if price.as_decimal() != Decimal(values["price"]) or size.as_decimal() != Decimal(
                values["size"]
            ):
                raise ValueError("market_ws_native_rounding")
            order = native.BookOrder(getattr(native.OrderSide, values["side"]), price, size, 0)
            delta = native.OrderBookDelta(
                native.InstrumentId.from_str(row["instrument_id"]),
                getattr(native.BookAction, row["action"]),
                order,
                row["flags"],
                row["sequence"],
                row["ts_event"],
                row["ts_init"],
            )
            if delta.to_dict() != row:
                raise ValueError("market_ws_native_delta_changed")
            deltas.append(delta)
        batch = native.OrderBookDeltas(
            native.InstrumentId.from_str(item["symbol"] + ".BINANCE"), deltas
        )
        if [delta.to_dict() for delta in batch.deltas] != item["deltas"]:
            raise ValueError("market_ws_native_batch_changed")
    return result


def state_type(base, account, requests, *, unsubscribe=False):
    Parent = account["state_type"](base, requests, unsubscribe=unsubscribe)

    class MarketState(Parent):
        PROFILE = PROFILE

        def __init__(self, *args):
            super().__init__(*args)
            self.market_updates = []

        def events(self, role):
            if role == "market":
                return [(op, raw) for op, raw in self.all_events(role) if op != 1]
            return super().events(role)

        def payload(self):
            return canonical(
                {
                    "profile": RECEIPT,
                    "account_b64": base64.b64encode(super().payload()).decode(),
                    "definitions": self.selected["market_definitions"],
                    "metadata_tls_sha256": self.selected["market_metadata_tls_sha256"],
                    "events": self.market_updates,
                }
            )

        def native_result(self):
            return expected_result(self.payload(), account["expected_result"])

        def feed(self, kind, payload, now, mono):
            if kind == "market_event":
                self.clock(payload, now, mono)
                if (
                    self.stage != "active"
                    or mono - self.grant_clock > base["WINDOW_NS"]
                    or any(w["stage"] != "pong" for w in self.wires.values())
                ):
                    raise ValueError("market_ws_both_live_required")
                index = len(self.market_updates) + 1
                opcode, raw, receipt = self.message(index, "market")
                if opcode != 1 or payload != {
                    **self.provenance.raw_fields(raw),
                    "receipt": receipt,
                }:
                    raise ValueError("market_ws_original_message")
                increments(
                    self.market_updates + [payload],
                    self.selected["market_definitions"],
                    complete=False,
                )
                self.market_updates.append(payload)
                return
            if kind == "close_prepared":
                increments(self.market_updates, self.selected["market_definitions"], complete=True)
            super().feed(kind, payload, now, mono)
            if kind == "peer_control" and payload["role"] == "market" and payload["opcode"] == 8:
                values = self.all_events("market")
                if [op for op, _ in values] != [9] + [1] * (
                    len(self.selected["symbols"]) * EVENTS_PER_SYMBOL
                ) + [8]:
                    raise ValueError("market_ws_exact_frame_sequence")

        def report(self):
            return {
                **super().report(),
                "market_events_recorded": len(self.market_updates),
                "market_native_acknowledged": self.acknowledged is not None,
                "snapshot_linked": False,
                "order_book_synchronized": False,
                "quote_ticks_created": False,
            }

    return MarketState


async def exchange(journal, chunk):
    for index in range(1, len(journal.state.selected["symbols"]) * EVENTS_PER_SYMBOL + 1):
        while len(journal.state.all_events("market")) <= index:
            await chunk()
        _, raw, receipt = journal.state.message(index, "market")
        journal.append(
            "market_event", {**journal.state.provenance.raw_fields(raw), "receipt": receipt}
        )

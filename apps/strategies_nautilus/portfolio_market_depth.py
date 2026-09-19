"""Detached BTCUSDT depth reconstruction; no execution engine or account state."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_ws_frames import MAX_FRAME, DepthError

REST = "https://testnet.binance.vision"
STREAM = "wss://stream.testnet.binance.vision/ws/btcusdt@depth@100ms"
PROFILE = "testnet_public_depth_evidence_v1"
SOURCE = {"rest": REST, "stream": STREAM, "symbol": "BTCUSDT", "timestamp_unit": "millisecond"}
SECOND = 1_000_000_000
MAX_AGE = 5 * SECOND
MAX_BUFFER = 16 * MAX_FRAME
MAX_EVENTS = 4096
MAX_ARCHIVE = 64 * MAX_FRAME


def integer(value, *, positive=False):
    if type(value) is not int or value < int(positive):
        raise DepthError("invalid_integer")
    return value


def depth_revision(value):
    if integer(value, positive=True) not in (1, 2):
        raise DepthError("unsupported_depth_revision")
    return value


def amount(value, *, positive=False):
    if not isinstance(value, str) or len(value) > 80:
        raise DepthError("invalid_decimal")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or (positive and number == 0):
            raise ValueError
        return number
    except (ValueError, ArithmeticError):
        raise DepthError("invalid_decimal") from None


class DepthBook:
    def __init__(
        self, metadata, *, revision=1, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT"
    ):
        self.revision = depth_revision(revision)
        if (
            any(
                not isinstance(value, str) or not value.isascii() or not value.isalnum()
                for value in (symbol, base_asset, quote_asset)
            )
            or symbol != base_asset + quote_asset
        ):
            raise DepthError("invalid_depth_symbol_selection")
        self.symbol = symbol
        rows = metadata["symbols"]
        if not isinstance(rows, list) or len(rows) != 1:
            raise DepthError("single_symbol_metadata_required")
        row = rows[0]
        if (
            row["symbol"] != symbol
            or row["baseAsset"] != base_asset
            or row["quoteAsset"] != quote_asset
            or row["status"] != "TRADING"
            or row["isSpotTradingAllowed"] is not True
        ):
            raise DepthError("invalid_spot_metadata")
        filters = [r for r in row["filters"] if r["filterType"] == "PRICE_FILTER"]
        if len(filters) != 1:
            raise DepthError("price_precision_required")
        tick = amount(filters[0]["tickSize"], positive=True)
        self.price_precision = max(0, -tick.normalize().as_tuple().exponent)
        self.size_precision = integer(row["baseAssetPrecision"])
        if self.price_precision > 16 or self.size_precision > 16:
            raise DepthError("unsupported_precision")
        self.last_id = None
        self.linked = False
        self.last_event_ns = None
        self.pending, self.pending_bytes, self.seen = [], 0, {}
        self.bids, self.asks = {}, {}
        self.bid_floor = self.ask_ceiling = None
        self.quotes = []
        self.obsolete = 0
        self.failed = None

    def fail(self, code):
        self.failed = code
        raise DepthError(code)

    def _levels(self, rows, *, snapshot=False):
        if not isinstance(rows, list) or len(rows) > (100 if snapshot else 20000):
            self.fail("invalid_depth_levels")
        values = {}
        for pair in rows:
            if not isinstance(pair, list) or len(pair) != 2:
                self.fail("invalid_depth_level")
            p, q = amount(pair[0], positive=True), amount(pair[1], positive=snapshot)
            if p in values:
                self.fail("duplicate_depth_price")
            if (
                Price(p, self.price_precision).as_decimal() != p
                or Quantity(q, self.size_precision).as_decimal() != q
            ):
                self.fail("native_depth_rounding")
            values[p] = q
        return values

    def event(self, event, *, received_ns, now_ns, raw_size):
        try:
            if self.failed:
                self.fail(self.failed)
            if (
                event.get("e") != "depthUpdate"
                or event.get("s") != self.symbol
                or raw_size > MAX_FRAME
            ):
                self.fail("unexpected_depth_frame")
            first, last = integer(event["U"], positive=True), integer(event["u"], positive=True)
            stamp = integer(event["E"], positive=True) * 1_000_000
            if first > last:
                self.fail("invalid_depth_range")
            if not 0 <= received_ns - stamp <= MAX_AGE or not 0 <= now_ns - stamp <= MAX_AGE:
                self.fail("future_or_stale_depth_event")
            self._levels(event["b"])
            self._levels(event["a"])
            digest = hashlib.sha256(canonical(event)).hexdigest()
            key = (first, last)
            if key in self.seen and self.seen[key] != digest:
                self.fail("conflicting_depth_range")
            self.seen[key] = digest
            if self.last_id is None:
                if len(self.pending) >= MAX_EVENTS or self.pending_bytes + raw_size > MAX_BUFFER:
                    self.fail("depth_buffer_exceeded")
                self.pending.append((event, received_ns, raw_size))
                self.pending_bytes += raw_size
                return
            self._apply(event, received_ns, now_ns)
        except Exception as exc:
            self.fail(str(exc) if isinstance(exc, DepthError) else "invalid_depth_event")

    def snapshot(self, body, *, now_ns):
        try:
            if self.failed:
                self.fail(self.failed)
            if self.last_id is not None or not self.pending:
                self.fail("buffered_single_snapshot_required")
            last = integer(body["lastUpdateId"], positive=True)
            if last < self.pending[0][0]["U"]:
                self.fail("snapshot_behind_first_buffered_event")
            self.bids = self._levels(body["bids"], snapshot=True)
            self.asks = self._levels(body["asks"], snapshot=True)
            if (
                list(self.bids) != sorted(self.bids, reverse=True)
                or list(self.asks) != sorted(self.asks)
                or not self.bids
                or not self.asks
                or max(self.bids) >= min(self.asks)
            ):
                self.fail("invalid_snapshot_book")
            self.bid_floor = min(self.bids) if len(self.bids) == 100 else None
            self.ask_ceiling = max(self.asks) if len(self.asks) == 100 else None
            self.last_id = last
            pending, self.pending = self.pending, []
            self.pending_bytes = 0
            for event, received_ns, _ in pending:
                self._apply(event, received_ns, now_ns)
        except Exception as exc:
            self.fail(str(exc) if isinstance(exc, DepthError) else "invalid_depth_snapshot")

    def _apply(self, event, received_ns, now_ns):
        first, last, stamp = event["U"], event["u"], event["E"] * 1_000_000
        if last <= self.last_id:
            self.obsolete += 1
            return  # Old events never refresh the book's age or native quote.
        if not 0 <= now_ns - stamp <= MAX_AGE or (
            self.last_event_ns is not None and stamp < self.last_event_ns
        ):
            self.fail("stale_or_regressing_depth_event")
        if not self.linked and self.revision == 1:
            if first == self.last_id + 1:
                self.fail("bootstrap_boundary_unqualified")
            if not first <= self.last_id < last:
                self.fail("bootstrap_overlap_missing")
        elif first > self.last_id + 1:
            self.fail("depth_sequence_gap")
        for target, rows in ((self.bids, event["b"]), (self.asks, event["a"])):
            for p, q in self._levels(rows).items():
                if q:
                    target[p] = q
                else:
                    target.pop(p, None)
        self.last_id, self.last_event_ns, self.linked = last, stamp, True
        if not self.bids or not self.asks:
            self.fail("empty_depth_side")
        bid, ask = max(self.bids), min(self.asks)
        if (self.bid_floor is not None and bid < self.bid_floor) or (
            self.ask_ceiling is not None and ask > self.ask_ceiling
        ):
            self.fail("snapshot_coverage_exhausted")
        if bid >= ask:
            self.fail("crossed_depth_book")
        quote = QuoteTick(
            InstrumentId.from_str(f"{self.symbol}.BINANCE"),
            Price(bid, self.price_precision),
            Price(ask, self.price_precision),
            Quantity(self.bids[bid], self.size_precision),
            Quantity(self.asks[ask], self.size_precision),
            stamp,
            received_ns,
        )
        self.quotes.append(QuoteTick.to_dict(quote))

    def check_age(self, now_ns):
        if self.failed:
            self.fail(self.failed)
        if self.linked and not 0 <= now_ns - self.last_event_ns <= MAX_AGE:
            self.fail("quiet_depth_expired")

    def summary(self):
        return {
            "locally_linked": self.linked and self.failed is None,
            "last_update_id": self.last_id,
            "last_event_ns": self.last_event_ns,
            "last_quote_age_at_receipt_ns": (
                self.quotes[-1]["ts_init"] - self.quotes[-1]["ts_event"] if self.quotes else None
            ),
            "native_quote_count": len(self.quotes),
            "obsolete_events": self.obsolete,
            "native_quotes_sha256": hashlib.sha256(canonical(self.quotes)).hexdigest(),
        }

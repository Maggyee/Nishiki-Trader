"""Synthetic joint account/market journal acceptance; no network or admission.

One owner drains callbacks in receipt order. All limits measure serialized bytes,
not Python/native RSS. Historical replay has no reusable account or stream fence.
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from apps.strategies_nautilus.portfolio_market_depth import (
    MAX_ARCHIVE,
    MAX_BUFFER,
    MAX_EVENTS,
    MAX_FRAME,
    REST,
    SECOND,
    DepthBook,
    DepthError,
    integer,
)
from apps.strategies_nautilus.portfolio_market_depth_archive import decode, flags
from apps.strategies_nautilus.portfolio_observation_plan import request_budget
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_testnet_mapping import ENDPOINT, map_observed_balances
from apps.strategies_nautilus.portfolio_testnet_observation import _open_orders, account_balances

PROFILE = "portfolio.synthetic_joint_observation.v1"
DESIGN_SHA256 = "05febee1b7b987c7cd3eb279ed7492f4988ecba5966b942fbc4d51f9c55f2ecb"
INCIDENT_RESERVE = 4096
DAY = 86400 * SECOND


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_fields(raw):
    return {"raw_b64": base64.b64encode(raw).decode(), "body_sha256": digest(raw)}


@dataclass(frozen=True)
class Limits:
    pending_bytes: int = MAX_BUFFER
    pending_events: int = MAX_EVENTS
    archive_bytes: int = MAX_ARCHIVE
    frame_bytes: int = MAX_FRAME

    def __post_init__(self):
        for value, ceiling in (
            (self.pending_bytes, MAX_BUFFER),
            (self.pending_events, MAX_EVENTS),
            (self.archive_bytes, MAX_ARCHIVE),
            (self.frame_bytes, MAX_FRAME),
        ):
            if type(value) is not int or not 0 < value <= ceiling:
                raise DepthError("invalid_joint_limits")
        if self.archive_bytes <= INCIDENT_RESERVE:
            raise DepthError("joint_incident_reserve_required")


class JointEvidence:
    profile = PROFILE

    def __init__(self):
        self.started = self.last = self.manifest = None
        self.failure = None
        self.completed = False
        self.books = {}
        self.market_start = self.linked_at = None
        self.account_connected = self.market_connected = False
        self.account_closed = self.market_closed = self.unsubscribed = False
        self.request_index = self.ws_index = 0
        self.budget = None
        self.limit = None
        self.used_weight = 0
        self.collections = []
        self.collecting = []
        self.market_refs = {}
        self.pending_sizes = {}
        self.account_events = []
        self.controls = deque()
        self.pongs = 0
        self.metadata = None

    @property
    def retained_bytes(self):
        return sum(sum(sizes) for sizes in self.pending_sizes.values())

    @property
    def retained_events(self):
        return sum(len(sizes) for sizes in self.pending_sizes.values())

    def feed(self, row, *, processed_ns, processed_mono):
        try:
            if (
                integer(processed_ns, positive=True) < row["received_ns"]
                or integer(processed_mono, positive=True) < row["monotonic_ns"]
                or abs((processed_ns - row["received_ns"]) - (processed_mono - row["monotonic_ns"]))
                > 50_000_000
            ):
                raise DepthError("joint_processing_clock_discontinuity")
            self._feed(row, processed_ns, processed_mono)
        except Exception as exc:
            self.failure = self.failure or (
                str(exc) if isinstance(exc, DepthError) else "invalid_joint_receipt"
            )
            raise DepthError(self.failure) from None

    def _feed(self, row, processed_ns, processed_mono):
        if self.failure or self.completed:
            raise DepthError("joint_segment_ended")
        now, mono = (
            integer(row["received_ns"], positive=True),
            integer(row["monotonic_ns"], positive=True),
        )
        kind = row["kind"]
        if self.started is None:
            manifest = row["manifest"]
            if kind != "started":
                raise DepthError("joint_start_required")
            self.validate_manifest(manifest)
            symbols = manifest["symbols"]
            self.manifest = manifest
            self.budget = request_budget(symbols)
            self.started = self.last = (now, mono)
            return
        if (
            now < self.last[0]
            or mono < self.last[1]
            or abs((now - self.started[0]) - (mono - self.started[1])) > 50_000_000
        ):
            raise DepthError("joint_clock_discontinuity")
        if (
            processed_mono - self.started[1]
            > (125 if kind in {"closed", "completed"} else 120) * SECOND
        ):
            raise DepthError("joint_duration_exceeded")
        self.last = now, mono
        for book in self.books.values():
            book.check_age(processed_ns)
        if self.market_start is not None:
            if self.linked_at is None and processed_mono - self.market_start[1] > 15 * SECOND:
                raise DepthError("joint_bootstrap_deadline")
            if (
                self.linked_at is not None
                and not self.market_closed
                and processed_mono - self.linked_at > 20 * SECOND
            ):
                raise DepthError("joint_observation_deadline")
        if kind == "rest_response":
            self._response(row, processed_ns)
        elif kind == "ws_operation":
            operations = self.budget["ws_api_operations"]
            if (
                self.ws_index >= len(operations)
                or row["operation"] != operations[self.ws_index]["operation"]
            ):
                raise DepthError("joint_ws_operation_order")
            if row["epoch"] != self.manifest["account_epoch"] or row["status"] != 200:
                raise DepthError("joint_account_epoch_or_status")
            if self.ws_index == 0 and self.request_index != 1:
                raise DepthError("joint_initial_clock_required")
            if self.ws_index == 1:
                if row["subscription_id"] != self.manifest["subscription_id"]:
                    raise DepthError("joint_subscription_mismatch")
                self.account_connected = True
            if self.ws_index == 2:
                if self.request_index != len(self.budget["rest_requests"]):
                    raise DepthError("joint_final_reads_required")
                self.unsubscribed = True
            self.ws_index += 1
        elif kind == "market_connected":
            if (
                self.market_connected
                or self.request_index != 7
                or set(self.books) != set(self.manifest["symbols"])
            ):
                raise DepthError("joint_single_frozen_market_connection")
            expected = "wss://stream.testnet.binance.vision/stream?streams=" + "/".join(
                s.lower() + "@depth@100ms" for s in self.manifest["symbols"]
            )
            if row["url"] != expected or row["epoch"] != self.manifest["market_epoch"]:
                raise DepthError("joint_market_source_mismatch")
            self.market_connected = True
            self.market_start = now, mono
        elif kind == "market_frame":
            if (
                not self.market_connected
                or self.market_closed
                or row["epoch"] != self.manifest["market_epoch"]
            ):
                raise DepthError("joint_foreign_market_epoch")
            body, size = self._body(row, MAX_FRAME)
            symbol = body["data"]["s"]
            if symbol not in self.books or body["stream"] != symbol.lower() + "@depth@100ms":
                raise DepthError("joint_combined_symbol_mismatch")
            book = self.books[symbol]
            pending = book.last_id is None
            book.event(body["data"], received_ns=now, now_ns=processed_ns, raw_size=size)
            if pending:
                self.pending_sizes.setdefault(symbol, []).append(len(canonical(row)))
            self.market_refs[symbol] = {
                "epoch": row["epoch"],
                "seq": row["seq"],
                "raw_sha256": row["body_sha256"],
                "U": body["data"]["U"],
                "u": body["data"]["u"],
                "E": body["data"]["E"],
                "received_ns": now,
                "monotonic_ns": mono,
                "snapshot": self.market_refs.get(symbol, {}).get("snapshot"),
            }
        elif kind == "account_frame":
            if (
                not self.account_connected
                or self.unsubscribed
                or row["epoch"] != self.manifest["account_epoch"]
            ):
                raise DepthError("joint_foreign_account_epoch")
            body, _ = self._body(row, MAX_FRAME)
            event = body["event"]
            if (
                type(body["subscriptionId"]) is not int
                or body["subscriptionId"] != self.manifest["subscription_id"]
            ):
                raise DepthError("joint_subscription_mismatch")
            stamp = integer(event["E"], positive=True) * 1_000_000
            if not 0 <= now - stamp <= 5 * SECOND or not 0 <= processed_ns - stamp <= 5 * SECOND:
                raise DepthError("joint_account_event_age")
            self.account_events.append(
                {"seq": row["seq"], "raw_sha256": row["body_sha256"], "event": event}
            )
            # No second settlement, inferred fee/funding classification or time/amount dedup.
            # This first acceptance profile requires quiescent balances, including in callbacks.
            if event["e"] != "outboundAccountPosition":
                raise DepthError("joint_account_event_requires_review")
            integer(event["u"], positive=True)
            baseline = account_balances(
                self.manifest["initial_account"], self.manifest["source"]["account_uid"]
            )
            seen = set()
            for balance in event["B"]:
                asset = balance["a"]
                if asset in seen or asset not in baseline:
                    raise DepthError("joint_account_event_asset_changed")
                seen.add(asset)
                check = account_balances(
                    {
                        "uid": int(self.manifest["source"]["account_uid"]),
                        "accountType": "SPOT",
                        "canTrade": True,
                        "balances": [
                            {"asset": asset, "free": balance["f"], "locked": balance["l"]}
                        ],
                    },
                    self.manifest["source"]["account_uid"],
                )
                if check[asset] != baseline[asset]:
                    raise DepthError("joint_account_event_delta_requires_review")
            if self.collecting:
                raise DepthError("joint_account_collection_interrupted")
        elif kind == "market_pong":
            if (
                not self.market_connected
                or self.market_closed
                or row["epoch"] != self.manifest["market_epoch"]
            ):
                raise DepthError("joint_control_outside_connection")
            payload = base64.b64decode(row["payload_b64"], validate=True)
            if len(payload) > 125 or row["echo_b64"] != row["payload_b64"]:
                raise DepthError("joint_invalid_pong")
            while self.controls and mono - self.controls[0] >= SECOND:
                self.controls.popleft()
            if len(self.controls) >= 5:
                raise DepthError("joint_control_rate_exceeded")
            self.controls.append(mono)
            self.pongs += 1
        elif kind == "tick":
            if not self.market_connected or self.market_closed:
                raise DepthError("joint_tick_outside_connection")
        elif kind == "closed":
            if not self.unsubscribed or row["transport"] not in {"account", "market"}:
                raise DepthError("joint_unsubscribe_before_close_required")
            which = row["transport"]
            if getattr(self, which + "_closed") or row["epoch"] != self.manifest[which + "_epoch"]:
                raise DepthError("joint_duplicate_or_foreign_close")
            setattr(self, which + "_closed", True)
        elif kind == "completed":
            if (
                not self.account_closed
                or not self.market_closed
                or self.linked_at is None
                or len(self.collections) != 2
            ):
                raise DepthError("joint_complete_intervals_required")
            if row["result"] != self.summary():
                raise DepthError("joint_seal_mismatch")
            self.completed = True
        else:
            self.extra_receipt(row)
        if (
            self.books
            and all(book.linked for book in self.books.values())
            and self.linked_at is None
        ):
            self.linked_at = mono

    def validate_manifest(self, manifest):
        # This profile deliberately cannot be relabelled as actual source evidence.
        if (
            manifest["synthetic"] is not True
            or manifest["design_sha256"] != DESIGN_SHA256
            or manifest["source"] != {"endpoint": REST, "account_uid": "1", "key_sha256": "0" * 64}
            or manifest["account_epoch"] != "synthetic-account"
            or manifest["market_epoch"] != "synthetic-market"
            or type(manifest["subscription_id"]) is not int
            or manifest["subscription_id"] < 0
        ):
            raise DepthError("synthetic_joint_manifest_required")
        symbols = manifest["symbols"]
        if (
            not isinstance(symbols, list)
            or not 0 < len(symbols) <= 3
            or symbols != sorted(set(symbols))
            or any(not isinstance(s, str) or not s.isascii() or not s.isalnum() for s in symbols)
        ):
            raise DepthError("invalid_joint_symbols")
        account_balances(manifest["initial_account"], "1")

    def route_snapshot(self, row, body, processed_ns):
        """V1 retains bookTicker only; derived profiles may freeze original routes."""

    def extra_receipt(self, row):
        raise DepthError("joint_unknown_or_interrupted_receipt")

    def _body(self, row, limit):
        raw = base64.b64decode(row["raw_b64"], validate=True)
        if len(raw) > limit or digest(raw) != row["body_sha256"]:
            raise DepthError("joint_raw_body_changed_or_oversized")
        return decode(raw), len(raw)

    def _response(self, row, processed_ns):
        if self.request_index >= len(self.budget["rest_requests"]) or self.unsubscribed:
            raise DepthError("joint_extra_response")
        expected = self.budget["rest_requests"][self.request_index]
        if (
            any(row[k] != expected[k] for k in ("phase", "method", "path", "params"))
            or row["status"] != 200
        ):
            raise DepthError("joint_response_selector_or_status")
        now, mono = self.last
        sent, sent_mono = (
            integer(row["sent_ns"], positive=True),
            integer(row["sent_monotonic_ns"], positive=True),
        )
        if (
            not self.started[0] <= sent <= now
            or not self.started[1] <= sent_mono <= mono
            or mono - sent_mono > 10 * SECOND
            or abs((now - sent) - (mono - sent_mono)) > 50_000_000
        ):
            raise DepthError("joint_request_time")
        body, _ = self._body(row, 16 * MAX_FRAME)
        used = row["used_weight_1m"]
        if type(used) is not int or used < 0:
            raise DepthError("joint_weight_usage_required")
        self.used_weight = used
        path, phase = expected["path"], expected["phase"]
        if path.endswith("/time"):
            stamp = integer(body["serverTime"], positive=True) * 1_000_000
            if (
                mono - sent_mono > 500_000_000
                or stamp - now < -250_000_000
                or stamp + 1_000_000 - sent > 250_000_000
            ):
                raise DepthError("joint_clock_sample_unqualified")
            if phase == "clock_linked" and self.linked_at is None:
                raise DepthError("joint_all_symbols_must_link")
        elif phase in {"account_before", "account_after"}:
            if not self.account_connected or row["epoch"] != self.manifest["account_epoch"]:
                raise DepthError("joint_signed_epoch_required")
            if phase == "account_after" and self.linked_at is None:
                raise DepthError("joint_market_interval_required")
            if self.collecting and sent < self.collecting[-1]["received_ns"]:
                raise DepthError("joint_account_reads_overlap")
            self.collecting.append(row)
            if len(self.collecting) == 4:
                bodies = [self._body(r, 16 * MAX_FRAME)[0] for r in self.collecting]
                before, orders, orders_after, after = bodies
                balances = account_balances(before, self.manifest["source"]["account_uid"])
                account_balances(after, self.manifest["source"]["account_uid"])
                _open_orders(orders)
                _open_orders(orders_after)
                baseline = account_balances(
                    self.manifest["initial_account"], self.manifest["source"]["account_uid"]
                )
                if before != after or orders != orders_after or balances != baseline or orders:
                    raise DepthError("joint_account_changed_or_open_orders")
                self.collections.append(
                    {
                        "phase": phase,
                        "epoch": row["epoch"],
                        "started_ns": self.collecting[0]["sent_ns"],
                        "ended_ns": now,
                        "receipt_sequences": [r["seq"] for r in self.collecting],
                        "raw_sha256": [r["body_sha256"] for r in self.collecting],
                        "balances": {
                            a: [str(free), str(locked)]
                            for a, (free, locked) in sorted(balances.items())
                        },
                    }
                )
                self.collecting = []
        elif path.endswith("/exchangeInfo"):
            rows = body["symbols"]
            selected = {r["symbol"]: r for r in rows}
            if len(selected) != len(rows):
                raise DepthError("joint_duplicate_metadata")
            for symbol in self.manifest["symbols"]:
                data = selected[symbol]
                self.books[symbol] = DepthBook(
                    {"symbols": [data]},
                    revision=2,
                    symbol=symbol,
                    base_asset=data["baseAsset"],
                    quote_asset=data["quoteAsset"],
                )
            limits = [
                r
                for r in body["rateLimits"]
                if r["rateLimitType"] == "REQUEST_WEIGHT"
                and r["interval"] == "MINUTE"
                and type(r["intervalNum"]) is int
                and r["intervalNum"] == 1
            ]
            if len(limits) != 1:
                raise DepthError("joint_weight_limit_required")
            self.limit = integer(limits[0]["limit"], positive=True)
            self.metadata = row
        elif path.endswith("/depth"):
            if not self.market_connected:
                raise DepthError("joint_market_connection_required")
            symbol = row["params"]["symbol"]
            self.books[symbol].snapshot(body, now_ns=processed_ns)
            self.pending_sizes[symbol] = []
            self.market_refs[symbol]["snapshot"] = {
                "L": body["lastUpdateId"],
                "seq": row["seq"],
                "raw_sha256": row["body_sha256"],
                "sent_ns": sent,
                "received_ns": now,
            }
        elif path.endswith("/ticker/bookTicker"):
            self.route_snapshot(row, body, processed_ns)
        # bookTicker is routing evidence only, never a native quote.
        self.request_index += 1
        remaining = sum(r["weight"] for r in self.budget["rest_requests"][self.request_index :])
        remaining += sum(r["weight"] for r in self.budget["ws_api_operations"][self.ws_index :])
        if self.limit is not None and used + remaining > self.limit:
            raise DepthError("joint_reserved_weight_exhausted")

    def summary(self):
        return {
            "profile": self.profile,
            "synthetic_only": True,
            "design_sha256": DESIGN_SHA256,
            "rest_get_responses": self.request_index,
            "ws_api_operations": self.ws_index,
            "documented_weight": sum(
                r["weight"] for r in self.budget["rest_requests"][: self.request_index]
            )
            + 2 * self.ws_index,
            "last_used_weight_1m": self.used_weight,
            "market_pongs": self.pongs,
            "account_intervals": self.collections,
            "account_events": self.account_events,
            "market_intervals": {
                s: {**b.summary(), "reference": self.market_refs.get(s)}
                for s, b in sorted(self.books.items())
            },
            "common_revision": None,
            "crossed_utc_boundary": self.started[0] // DAY != self.last[0] // DAY,
            "qualified_equity_usdt": None,
            "qualified_day_open_usdt": None,
            "qualified_peak_equity_usdt": None,
            "qualified_daily_loss_usdt": None,
            "segment_failed": self.failure is not None,
            "fresh_route_selection_verified": False,
            "current_shared_ip_budget_verified": False,
            "network_entrypoint_implemented": False,
            "new_probe_authorized": False,
            **flags(),
        }


class JointJournal:
    """Durable-before-parse queue shared by both callbacks and bootstrap buffers."""

    def __init__(self, path, *, manifest, clock, limits=None, evidence_type=JointEvidence):
        self.clock, self.limits = clock, limits or Limits()
        self.state = evidence_type()
        self.queue = deque()
        self.pending_bytes = 0
        self.sequence, self.previous, self.size = 0, "0" * 64, 0
        self.failed = False
        self.file = os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb"
        )
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.append("started", manifest=manifest)
        except BaseException:
            self.close()
            raise

    def _persist(self, row, *, incident=False):
        encoded = canonical(row | {"sha256": digest(canonical(row))}) + b"\n"
        cap = self.limits.archive_bytes - (0 if incident else INCIDENT_RESERVE)
        if self.size + len(encoded) > cap:
            raise DepthError("joint_archive_size_exceeded")
        try:
            self.file.write(encoded)
            self.file.flush()
            os.fsync(self.file.fileno())
        except Exception:
            raise DepthError("joint_archive_persistence_failed") from None
        self.sequence += 1
        self.previous, self.size = digest(canonical(row)), self.size + len(encoded)

    def _row(self, kind, fields):
        if {"seq", "previous", "profile", "kind"} & fields.keys():
            raise DepthError("joint_reserved_receipt_field")
        now, mono = self.clock()
        return {
            "received_ns": now,
            "monotonic_ns": mono,
            **fields,
            "profile": self.state.profile,
            "seq": self.sequence,
            "previous": self.previous,
            "kind": kind,
        }

    def _abort(self, code, row):
        self.failed = True
        self.state.failure = self.state.failure or code
        # Reserved space records overflow without retaining an unbounded offending payload.
        # Disk failure may prevent even this incident; an unsealed prefix still fails replay.
        try:
            incident = self._row(
                "aborted", {"reason": code, "rejected_receipt_sha256": digest(canonical(row))}
            )
            self._persist(incident, incident=True)
        except Exception:
            pass

    def enqueue(self, kind, **fields):
        if self.failed or self.state.completed:
            raise DepthError("joint_archive_ended")
        row = decode(canonical(self._row(kind, fields)))
        try:
            size = len(canonical(row))
            if (
                self.pending_bytes + self.state.retained_bytes + size > self.limits.pending_bytes
                or len(self.queue) + self.state.retained_events + 1 > self.limits.pending_events
            ):
                raise DepthError("joint_shared_pending_exceeded")
            self._persist(row)
            self.queue.append((row, size))
            self.pending_bytes += size
        except DepthError as exc:
            self._abort(str(exc), row)
            raise

    def drain(self):
        if self.failed:
            raise DepthError("joint_archive_ended")
        while self.queue:
            row, size = self.queue[0]
            try:
                if row["kind"] in {"market_frame", "account_frame", "account_wire"} and (
                    len(base64.b64decode(row["raw_b64"], validate=True)) > self.limits.frame_bytes
                ):
                    raise DepthError("joint_frame_limit_exceeded")
                dispatch = self._row("dispatch", {"receipt_seq": row["seq"]})
                self._persist(dispatch)
                self.state.feed(
                    row,
                    processed_ns=dispatch["received_ns"],
                    processed_mono=dispatch["monotonic_ns"],
                )
            except Exception as exc:
                code = str(exc) if isinstance(exc, DepthError) else "invalid_joint_receipt"
                self._abort(code, row)
                raise DepthError(code) from None
            self.queue.popleft()
            self.pending_bytes -= size

    def append(self, kind, **fields):
        self.enqueue(kind, **fields)
        self.drain()

    def complete(self):
        self.drain()
        self.append("completed", result=self.state.summary())

    def close(self):
        self.file.close()


def replay_joint(raw, *, expected_sha256, evidence_type=JointEvidence):
    """Rebuild native quotes and isolated CASH snapshots from selected closed bytes."""
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= MAX_ARCHIVE
        or digest(raw) != expected_sha256
    ):
        raise DepthError("selected_joint_archive_changed")
    state, previous = evidence_type(), "0" * 64
    pending, pending_bytes = deque(), 0
    last_clock = (0, 0)
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise DepthError("truncated_joint_archive")
        row = decode(line)
        claimed = row.pop("sha256")
        if (
            type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous"] != previous
            or row["profile"] != state.profile
            or digest(canonical(row)) != claimed
        ):
            raise DepthError("joint_archive_integrity_mismatch")
        current = (
            integer(row["received_ns"], positive=True),
            integer(row["monotonic_ns"], positive=True),
        )
        if current[0] < last_clock[0] or current[1] < last_clock[1] or state.completed:
            raise DepthError("joint_archive_clock_or_closure")
        last_clock = current
        if row["kind"] == "dispatch":
            if (
                not pending
                or type(row["receipt_seq"]) is not int
                or row["receipt_seq"] != pending[0]["seq"]
            ):
                raise DepthError("joint_dispatch_order")
            original = pending.popleft()
            pending_bytes -= len(canonical(original))
            state.feed(original, processed_ns=current[0], processed_mono=current[1])
        else:
            pending.append(row)
            pending_bytes += len(canonical(row))
        if (
            state.retained_bytes + pending_bytes > MAX_BUFFER
            or state.retained_events + len(pending) > MAX_EVENTS
        ):
            raise DepthError("joint_shared_pending_exceeded")
        previous = claimed
    if not state.completed or pending:
        raise DepthError("completed_joint_archive_required")
    metadata = state.metadata
    response = base64.b64decode(metadata["raw_b64"], validate=True)
    wrapped = canonical(
        {
            "schema_version": "portfolio.testnet_exchange_info_observation.v1",
            "endpoint": ENDPOINT,
            "started_ns": metadata["sent_ns"],
            "received_ns": metadata["received_ns"],
            "response_body": response.decode(),
            "response_sha256": digest(response),
        }
    )
    native = []
    for collection in state.collections:
        result = map_observed_balances(
            wrapped,
            expected_sha256=digest(wrapped),
            balances={
                a: tuple(Decimal(v) for v in amounts)
                for a, amounts in collection["balances"].items()
            },
            account_uid=state.manifest["source"]["account_uid"],
            observed_ns=collection["ended_ns"],
        )
        if not result["detached_native_account_balances_equal"]:
            raise DepthError("joint_native_account_mapping_failed")
        native.append(result)
    return {
        "status": (
            "synthetic_joint_archive_replayed"
            if state.profile == PROFILE
            else "loopback_joint_archive_replayed"
        ),
        "archive_sha256": expected_sha256,
        "completion_sha256": previous,
        "summary": state.summary(),
        "native_accounts": native,
        "native_quotes": {s: b.quotes for s, b in sorted(state.books.items())},
        "historical_replay_only": True,
        "venue_requests_made": 0,
        "credentials_loaded": False,
        **flags(),
    }

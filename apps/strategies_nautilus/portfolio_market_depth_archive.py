"""Durable public-depth receipts and detached replay with no reusable live fence."""

from __future__ import annotations

import base64
import hashlib
import json
import os

from apps.strategies_nautilus.portfolio_market_depth import (
    MAX_ARCHIVE,
    MAX_FRAME,
    PROFILE,
    SECOND,
    SOURCE,
    DepthBook,
    DepthError,
    integer,
)
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_venue import _unique_object

CONTRACT_SHA256 = "376eebff8fd2309027df2334f39d3ec73fd017f6a8afff1b3f0e3ea3023d879e"
REQUESTS = [
    ("/api/v3/time", {}, 1),
    ("/api/v3/exchangeInfo", {"symbol": "BTCUSDT"}, 20),
    ("/api/v3/depth", {"symbol": "BTCUSDT", "limit": "100"}, 5),
    ("/api/v3/time", {}, 1),
    ("/api/v3/time", {}, 1),
]


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError):
        raise DepthError("invalid_depth_json") from None


def flags():
    return dict.fromkeys(
        (
            "current_account_verified",
            "account_market_atomic_revision_verified",
            "valuation_qualified",
            "baseline_qualified",
            "runtime_ready",
            "new_orders_authorized",
        ),
        False,
    )


class DepthEvidence:
    def __init__(self):
        self.started = self.last = None
        self.book = None
        self.connected = self.closed = self.completed = False
        self.requests = self.responses_seen = self.frames_seen = 0
        self.weight_limit = None
        self.used_weight = 0
        self.frames = 0
        self.failure = None

    def feed(self, row):
        try:
            self._feed(row)
        except Exception as exc:
            self.failure = self.failure or (
                str(exc) if isinstance(exc, DepthError) else "invalid_depth_receipt"
            )
            raise DepthError(self.failure) from None

    def _feed(self, row):
        if self.failure or self.completed:
            raise DepthError("depth_segment_already_ended")
        now, mono = (
            integer(row["received_ns"], positive=True),
            integer(row["monotonic_ns"], positive=True),
        )
        kind = row["kind"]
        if self.started is None:
            if kind != "process_started" or row["contract_sha256"] != CONTRACT_SHA256:
                raise DepthError("depth_contract_start_required")
            self.started = self.last = (now, mono)
            return
        if (
            now < self.last[0]
            or mono < self.last[1]
            or abs((now - self.started[0]) - (mono - self.started[1])) > 50_000_000
        ):
            raise DepthError("depth_clock_discontinuity")
        elapsed = mono - self.started[1]
        if elapsed > (125 if kind in {"transport_closed", "completed"} else 120) * SECOND:
            raise DepthError("depth_duration_exceeded")
        if (self.book is None or not self.book.linked) and elapsed > 15 * SECOND:
            raise DepthError("depth_bootstrap_deadline")
        self.last = (now, mono)
        if self.book:
            self.book.check_age(now)
        if kind == "rest_response":
            self.responses_seen += 1
            if self.closed or self.requests >= len(REQUESTS):
                raise DepthError("unexpected_public_response")
            path, params, _ = REQUESTS[self.requests]
            sent, sent_mono = (
                integer(row["sent_ns"], positive=True),
                integer(row["sent_monotonic_ns"], positive=True),
            )
            if (
                row["path"] != path
                or row["params"] != params
                or integer(row["status"]) != 200
                or not self.started[0] <= sent <= now
                or not self.started[1] <= sent_mono <= mono
                or mono - sent_mono > 10 * SECOND
                or abs((now - sent) - (mono - sent_mono)) > 50_000_000
            ):
                raise DepthError("public_response_selector_status_time")
            body, _ = self._body(row, limit=8 * MAX_FRAME)
            headers = row["headers"]
            used = headers.get("x-mbx-used-weight-1m")
            if not isinstance(used, str) or not used.isascii() or not used.isdecimal():
                raise DepthError("public_weight_usage_unavailable")
            self.used_weight = int(used)
            if path.endswith("/time"):
                stamp = integer(body["serverTime"], positive=True) * 1_000_000
                if (
                    mono - sent_mono > 500_000_000
                    or stamp - now < -250_000_000
                    or stamp + 1_000_000 - sent > 250_000_000
                ):
                    raise DepthError("public_clock_sample_unqualified")
            elif path.endswith("/exchangeInfo"):
                self.book = DepthBook(body)
                limits = [
                    r
                    for r in body["rateLimits"]
                    if r["rateLimitType"] == "REQUEST_WEIGHT"
                    and r["interval"] == "MINUTE"
                    and type(r["intervalNum"]) is int
                    and r["intervalNum"] == 1
                ]
                if len(limits) != 1:
                    raise DepthError("public_weight_limit_unavailable")
                self.weight_limit = integer(limits[0]["limit"], positive=True)
            else:
                if not self.connected:
                    raise DepthError("depth_stream_before_snapshot_required")
                self.book.snapshot(body, now_ns=now)
            self.requests += 1
            remaining_weight = sum(r[2] for r in REQUESTS[self.requests :])
            if (
                self.weight_limit is not None
                and self.used_weight + remaining_weight > self.weight_limit
            ):
                raise DepthError("public_weight_budget_exhausted")
        elif kind == "connected":
            if self.connected or self.closed or self.requests != 2:
                raise DepthError("single_public_connection_required")
            self.connected = True
        elif kind == "depth_frame":
            self.frames_seen += 1
            if not self.connected or self.closed or self.book is None:
                raise DepthError("depth_frame_outside_connection")
            body, raw_size = self._body(row, limit=MAX_FRAME)
            self.book.event(body, received_ns=now, now_ns=now, raw_size=raw_size)
            self.frames += 1
        elif kind == "tick":
            if not self.connected or self.closed:
                raise DepthError("depth_health_outside_connection")
        elif kind == "transport_closed":
            if not self.connected or self.closed or self.requests != 5:
                raise DepthError("incomplete_public_transport")
            self.closed = True
        elif kind == "completed":
            if (
                not self.closed
                or self.book is None
                or not self.book.linked
                or not self.book.quotes
                or row["result"] != self.summary()
            ):
                raise DepthError("incomplete_depth_seal")
            self.completed = True
        else:
            raise DepthError("interrupted_depth_segment")

    def _body(self, row, *, limit):
        raw = base64.b64decode(row["raw_b64"], validate=True)
        if len(raw) > limit or hashlib.sha256(raw).hexdigest() != row["body_sha256"]:
            raise DepthError("depth_raw_body_changed_or_oversized")
        return decode(raw), len(raw)

    def summary(self):
        return {
            "profile": PROFILE,
            "source": SOURCE,
            "contract_sha256": CONTRACT_SHA256,
            "public_get_responses": self.responses_seen,
            "validated_get_responses": self.requests,
            "depth_frames": self.frames_seen,
            "validated_depth_frames": self.frames,
            "last_used_weight_1m": self.used_weight,
            "observed_weight_limit_1m": self.weight_limit,
            **(
                self.book.summary()
                if self.book
                else {"locally_linked": False, "native_quote_count": 0}
            ),
            "locally_linked": bool(
                self.book and self.book.linked and not self.book.failed and not self.failure
            ),
            "segment_failed": self.failure is not None,
            **flags(),
        }


class DepthJournal:
    def __init__(self, path, *, epoch, clock):
        self.clock, self.epoch = clock, epoch
        self.state = DepthEvidence()
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
            self.append("process_started", contract_sha256=CONTRACT_SHA256)
        except BaseException:
            self.close()
            raise

    def append(self, kind, **fields):
        if self.failed:
            raise DepthError("depth_archive_requires_review")
        now, mono = self.clock()
        row = {
            "profile": PROFILE,
            "source": SOURCE,
            "epoch": self.epoch,
            "seq": self.sequence,
            "previous": self.previous,
            "kind": kind,
            "received_ns": now,
            "monotonic_ns": mono,
            **fields,
        }
        digest = hashlib.sha256(canonical(row)).hexdigest()
        raw = canonical(row | {"sha256": digest}) + b"\n"
        if self.size + len(raw) > MAX_ARCHIVE:
            self.failed = True
            self.state.failure = "depth_archive_size_exceeded"
            raise DepthError(self.state.failure)
        try:
            self.file.write(raw)
            self.file.flush()
            os.fsync(self.file.fileno())
        except Exception:
            self.failed = True
            self.state.failure = "depth_archive_persistence_failed"
            raise DepthError(self.state.failure) from None
        self.sequence += 1
        self.previous, self.size = digest, self.size + len(raw)
        # All interpretation and native conversion follow durable persistence.
        self.state.feed(row)

    def close(self):
        self.file.close()


def replay_depth(raw, *, expected_sha256):
    try:
        if (
            not isinstance(raw, bytes)
            or not 0 < len(raw) <= MAX_ARCHIVE
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise DepthError("selected_depth_archive_changed")
        state, previous, epoch = DepthEvidence(), "0" * 64, None
        for seq, line in enumerate(raw.splitlines(keepends=True)):
            if not line.endswith(b"\n"):
                raise DepthError("truncated_depth_archive")
            row = decode(line)
            digest = row.pop("sha256")
            if (
                type(row["seq"]) is not int
                or row["seq"] != seq
                or row["previous"] != previous
                or row["profile"] != PROFILE
                or row["source"] != SOURCE
                or hashlib.sha256(canonical(row)).hexdigest() != digest
            ):
                raise DepthError("depth_archive_integrity_mismatch")
            if epoch is None:
                epoch = row["epoch"]
                if not isinstance(epoch, str) or not epoch:
                    raise DepthError("depth_epoch_required")
            if row["epoch"] != epoch:
                raise DepthError("depth_epoch_changed")
            previous = digest
            state.feed(row)
        if not state.completed:
            raise DepthError("completed_depth_archive_required")
        return {
            "status": "historical_depth_replayed",
            "archive_sha256": expected_sha256,
            "completion_sha256": previous,
            "summary": state.summary(),
            "native_quotes": state.book.quotes,
            "historical_replay_only": True,
            **flags(),
        }
    except Exception:
        raise DepthError("depth_archive_replay_failed") from None

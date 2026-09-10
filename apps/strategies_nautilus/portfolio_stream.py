"""Durable observations of a Binance subscription, never a global gap-free claim."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from apps.strategies_nautilus.portfolio_venue import _decimal, _unique_object


class StreamError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class SourceBinding:
    endpoint: str
    account_uid: str
    key_sha256: str


def bind_source(client, account_uid):
    endpoint = client.base_url.rstrip("/")
    if endpoint not in {"https://api.binance.com", "https://testnet.binance.vision"}:
        raise StreamError("unsupported account source endpoint")
    if not isinstance(client.api_key, str) or not client.api_key or not account_uid:
        raise StreamError("explicit source identity required")
    return SourceBinding(endpoint, account_uid, hashlib.sha256(client.api_key.encode()).hexdigest())


@dataclass(frozen=True)
class StreamFence:
    epoch: str
    revision: int
    binding: SourceBinding


class UserStreamJournal:
    """Single-writer hash chain. A restart always requires a new subscription.

    All methods must run serially on the transport's owning event-loop thread.
    Transport callbacks must report subscription acknowledgement, pong/message
    activity and disconnects. Local receipt numbers are NOT exchange sequences.
    Account snapshots are not updated from partial outboundAccountPosition rows.
    """

    def __init__(self, path: Path, binding: SourceBinding, *, clock_ns, max_age_ns=60_000_000_000):
        if type(max_age_ns) is not int or max_age_ns <= 0:
            raise StreamError("positive stream freshness window required")
        self.binding, self.clock_ns, self.max_age_ns = binding, clock_ns, max_age_ns
        self.epoch, self.revision, self.subscription_id = None, 0, None
        self.last_transport_ns = 0
        self.connected = False
        self._transport_check = None
        self._failed = False
        self._seen = {}
        self._previous = "0" * 64
        self._sequence = 0
        self._file = os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR, 0o600), "r+b")
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for raw in self._file:
                if not raw.endswith(b"\n"):
                    raise StreamError("incomplete stream archive record")
                row = json.loads(raw, object_pairs_hook=_unique_object)
                digest = row.pop("sha256")
                if (
                    row["seq"] != self._sequence
                    or row["previous"] != self._previous
                    or row["binding"] != asdict(binding)
                    or hashlib.sha256(canonical(row)).hexdigest() != digest
                ):
                    raise StreamError("stream archive integrity/source mismatch")
                self._sequence += 1
                self._previous = digest
            self._append("process_started")
        except Exception:
            self._file.close()
            raise

    def _append(self, kind, **fields):
        if self._failed:
            raise StreamError("stream archive requires recovery")
        row = {
            "seq": self._sequence,
            "previous": self._previous,
            "binding": asdict(self.binding),
            "received_ns": self.clock_ns(),
            "epoch": self.epoch,
            "kind": kind,
            **fields,
        }
        digest = hashlib.sha256(canonical(row)).hexdigest()
        try:
            self._file.write(canonical({**row, "sha256": digest}) + b"\n")
            self._file.flush()
            os.fsync(self._file.fileno())
        except Exception:
            self.connected = False
            self._failed = True
            raise StreamError("stream archive persistence failed") from None
        self._sequence += 1
        self._previous = digest

    def subscribed(self, subscription_id: int, binding: SourceBinding):
        """Called only after the transport confirms the signed subscription."""
        if binding != self.binding or type(subscription_id) is not int or subscription_id < 0:
            self.disconnect("subscription/source mismatch")
            raise StreamError("subscription/source mismatch")
        self.epoch = str(uuid4())
        self.revision += 1
        self.subscription_id = subscription_id
        self._seen.clear()
        self._append("subscribed", subscription_id=subscription_id)
        self.connected = True
        self.last_transport_ns = self.clock_ns()

    def transport_alive(self):
        if not self.connected:
            raise StreamError("subscription not connected")
        now = self.clock_ns()
        if now < self.last_transport_ns or now - self.last_transport_ns > self.max_age_ns:
            self.disconnect("transport continuity expired")
            raise StreamError("transport continuity expired")
        self.last_transport_ns = now

    def disconnect(self, reason="transport disconnected"):
        self.connected = False
        self.revision += 1
        self._append("disconnected", reason=reason)

    def observe(self, raw: bytes):
        """Archive a raw WS API account envelope before any downstream processing."""
        self.fence()
        try:
            if len(raw) > 65_536:
                raise StreamError("oversized user-stream event")
            body = json.loads(raw, object_pairs_hook=_unique_object)
            if (
                type(body["subscriptionId"]) is not int
                or body["subscriptionId"] != self.subscription_id
            ):
                raise StreamError("foreign user-stream subscription")
            event = body["event"]
            kind, ts = event["e"], event["E"]
            if type(ts) is not int or not 0 <= self.clock_ns() - ts * 1_000_000 <= self.max_age_ns:
                raise StreamError("stale/future stream event")
            if kind not in {"executionReport", "outboundAccountPosition"}:
                raise StreamError("stream event requires fresh account reconciliation")
            duplicate = False
            if kind == "executionReport":
                if event["s"] != "BTCUSDT" or any(
                    type(event[k]) is not int or event[k] < 0 for k in ("i", "I")
                ):
                    raise StreamError("unsupported stream order identity")
                key = (event["s"], event["i"], event["I"])
                digest = hashlib.sha256(canonical(event)).hexdigest()
                if key in self._seen:
                    if self._seen[key] != digest:
                        raise StreamError("conflicting execution-report replay")
                    duplicate = True
                self._seen[key] = digest
                if len(self._seen) > 100_000:
                    raise StreamError("stream replay index requires archive rotation")
            else:
                if (
                    type(event["u"]) is not int
                    or not 0 <= event["u"] <= ts
                    or not isinstance(event["B"], list)
                ):
                    raise StreamError("malformed account update")
                # Partial asset updates are evidence, never a complete account snapshot.
                if any(row["a"] not in {"BTC", "USDT"} for row in event["B"]):
                    raise StreamError("unexpected stream asset")
                if len({row["a"] for row in event["B"]}) != len(event["B"]):
                    raise StreamError("duplicate stream asset")
                for row in event["B"]:
                    for key in ("f", "l"):
                        _decimal(row[key])
            self.revision += 1  # even identical replay invalidates an in-flight REST fence
            self._append("event", raw=raw.decode(), duplicate=duplicate)
            self.transport_alive()
            return duplicate
        except Exception as exc:
            reason = str(exc) if isinstance(exc, StreamError) else "malformed user-stream event"
            self.disconnect(reason)
            raise StreamError(reason) from None

    def fence(self):
        now = self.clock_ns()
        transport_ok = self._transport_check is None or self._transport_check()
        if (
            not self.connected
            or not transport_ok
            or not 0 <= now - self.last_transport_ns <= self.max_age_ns
        ):
            if self.connected:
                self.disconnect("transport continuity expired")
            raise StreamError("fresh connected subscription required")
        return StreamFence(self.epoch, self.revision, self.binding)

    def attach_transport(self, check):
        """Bind one owning transport before subscribing; never replace it in place."""
        if self.connected or self._transport_check is not None:
            raise StreamError("stream transport already attached or subscribed")
        self._transport_check = check

    def assert_fence(self, fence):
        if self.fence() != fence:
            raise StreamError("stream changed during or after account collection")

    def record_collection(self, fence, hashes):
        self.assert_fence(fence)
        self._append("rest_collection", response_sha256=hashes)

    def close(self):
        self.connected = False
        self._file.close()

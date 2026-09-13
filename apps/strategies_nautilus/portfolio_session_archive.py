"""Detached replay of explicitly pinned ADR-017 raw session archives.

No HTTP client, journal, reusable fence, session lease or execution permission.
Historical receipt times validate historical collection only, never current freshness.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_transport import (
    HISTORY_NS,
    PROFILE,
    order_projection,
)
from apps.strategies_nautilus.portfolio_stream import SourceBinding, StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_observation import (
    _binding,
    _digest,
    _open_orders,
    account_balances,
)
from apps.strategies_nautilus.portfolio_venue import _unique_object

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
COLLECTION_NS = 60_000_000_000


@dataclass(frozen=True)
class ArchivedSession:
    evidence_raw: bytes
    archive_sha256: str
    checkpoint_sha256: str
    collection_id: str
    completion_sha256: str
    completion_seq: int
    started_ns: int
    completed_ns: int
    response_count: int

    def summary(self):
        evidence = json.loads(self.evidence_raw)
        return {
            "evidence_basis": "archived_session_reconciliation_at_observation",
            "archive_sha256": self.archive_sha256,
            "checkpoint_sha256": self.checkpoint_sha256,
            "evidence_sha256": hashlib.sha256(self.evidence_raw).hexdigest(),
            "collection_id": self.collection_id,
            "completion_sha256": self.completion_sha256,
            "completion_seq": self.completion_seq,
            "collection_started_ns": self.started_ns,
            "collection_completed_ns": self.completed_ns,
            "observation_received_ns": evidence["received_ns"],
            "response_count": self.response_count,
            "current_venue_state_verified": False,
            "source_authenticated": False,
            "global_continuity_verified": False,
            "new_orders_authorized": False,
            "cancel_retry_allowed": False,
            "runtime_ready": False,
        }


def _receipts(raw, state, archive_sha256, checkpoint_sha256, collection_id):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE_BYTES
            or hashlib.sha256(raw).hexdigest() != archive_sha256
            or not isinstance(collection_id, str) or not collection_id):
        raise StreamError("explicit bounded archive and collection required")
    _binding(SourceBinding(**state["source"]))
    previous, epoch, start, finish = "0" * 64, None, None, None
    last_ns, response_ns = 0, 0
    seen_epochs, receipts = set(), []
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise StreamError("incomplete session archive row")
        row = json.loads(line, object_pairs_hook=_unique_object)
        digest = row.pop("sha256")
        if (type(row["seq"]) is not int or row["seq"] != seq
                or row["previous"] != previous or row["binding"] != state["source"]
                or hashlib.sha256(canonical(row)).hexdigest() != digest
                or type(row["received_ns"]) is not int
                or not row["received_ns"] > 0 or row["received_ns"] < last_ns):
            raise StreamError("session archive integrity/source/clock mismatch")
        previous = digest
        prior_ns, last_ns = last_ns, row["received_ns"]
        kind = row["kind"]
        if kind in {"process_started", "disconnected"}:
            epoch = None
        elif kind == "subscribed":
            if (not isinstance(row["epoch"], str) or not row["epoch"]
                    or row["epoch"] in seen_epochs
                    or type(row["subscription_id"]) is not int or row["subscription_id"] < 0):
                raise StreamError("invalid session archive subscription")
            epoch = row["epoch"]
            seen_epochs.add(epoch)
        selected = row.get("collection_id") == collection_id
        if kind == "rest_started" and selected:
            if (start is not None or not epoch or row["epoch"] != epoch
                    or row["anchor"] != {"profile": PROFILE, "checkpoint_sha256": checkpoint_sha256}
                    or type(row["started_ns"]) is not int
                    or not state["updated_ns"] < row["started_ns"] <= last_ns
                    or row["started_ns"] < prior_ns
                    or row["started_ns"] - state["started_ns"] > HISTORY_NS
                    or last_ns - row["started_ns"] > COLLECTION_NS):
                raise StreamError("invalid selected historical session collection")
            start = row
            response_ns = row["started_ns"]
        elif start is not None and finish is None:
            if (epoch != start["epoch"] or row["epoch"] != epoch
                    or last_ns - start["started_ns"] > COLLECTION_NS):
                raise StreamError("historical collection epoch/time changed")
            if kind == "testnet_transport_alive" and not selected:
                continue
            if not selected:
                raise StreamError("historical collection interrupted")
            if kind == "rest_response":
                if (len(receipts) >= 4 + 2 * len(state["intents"])
                        or type(row["response_ns"]) is not int
                        or not max(response_ns, prior_ns) <= row["response_ns"] <= last_ns
                        or not isinstance(row["raw"], str)
                        or len(row["raw"].encode()) > 8 * 1024 * 1024
                        or hashlib.sha256(row["raw"].encode()).hexdigest() != row["response_sha256"]):
                    raise StreamError("invalid historical response receipt")
                receipts.append(row)
                response_ns = row["response_ns"]
            elif kind == "session_collection_completed":
                finish = row | {"sha256": digest}
            else:
                raise StreamError("historical collection did not complete")
        elif selected:
            # Includes orphan selected receipts before start and identity reuse in the tail.
            raise StreamError("historical collection identity reused or incomplete")
    if start is None or finish is None or len(receipts) != 4 + 2 * len(state["intents"]):
        raise StreamError("complete raw historical session collection required")
    return start, receipts, finish


def _evidence(receipts, state):
    index = 0

    def read(path, params):
        nonlocal index
        row = receipts[index]
        index += 1
        if row["path"] != path or row["params"] != params:
            raise StreamError("historical original-order selector/sequence mismatch")
        return json.loads(row["raw"], object_pairs_hook=_unique_object)

    account = read("/api/v3/account", {"omitZeroBalances": "false"})
    opened = read("/api/v3/openOrders", {})
    account_balances(account, state["source"]["account_uid"])
    _open_orders(opened)
    orders, trades = [], []
    for oid in sorted(state["intents"]):
        row = order_projection(read("/api/v3/order", {"symbol": "BTCUSDT", "origClientOrderId": oid}))
        if row["clientOrderId"] != oid:
            raise StreamError("historical response returned a different original order")
        fills = read("/api/v3/myTrades", {"symbol": "BTCUSDT", "orderId": str(row["orderId"]), "limit": "1000"})
        if (not isinstance(fills, list) or len(fills) >= 1000
                or any(t["orderId"] != row["orderId"] for t in fills)):
            raise StreamError("complete original historical trades required")
        orders.append(row)
        trades.extend(fills)
    after_opened = read("/api/v3/openOrders", {})
    after_account = read("/api/v3/account", {"omitZeroBalances": "false"})
    if account != after_account or opened != after_opened:
        raise StreamError("historical bracket account/orders changed")
    projected = [order_projection(row) for row in opened]
    active = [row for row in orders if row["status"] in {"NEW", "PARTIALLY_FILLED"}]
    if sorted(projected, key=lambda r: r["orderId"]) != sorted(active, key=lambda r: r["orderId"]):
        raise StreamError("historical foreign/conflicting account-wide orders")
    return canonical({
        "profile": "offline_testnet_session_recovery_v1",
        "source": state["source"],
        "history_start_ns": state["started_ns"],
        "received_ns": receipts[-1]["response_ns"],
        "account": account,
        "open_orders": projected,
        "orders": orders,
        "trades": trades,
    })


def replay_session_collection(raw, checkpoint_raw, *, archive_sha256, checkpoint_sha256, collection_id):
    """Reproduce one original seal, validating the complete archive including its tail.

    Digests must come from retained references. Hashing damaged bytes now does not
    establish historical provenance. This returns data only, never CollectedSession.
    """
    try:
        _digest(archive_sha256)
        _digest(checkpoint_sha256)
        if (not isinstance(checkpoint_raw, bytes) or not 0 < len(checkpoint_raw) <= 32 * 1024 * 1024
                or hashlib.sha256(checkpoint_raw).hexdigest() != checkpoint_sha256):
            raise StreamError("original selected checkpoint required")
        state = read_session(checkpoint_raw)["state"]
        if len(state["intents"]) > 2:
            raise StreamError("bounded original session required")
        start, receipts, finish = _receipts(raw, state, archive_sha256, checkpoint_sha256, collection_id)
        evidence_raw = _evidence(receipts, state)
        if hashlib.sha256(evidence_raw).hexdigest() != finish["evidence_sha256"]:
            raise StreamError("historical session evidence seal mismatch")
        return ArchivedSession(evidence_raw, archive_sha256, checkpoint_sha256, collection_id,
                               finish["sha256"], finish["seq"], start["started_ns"],
                               finish["received_ns"], len(receipts))
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, IndexError):
        raise StreamError("archived session collection failed validation") from None

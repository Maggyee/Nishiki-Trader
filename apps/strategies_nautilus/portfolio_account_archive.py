"""Replay explicitly selected local REST receipts without a reusable stream fence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_account_collector import (
    BinanceReadOnlyAccountCollector,
    CollectedAccount,
)
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_venue import _unique_object


class AccountArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ArchivedAccount:
    collected: CollectedAccount
    archive_sha256: str
    collection_id: str
    completion_sha256: str
    completion_seq: int

    def summary(self):
        return {
            "status": "archived_collection_replayed",
            "archive_sha256": self.archive_sha256,
            "collection_id": self.collection_id,
            "completion_sha256": self.completion_sha256,
            "completion_seq": self.completion_seq,
            "response_count": len(self.collected.wire_sha256),
            "api_trading_enabled": self.collected.api_trading_enabled,
            "start_ns": self.collected.evidence.start_ns,
            "end_ns": self.collected.evidence.end_ns,
            "runtime_ready": False,
            "real_account_verified": False,
            "atomic_revision_verified": False,
            "downtime_history_complete": False,
        }


def _selected_receipts(raw, source, expected_sha256, collection_id, anchor):
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= 64 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise AccountArchiveError("selected archive size/digest mismatch")
    if (
        source.endpoint not in {"https://api.binance.com", "https://testnet.binance.vision"}
        or not isinstance(source.account_uid, str)
        or not source.account_uid
        or source.account_uid != anchor.venue_uid
        or not isinstance(source.key_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", source.key_sha256) is None
        or not isinstance(collection_id, str)
        or not collection_id
    ):
        raise AccountArchiveError("explicit archive source/collection identity required")
    expected_anchor = {**asdict(anchor), "quote": str(anchor.quote), "base": str(anchor.base)}
    if (
        type(anchor.start_ns) is not int
        or anchor.start_ns <= 0
        or not anchor.quote.is_finite()
        or anchor.quote <= 0
        or anchor.base != 0
    ):
        raise AccountArchiveError("positive independent flat account baseline required")
    previous, active_epoch = "0" * 64, None
    start, finish, receipts = None, None, []
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise AccountArchiveError("incomplete archive record")
        row = json.loads(line, object_pairs_hook=_unique_object)
        digest = row.pop("sha256")
        if (
            type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous"] != previous
            or row["binding"] != asdict(source)
            or hashlib.sha256(canonical(row)).hexdigest() != digest
            or type(row["received_ns"]) is not int
            or row["received_ns"] <= 0
        ):
            raise AccountArchiveError("archive integrity/source mismatch")
        previous = digest
        kind = row["kind"]
        if kind in {"process_started", "disconnected"}:
            active_epoch = None
        elif kind == "subscribed":
            active_epoch = row["epoch"]
        if row.get("collection_id") == collection_id and kind == "rest_started":
            if start is not None or not active_epoch or active_epoch != row["epoch"]:
                raise AccountArchiveError("ambiguous/unsubscribed archive collection")
            if (
                row["anchor"] != expected_anchor
                or type(row["started_ns"]) is not int
                or not anchor.start_ns <= row["started_ns"] <= row["received_ns"]
            ):
                raise AccountArchiveError("archive baseline/time mismatch")
            start = row
            continue
        if start is not None and finish is None:
            if (
                row.get("collection_id") != collection_id
                or row["epoch"] != start["epoch"]
                or kind not in {"rest_response", "rest_collection"}
                or row["received_ns"] < start["received_ns"]
            ):
                raise AccountArchiveError("collection interrupted by stream or process activity")
            if kind == "rest_response":
                if (
                    len(receipts) >= 69
                    or type(row["response_ns"]) is not int
                    or not start["started_ns"] <= row["response_ns"] <= row["received_ns"]
                    or hashlib.sha256(row["raw"].encode()).hexdigest() != row["response_sha256"]
                ):
                    raise AccountArchiveError("invalid archived response receipt")
                receipts.append(row)
            else:
                finish = {**row, "sha256": digest}
        elif finish is not None and row.get("collection_id") == collection_id:
            raise AccountArchiveError("collection identity reused after completion")
    if start is None or finish is None or not receipts:
        raise AccountArchiveError(
            "complete raw account collection required; hashes alone cannot replay"
        )
    return start, receipts, finish


async def replay_account_collection(raw, *, source, expected_sha256, collection_id, anchor):
    """Reuse collector validation against retained bodies, never authenticate or connect.

    The expected digest must select a closed archive/copy. A hash calculated only
    after suspected data loss cannot prove the missing tail ever existed.
    """
    try:
        start, receipts, finish = _selected_receipts(
            raw, source, expected_sha256, collection_id, anchor
        )

        class ReplayClient:
            base_url = source.endpoint

            def __init__(self):
                self.now = start["started_ns"]
                self.index = 0

            async def sign_request(self, method, path, *, payload):
                if self.index >= len(receipts):
                    raise AccountArchiveError("missing archived response")
                receipt = receipts[self.index]
                selectors = {
                    k: v for k, v in payload.items() if k not in {"timestamp", "recvWindow"}
                }
                if (
                    method != HttpMethod.GET
                    or path != receipt["path"]
                    or selectors != receipt["params"]
                    or receipt["response_ns"] < self.now
                ):
                    raise AccountArchiveError("archive request/cursor/time mismatch")
                self.index += 1
                self.now = receipt["response_ns"]
                return receipt["raw"].encode()

        client = ReplayClient()
        collected = await BinanceReadOnlyAccountCollector(
            client, clock_ns=lambda: client.now
        ).collect(anchor)
        if (
            client.index != len(receipts)
            or [list(pair) for pair in collected.wire_sha256] != finish["response_sha256"]
            or not collected.evidence.end_ns <= finish["received_ns"]
            or finish["received_ns"] - start["started_ns"] > 60_000_000_000
        ):
            raise AccountArchiveError("archive completion receipts/time mismatch")
        # No journal is attached: archived subscription epochs cannot become a live fence.
        return ArchivedAccount(
            collected, expected_sha256, collection_id, finish["sha256"], finish["seq"]
        )
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
        raise AccountArchiveError("archived account collection failed validation") from None

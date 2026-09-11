"""Full-account testnet observations, deliberately separate from recovery evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_stream import (
    StreamError,
    UserStreamJournal,
    bind_source,
    canonical,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.portfolio_venue import _decimal, _unique_object

PROFILE = "portfolio.testnet_observation.v1"
REQUESTS = (
    ("/api/v3/account", {"omitZeroBalances": "false"}),
    ("/api/v3/openOrders", {}),
    ("/api/v3/openOrders", {}),
    ("/api/v3/account", {"omitZeroBalances": "false"}),
)


def _digest(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise StreamError("SHA256 digest required")
    return value


def _binding(source):
    if (
        source.endpoint != TESTNET_REST
        or not isinstance(source.account_uid, str)
        or not source.account_uid.isascii()
        or not source.account_uid.isdecimal()
        or str(int(source.account_uid)) != source.account_uid
    ):
        raise StreamError("explicit testnet account identity required")
    _digest(source.key_sha256)


def _name(value):
    if not isinstance(value, str) or not 0 < len(value) <= 128 or not value.isprintable():
        raise StreamError("invalid asset/symbol name")
    return value


def account_balances(body, uid):
    if (
        not isinstance(body, dict)
        or type(body.get("uid")) is not int
        or body["uid"] < 0
        or str(body["uid"]) != uid
        or body.get("accountType") != "SPOT"
        or type(body.get("canTrade")) is not bool
        or not isinstance(body.get("balances"), list)
        or len(body["balances"]) > 10_000
    ):
        raise StreamError("invalid full testnet account identity/balances")
    balances = {}
    for row in body["balances"]:
        if not isinstance(row, dict) or not {"asset", "free", "locked"} <= row.keys():
            raise StreamError("invalid account asset row")
        asset = _name(row["asset"])
        if asset in balances:
            raise StreamError("duplicate account asset")
        balances[asset] = (_decimal(row["free"]), _decimal(row["locked"]))
    return balances


def _open_orders(body):
    if not isinstance(body, list) or len(body) > 10_000:
        raise StreamError("invalid account-wide open orders")
    seen = set()
    for row in body:
        if not isinstance(row, dict) or not {"symbol", "orderId"} <= row.keys():
            raise StreamError("invalid open-order row")
        symbol = _name(row["symbol"])
        if type(row["orderId"]) is not int or row["orderId"] < 0:
            raise StreamError("invalid open-order identity")
        key = (symbol, row["orderId"])
        if key in seen:
            raise StreamError("duplicate open-order identity")
        seen.add(key)


def select_initial_observation(raw, expected_sha256, http):
    """Bind to a prior observed UID, without declaring it independently verified."""
    if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise StreamError("selected initial observation changed")
    wrapped = json.loads(raw, object_pairs_hook=_unique_object)
    if (
        wrapped["schema_version"] != "portfolio.testnet_initial_account_observation.v1"
        or wrapped["endpoint"] != TESTNET_REST
        or http.base_url != TESTNET_REST
        or wrapped["path"] != "/api/v3/account"
        or wrapped["key_sha256"] != hashlib.sha256(http.api_key.encode()).hexdigest()
        or hashlib.sha256(wrapped["response_body"].encode()).hexdigest()
        != wrapped["response_sha256"]
    ):
        raise StreamError("initial observation source mismatch")
    body = json.loads(wrapped["response_body"], object_pairs_hook=_unique_object)
    uid = str(body["uid"])
    account_balances(body, uid)
    return bind_source(http, uid)


class TestnetObservationJournal(UserStreamJournal):
    """Account-wide raw envelopes only; never apply them to native balances/orders."""

    __test__ = False

    def __init__(self, path, binding, **kwargs):
        _binding(binding)
        super().__init__(path, binding, **kwargs)

    def begin_collection(self, fence, anchor, started_ns):
        if set(anchor) != {"profile", "selection_sha256"} or anchor["profile"] != PROFILE:
            raise StreamError("testnet observation profile cannot collect recovery evidence")
        _digest(anchor["selection_sha256"])
        now = self.clock_ns()
        if (
            type(started_ns) is not int
            or type(now) is not int
            or not 0 < started_ns <= now <= started_ns + 60_000_000_000
        ):
            raise StreamError("invalid testnet observation start time")
        return super().begin_collection(fence, anchor, started_ns)

    def record_collection(self, *args, **kwargs):
        raise StreamError("testnet observations cannot seal strict account evidence")

    def finish_observation(self, fence, collection_id, hashes):
        self.assert_fence(fence)
        if collection_id is None or collection_id != self._active_collection:
            raise StreamError("active testnet observation required")
        self._append(
            "testnet_observation_completed", collection_id=collection_id, response_sha256=hashes
        )
        self._active_collection = None

    def transport_alive(self):
        super().transport_alive()
        self._append("testnet_transport_alive")

    def observe(self, raw):
        self.fence()
        try:
            if len(raw) > 65_536:
                raise StreamError("oversized testnet event")
            body = json.loads(raw, object_pairs_hook=_unique_object)
            if (
                type(body["subscriptionId"]) is not int
                or body["subscriptionId"] != self.subscription_id
            ):
                raise StreamError("foreign testnet subscription")
            event = body["event"]
            if (
                type(event["E"]) is not int
                or not 0 <= self.clock_ns() - event["E"] * 1_000_000 <= self.max_age_ns
            ):
                raise StreamError("stale/future testnet event")
            # Persist all source-bound envelopes before interpreting their kind.
            self.revision += 1
            self._append("testnet_event", raw=raw.decode())
            if event["e"] not in {
                "outboundAccountPosition",
                "balanceUpdate",
                "executionReport",
                "externalLockUpdate",
                "listStatus",
            }:
                raise StreamError("testnet event requires review or ended subscription")
            # Raw evidence only: no deduplication, balance patching, or fill inference.
            self.transport_alive()
            return False
        except Exception:
            self.disconnect("invalid or terminal testnet account event")
            raise StreamError("invalid or terminal testnet account event") from None


def _summary(bodies, binding, collection_id, hashes):
    first, opened, opened_after, last = bodies
    balances = account_balances(first, binding.account_uid)
    account_balances(last, binding.account_uid)
    _open_orders(opened)
    _open_orders(opened_after)
    if first != last or opened != opened_after:
        raise StreamError("testnet account changed during observation")
    return {
        "profile": PROFILE,
        "collection_id": collection_id,
        "assets_recorded": len(balances),
        "nonzero_assets": sum(free + locked > 0 for free, locked in balances.values()),
        "open_orders_recorded": len(opened),
        "response_sha256": [list(pair) for pair in hashes],
        "uid_matches_selected_observation": True,
        "independent_uid_verified": False,
        "baseline_qualified": False,
        "api_key_restrictions_verified": False,
        "api_trading_enabled": None,
        "atomic_revision_verified": False,
        "downtime_history_complete": False,
        "runtime_ready": False,
    }


async def collect_testnet_observation(http, journal, *, selection_sha256):
    if not isinstance(journal, TestnetObservationJournal) or http.base_url != TESTNET_REST:
        raise StreamError("explicit testnet observation transport required")
    _digest(selection_sha256)
    fence, started = journal.fence(), journal.clock_ns()
    collection_id = journal.begin_collection(
        fence, {"profile": PROFILE, "selection_sha256": selection_sha256}, started
    )
    hashes, bodies = [], []
    previous_ns = started
    try:
        async with asyncio.timeout(60):
            for path, params in REQUESTS:
                journal.assert_fence(fence)
                if bind_source(http, journal.binding.account_uid) != journal.binding:
                    raise StreamError("testnet source changed")
                now = journal.clock_ns()
                if type(now) is not int or not previous_ns <= now <= started + 60_000_000_000:
                    raise StreamError("testnet observation clock changed")
                raw = await http.sign_request(
                    HttpMethod.GET,
                    path,
                    payload={**params, "timestamp": str(now // 1_000_000), "recvWindow": "5000"},
                )
                received = journal.clock_ns()
                if type(received) is not int or not now <= received <= started + 60_000_000_000:
                    raise StreamError("testnet observation clock changed")
                journal.record_response(fence, collection_id, path, dict(params), raw, received)
                hashes.append((path, hashlib.sha256(raw).hexdigest()))
                bodies.append(json.loads(raw, object_pairs_hook=_unique_object))
                previous_ns = received
            result = _summary(bodies, journal.binding, collection_id, hashes)
            if bind_source(http, journal.binding.account_uid) != journal.binding:
                raise StreamError("testnet source changed")
            ended = journal.clock_ns()
            if type(ended) is not int or not previous_ns <= ended <= started + 60_000_000_000:
                raise StreamError("testnet observation clock changed")
            journal.finish_observation(fence, collection_id, hashes)
            return result
    finally:
        journal.abort_collection(collection_id)


def replay_testnet_observation(raw, *, source, expected_sha256, collection_id, selection_sha256):
    """Pure local replay of one sealed observation; no current transport object."""
    _binding(source)
    _digest(selection_sha256)
    if (
        source.endpoint != TESTNET_REST
        or not 0 < len(raw) <= 64 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise StreamError("testnet archive source/digest mismatch")
    previous, epoch, started, finished = "0" * 64, None, None, None
    receipts = []
    last_ns = 0
    response_ns = 0
    seen_epochs = set()
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise StreamError("incomplete testnet archive row")
        row = json.loads(line, object_pairs_hook=_unique_object)
        digest = row.pop("sha256")
        if (
            type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous"] != previous
            or row["binding"] != asdict(source)
            or hashlib.sha256(canonical(row)).hexdigest() != digest
        ):
            raise StreamError("testnet archive integrity mismatch")
        previous = digest
        if (
            type(row["received_ns"]) is not int
            or row["received_ns"] <= 0
            or row["received_ns"] < last_ns
        ):
            raise StreamError("testnet archive clock changed")
        prior_ns, last_ns = last_ns, row["received_ns"]
        kind = row["kind"]
        if kind in {"process_started", "disconnected"}:
            epoch = None
        elif kind == "subscribed":
            if (
                not isinstance(row["epoch"], str)
                or not row["epoch"]
                or row["epoch"] in seen_epochs
                or type(row.get("subscription_id")) is not int
                or row["subscription_id"] < 0
            ):
                raise StreamError("invalid testnet subscription epoch")
            epoch = row["epoch"]
            seen_epochs.add(epoch)
        if kind == "rest_started" and row.get("collection_id") == collection_id:
            if (
                started is not None
                or not epoch
                or row["epoch"] != epoch
                or row["anchor"] != {"profile": PROFILE, "selection_sha256": selection_sha256}
                or type(row["started_ns"]) is not int
                or not 0
                < row["started_ns"]
                <= row["received_ns"]
                <= row["started_ns"] + 60_000_000_000
                or row["started_ns"] < prior_ns
            ):
                raise StreamError("invalid selected testnet observation")
            started = row
            response_ns = row["started_ns"]
        elif started is not None and finished is None:
            if (
                row["epoch"] != epoch
                or epoch != started["epoch"]
                or row["received_ns"] > started["started_ns"] + 60_000_000_000
            ):
                raise StreamError("testnet archive epoch/time changed")
            if kind == "testnet_transport_alive":
                continue
            if row.get("collection_id") != collection_id:
                raise StreamError("testnet observation interrupted")
            if kind == "rest_response":
                if (
                    len(receipts) >= 4
                    or (row["path"], row["params"]) != REQUESTS[len(receipts)]
                    or type(row["response_ns"]) is not int
                    or not response_ns <= row["response_ns"] <= row["received_ns"]
                    or hashlib.sha256(row["raw"].encode()).hexdigest() != row["response_sha256"]
                ):
                    raise StreamError("testnet receipt mismatch")
                receipts.append(row)
                response_ns = row["response_ns"]
            elif kind == "testnet_observation_completed":
                finished = row
            else:
                raise StreamError("testnet observation did not complete")
        elif finished is not None and row.get("collection_id") == collection_id:
            raise StreamError("testnet observation identity reused")
    if finished is None or len(receipts) != 4:
        raise StreamError("complete testnet observation required")
    hashes = [[row["path"], row["response_sha256"]] for row in receipts]
    if hashes != finished["response_sha256"]:
        raise StreamError("testnet completion hash mismatch")
    return _summary(
        [json.loads(row["raw"], object_pairs_hook=_unique_object) for row in receipts],
        source,
        collection_id,
        hashes,
    )

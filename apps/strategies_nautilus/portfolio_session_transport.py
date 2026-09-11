"""Source-bound ADR-017 account/order/trade reads and fixed session ownership.

GET-only. A collected receipt can support native recovery, never grant trading or
prove global exchange continuity. The observation-only profile remains separate.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_stream import (
    StreamError,
    UserStreamJournal,
    bind_source,
    canonical,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    Ed25519TestnetReadOnlyHttpClient,
)
from apps.strategies_nautilus.portfolio_testnet_observation import (
    TestnetObservationJournal,
    _binding,
    _digest,
    _open_orders,
    account_balances,
)
from apps.strategies_nautilus.portfolio_venue import _unique_object

PROFILE = "portfolio.testnet_session_collection.v1"
SCOPE = "testnet-engineering-session-v1-20260911"
STATE_ROOT = Path.home() / ".local/state/trader/spot-testnet-engineering-v1"
ORDER_FIELDS = (
    "symbol",
    "clientOrderId",
    "orderId",
    "side",
    "origQty",
    "executedQty",
    "price",
    "cummulativeQuoteQty",
    "status",
    "type",
    "timeInForce",
    "orderListId",
    "time",
    "updateTime",
)


def private_read(path, limit=32 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > limit
        ):
            raise StreamError("private bounded session file required")
        raw = source.read(limit + 1)
        if len(raw) > limit:
            raise StreamError("session file grew beyond bound")
        return raw


def write_private_new(path, raw):
    """Exclusive publication; a failed fsync leaves the file for explicit review."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class SessionLease:
    """One account experiment across invocations; no CLI root/session-ID override.

    The manifest never changes. The exclusive activation marker is written before
    creating the native ledger. Missing ledger after activation is ambiguous and
    cannot be interpreted as a fresh allowance. Tests can supply a temporary root.
    """

    def __init__(self, binding, selection_sha256, *, root=STATE_ROOT):
        _binding(binding)
        _digest(selection_sha256)
        self.root, self.binding = Path(root), binding
        self._fd = None
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise StreamError("private session directory required")
        try:
            self._fd = os.open(
                self.root / "owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise StreamError("private session lease required")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            selected = {
                "scope": SCOPE,
                "source": asdict(binding),
                "selection_sha256": selection_sha256,
            }
            manifest = self.root / "scope.json"
            if manifest.exists():
                self.state = json.loads(private_read(manifest), object_pairs_hook=_unique_object)
                if any(self.state.get(k) != v for k, v in selected.items()):
                    raise StreamError("fixed account scope/source cannot be replaced")
                sid = self.state.get("session_id")
                if (
                    not isinstance(sid, str)
                    or len(sid) != 20
                    or not sid.isascii()
                    or not sid.isalnum()
                ):
                    raise StreamError("invalid fixed session identity")
            else:
                if any(
                    (self.root / p).exists()
                    for p in ("activated.json", "native.json", "stream.jsonl")
                ):
                    raise StreamError("missing scope manifest cannot reset existing session files")
                self.state = selected | {"session_id": uuid4().hex[:20]}
                write_private_new(manifest, canonical(self.state))
            readme = self.root / "README.md"
            if not readme.exists():
                write_private_new(
                    readme,
                    b"# Private testnet engineering session\n\nFixed ADR-017 account/session ownership and private evidence. Current phase: transport/recovery qualification. No production credentials or unrelated-asset operations. Native activation is exclusive; never delete files to reset an allowance. Next entrypoint: apps.ops.portfolio_session_transport.\n",
                )
        except BaseException:
            self.close()
            raise

    @property
    def checkpoint_path(self):
        return self.root / "native.json"

    def activate(self):
        if self._fd is None or self.checkpoint_path.exists():
            raise StreamError("owned unused session activation required")
        write_private_new(self.root / "activated.json", canonical(self.state))

    def assert_active(self):
        if self._fd is None:
            raise StreamError("session lease is closed")
        if json.loads(private_read(self.root / "activated.json")) != self.state:
            raise StreamError("session activation changed")
        if not self.checkpoint_path.is_file():
            raise StreamError("activated session lacks native checkpoint; do not recreate")

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


class SessionReadHttpClient(Ed25519TestnetReadOnlyHttpClient):
    """Exact GET selectors and no upstream signed-query logging or write endpoint."""

    def __init__(self, *args, client_order_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.client_order_ids = frozenset(client_order_ids)
        self.venue_order_ids = set()

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        params = dict(payload or {})
        selectors = {
            k: v for k, v in params.items() if k not in {"timestamp", "recvWindow", "signature"}
        }
        valid = (
            (url_path == "/api/v3/account" and selectors == {"omitZeroBalances": "false"})
            or (url_path == "/api/v3/openOrders" and selectors == {})
            or (
                url_path == "/api/v3/order"
                and selectors.get("origClientOrderId") in self.client_order_ids
                and set(selectors) == {"symbol", "origClientOrderId"}
                and selectors["symbol"] == "BTCUSDT"
            )
            or (
                url_path == "/api/v3/myTrades"
                and selectors.get("orderId") in self.venue_order_ids
                and set(selectors) == {"symbol", "orderId", "limit"}
                and selectors["symbol"] == "BTCUSDT"
                and selectors["limit"] == "1000"
            )
        )
        if (
            self.base_url != TESTNET_REST
            or http_method != HttpMethod.GET
            or not valid
            or set(params) != set(selectors) | {"timestamp", "recvWindow", "signature"}
            or params["recvWindow"] != "5000"
        ):
            raise StreamError("only exact known-session testnet GET requests allowed")
        try:
            async with asyncio.timeout(10):
                response = await self._client.request(
                    HttpMethod.GET,
                    url=TESTNET_REST + url_path + "?" + urlencode(params),
                    headers=self.headers,
                    body=None,
                    keys=ratelimiter_keys,
                )
            if response.status != 200 or len(response.body) > 8 * 1024 * 1024:
                raise StreamError(
                    "session GET rejected or oversized; original intent remains uncertain"
                )
            return response.body
        except Exception:
            raise StreamError("session GET failed; no automatic retry") from None


class SessionJournal(TestnetObservationJournal):
    """Full-account raw archive with separate engineering recovery receipts."""

    def __init__(self, *args, **kwargs):
        self.execution_handler = None
        self.account_handler = None
        super().__init__(*args, **kwargs)

    def begin_collection(self, fence, anchor, started_ns):
        if set(anchor) != {"profile", "checkpoint_sha256"} or anchor["profile"] != PROFILE:
            raise StreamError("explicit session recovery collection required")
        _digest(anchor["checkpoint_sha256"])
        return UserStreamJournal.begin_collection(self, fence, anchor, started_ns)

    def record_response(self, fence, collection_id, path, params, raw, response_ns):
        self.assert_fence(fence)
        if collection_id != self._active_collection or collection_id is None:
            raise StreamError("active session collection required")
        if path not in {
            "/api/v3/account",
            "/api/v3/openOrders",
            "/api/v3/order",
            "/api/v3/myTrades",
        }:
            raise StreamError("unexpected session receipt path")
        if (
            set(params) - {"omitZeroBalances", "symbol", "origClientOrderId", "orderId", "limit"}
            or len(raw) > 8 * 1024 * 1024
        ):
            raise StreamError("unsigned bounded session response required")
        self._append(
            "rest_response",
            collection_id=collection_id,
            path=path,
            params=params,
            raw=raw.decode(),
            response_ns=response_ns,
            response_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def seal(self, fence, collection_id, evidence):
        self.assert_fence(fence)
        if collection_id != self._active_collection or collection_id is None:
            raise StreamError("active session collection required")
        self._append(
            "session_collection_completed",
            collection_id=collection_id,
            evidence_sha256=hashlib.sha256(canonical(evidence)).hexdigest(),
        )
        self._active_collection = None

    def observe(self, raw):
        duplicate = super().observe(raw)  # durable source-bound raw envelope first
        event = json.loads(raw, object_pairs_hook=_unique_object)["event"]
        try:
            if event["e"] == "executionReport" and self.execution_handler is not None:
                self.execution_handler(canonical(event))
            elif event["e"] == "outboundAccountPosition" and self.account_handler is not None:
                self.account_handler(event)
            else:
                raise StreamError("account event requires attached native handlers/reconciliation")
        except Exception:
            self.disconnect("session event could not be applied or correlated")
            raise StreamError("session event requires native reconciliation") from None
        return duplicate


@dataclass(frozen=True)
class CollectedSession:
    checkpoint_sha256: str
    evidence: dict
    fence: object
    collection_id: str
    evidence_sha256: str

    def assert_current(self, journal, checkpoint_sha256):
        journal.assert_fence(self.fence)
        if self.checkpoint_sha256 != checkpoint_sha256 or self.evidence["source"] != asdict(
            journal.binding
        ):
            raise StreamError("session receipt/checkpoint/source changed")
        if hashlib.sha256(canonical(self.evidence)).hexdigest() != self.evidence_sha256:
            raise StreamError("sealed session evidence changed")
        if not 0 <= journal.clock_ns() - self.evidence["received_ns"] <= 5_000_000_000:
            raise StreamError("session recovery receipt expired")


def order_projection(row):
    result = {key: row[key] for key in ORDER_FIELDS}
    if result["symbol"] != "BTCUSDT" or type(result["orderId"]) is not int or result["orderId"] < 0:
        raise StreamError("invalid original session order")
    return result


async def collect_session(http, journal, state, checkpoint_sha256):
    """Bracket original-ID reads with stable complete account-wide observations.

    A full 1000-trade page is refused because completeness is unknown. Matching
    REST reads and a local subscription fence are not global stream continuity.
    """
    if type(http) is not SessionReadHttpClient or type(journal) is not SessionJournal:
        raise StreamError("dedicated session transport required")
    _digest(checkpoint_sha256)
    if (
        asdict(journal.binding) != state["source"]
        or bind_source(http, journal.binding.account_uid) != journal.binding
    ):
        raise StreamError("session checkpoint/transport source mismatch")
    if set(state["intents"]) != http.client_order_ids or len(state["intents"]) > 2:
        raise StreamError("exact original session order IDs required")
    started = journal.clock_ns()
    if (
        not state["started_ns"] <= state["updated_ns"] < started
        or started - state["started_ns"] > 86_400_000_000_000
    ):
        raise StreamError("session history must be later than checkpoint and within 24 hours")
    fence = journal.fence()
    collection_id = journal.begin_collection(
        fence, {"profile": PROFILE, "checkpoint_sha256": checkpoint_sha256}, started
    )
    previous = started

    async def read(path, params):
        nonlocal previous
        journal.assert_fence(fence)
        now = journal.clock_ns()
        if (
            not previous <= now <= started + 60_000_000_000
            or bind_source(http, journal.binding.account_uid) != journal.binding
        ):
            raise StreamError("session source/clock changed during collection")
        raw = await http.sign_request(
            HttpMethod.GET,
            path,
            params | {"timestamp": str(now // 1_000_000), "recvWindow": "5000"},
        )
        received = journal.clock_ns()
        if not now <= received <= started + 60_000_000_000:
            raise StreamError("session collection clock regressed or expired")
        journal.record_response(fence, collection_id, path, params, raw, received)
        previous = received
        return json.loads(raw, object_pairs_hook=_unique_object)

    try:
        async with asyncio.timeout(60):
            account = await read("/api/v3/account", {"omitZeroBalances": "false"})
            opened = await read("/api/v3/openOrders", {})
            account_balances(account, journal.binding.account_uid)
            _open_orders(opened)
            orders, trades = [], []
            for oid in sorted(state["intents"]):
                row = order_projection(
                    await read("/api/v3/order", {"symbol": "BTCUSDT", "origClientOrderId": oid})
                )
                if row["clientOrderId"] != oid:
                    raise StreamError("original client order query returned a different order")
                http.venue_order_ids.add(str(row["orderId"]))
                fills = await read(
                    "/api/v3/myTrades",
                    {"symbol": "BTCUSDT", "orderId": str(row["orderId"]), "limit": "1000"},
                )
                if (
                    not isinstance(fills, list)
                    or len(fills) >= 1000
                    or any(t["orderId"] != row["orderId"] for t in fills)
                ):
                    raise StreamError("complete original trade history required")
                orders.append(row)
                trades.extend(fills)
            after_opened = await read("/api/v3/openOrders", {})
            after_account = await read("/api/v3/account", {"omitZeroBalances": "false"})
            if account != after_account or opened != after_opened:
                raise StreamError("account/order state changed during session collection")
            projected_open = [order_projection(row) for row in opened]
            active = [row for row in orders if row["status"] in {"NEW", "PARTIALLY_FILLED"}]
            if sorted(projected_open, key=lambda r: r["orderId"]) != sorted(
                active, key=lambda r: r["orderId"]
            ):
                raise StreamError("foreign or conflicting account-wide open order")
            evidence = {
                # Numeric reconciliation consumes the existing detached schema.
                # Authentic transport/freshness authority stays with this receipt.
                "profile": "offline_testnet_session_recovery_v1",
                "source": state["source"],
                "history_start_ns": state["started_ns"],
                "received_ns": previous,
                "account": account,
                "open_orders": projected_open,
                "orders": orders,
                "trades": trades,
            }
            journal.seal(fence, collection_id, evidence)
            result = CollectedSession(
                checkpoint_sha256,
                evidence,
                fence,
                collection_id,
                hashlib.sha256(canonical(evidence)).hexdigest(),
            )
            result.assert_current(journal, checkpoint_sha256)
            return result
    finally:
        journal.abort_collection(collection_id)

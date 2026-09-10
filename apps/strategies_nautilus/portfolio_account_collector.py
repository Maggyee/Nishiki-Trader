"""Explicit read-only signed Binance collector; no credential discovery or orders.

Uses an already configured native BinanceHttpClient. Stable REST reads are useful
reconciliation evidence, but do not establish an atomic user-stream revision.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_account import AccountAnchor, AccountEvidence
from apps.strategies_nautilus.portfolio_stream import StreamFence, bind_source
from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    VenueInputError,
    _unique_object,
)

DAY_NS = 86_400_000_000_000


class BinanceAccountReadOnlyHttpClient(BinanceHttpClient):
    """Native signer/HTTP I/O with bounded GET paths and no signed-URL logging.

    The upstream send_request logs its signed query at DEBUG. This account-only
    extension avoids that logging path and never includes private errors in exceptions.
    """

    async def send_request(self, http_method, url_path, payload=None, ratelimiter_keys=None):
        if (
            self.base_url.rstrip("/")
            not in {"https://api.binance.com", "https://testnet.binance.vision"}
            or http_method != HttpMethod.GET
            or url_path
            not in {
                "/sapi/v1/account/apiRestrictions",
                "/api/v3/account",
                "/api/v3/openOrders",
                "/api/v3/allOrders",
                "/api/v3/myTrades",
            }
        ):
            raise VenueInputError("only qualified read-only account requests are allowed")
        try:
            async with asyncio.timeout(10):
                response = await self._client.request(
                    http_method,
                    url=self.base_url.rstrip("/")
                    + url_path
                    + ("?" + urlencode(payload) if payload else ""),
                    headers=self.headers,
                    body=None,
                    keys=ratelimiter_keys,
                )
            if response.status != 200:
                raise VenueInputError("signed account read rejected")
            return response.body
        except Exception:
            raise VenueInputError("signed account read failed") from None


@dataclass(frozen=True)
class CollectedAccount:
    evidence: AccountEvidence
    wire_sha256: tuple[tuple[str, str], ...]
    api_trading_enabled: bool
    atomic_revision_verified: bool = False
    stream_fence: StreamFence | None = None
    collection_id: str | None = None


class BinanceReadOnlyAccountCollector:
    """Bounded signed GETs only. Caller owns credentials, connection and clock.

    Initial history is deliberately limited to 24 hours. Older anchors require
    a separately qualified continuous archive; exchange retention isn't assumed.
    """

    def __init__(self, client, *, clock_ns, max_pages=32, stream=None):
        if client.base_url.rstrip("/") not in {
            "https://api.binance.com",
            "https://testnet.binance.vision",
        }:
            raise VenueInputError("unsupported signed account endpoint")
        if type(max_pages) is not int or not 1 <= max_pages <= 32:
            raise VenueInputError("invalid account pagination bound")
        self.client = client
        self.clock_ns = clock_ns
        self.max_pages = max_pages
        self.stream = stream

    async def collect(self, anchor: AccountAnchor) -> CollectedAccount:
        hashes = []
        fence = None
        collection_id = None
        if self.stream is not None:
            if bind_source(self.client, anchor.venue_uid) != self.stream.binding:
                raise VenueInputError("REST/user-stream source mismatch")
            fence = self.stream.fence()

        async def get(path, params=None):
            # The native signer may mutate payload. Keep a separate unsigned copy.
            selectors = dict(params or {})
            payload = {
                **selectors,
                "timestamp": str(self.clock_ns() // 1_000_000),
                "recvWindow": "5000",
            }
            try:
                raw = await self.client.sign_request(HttpMethod.GET, path, payload=payload)
                received_ns = self.clock_ns()
                if self.stream is not None:
                    self.stream.record_response(
                        fence, collection_id, path, selectors, raw, received_ns
                    )
                body = raw.decode()
                parsed = json.loads(body, object_pairs_hook=_unique_object)
            except Exception:
                raise VenueInputError("signed account read failed") from None
            hashes.append((path, hashlib.sha256(raw).hexdigest()))
            return parsed, body, received_ns

        started = self.clock_ns()
        if not 0 < anchor.start_ns <= started or started - anchor.start_ns > DAY_NS:
            raise VenueInputError("account anchor requires a complete recent history archive")
        if self.stream is not None:
            collection_id = self.stream.begin_collection(
                fence,
                {**asdict(anchor), "quote": str(anchor.quote), "base": str(anchor.base)},
                started,
            )
        permissions, _, _ = await get("/sapi/v1/account/apiRestrictions")
        if (
            permissions.get("enableReading") is not True
            or type(permissions.get("enableSpotAndMarginTrading")) is not bool
        ):
            raise VenueInputError("account API reading permission absent/ambiguous")
        first, _, _ = await get("/api/v3/account", {"omitZeroBalances": "false"})
        if str(first.get("uid")) != anchor.venue_uid:
            raise VenueInputError("signed account UID mismatch")
        opened, _, _ = await get("/api/v3/openOrders")

        async def history(path, id_key, cursor_key):
            rows, seen = [], set()
            params = {
                "symbol": "BTCUSDT",
                "startTime": str(anchor.start_ns // 1_000_000),
                "limit": "1000",
            }
            for _ in range(self.max_pages):
                page, _, received = await get(path, params)
                if not isinstance(page, list) or len(page) > 1000:
                    raise VenueInputError("invalid account history page")
                ids = [r[id_key] for r in page]
                if any(type(i) is not int or i < 0 or i in seen for i in ids) or ids != sorted(
                    set(ids)
                ):
                    raise VenueInputError("duplicate or unordered account history page")
                if rows and ids and ids[0] <= rows[-1][id_key]:
                    raise VenueInputError("account history cursor did not advance")
                seen.update(ids)
                rows.extend(page)
                if len(page) < 1000:
                    return CapturedResponse(json.dumps(rows), received, anchor.venue_uid, "BTCUSDT")
                params = {"symbol": "BTCUSDT", cursor_key: str(ids[-1] + 1), "limit": "1000"}
            raise VenueInputError("account history pagination incomplete")

        orders = await history("/api/v3/allOrders", "orderId", "orderId")
        trades = await history("/api/v3/myTrades", "id", "fromId")
        opened_after, open_body, open_ns = await get("/api/v3/openOrders")
        last, account_body, account_ns = await get("/api/v3/account", {"omitZeroBalances": "false"})
        if first != last or opened != opened_after:
            raise VenueInputError(
                "account changed during collection; recollect before reconciliation"
            )
        if account_ns - started > 60_000_000_000:
            raise VenueInputError("account collection exceeded freshness window")
        if self.stream is not None:
            if bind_source(self.client, anchor.venue_uid) != fence.binding:
                raise VenueInputError("REST source changed during collection")
            self.stream.record_collection(fence, tuple(hashes), collection_id=collection_id)
        return CollectedAccount(
            AccountEvidence(
                CapturedResponse(account_body, account_ns, anchor.venue_uid),
                orders,
                trades,
                CapturedResponse(open_body, open_ns, anchor.venue_uid),
                anchor.start_ns,
                account_ns,
            ),
            tuple(hashes),
            permissions["enableSpotAndMarginTrading"],
            stream_fence=fence,
            collection_id=collection_id,
        )

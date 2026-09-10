"""Read-only Spot transport using Nautilus signing and native WebSocket I/O.

No execution client is created. Source credentials are explicit; this transport
does not select an account, discover secrets, or grant runtime readiness.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from uuid import uuid4

from nautilus_trader.adapters.binance.websocket.user import BinanceUserDataWebSocketClient
from nautilus_trader.core.nautilus_pyo3 import WebSocketClient, WebSocketConfig

from apps.strategies_nautilus.portfolio_account_collector import (
    BinanceAccountReadOnlyHttpClient,
    BinanceReadOnlyAccountCollector,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, bind_source, canonical
from apps.strategies_nautilus.portfolio_venue import _unique_object

WS_ENDPOINTS = {
    "https://api.binance.com": "wss://ws-api.binance.com:443/ws-api/v3",
    "https://testnet.binance.vision": "wss://ws-api.testnet.binance.vision/ws-api/v3",
}
SUBSCRIBE = "userDataStream.subscribe.signature"


class ReadOnlyBinanceUserStream(BinanceUserDataWebSocketClient):
    """Owned by one event loop. Every reconnect requires explicit fresh start.

    Reuses the native signer's HMAC/Ed25519 support and Rust WebSocket transport.
    Overrides request logging, session authentication, response dispatch and
    recovery: raw signed requests/errors must never enter application logs.
    """

    def __init__(self, http_client, *, api_secret, journal, clock, loop):
        if not isinstance(http_client, BinanceAccountReadOnlyHttpClient):
            raise StreamError("account-only HTTP client without signed-URL logging required")
        binding = bind_source(http_client, journal.binding.account_uid)
        if binding != journal.binding:
            raise StreamError("REST/user-stream source mismatch")
        if not isinstance(api_secret, str) or not api_secret:
            raise StreamError("explicit user-stream secret required")
        super().__init__(
            clock=clock,
            base_url=WS_ENDPOINTS[binding.endpoint],
            handler=lambda raw: None,
            api_key=http_client.api_key,
            api_secret=api_secret,
            loop=loop,
        )
        self.journal = journal
        self._http_client = http_client
        self._binding = binding
        self._generation = 0
        self._tainted = True
        self._requests = {}
        self._health_task = None
        self._starting = False
        journal.attach_transport(self._transport_current)

    def _transport_current(self):
        try:
            return (
                not self._tainted
                and self._client is not None
                and self._client.is_active()
                and not self._client.is_reconnecting()
                and not self._client.is_disconnecting()
                and bind_source(self._http_client, self._binding.account_uid) == self._binding
            )
        except Exception:
            return False

    def _invalidate(self, reason):
        self._tainted = True
        self._subscription_id = None
        self._is_authenticated = False
        # Persistence failure already blocks the journal; still wake all waiters.
        try:
            self.journal.disconnect(reason)
        finally:
            for _, future in self._requests.values():
                if not future.done():
                    future.set_exception(StreamError(reason))
            self._requests.clear()

    def _handle_message(self, raw):
        if self._tainted:
            return
        try:
            if len(raw) > 65_536:
                raise StreamError("oversized user-stream frame")
            message = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(message, dict):
                raise StreamError("invalid user-stream frame")
            if "id" not in message:
                self.journal.observe(raw)
                return
            request_id = message["id"]
            if not isinstance(request_id, str) or request_id not in self._requests:
                raise StreamError("unknown user-stream response")
            method, future = self._requests[request_id]
            if (
                type(message.get("status")) is not int
                or message["status"] != 200
                or "error" in message
                or "event" in message
                or not isinstance(message.get("result"), dict)
            ):
                raise StreamError("user-stream request rejected")
            if method == SUBSCRIBE:
                subscription_id = message["result"].get("subscriptionId")
                if type(subscription_id) is not int or subscription_id < 0:
                    raise StreamError("invalid subscription acknowledgement")
                # Bind synchronously before another event callback can run.
                self.journal.subscribed(subscription_id, self._binding)
                self._subscription_id = str(subscription_id)
            elif method == "ping":
                if message["result"]:
                    raise StreamError("invalid ping response")
                self.journal.transport_alive()
            elif method == "userDataStream.unsubscribe":
                self.journal.disconnect("subscription ended")
                self._subscription_id = None
            self._requests.pop(request_id)
            if not future.done():
                future.set_result(message)
        except Exception:
            # Do not echo server errors, signed payloads or malformed private data.
            with suppress(Exception):
                self._invalidate("user-stream response/event failed validation")

    async def _send_request(self, method, params=None, timeout=10.0):
        if method not in {SUBSCRIBE, "ping", "userDataStream.unsubscribe"}:
            raise StreamError("only read-only user-stream methods are allowed")
        if method == SUBSCRIBE and (
            self._subscription_id is not None
            or any(m == SUBSCRIBE for m, _ in self._requests.values())
        ):
            raise StreamError("subscription already active or pending")
        if not self._transport_current():
            raise StreamError("fresh user-stream transport required")
        request_id = str(uuid4())
        future = self._loop.create_future()
        self._requests[request_id] = (method, future)
        try:
            # Bound both network send and reply wait. Never call upstream's logger.
            async with asyncio.timeout(timeout):
                await self._client.send_text(
                    canonical({"id": request_id, "method": method, "params": params or {}})
                )
                return await future
        except BaseException as exc:
            self._requests.pop(request_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # retrieve if send failed after a callback rejected
            with suppress(Exception):
                self._invalidate("user-stream request interrupted or failed")
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise StreamError("user-stream request interrupted or failed") from None
        finally:
            self._requests.pop(request_id, None)

    async def connect(self):
        if self._client is not None or self._starting:
            raise StreamError("close existing user-stream transport before reconnecting")
        if bind_source(self._http_client, self._binding.account_uid) != self._binding:
            raise StreamError("REST source changed")
        self._starting = True
        self._generation += 1
        generation = self._generation
        self._tainted = False
        try:
            config = WebSocketConfig(
                url=self._base_url, headers=[], heartbeat=20, reconnect_max_attempts=1
            )
            async with asyncio.timeout(10):
                client = await WebSocketClient.connect(
                    loop_=self._loop,
                    config=config,
                    handler=lambda raw: (
                        self._handle_message(raw) if generation == self._generation else None
                    ),
                    post_reconnection=lambda: (
                        self._handle_reconnect() if generation == self._generation else None
                    ),
                )
            if generation != self._generation:
                await client.disconnect()
                raise StreamError("user-stream connection attempt superseded")
            self._client = client
        except BaseException as exc:
            with suppress(Exception):
                self._invalidate("user-stream connection failed")
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise StreamError("user-stream connection failed") from None
        finally:
            self._starting = False

    def _handle_reconnect(self):
        with suppress(Exception):
            self._invalidate("user-stream connection changed; fresh subscription required")

    async def subscribe_user_data_stream(self, pre_dispatch_hook=None):
        if self._subscription_id is not None or pre_dispatch_hook is not None:
            raise StreamError("fresh explicit subscription without dispatch hooks required")
        params = {
            "apiKey": self._api_key,
            "recvWindow": 5000,
            "timestamp": self._clock.timestamp_ms(),
        }
        params["signature"] = self._get_sign(
            "&".join(f"{key}={params[key]}" for key in sorted(params))
        )
        await self._send_request(SUBSCRIBE, params)
        self.journal.fence()
        return self._subscription_id

    async def start(self):
        try:
            await self.connect()
            await self.subscribe_user_data_stream()
            self._health_task = self._loop.create_task(self._health_loop())
        except BaseException:
            await self.disconnect()
            raise

    async def ping(self):
        self.journal.fence()
        await self._send_request("ping")
        self.journal.fence()

    async def _health_loop(self):
        try:
            while True:
                await asyncio.sleep(min(20, self.journal.max_age_ns / 3_000_000_000))
                await self.ping()
        except asyncio.CancelledError:
            raise
        except Exception:
            with suppress(Exception):
                await self.disconnect()

    async def collect(self, anchor):
        await self.ping()
        result = await BinanceReadOnlyAccountCollector(
            self._http_client,
            clock_ns=self.journal.clock_ns,
            stream=self.journal,
        ).collect(anchor)
        self.journal.assert_fence(result.stream_fence)
        return result

    async def disconnect(self):
        with suppress(Exception):
            self._invalidate("user-stream transport closed")
        self._generation += 1  # Ignore callbacks from a discarded native connection.
        health, self._health_task = self._health_task, None
        if health is not None and health is not asyncio.current_task():
            health.cancel()
            with suppress(asyncio.CancelledError):
                await health
        client, self._client = self._client, None
        if client is not None:
            try:
                async with asyncio.timeout(5):
                    await client.disconnect()
            except Exception:
                raise StreamError("user-stream transport close failed") from None

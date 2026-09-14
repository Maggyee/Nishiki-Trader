"""Bounded local-peer integration: native WebSockets and Nautilus Ed25519 signing.

No credential discovery, exchange endpoint override, reconnect or order method.
The caller supplies synthetic peer URLs and a signer bound to selected input bytes.
"""

from __future__ import annotations

import asyncio
import base64
import http.client
from contextlib import suppress
from urllib.parse import urlencode, urlsplit

from nautilus_trader.core.nautilus_pyo3 import WebSocketClient, WebSocketConfig

from apps.strategies_nautilus.portfolio_joint_observation import digest, raw_fields
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence, loopback_url
from apps.strategies_nautilus.portfolio_market_depth import MAX_FRAME, DepthError
from apps.strategies_nautilus.portfolio_stream import canonical


def local_get(base, path, params, headers):
    """One bounded stdlib HTTP read, without redirect or proxy handling."""
    parsed = urlsplit(loopback_url(base, "http"))
    connection = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=10)
    try:
        connection.request(
            "GET", path + ("?" + urlencode(params) if params else ""), headers=headers
        )
        response = connection.getresponse()
        raw = response.read(16 * MAX_FRAME + 1)
        return response.status, response.getheader("X-MBX-USED-WEIGHT-1M"), raw
    finally:
        connection.close()


async def run_loopback(journal, signer, *, observe_seconds=0.1):
    """Run one local fixture scope and always close both sockets on failure.

    Single event-loop ownership serializes callbacks. There is no executable
    exchange capture path. An interrupted request consumes preparation permanently.
    """
    if type(journal.state) is not RoutedJointEvidence:
        raise DepthError("explicit_bounded_loopback_profile_required")
    return await _run_loopback(journal, signer, observe_seconds=observe_seconds)


async def _run_loopback(journal, signer, *, observe_seconds, transport=None):
    state = journal.state
    if not 0 < observe_seconds <= 10:
        raise DepthError("explicit_bounded_loopback_profile_required")
    if transport is not None:
        from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
        from apps.strategies_nautilus.portfolio_joint_tls_transport import TLSBackend

        if type(state) is not TLSJointEvidence or type(transport) is not TLSBackend:
            raise DepthError("explicit_tls_loopback_backend_required")
    manifest = state.manifest
    endpoints = manifest["wire_endpoints"]
    for name, scheme in (("http", "http"), ("account", "ws"), ("market", "ws")):
        loopback_url(endpoints[name], scheme)
    if digest(signer.api_key.encode()) != manifest["source"]["key_sha256"]:
        raise DepthError("loopback_signer_does_not_match_selection")
    loop = asyncio.get_running_loop()
    clients, closing, pong_tasks = {}, set(), set()
    connected = {name: asyncio.Event() for name in ("account", "market")}
    ended = False
    failure = None
    pending_reply = None
    first_frames = asyncio.Event()

    def fail(code):
        nonlocal failure
        if failure is None:
            failure = code
            journal._abort(code, {"kind": "loopback_transport_failure"})
        first_frames.set()
        if pending_reply is not None and not pending_reply.done():
            pending_reply.set_exception(DepthError(code))

    if transport is not None:
        transport.on_failure = fail

    def append(kind, **fields):
        if failure:
            raise DepthError(failure)
        journal.append(kind, **fields)

    def account_frame(raw):
        if ended or failure:
            return
        previous = state.ws_index
        try:
            append("account_wire", epoch=manifest["account_epoch"], **raw_fields(raw))
            if (
                state.ws_index != previous
                and pending_reply is not None
                and not pending_reply.done()
            ):
                pending_reply.set_result(None)
        except Exception:
            fail("loopback_account_callback_failed")

    def market_frame(raw):
        if ended or failure:
            return
        try:
            # A native callback may precede connect() returning. Mark the sole
            # prepared connection now; connect must still return an active handle
            # before a snapshot request can proceed.
            if not state.market_connected:
                mark_market_connected()
            append("market_frame", epoch=manifest["market_epoch"], **raw_fields(raw))
            if all(book.pending or book.last_id is not None for book in state.books.values()):
                first_frames.set()
        except Exception:
            fail("loopback_market_callback_failed")

    async def pong(name, payload):
        try:
            # Native callbacks can run before connect() returns its handle.
            # The enclosing capture timeout and cleanup also bound this wait.
            await connected[name].wait()
            client = clients.get(name)
            if client is None or not client.is_active():
                raise DepthError("loopback_ping_without_transport")
            await client.send_pong(payload)
        except Exception:
            fail("loopback_pong_failed")

    def ping(name, raw):
        if ended or failure:
            return
        try:
            if name == "market" and not state.market_connected:
                mark_market_connected()
            elif name == "account" and state.ws_index == 0:
                mark_account_connected()
            # Each connection retains its own payload-echo control-rate gate.
            append(
                name + "_pong",
                epoch=manifest[name + "_epoch"],
                payload_b64=base64.b64encode(raw).decode(),
                echo_b64=base64.b64encode(raw).decode(),
            )
            task = loop.create_task(pong(name, raw))
            pong_tasks.add(task)
            task.add_done_callback(pong_tasks.discard)
        except Exception:
            fail("loopback_control_callback_failed")

    def healthy():
        if failure:
            raise DepthError(failure)
        if journal.failed:
            raise DepthError("loopback_journal_failed")
        if digest(signer.api_key.encode()) != manifest["source"]["key_sha256"]:
            raise DepthError("loopback_signer_changed")
        for name, client in clients.items():
            if name not in closing and (
                not client.is_active() or client.is_reconnecting() or client.is_disconnecting()
            ):
                raise DepthError("loopback_transport_lost")

    def prepare():
        healthy()
        op = state.next_operation()
        op_id = state.prepared_count
        append(
            "operation_prepared", operation=op, operation_id=op_id, request_id=f"loopback-{op_id}"
        )
        return op, op_id

    async def read():
        op, op_id = prepare()
        if op["kind"] != "rest":
            raise DepthError("loopback_rest_out_of_sequence")
        sent, sent_mono = journal.clock()
        params, headers = dict(op["params"]), {}
        if op["phase"].startswith("account_"):
            params.update(timestamp=str(sent // 1_000_000), recvWindow="5000")
            params["signature"] = signer._get_sign(urlencode(params))
            headers["X-MBX-APIKEY"] = signer.api_key
        async with asyncio.timeout(10):
            if transport is None:
                status, usage, raw = await asyncio.to_thread(
                    local_get, endpoints["http"], op["path"], params, headers
                )
            else:
                status, usage, raw = await transport.get(op, params, headers)
        # Always preserve returned bytes/status before any body or usage validation.
        fields = {k: op[k] for k in ("phase", "method", "path", "params")}
        append(
            "rest_response",
            **fields,
            operation_id=op_id,
            sent_ns=sent,
            sent_monotonic_ns=sent_mono,
            status=status,
            used_weight_1m=(
                int(usage) if usage and usage.isascii() and usage.isdecimal() else None
            ),
            epoch=manifest["account_epoch"],
            **raw_fields(raw),
        )
        healthy()

    async def connect(name, handler):
        if transport is not None:
            async with asyncio.timeout(10):
                clients[name] = await transport.connect(name, handler, lambda raw: ping(name, raw))
            connected[name].set()
            healthy()
            return
        url = endpoints[name] + (
            "/stream?streams="
            + "/".join(s.lower() + "@depth@100ms" for s in state.manifest["symbols"])
            if name == "market"
            else "/ws-api/v3"
        )
        config = WebSocketConfig(url=url, headers=[], heartbeat=None, reconnect_max_attempts=0)
        async with asyncio.timeout(10):
            client = await WebSocketClient.connect(
                loop_=loop,
                config=config,
                handler=handler,
                ping_handler=lambda raw: ping(name, raw),
                post_reconnection=lambda: fail("loopback_unexpected_reconnect"),
            )
        clients[name] = client
        connected[name].set()
        healthy()

    def mark_account_connected():
        if state.ws_index:
            return
        append(
            "ws_operation",
            operation_id=state.prepared["operation_id"],
            operation="ws_api_connection",
            status=200,
            epoch=manifest["account_epoch"],
        )

    def mark_market_connected():
        if state.market_connected:
            return
        op = state.prepared
        append(
            "market_connected",
            operation_id=op["operation_id"],
            epoch=manifest["market_epoch"],
            url="wss://stream.testnet.binance.vision/stream?streams="
            + "/".join(s.lower() + "@depth@100ms" for s in state.manifest["symbols"]),
        )

    async def account_request():
        nonlocal pending_reply
        op, op_id = prepare()
        pending_reply = loop.create_future()
        params = {}
        if op["operation"] == "userDataStream.subscribe.signature":
            params = {
                "apiKey": signer.api_key,
                "recvWindow": 5000,
                "timestamp": journal.clock()[0] // 1_000_000,
            }
            params["signature"] = signer._get_sign(
                "&".join(f"{key}={params[key]}" for key in sorted(params))
            )
        try:
            async with asyncio.timeout(10):
                await clients["account"].send_text(
                    canonical(
                        {"id": f"loopback-{op_id}", "method": op["operation"], "params": params}
                    )
                )
                await pending_reply
        finally:
            if not pending_reply.done():
                pending_reply.cancel()
            elif not pending_reply.cancelled():
                pending_reply.exception()
            pending_reply = None

    async def health_loop():
        try:
            while True:
                await asyncio.sleep(0.02)
                healthy()
                if state.market_connected and not state.market_closed:
                    append("tick")
        except asyncio.CancelledError:
            raise
        except Exception:
            fail("loopback_health_failed")

    health = loop.create_task(health_loop())
    try:
        async with asyncio.timeout(120):
            await read()
            prepare()
            await connect("account", account_frame)
            mark_account_connected()
            await account_request()
            for _ in range(6):
                await read()  # full account, metadata, then original book routes
            prepare()
            async with asyncio.timeout(15):
                await connect("market", market_frame)
                mark_market_connected()
                await first_frames.wait()
                healthy()
                for _ in state.manifest["symbols"]:
                    await read()
            await read()  # linked clock sample
            await asyncio.sleep(observe_seconds)
            for _ in range(5):
                await read()  # second full account, final clock
            await account_request()  # unsubscribe acknowledgement before closure
            healthy()
        async with asyncio.timeout(5):
            # Initiate both closes together so one stalled close cannot postpone
            # the other or open a second shutdown allowance in finally.
            closing.update(clients)
            outcomes = await asyncio.gather(
                *(clients[name].disconnect() for name in ("market", "account")),
                return_exceptions=True,
            )
            if any(isinstance(outcome, BaseException) for outcome in outcomes):
                raise DepthError("loopback_transport_close_failed")
            for name in ("market", "account"):
                append("closed", transport=name, epoch=manifest[name + "_epoch"])
            if pong_tasks:
                await asyncio.gather(*pong_tasks)
        ended = True
        journal.complete()
        return {
            "status": "loopback_joint_completed",
            "summary": state.summary(),
            "venue_requests_made": 0,
        }
    except BaseException as exc:
        fail(str(exc) if isinstance(exc, DepthError) else "loopback_transport_interrupted")
        if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
            raise
        return {"status": "loopback_joint_failed", "reason": failure, "venue_requests_made": 0}
    finally:
        ended = True
        health.cancel()
        with suppress(asyncio.CancelledError):
            await health
        for task in list(pong_tasks):
            task.cancel()
        if pong_tasks:
            await asyncio.gather(*pong_tasks, return_exceptions=True)
        # Both failure closes share one five-second allowance, with no retries.
        remaining = [client for name, client in clients.items() if name not in closing]
        closing.update(clients)
        if remaining:
            with suppress(Exception):
                async with asyncio.timeout(5):
                    await asyncio.gather(
                        *(client.disconnect() for client in remaining), return_exceptions=True
                    )

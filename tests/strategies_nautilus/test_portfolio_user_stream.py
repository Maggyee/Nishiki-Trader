from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import struct
from contextlib import suppress
from types import SimpleNamespace

import pytest
from nautilus_trader.common.component import TestClock
from nautilus_trader.core.nautilus_pyo3 import WebSocketClient, WebSocketConfig

from apps.strategies_nautilus.portfolio_account_collector import BinanceAccountReadOnlyHttpClient
from apps.strategies_nautilus.portfolio_stream import StreamError, UserStreamJournal, bind_source
from apps.strategies_nautilus.portfolio_user_stream import SUBSCRIBE, ReadOnlyBinanceUserStream
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND

KEY, SECRET = "fixture-key", "fixture-secret"


def event(subscription_id=7):
    return json.dumps(
        {
            "subscriptionId": subscription_id,
            "event": {
                "e": "executionReport",
                "E": BASE_NS // 1_000_000,
                "s": "BTCUSDT",
                "i": 123,
                "I": 456,
            },
        }
    ).encode()


def check_signature(request):
    assert request["method"] == SUBSCRIBE
    params = request["params"]
    assert params["apiKey"] == KEY
    message = "&".join(f"{key}={params[key]}" for key in sorted(params) if key != "signature")
    assert hmac.compare_digest(
        params["signature"], hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    )


class FakeSocket:
    def __init__(self):
        self.active = True
        self.reconnecting = False
        self.handler = None
        self.sent = []
        self.reply = True
        self.after_ack = None
        self.mutate = lambda r: r

    def is_active(self):
        return self.active

    def is_reconnecting(self):
        return self.reconnecting

    def is_disconnecting(self):
        return False

    async def disconnect(self):
        self.active = False

    async def send_text(self, raw):
        request = json.loads(raw)
        self.sent.append(request)
        if request["method"] == SUBSCRIBE:
            check_signature(request)
        if self.reply:
            result = {"subscriptionId": 7} if request["method"] == SUBSCRIBE else {}
            self.handler(
                json.dumps(
                    self.mutate({"id": request["id"], "status": 200, "result": result})
                ).encode()
            )
            if self.after_ack is not None:
                self.handler(self.after_ack)


@pytest.fixture
def case(tmp_path, monkeypatch):
    loop = asyncio.new_event_loop()
    clock = TestClock()
    clock.set_time(BASE_NS + SECOND)
    http = BinanceAccountReadOnlyHttpClient(clock, KEY, SECRET, "https://api.binance.com")
    journal = UserStreamJournal(
        tmp_path / "events.jsonl", bind_source(http, "123"), clock_ns=clock.timestamp_ns
    )
    stream = ReadOnlyBinanceUserStream(
        http, api_secret=SECRET, journal=journal, clock=clock, loop=loop
    )
    socket = FakeSocket()

    async def connect(**kwargs):
        socket.handler = kwargs["handler"]
        socket.reconnect_callback = kwargs["post_reconnection"]
        return socket

    monkeypatch.setattr(
        "apps.strategies_nautilus.portfolio_user_stream.WebSocketClient",
        SimpleNamespace(connect=connect),
    )
    yield SimpleNamespace(
        loop=loop,
        clock=clock,
        http=http,
        journal=journal,
        stream=stream,
        socket=socket,
        path=tmp_path / "events.jsonl",
    )
    loop.run_until_complete(stream.disconnect())
    journal.close()
    loop.close()


def test_signed_subscription_binds_before_immediate_first_event(case):
    case.socket.after_ack = event()
    case.loop.run_until_complete(case.stream.start())
    assert case.journal.fence().revision == 2
    rows = [json.loads(line) for line in case.path.read_text().splitlines()]
    assert rows[-1]["kind"] == "event"
    assert json.loads(rows[-1]["raw"])["subscriptionId"] == 7
    assert KEY not in case.path.read_text() and SECRET not in case.path.read_text()
    assert [r["method"] for r in case.socket.sent] == [SUBSCRIBE]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: {**r, "status": 401, "error": {"msg": SECRET}},
        lambda r: {**r, "status": True},
        lambda r: {**r, "result": {"subscriptionId": True}},
        lambda r: {**r, "result": {"subscriptionId": -1}},
        lambda r: {**r, "result": {}},
        lambda r: {**r, "id": "unknown"},
        lambda r: {**r, "event": {}},
    ],
)
def test_bad_ack_cannot_connect_or_leak_server_error(case, mutation):
    case.socket.mutate = mutation
    with pytest.raises(StreamError) as exc:
        case.loop.run_until_complete(case.stream.start())
    assert SECRET not in str(exc.value)
    assert not case.socket.active
    with pytest.raises(StreamError):
        case.journal.fence()


@pytest.mark.parametrize(
    "method",
    ["session.logon", "order.place", "order.cancel", "userDataStream.start", "session.logout"],
)
def test_no_session_authentication_or_trading_requests(case, method):
    case.loop.run_until_complete(case.stream.start())
    before = len(case.socket.sent)
    with pytest.raises(StreamError, match="only read-only"):
        case.loop.run_until_complete(case.stream._send_request(method))
    assert len(case.socket.sent) == before


@pytest.mark.parametrize(
    "failure",
    [
        "inactive",
        "reconnecting",
        "reconnected",
        "key_changed",
        "foreign_event",
        "malformed",
        "terminated",
    ],
)
def test_transport_failures_invalidate_existing_rest_fences(case, failure):
    case.loop.run_until_complete(case.stream.start())
    fence = case.journal.fence()
    if failure == "inactive":
        case.socket.active = False
    elif failure == "reconnecting":
        case.socket.reconnecting = True
    elif failure == "reconnected":
        case.socket.reconnect_callback()
    elif failure == "key_changed":
        case.http._key = "another-key"
    elif failure == "foreign_event":
        case.socket.handler(event(8))
    elif failure == "malformed":
        case.socket.handler(b'{"id":"a","id":"b"}')
    else:
        case.socket.handler(
            json.dumps({"subscriptionId": 7, "event": {"e": "eventStreamTerminated"}}).encode()
        )
    with pytest.raises(StreamError):
        case.journal.assert_fence(fence)
    assert len(case.socket.sent) == 1  # no automatic reauthentication/resubmission


def test_ping_checks_health_without_changing_account_revision(case):
    case.loop.run_until_complete(case.stream.start())
    fence = case.journal.fence()
    case.clock.set_time(BASE_NS + 10 * SECOND)
    case.loop.run_until_complete(case.stream.ping())
    case.journal.assert_fence(fence)
    assert case.journal.last_transport_ns == BASE_NS + 10 * SECOND


def test_request_timeout_removes_waiter_and_blocks_journal(case):
    case.loop.run_until_complete(case.stream.start())
    case.socket.reply = False
    with pytest.raises(StreamError):
        case.loop.run_until_complete(case.stream._send_request("ping", timeout=0.005))
    assert not case.stream._requests
    with pytest.raises(StreamError):
        case.journal.fence()


def test_cancelled_request_removes_waiter_and_blocks_journal(case):
    async def run():
        await case.stream.start()
        case.socket.reply = False
        task = asyncio.create_task(case.stream.ping())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    case.loop.run_until_complete(run())
    assert not case.stream._requests
    with pytest.raises(StreamError):
        case.journal.fence()


def test_old_connection_callbacks_cannot_change_a_new_epoch(case):
    case.loop.run_until_complete(case.stream.start())
    old_handler, old_reconnect = case.socket.handler, case.socket.reconnect_callback
    old_fence = case.journal.fence()
    case.loop.run_until_complete(case.stream.disconnect())
    case.socket.active = True
    case.loop.run_until_complete(case.stream.start())
    new_fence = case.journal.fence()
    old_handler(event(99))
    old_reconnect()
    case.journal.assert_fence(new_fence)
    with pytest.raises(StreamError):
        case.journal.assert_fence(old_fence)


# Minimal stdlib-only loopback WebSocket peer: tests actual native Rust socket I/O.
async def read_frame(reader):
    first, second = await reader.readexactly(2)
    size = second & 127
    if size == 126:
        size = struct.unpack("!H", await reader.readexactly(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", await reader.readexactly(8))[0]
    assert size < 65536
    mask = await reader.readexactly(4) if second & 128 else b""
    data = await reader.readexactly(size)
    if mask:
        data = bytes(value ^ mask[i % 4] for i, value in enumerate(data))
    return first & 15, data


def frame(data, opcode=1):
    size = len(data)
    return (
        bytes([128 | opcode, size]) + data
        if size < 126
        else bytes([128 | opcode, 126]) + struct.pack("!H", size) + data
    )


@pytest.mark.parametrize("drop", [False, True])
def test_real_native_websocket_receipts_and_connection_loss(tmp_path, monkeypatch, drop):
    async def run():
        clock = TestClock()
        clock.set_time(BASE_NS + SECOND)
        http = BinanceAccountReadOnlyHttpClient(clock, KEY, SECRET, "https://api.binance.com")
        journal = UserStreamJournal(
            tmp_path / "wire.jsonl", bind_source(http, "123"), clock_ns=clock.timestamp_ns
        )
        stream = ReadOnlyBinanceUserStream(
            http, api_secret=SECRET, journal=journal, clock=clock, loop=asyncio.get_running_loop()
        )
        errors, methods, writers = [], [], []
        event_sent = asyncio.Event()
        close_peer = asyncio.Event()

        async def peer(reader, writer):
            writers.append(writer)
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                headers = dict(
                    line.split(b": ", 1) for line in header.split(b"\r\n")[1:] if b": " in line
                )
                key = next(
                    value for key, value in headers.items() if key.lower() == b"sec-websocket-key"
                )
                accept = base64.b64encode(
                    hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
                )
                writer.write(
                    b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
                    + accept
                    + b"\r\n\r\n"
                )
                await writer.drain()
                while True:
                    opcode, raw = await read_frame(reader)
                    if opcode == 8:
                        writer.write(frame(raw, 8))
                        await writer.drain()
                        break
                    if opcode == 9:
                        writer.write(frame(raw, 10))
                        await writer.drain()
                        continue
                    if opcode != 1:
                        continue
                    request = json.loads(raw)
                    methods.append(request["method"])
                    result = {}
                    if request["method"] == SUBSCRIBE:
                        check_signature(request)
                        result = {"subscriptionId": 7}
                    writer.write(
                        frame(
                            json.dumps(
                                {"id": request["id"], "status": 200, "result": result}
                            ).encode()
                        )
                    )
                    if request["method"] == SUBSCRIBE:
                        writer.write(frame(event()))
                        event_sent.set()
                    await writer.drain()
                    if drop:
                        await close_peer.wait()
                        break
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            except Exception as exc:
                errors.append(exc)
            finally:
                writer.close()
                with suppress(ConnectionError):
                    await writer.wait_closed()

        server = await asyncio.start_server(peer, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        async def loopback_connect(**kwargs):
            # Production API exposes no custom host switch. Redirect only this test.
            kwargs["config"] = WebSocketConfig(
                url=f"ws://127.0.0.1:{port}", headers=[], reconnect_delay_initial_ms=10000
            )
            return await WebSocketClient.connect(**kwargs)

        monkeypatch.setattr(
            "apps.strategies_nautilus.portfolio_user_stream.WebSocketClient",
            SimpleNamespace(connect=loopback_connect),
        )
        try:
            async with asyncio.timeout(8):
                await stream.start()
                await event_sent.wait()
                # Wait for native receive callback, not merely the peer's write.
                while journal.revision < 2:
                    await asyncio.sleep(0.005)
                fence = journal.fence()
                if drop:
                    close_peer.set()
                    while stream._transport_current():
                        await asyncio.sleep(0.005)
                    with pytest.raises(StreamError):
                        journal.assert_fence(fence)
                else:
                    await stream.ping()
                    journal.assert_fence(fence)
                assert methods == ([SUBSCRIBE] if drop else [SUBSCRIBE, "ping"])
                assert not errors
        finally:
            await stream.disconnect()
            journal.close()
            server.close()
            await server.wait_closed()
            for writer in writers:
                writer.close()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["quiet", "event", "disconnect", "key"])
def test_native_stream_and_rest_collection_share_one_source_fence(case, monkeypatch, change):
    from decimal import Decimal

    from apps.strategies_nautilus.portfolio_account import AccountAnchor

    calls = []

    async def wire(method, path, *, payload, ratelimiter_keys=None):
        calls.append(path)
        if path.endswith("apiRestrictions"):
            body = {"enableReading": True, "enableSpotAndMarginTrading": False}
        elif path.endswith("account"):
            body = {"uid": 123, "balances": []}
        else:
            body = []
        if path.endswith("allOrders"):
            if change == "event":
                case.socket.handler(event())
            elif change == "disconnect":
                case.socket.active = False
            elif change == "key":
                case.http._key = "changed-key"
        return json.dumps(body).encode()

    monkeypatch.setattr(case.http, "send_request", wire)
    case.loop.run_until_complete(case.stream.start())
    anchor = AccountAnchor("123", "BINANCE-001", BASE_NS, Decimal("500"))
    if change != "quiet":
        with pytest.raises(ValueError):
            case.loop.run_until_complete(case.stream.collect(anchor))
    else:
        result = case.loop.run_until_complete(case.stream.collect(anchor))
        case.journal.assert_fence(result.stream_fence)
        assert not result.atomic_revision_verified
        assert not result.api_trading_enabled
        assert len(calls) == 7
        case.loop.run_until_complete(case.stream.disconnect())
        with pytest.raises(StreamError):
            case.journal.assert_fence(result.stream_fence)


def test_concurrent_subscriptions_cannot_replace_an_epoch(case):
    async def run():
        await case.stream.connect()
        case.socket.reply = False
        pending = asyncio.create_task(case.stream.subscribe_user_data_stream())
        await asyncio.sleep(0)
        with pytest.raises(StreamError, match="already active or pending"):
            await case.stream.subscribe_user_data_stream()
        assert len(case.socket.sent) == 1
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    case.loop.run_until_complete(run())


def test_failed_persistence_never_acknowledges_subscription(case, monkeypatch):
    import apps.strategies_nautilus.portfolio_stream as module

    monkeypatch.setattr(module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(StreamError):
        case.loop.run_until_complete(case.stream.start())
    assert not case.stream._requests
    assert not case.socket.active
    with pytest.raises(StreamError):
        case.journal.fence()


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v3/order"),
        ("DELETE", "/api/v3/order"),
        ("GET", "/api/v3/order"),
        ("GET", "/api/v3/account?unexpected=1"),
    ],
)
def test_account_http_extension_rejects_unqualified_methods_and_paths(method, path):
    from nautilus_trader.core.nautilus_pyo3 import HttpMethod

    from apps.strategies_nautilus.portfolio_account_collector import (
        BinanceAccountReadOnlyHttpClient,
    )
    from apps.strategies_nautilus.portfolio_venue import VenueInputError

    http = BinanceAccountReadOnlyHttpClient(TestClock(), KEY, SECRET, "https://api.binance.com")
    with pytest.raises(VenueInputError, match="only qualified"):
        asyncio.run(http.sign_request(getattr(HttpMethod, method), path, {"timestamp": "1"}))


@pytest.mark.parametrize("status", [200, 400, 302])
def test_account_http_native_signer_preserved_without_signed_url_logging(monkeypatch, status):
    from urllib.parse import parse_qsl, urlencode, urlsplit

    from nautilus_trader.core.nautilus_pyo3 import HttpMethod

    from apps.strategies_nautilus.portfolio_account_collector import (
        BinanceAccountReadOnlyHttpClient,
    )
    from apps.strategies_nautilus.portfolio_venue import VenueInputError

    http = BinanceAccountReadOnlyHttpClient(TestClock(), KEY, SECRET, "https://api.binance.com")
    calls = []

    async def request(method, *, url, headers, body, keys):
        assert method == HttpMethod.GET and headers["X-MBX-APIKEY"] == KEY and body is None
        params = dict(parse_qsl(urlsplit(url).query))
        signature = params.pop("signature")
        assert hmac.compare_digest(
            signature,
            hmac.new(SECRET.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest(),
        )
        calls.append(urlsplit(url).path)
        return SimpleNamespace(
            status=status, body=(b'{"uid":123}' if status == 200 else SECRET.encode())
        )

    def forbidden_log(*args):
        pytest.fail("signed URL reached upstream debug logger")

    monkeypatch.setattr(http, "_client", SimpleNamespace(request=request))
    monkeypatch.setattr(http, "_log", SimpleNamespace(debug=forbidden_log))
    if status == 200:
        assert (
            asyncio.run(http.sign_request(HttpMethod.GET, "/api/v3/account", {"timestamp": "1"}))
            == b'{"uid":123}'
        )
    else:
        with pytest.raises(VenueInputError) as exc:
            asyncio.run(http.sign_request(HttpMethod.GET, "/api/v3/account", {"timestamp": "1"}))
        assert SECRET not in str(exc.value)
    assert calls == ["/api/v3/account"]


def test_unbound_early_event_does_not_get_dropped_then_allow_collection(case, monkeypatch):
    async def early_event(raw):
        case.socket.handler(event())
        request = json.loads(raw)
        case.socket.handler(
            json.dumps(
                {"id": request["id"], "status": 200, "result": {"subscriptionId": 7}}
            ).encode()
        )

    monkeypatch.setattr(case.socket, "send_text", early_event)
    with pytest.raises(StreamError):
        case.loop.run_until_complete(case.stream.start())
    assert not case.socket.active
    assert not case.stream._requests


def test_send_exception_never_exposes_private_payload(case, monkeypatch):
    async def fail_send(raw):
        raise RuntimeError(raw.decode() + SECRET)

    monkeypatch.setattr(case.socket, "send_text", fail_send)
    with pytest.raises(StreamError) as exc:
        case.loop.run_until_complete(case.stream.start())
    assert SECRET not in str(exc.value) and KEY not in str(exc.value)
    assert not case.stream._requests


def test_transport_requires_account_only_http_client(case):
    from nautilus_trader.adapters.binance.http.client import BinanceHttpClient

    unsafe = BinanceHttpClient(case.clock, KEY, SECRET, "https://api.binance.com")
    with pytest.raises(StreamError, match="without signed-URL logging"):
        ReadOnlyBinanceUserStream(
            unsafe, api_secret=SECRET, journal=case.journal, clock=case.clock, loop=case.loop
        )

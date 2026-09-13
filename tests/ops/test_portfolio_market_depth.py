"""Bounded public transport, failure cleanup, and native wire acceptance."""

import asyncio
import base64
import hashlib
import time

import pytest
from nautilus_trader.core.nautilus_pyo3 import WebSocketConfig

from apps.ops import portfolio_market_depth as cli
from apps.strategies_nautilus.portfolio_market_depth import STREAM, DepthError
from apps.strategies_nautilus.portfolio_market_depth_archive import REQUESTS, replay_depth
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_market_depth import delta, metadata, snapshot
from tests.strategies_nautilus.test_portfolio_user_stream import frame, read_frame


class Socket:
    active = True
    closes = 0

    def is_active(self):
        return self.active

    def is_reconnecting(self):
        return False

    def is_disconnecting(self):
        return False

    def is_closed(self):
        return not self.active

    async def disconnect(self):
        self.closes += 1
        self.active = False

    async def send_pong(self, raw):
        pass


@pytest.mark.parametrize(
    "failure",
    [None, "boundary", "disconnect", "shutdown", "clock", "weight", "bad_json", "ping_limit"],
)
@pytest.mark.parametrize("revision", [1, 2])
def test_probe_exact_public_budget_and_failure_cleanup(tmp_path, monkeypatch, failure, revision):
    calls, sockets = [], []

    def get(path, params):
        calls.append((path, params))
        assert calls == [(p, s) for p, s, _ in REQUESTS[: len(calls)]]
        body = {"serverTime": time.time_ns() // 1_000_000}
        if failure == "clock":
            body["serverTime"] += 1000
        if path.endswith("/exchangeInfo"):
            body = metadata()
        if path.endswith("/depth"):
            body = snapshot()
        return (
            200,
            {"x-mbx-used-weight-1m": "6000" if failure == "weight" else "28"},
            canonical(body),
        )

    async def connect(**kwargs):
        sock = Socket()
        sockets.append(sock)

        def deliver():
            stamp = time.time_ns() // 1_000_000
            if failure == "boundary":
                kwargs["handler"](canonical(delta(99, 100, E=stamp)))
                kwargs["handler"](canonical(delta(101, 102, E=stamp)))
            elif failure == "bad_json":
                kwargs["handler"](b"\xff")
            else:
                kwargs["handler"](
                    canonical(
                        delta(
                            E=stamp, e="serverShutdown" if failure == "shutdown" else "depthUpdate"
                        )
                    )
                )
            if failure == "disconnect":
                sock.active = False
            if failure == "ping_limit":
                for _ in range(6):
                    kwargs["ping_handler"](b"echo")

        asyncio.get_running_loop().call_soon(deliver)
        return sock

    monkeypatch.setattr(cli, "public_get", get)
    monkeypatch.setattr(cli, "connect_depth", connect)
    path = tmp_path / "wire.jsonl"
    result = asyncio.run(cli.probe(path, seconds=2, revision=revision))
    raw = path.read_bytes()
    if failure is None or (failure == "boundary" and revision == 2):
        assert len(calls) == 5 and len(sockets) == 1 and sockets[0].closes == 1
        assert result["status"] == "public_depth_probe_completed"
        replay = replay_depth(
            raw, expected_sha256=hashlib.sha256(raw).hexdigest(), revision=revision
        )
        assert (
            replay["summary"] == result["summary"] and replay["summary"]["native_quote_count"] == 1
        )
    else:
        assert result["status"] == "public_depth_probe_failed"
        assert result["summary"]["segment_failed"] and not result["summary"]["locally_linked"]
        assert len(calls) <= 3 and len(sockets) <= 1
        assert result["summary"]["public_get_responses"] == len(calls)
        assert all(s.closes <= 1 for s in sockets)
        assert b'"kind":"completed"' not in raw
        with pytest.raises(DepthError):
            replay_depth(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), revision=revision)


def test_public_http_whitelist_method_host_no_credentials(monkeypatch):
    observed = []

    class Connection:
        def __init__(self, host, **kw):
            assert host == "testnet.binance.vision" and kw == {"timeout": 10}

        def request(self, method, url, headers):
            assert method == "GET"
            assert list(headers) == ["User-Agent"]
            observed.append(url)

        def getresponse(self):
            return self

        status = 200

        def read(self, size):
            return b"{}"

        def getheaders(self):
            return [("X-MBX-USED-WEIGHT-1M", "28")]

        def close(self):
            pass

    monkeypatch.setattr(cli.http.client, "HTTPSConnection", Connection)
    for path, params, _ in REQUESTS:
        cli.public_get(path, params)
    assert len(observed) == 5
    for path, params in [
        ("/api/v3/account", {}),
        ("/api/v3/depth", {"symbol": "ETHUSDT", "limit": "100"}),
        ("/api/v3/time", {"signature": "forbidden"}),
    ]:
        with pytest.raises(DepthError, match="not_allowlisted"):
            cli.public_get(path, params)
    assert len(observed) == 5


def test_existing_or_shared_output_refused_before_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network must not run")

    monkeypatch.setattr(cli, "probe", forbidden)
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"original")
    for archive, report in [
        (tmp_path / "new.jsonl", existing),
        (tmp_path / "same", tmp_path / "same"),
    ]:
        assert cli.main(["--probe", "--archive", str(archive), "--report", str(report)]) == 1
        assert not archive.exists()
    assert existing.read_bytes() == b"original"


def test_native_socket_raw_frame_ping_echo_and_zero_reconnect(monkeypatch):
    async def run():
        connections, errors, frames, pongs = [], [], [], []
        ready, done = asyncio.Event(), asyncio.Event()
        native = None
        pong_tasks = []

        async def peer(reader, writer):
            connections.append(writer)
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                key = next(
                    line.split(b":", 1)[1].strip()
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"sec-websocket-key:")
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
                await ready.wait()
                writer.write(frame(b'{"raw":"depth"}'))
                writer.write(frame(b"exact-payload", 9))
                await writer.drain()
                opcode, payload = await asyncio.wait_for(read_frame(reader), 3)
                pongs.append((opcode, payload))
            except Exception as exc:
                errors.append(exc)
            finally:
                writer.close()
                await writer.wait_closed()
                done.set()

        server = await asyncio.start_server(peer, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        def config(**kwargs):
            assert kwargs == {
                "url": STREAM,
                "headers": [],
                "heartbeat": None,
                "reconnect_max_attempts": 0,
            }
            return WebSocketConfig(
                **(
                    kwargs
                    | {
                        "url": f"ws://127.0.0.1:{port}",
                        "reconnect_delay_initial_ms": 10,
                        "reconnect_delay_max_ms": 10,
                        "reconnect_jitter_ms": 0,
                    }
                )
            )

        monkeypatch.setattr(cli, "WebSocketConfig", config)

        def ping(raw):
            pong_tasks.append(asyncio.create_task(native.send_pong(raw)))

        reconnects = []
        try:
            native = await cli.connect_depth(
                handler=frames.append,
                ping_handler=ping,
                post_reconnection=lambda: reconnects.append(True),
            )
            ready.set()
            await asyncio.wait_for(done.wait(), 5)
            await asyncio.gather(*pong_tasks)
            async with asyncio.timeout(5):
                while not native.is_closed():
                    await asyncio.sleep(0.01)
            await asyncio.sleep(0.1)
            assert not errors and len(connections) == 1 and not reconnects
            assert frames == [b'{"raw":"depth"}']
            assert pongs == [(10, b"exact-payload")]
        finally:
            if native is not None and not native.is_closed():
                await native.disconnect()
            server.close()
            await server.wait_closed()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["quiet", "http"])
def test_timeout_or_http_failure_has_no_retry(tmp_path, monkeypatch, failure):
    calls = []
    sock = Socket()

    def get(path, params):
        calls.append(path)
        if failure == "http":
            raise TimeoutError("fixture")
        body = (
            metadata()
            if path.endswith("exchangeInfo")
            else {"serverTime": time.time_ns() // 1_000_000}
        )
        return 200, {"x-mbx-used-weight-1m": "28"}, canonical(body)

    async def connect(**kwargs):
        return sock

    monkeypatch.setattr(cli, "public_get", get)
    monkeypatch.setattr(cli, "connect_depth", connect)
    start = time.monotonic()
    result = asyncio.run(cli.probe(tmp_path / "timeout.jsonl", seconds=1))
    assert result["status"] == "public_depth_probe_failed" and result["summary"]["segment_failed"]
    assert len(calls) == (1 if failure == "http" else 2)
    assert sock.closes == (0 if failure == "http" else 1)
    assert time.monotonic() - start < 3

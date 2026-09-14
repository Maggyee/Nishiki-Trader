"""Actual native socket I/O stays on three local peers, with ephemeral signing keys."""

import _socket
import asyncio
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import suppress
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest
from nautilus_trader.common.component import TestClock

from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence
from apps.strategies_nautilus.portfolio_joint_transport import run_loopback
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from apps.strategies_nautilus.portfolio_stream import canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import load_testnet_ed25519_credentials
from tests.strategies_nautilus.test_portfolio_joint_observation import (
    SYMBOLS,
    all_metadata,
    manifest,
)
from tests.strategies_nautilus.test_portfolio_joint_routes import (
    KEY,
    replay,
    route_books,
    route_manifest,
)
from tests.strategies_nautilus.test_portfolio_market_depth import BASE, delta, snapshot
from tests.strategies_nautilus.test_portfolio_testnet_credentials import (
    configured as configured,
)
from tests.strategies_nautilus.test_portfolio_testnet_credentials import (
    verify_signature,
)
from tests.strategies_nautilus.test_portfolio_user_stream import frame, read_frame


class LocalClock:
    def __init__(self):
        self.start = time.monotonic_ns()

    def __call__(self):
        mono = time.monotonic_ns()
        return BASE + mono - self.start, mono


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "burst",
        "market_drop",
        "account_drop",
        "unknown_event",
        "weight",
        "buffer",
        "disk",
        "cancel",
    ],
)
def test_native_signed_joint_loopback(tmp_path, configured, monkeypatch, failure):
    def only_local_connect(sock, address):
        assert address[0] == "127.0.0.1"
        return _socket.socket.connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", only_local_connect)

    async def run():
        config, _, public = configured
        clock = LocalClock()
        native_clock = TestClock()
        native_clock.set_time(clock()[0])
        signer = load_testnet_ed25519_credentials(config).create_http_client(native_clock)
        counts = {"http": 0, "account": 0, "market": 0}
        writers, errors, methods, signed, paths, pongs = [], [], [], [], [], []
        account_writer = market_writer = None
        next_ids = {s: 499 if failure == "burst" else 103 for s in SYMBOLS}
        usage = 0
        disk_failed = False
        disconnect_now = asyncio.Event()
        market_live = asyncio.Event()
        original_fsync = os.fsync

        if failure == "disk":

            def fsync(fd):
                if disk_failed:
                    raise OSError("injected disk failure")
                return original_fsync(fd)

            monkeypatch.setattr(os, "fsync", fsync)

        async def handshake(reader, writer):
            header = await reader.readuntil(b"\r\n\r\n")
            request_path = header.split(b" ", 2)[1].decode()
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
            return request_path

        async def close(writer):
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

        async def http_peer(reader, writer):
            nonlocal usage, disk_failed
            writers.append(writer)
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                method, url, _ = header.split(b"\r\n")[0].decode().split(" ")
                assert method == "GET"
                parsed = urlsplit(url)
                path = parsed.path
                paths.append(path)
                counts["http"] += 1
                params = dict(parse_qsl(parsed.query))
                if path in {"/api/v3/account", "/api/v3/openOrders"}:
                    signature = params.pop("signature")
                    assert f"X-MBX-APIKEY: {KEY}".encode() in header
                    verify_signature(tmp_path, public, urlencode(params), signature)
                    signed.append(path)
                    body = manifest()["initial_account"] if path.endswith("/account") else []
                    usage += 20 if path.endswith("/account") else 80
                    if counts["http"] > 10 and failure in {None, "burst"}:
                        symbol = SYMBOLS[counts["http"] % 3]
                        first = next_ids[symbol]
                        next_ids[symbol] += 2
                        update = delta(first, first + 1, s=symbol, E=clock()[0] // 1_000_000)
                        market_writer.write(
                            frame(
                                canonical(
                                    {"stream": symbol.lower() + "@depth@100ms", "data": update}
                                )
                            )
                        )
                        await market_writer.drain()
                        await asyncio.sleep(0.005)
                    if counts["http"] > 10 and failure == "account_drop":
                        await close(account_writer)
                        await asyncio.sleep(0.06)
                elif path.endswith("/time"):
                    body = {"serverTime": clock()[0] // 1_000_000}
                    usage += 1
                elif path.endswith("/exchangeInfo"):
                    body = all_metadata()
                    usage += 20
                elif path.endswith("bookTicker"):
                    body = route_books()
                    usage += 4
                else:
                    assert path == "/api/v3/depth"
                    assert params["symbol"] in SYMBOLS and params["limit"] == "100"
                    body = snapshot()
                    usage += 5
                    if failure == "disk":
                        disk_failed = True
                if failure == "weight" and counts["http"] == 3:
                    usage = 5999
                if failure == "market_drop" and path.endswith("/depth"):
                    disconnect_now.set()
                    await asyncio.sleep(0.06)
                raw = canonical(body)
                writer.write(
                    f"HTTP/1.1 200 OK\r\nContent-Length: {len(raw)}\r\nX-MBX-USED-WEIGHT-1M: {usage}\r\nConnection: close\r\n\r\n".encode()
                    + raw
                )
                await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            except Exception as exc:
                errors.append(exc)
            finally:
                await close(writer)

        async def account_peer(reader, writer):
            nonlocal account_writer, usage
            writers.append(writer)
            counts["account"] += 1
            usage += 2
            account_writer = writer
            try:
                assert await handshake(reader, writer) == "/ws-api/v3"
                while True:
                    opcode, raw = await read_frame(reader)
                    if opcode == 8:
                        writer.write(frame(raw, 8))
                        await writer.drain()
                        break
                    if opcode == 10:
                        pongs.append(("account", raw))
                        continue
                    assert opcode == 1
                    request = json.loads(raw)
                    operation = request["method"]
                    methods.append(operation)
                    assert operation in {
                        "userDataStream.subscribe.signature",
                        "userDataStream.unsubscribe",
                    }
                    result = {}
                    usage += 2
                    if operation.endswith("signature"):
                        params = request["params"]
                        assert params["apiKey"] == KEY
                        verify_signature(
                            tmp_path,
                            public,
                            "&".join(
                                f"{key}={params[key]}"
                                for key in sorted(params)
                                if key != "signature"
                            ),
                            params["signature"],
                        )
                        signed.append("WS subscribe")
                        result = {"subscriptionId": 7}
                    response = {
                        "id": request["id"],
                        "status": 200,
                        "result": result,
                        "rateLimits": [
                            {
                                "rateLimitType": "REQUEST_WEIGHT",
                                "interval": "MINUTE",
                                "intervalNum": 1,
                                "limit": 6000,
                                "count": usage,
                            }
                        ],
                    }
                    writer.write(frame(canonical(response)))
                    if operation.endswith("signature"):
                        # Immediate account envelope follows the acknowledgement in one write.
                        event = {
                            "e": "outboundAccountPosition",
                            "E": clock()[0] // 1_000_000,
                            "u": clock()[0] // 1_000_000,
                            "B": [{"a": "BTC", "f": "1", "l": "0"}],
                        }
                        if failure == "unknown_event":
                            event["e"] = "balanceUpdate"
                        writer.write(frame(canonical({"subscriptionId": 7, "event": event})))
                        writer.write(frame(b"account-ping", 9))
                    await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            except Exception as exc:
                errors.append(exc)
            finally:
                await close(writer)

        async def market_peer(reader, writer):
            nonlocal market_writer
            market_writer = writer
            writers.append(writer)
            counts["market"] += 1
            try:
                expected = "/stream?streams=" + "/".join(
                    s.lower() + "@depth@100ms" for s in SYMBOLS
                )
                assert await handshake(reader, writer) == expected
                for number in range(100 if failure == "burst" else 1):
                    for symbol in SYMBOLS:
                        update = delta(
                            99 + number * 4, 102 + number * 4, s=symbol, E=clock()[0] // 1_000_000
                        )
                        writer.write(
                            frame(
                                canonical(
                                    {"stream": symbol.lower() + "@depth@100ms", "data": update}
                                )
                            )
                        )
                await writer.drain()
                market_live.set()
                if failure == "market_drop":
                    await disconnect_now.wait()
                    return
                # Wait until the native connect future has installed its handle.
                await asyncio.sleep(0.02)
                writer.write(frame(b"market-ping", 9))
                await writer.drain()
                while True:
                    opcode, raw = await read_frame(reader)
                    if opcode == 8:
                        writer.write(frame(raw, 8))
                        await writer.drain()
                        break
                    if opcode == 10:
                        pongs.append(("market", raw))
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            except Exception as exc:
                errors.append(exc)
            finally:
                await close(writer)

        servers = [
            await asyncio.start_server(peer, "127.0.0.1", 0)
            for peer in (http_peer, account_peer, market_peer)
        ]
        endpoints = {
            name: f"{scheme}://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            for name, scheme, server in zip(
                ("http", "account", "market"), ("http", "ws", "ws"), servers, strict=True
            )
        }
        path = tmp_path / "native-loopback.jsonl"
        j = joint.JointJournal(
            path,
            manifest=route_manifest(clock, endpoints),
            clock=clock,
            evidence_type=RoutedJointEvidence,
            limits=joint.Limits(pending_events=3) if failure == "buffer" else None,
        )
        try:
            async with asyncio.timeout(15):
                task = asyncio.create_task(run_loopback(j, signer, observe_seconds=0.1))
                if failure == "cancel":
                    await market_live.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                    result = {"status": "loopback_joint_failed"}
                else:
                    result = await task
            j.close()
            raw = path.read_bytes()
            assert not errors, errors
            assert (
                KEY.encode() not in raw and b"PRIVATE KEY" not in raw and b'"signature"' not in raw
            )
            assert counts["account"] <= 1 and counts["market"] <= 1
            if failure in {None, "burst"}:
                assert result["status"] == "loopback_joint_completed", (result, j.state.failure)
                report = replay(raw)
                assert report["summary"] == result["summary"]
                assert counts == {"http": 16, "account": 1, "market": 1}
                if failure is None:
                    outputs = []
                    for i in range(2):
                        output = tmp_path / f"native-replay{i}.json"
                        proc = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "apps.ops.portfolio_joint_observation",
                                "--loopback-profile",
                                "--archive",
                                str(path),
                                "--archive-sha256",
                                joint.digest(raw),
                                "--report",
                                str(output),
                            ],
                            capture_output=True,
                            timeout=30,
                        )
                        assert proc.returncode == 0, proc.stdout + proc.stderr
                        outputs.append(output.read_bytes())
                    assert outputs[0] == outputs[1] and json.loads(outputs[0]) == report
                    assert path.read_bytes() == raw
                assert len(signed) == 9
                assert methods == [
                    "userDataStream.subscribe.signature",
                    "userDataStream.unsubscribe",
                ]
                assert set(pongs) == {("account", b"account-ping"), ("market", b"market-ping")}
                assert (
                    sum(len(quotes) for quotes in report["native_quotes"].values())
                    == (300 if failure == "burst" else 3) + 4
                )
                rows = [json.loads(line) for line in raw.splitlines()]
                intervals = report["summary"]["account_intervals"][-1]["receipt_sequences"]
                assert any(
                    r["kind"] == "market_frame" and intervals[0] < r["seq"] < intervals[-1]
                    for r in rows
                )
            else:
                assert result["status"] == "loopback_joint_failed"
                assert not j.state.completed
                with pytest.raises((DepthError, ValueError)):
                    replay(raw)
            # Both local peers saw close/EOF; native clients never reconnect.
            await asyncio.sleep(0.03)
            assert counts["account"] <= 1 and counts["market"] <= 1
        finally:
            j.close()
            for server in servers:
                server.close()
                await server.wait_closed()
            for writer in writers:
                await close(writer)

    asyncio.run(run())

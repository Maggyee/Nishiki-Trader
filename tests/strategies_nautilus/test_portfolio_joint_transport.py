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

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_joint_egress import (
    binding_pin,
    replay_accounted,
    run_accounted_tls_loopback,
)
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence
from apps.strategies_nautilus.portfolio_joint_tls_evidence import PROFILE as TLS_PROFILE
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
from apps.strategies_nautilus.portfolio_joint_tls_transport import run_tls_loopback
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
from tests.strategies_nautilus.test_portfolio_tls_provenance import certificates as certificates
from tests.strategies_nautilus.test_portfolio_user_stream import frame, read_frame


class LocalClock:
    def __init__(self):
        self.start = time.monotonic_ns()

    def __call__(self):
        mono = time.monotonic_ns()
        return BASE + mono - self.start, mono


CASES = [
    None,
    "burst",
    "market_drop",
    "account_drop",
    "unknown_event",
    "weight",
    "buffer",
    "disk",
    "cancel",
    "fragmented",
]


@pytest.mark.parametrize(
    "tls_mode,failure,accounted_mode",
    [(mode, failure, False) for mode in (False, True) for failure in CASES]
    + [
        (True, failure, False)
        for failure in (
            "tls_untrusted",
            "duplicate_weight",
            "masked_frame",
            "fragment_gap",
            "unexpected_close",
        )
    ]
    + [
        (True, failure, True)
        for failure in CASES
        + [
            "tls_untrusted",
            "duplicate_weight",
            "ledger_prepare_disk",
            "ledger_outcome_disk",
            "slow_metadata_body",
        ]
    ],
)
def test_native_signed_joint_loopback(
    tmp_path, configured, monkeypatch, failure, tls_mode, certificates, accounted_mode
):
    wire_guard = {}

    def only_local_connect(sock, address):
        assert address[0] == "127.0.0.1"
        if accounted_mode:
            ledger_raw = wire_guard["ledger_path"].read_bytes()
            ledger_report = attempts.replay(
                ledger_raw,
                expected_sha256=joint.digest(ledger_raw),
                binding_sha256=wire_guard["pin"],
                profile=attempts.JOINT_PROFILE,
            )
            assert (
                ledger_report["pending_attempt"]
                == wire_guard["journal"].state.prepared["operation_id"]
            )
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

        def message(raw):
            if failure != "fragmented":
                return frame(raw)
            cut = len(raw) // 2
            first = frame(raw[:cut])
            return (
                bytes([first[0] & 0x7F])
                + first[1:]
                + frame(b"fragment-ping", 9)
                + frame(raw[cut:], 0)
            )

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
            if failure == "fragmented":
                writer.write(frame(b"upgrade-ping", 9))
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
                    if counts["http"] > 10 and failure in {None, "burst", "fragmented"}:
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
                header = f"HTTP/1.1 200 OK\r\nContent-Length: {len(raw)}\r\nX-MBX-USED-WEIGHT-1M: {usage}\r\nConnection: close\r\n".encode()
                if failure == "duplicate_weight":
                    header += f"x-mbx-used-weight-1m: {usage}\r\n".encode()
                if failure == "slow_metadata_body" and path.endswith("/exchangeInfo"):
                    writer.write(header + b"\r\n")
                    await writer.drain()
                    await asyncio.sleep(5.2)
                    writer.write(raw)
                else:
                    writer.write(header + b"\r\n" + raw)
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
                    writer.write(
                        message(canonical(response))
                        if operation.endswith("signature")
                        else frame(canonical(response))
                    )
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
                if failure == "masked_frame":
                    from apps.strategies_nautilus.portfolio_ws_frames import client_frame

                    writer.write(client_frame(b"{}"))
                    await writer.drain()
                    return
                if failure in {"fragment_gap", "unexpected_close"}:
                    writer.write(
                        b"\x01\x02{}" if failure == "fragment_gap" else frame(b"\x03\xe8", 8)
                    )
                    await writer.drain()
                    return
                for number in range(100 if failure == "burst" else 1):
                    for symbol in SYMBOLS:
                        update = delta(
                            99 + number * 4, 102 + number * 4, s=symbol, E=clock()[0] // 1_000_000
                        )
                        writer.write(
                            message(
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
            await asyncio.start_server(
                peer,
                "127.0.0.1",
                0,
                ssl=certificates["foreign" if failure == "tls_untrusted" else "selected"][0]
                if tls_mode
                else None,
            )
            for peer in (http_peer, account_peer, market_peer)
        ]
        endpoints = {
            name: f"{scheme}://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            for name, scheme, server in zip(
                ("http", "account", "market"), ("http", "ws", "ws"), servers, strict=True
            )
        }
        path = tmp_path / "native-loopback.jsonl"
        selection = route_manifest(clock, endpoints)
        if tls_mode:
            selection.update(
                tls_profile=TLS_PROFILE,
                tls_trust_sha256=joint.digest(certificates["selected"][1]),
                tls_endpoints={
                    name: f"{'https' if name == 'http' else 'wss'}://{name}.fixture.invalid:{urlsplit(url).port}"
                    for name, url in endpoints.items()
                },
            )
        j = joint.JointJournal(
            path,
            manifest=selection,
            clock=clock,
            evidence_type=TLSJointEvidence if tls_mode else RoutedJointEvidence,
            limits=joint.Limits(pending_events=3) if failure == "buffer" else None,
        )
        ledger_root = tmp_path / "attempts"
        if accounted_mode:
            ledger_root.mkdir(mode=0o700)
            (ledger_root / "README.md").write_text(
                "Local joint attempt fixture. No real gateway. Next: replay.\n"
            )
            ledger_path = ledger_root / attempts.JOINT_SCOPE / "events.jsonl"
            wire_guard.update(ledger_path=ledger_path, journal=j, pin=binding_pin(selection))
            if failure in {"ledger_prepare_disk", "ledger_outcome_disk"}:

                def fail_ledger_sync(fd):
                    target = os.readlink(f"/proc/self/fd/{fd}")
                    if target == str(ledger_path):
                        last = json.loads(ledger_path.read_bytes().splitlines()[-1])
                        if last["kind"] == (
                            "prepared" if failure == "ledger_prepare_disk" else "outcome"
                        ):
                            raise OSError("injected ledger fsync failure")
                    return original_fsync(fd)

                monkeypatch.setattr(os, "fsync", fail_ledger_sync)
        try:
            async with asyncio.timeout(15):
                task = asyncio.create_task(
                    run_accounted_tls_loopback(
                        j,
                        signer,
                        ledger_root=ledger_root,
                        trust_pem=certificates["selected"][1],
                        observe_seconds=0.1,
                    )
                    if accounted_mode
                    else run_tls_loopback(
                        j, signer, trust_pem=certificates["selected"][1], observe_seconds=0.1
                    )
                    if tls_mode
                    else run_loopback(j, signer, observe_seconds=0.1)
                )
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
            if accounted_mode:
                ledger_raw = ledger_path.read_bytes()
                ledger_report = attempts.replay(
                    ledger_raw,
                    expected_sha256=joint.digest(ledger_raw),
                    binding_sha256=wire_guard["pin"],
                    profile=attempts.JOINT_PROFILE,
                )
                assert not ledger_report["network_admitted"]
                assert ledger_report["used_upper_bound"] is None
                with pytest.raises(FileExistsError):
                    attempts.AttemptLedger(
                        ledger_root,
                        binding=None,
                        binding_sha256=wire_guard["pin"],
                        profile=attempts.JOINT_PROFILE,
                    )
                if failure == "ledger_prepare_disk":
                    assert counts == {"http": 0, "account": 0, "market": 0}
                elif failure == "ledger_outcome_disk":
                    assert counts == {"http": 1, "account": 0, "market": 0}
                elif failure == "slow_metadata_body":
                    assert counts == {"http": 6, "account": 1, "market": 0}
                    assert ledger_report["recorded_attempts"] == 8
                    assert "joint_dispatch_usage" in result["reason"]
                if failure in {"ledger_prepare_disk", "tls_untrusted", "cancel"}:
                    outputs = []
                    for index in range(2):
                        output = tmp_path / f"failed-attempt-replay-{index}.json"
                        proc = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "apps.ops.portfolio_egress_ledger",
                                "--joint-profile",
                                "--archive",
                                str(ledger_path),
                                "--archive-sha256",
                                joint.digest(ledger_raw),
                                "--binding-sha256",
                                wire_guard["pin"],
                                "--report",
                                str(output),
                            ],
                            capture_output=True,
                            timeout=30,
                        )
                        assert proc.returncode == 2, proc.stdout + proc.stderr
                        outputs.append(output.read_bytes())
                    assert outputs[0] == outputs[1]
                    assert json.loads(outputs[0]) == ledger_report
            assert not errors, errors
            assert (
                KEY.encode() not in raw and b"PRIVATE KEY" not in raw and b'"signature"' not in raw
            )
            assert counts["account"] <= 1 and counts["market"] <= 1
            if failure in {None, "burst", "fragmented"}:
                assert result["status"] == "loopback_joint_completed", (result, j.state.failure)
                report = (
                    joint.replay_joint(
                        raw, expected_sha256=joint.digest(raw), evidence_type=TLSJointEvidence
                    )
                    if tls_mode
                    else replay(raw)
                )
                assert report["summary"] == result["summary"]
                assert counts == {"http": 16, "account": 1, "market": 1}
                accounting_report = None
                if accounted_mode:
                    accounting_report = replay_accounted(
                        raw,
                        ledger_raw,
                        joint_sha256=joint.digest(raw),
                        ledger_sha256=joint.digest(ledger_raw),
                    )
                    assert accounting_report["documented_weight"] == 448
                    assert accounting_report["unknown_charge_attempts"] == 1
                    assert accounting_report["prepared_tcp_connections"] == 18
                    assert ledger_report["recorded_attempts"] == 20
                    assert sum(c["raw_requests"] for c in ledger_report["counts"]) == 16
                    assert accounting_report["joint"] == report
                if accounted_mode and failure is None:
                    from tests.strategies_nautilus.test_portfolio_joint_egress import (
                        assert_rehashed_links_refused,
                    )

                    assert_rehashed_links_refused(raw, ledger_raw)
                if failure is None:
                    outputs = []
                    for i in range(2):
                        output = tmp_path / f"native-replay{i}.json"
                        proc = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "apps.ops.portfolio_joint_observation",
                                "--tls-loopback-profile" if tls_mode else "--loopback-profile",
                                *(
                                    [
                                        "--attempt-ledger",
                                        str(ledger_path),
                                        "--attempt-ledger-sha256",
                                        joint.digest(ledger_raw),
                                    ]
                                    if accounted_mode
                                    else []
                                ),
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
                    assert outputs[0] == outputs[1] and json.loads(outputs[0]) == (
                        accounting_report or report
                    )
                    assert path.read_bytes() == raw
                    if tls_mode:
                        # Rehash every row: rejection must come from source semantics,
                        # not the outer selected-file digest or journal chain.
                        for change, expected in (
                            ("account_wire", "joint_tls_frame_binding_or_age"),
                            ("market_frame", "joint_tls_frame_binding_or_age"),
                            ("rest_response", "joint_tls_http_original_response_required"),
                            ("endpoint", "joint_tls_source_binding_changed"),
                            ("trust_sha256", "joint_tls_source_binding_changed"),
                            ("close", "joint_tls_unsolicited_close"),
                        ):
                            altered = [json.loads(line) for line in raw.splitlines()]
                            kind = (
                                "tls_opened"
                                if change in {"endpoint", "trust_sha256"}
                                else "tls_close_prepared"
                                if change == "close"
                                else change
                            )
                            row = next(r for r in altered if r["kind"] == kind)
                            if change in {"account_wire", "market_frame", "rest_response"}:
                                payload = base64.b64decode(row["raw_b64"]) + b" "
                                row.update(joint.raw_fields(payload))
                            elif change == "close":
                                row["kind"] = "tick"
                            else:
                                row[change] = "0" * 64 if change == "trust_sha256" else "foreign"
                            previous = "0" * 64
                            for row in altered:
                                row.pop("sha256")
                                row["previous"] = previous
                                previous = joint.digest(canonical(row))
                                row["sha256"] = previous
                            changed_raw = b"".join(canonical(row) + b"\n" for row in altered)
                            with pytest.raises(DepthError, match=expected):
                                joint.replay_joint(
                                    changed_raw,
                                    expected_sha256=joint.digest(changed_raw),
                                    evidence_type=TLSJointEvidence,
                                )
                assert len(signed) == 9
                if tls_mode:
                    assert len(report["summary"]["tls_connections"]) == 18
                    assert all(c["closed"] for c in report["summary"]["tls_connections"])
                assert methods == [
                    "userDataStream.subscribe.signature",
                    "userDataStream.unsubscribe",
                ]
                expected_pongs = {("account", b"account-ping"), ("market", b"market-ping")}
                if failure == "fragmented":
                    expected_pongs |= {("account", b"fragment-ping"), ("market", b"fragment-ping")}
                    expected_pongs |= {("account", b"upgrade-ping"), ("market", b"upgrade-ping")}
                assert set(pongs) == expected_pongs
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
                    joint.replay_joint(
                        raw,
                        expected_sha256=joint.digest(raw),
                        evidence_type=TLSJointEvidence if tls_mode else RoutedJointEvidence,
                    )
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

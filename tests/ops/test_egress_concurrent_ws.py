"""Concurrent installed WebSocket custody, original replay and failure boundaries."""

import asyncio
import copy
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_read_sequence import capture_sequence


@pytest.fixture(scope="module")
def originals(tmp_path_factory):
    yield from capture_sequence(tmp_path_factory, routes=True)


@pytest.fixture
def fixture(originals):
    code = load("gateway_concurrent_ws")
    sequence = load("gateway_read_sequence")
    frames = load("installed_gateway").load(
        Path("apps/strategies_nautilus/portfolio_ws_frames.py").read_bytes()
    )
    selected = code.selection(
        originals.raw, originals.bundles, sequence.__dict__, originals.modules
    )
    # Synthetic transcript tests use original-relative fixed clocks, independent of test duration.
    code.time = SimpleNamespace(
        time_ns=lambda: selected["route_completed"]["utc_ns"] + 1_000_000,
        monotonic_ns=lambda: selected["route_completed"]["monotonic_ns"] + 1_000_000,
        monotonic=time.monotonic,
    )
    return SimpleNamespace(
        code=code, frames=frames, selected=selected, provenance=originals.modules["provenance"]
    )


def make_archive(fixture, tmp_path):
    code, provenance = fixture.code, fixture.provenance
    journal = code.Journal(
        tmp_path / "ws.jsonl", fixture.selected, provenance, fixture.frames, lambda: None
    )
    nonces = {role: "MDEyMzQ1Njc4OWFiY2RlZg==" for role in code.ROLES}
    import base64
    import hashlib

    def emit(kind, payload):
        journal.append(kind, payload)

    def raw(role, value):
        return {"role": role, **provenance.raw_fields(value)}

    for role in code.ROLES:
        emit(
            "connection_prepared",
            {
                "role": role,
                "endpoint": code.endpoint(role, fixture.selected)[0],
                "nonce": nonces[role],
                "peer": list(code.PEER),
            },
        )
    emit("grant_prepared", {"mark": code.MARK, "ttl_ms": 5000})
    emit("activated", {})
    for role in code.ROLES:
        emit(
            "tls_connected",
            {
                "role": role,
                "peer": list(code.PEER),
                "server_hostname": role + ".fixture.invalid",
                "peer_certificate_sha256": "a" * 64,
                "tls_version": "TLSv1.3",
                "cipher": ["TLS_AES_256_GCM_SHA384", "TLSv1.3", 256],
                "check_hostname": True,
                "verify_mode": "CERT_REQUIRED",
                "tls_minimum_version": "TLSv1.2",
            },
        )
        emit("request_prepared", raw(role, code.request(role, fixture.selected, nonces[role])))
        accept = base64.b64encode(
            hashlib.sha1(nonces[role].encode() + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
        )
        header = (
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
            + accept
            + b"\r\n\r\n"
        )
        ping = b"fixture:" + role.encode()
        for chunk in (header[:11], header[11:] + bytes([0x89, len(ping)]) + ping):
            emit("response_chunk", raw(role, chunk))
        emit("upgrade_accepted", {"role": role})
        emit("peer_control", {**raw(role, ping), "opcode": 9})
        emit("pong_prepared", raw(role, fixture.frames["client_frame"](ping, 10)))
    for role in code.ROLES:
        emit("close_prepared", raw(role, fixture.frames["client_frame"](b"\x03\xe8", 8)))
        emit("response_chunk", raw(role, b"\x88\x02\x03\xe8"))
        emit("peer_control", {**raw(role, b"\x03\xe8"), "opcode": 8})
    for kind in ("sockets_closed", "stop_requested", "revoked", "completed"):
        emit(kind, {})
    value = journal.expected
    journal.close()
    return value


def review(fixture, raw):
    return fixture.code.replay(
        raw,
        expected_sha256=fixture.code.digest(raw),
        selected=fixture.selected,
        provenance=fixture.provenance,
        frames=fixture.frames,
    )


def rehash(fixture, rows):
    raw = b""
    previous = None
    for seq, row in enumerate(rows):
        row.update(seq=seq, previous_sha256=previous)
        line = fixture.code.canonical(row) + b"\n"
        raw += line
        previous = fixture.code.digest(line)
    return raw


def test_two_connections_use_original_symbols_and_control_receipt_clocks(fixture, tmp_path):
    raw = make_archive(fixture, tmp_path)
    report = review(fixture, raw)
    assert report["status"] == "complete" and report["prepared_connections"] == 2
    assert report["symbols"] == ["BNBUSDT", "BTCUSDT"]
    assert report["both_channels_live_before_close"] and report["revocation_recorded"]
    assert (
        not report["account_subscription_authenticated"] and not report["native_events_delivered"]
    )
    assert report["market_connection_charge"] is None and report["actual_usage_upper_bound"] is None
    rows = list(map(json.loads, raw.splitlines()))
    for role, value in report["channels"].items():
        chunks = [r for r in rows if r["kind"] == "response_chunk" and r["payload"]["role"] == role]
        assert value["header_receipt"] == {k: chunks[1][k] for k in ("utc_ns", "monotonic_ns")}


def test_all_truncated_prefixes_remain_consumed_incomplete(fixture, tmp_path):
    raw = make_archive(fixture, tmp_path)
    lines = raw.splitlines(keepends=True)
    for end in range(1, len(lines)):
        report = review(fixture, b"".join(lines[:end]))
        assert report["status"] == "incomplete_no_resume" and not report["restart_allowed"]


@pytest.mark.parametrize(
    "damage",
    [
        "symbol",
        "peer",
        "nonce",
        "certificate",
        "hostname",
        "verify",
        "request",
        "upgrade",
        "masked_ping",
        "extra_ping",
        "close",
        "unmasked_pong",
        "pong_data",
        "clock",
        "deadline",
        "early_close",
        "no_revoke",
        "after_terminal",
    ],
)
def test_fully_rehashed_transport_tampering_refused(fixture, tmp_path, damage):
    rows = list(map(json.loads, make_archive(fixture, tmp_path).splitlines()))

    def row(kind, role=None):
        return next(
            r
            for r in rows
            if r["kind"] == kind and (role is None or r["payload"].get("role") == role)
        )

    if damage == "symbol":
        row("started")["payload"]["symbols"] = ["ETHUSDT"]
    elif damage == "peer":
        row("connection_prepared")["payload"]["peer"][0] = "127.0.0.1"
    elif damage == "nonce":
        row("connection_prepared")["payload"]["nonce"] = "AA=="
    elif damage == "certificate":
        row("tls_connected")["payload"]["peer_certificate_sha256"] = "invalid"
    elif damage == "hostname":
        row("tls_connected")["payload"]["server_hostname"] = "real.example"
    elif damage == "verify":
        row("tls_connected")["payload"]["check_hostname"] = False
    elif damage == "request":
        target = row("request_prepared")
        target["payload"].update(
            fixture.provenance.raw_fields(
                fixture.code.original(target["payload"]).replace(b"/ws-api/v3", b"/orders")
            )
        )
    elif damage in {"upgrade", "masked_ping", "extra_ping"}:
        target = [r for r in rows if r["kind"] == "response_chunk"][1]
        original = fixture.code.original(target["payload"])
        if damage == "upgrade":
            original = original.replace(b"Upgrade: websocket", b"Upgrade: forbidden")
        elif damage == "masked_ping":
            original = original.replace(b"\x89\x0f", b"\x89\x8f")
        else:
            original += b"\x89\x01x"
        target["payload"].update(fixture.provenance.raw_fields(original))
    elif damage == "close":
        target = next(
            r for r in rows if r["kind"] == "peer_control" and r["payload"]["opcode"] == 8
        )
        target["payload"]["opcode"] = 9
    elif damage in {"unmasked_pong", "pong_data"}:
        target = row("pong_prepared")
        raw = bytearray(fixture.code.original(target["payload"]))
        raw[1 if damage == "unmasked_pong" else -1] ^= 0x80 if damage == "unmasked_pong" else 1
        target["payload"].update(fixture.provenance.raw_fields(bytes(raw)))
    elif damage == "clock":
        row("request_prepared")["utc_ns"] += 100_000_000
    elif damage == "deadline":
        index = rows.index(row("request_prepared"))
        for r in rows[index:]:
            r["utc_ns"] += 5_000_000_000
            r["monotonic_ns"] += 5_000_000_000
    elif damage == "early_close":
        target = row("close_prepared")
        rows.remove(target)
        rows.insert(rows.index(row("tls_connected", "market")), target)
    elif damage == "no_revoke":
        rows.remove(row("revoked"))
    else:
        rows.append(copy.deepcopy(rows[-1]))
    with pytest.raises((ValueError, KeyError)):
        review(fixture, rehash(fixture, rows))


def test_completed_route_originals_required(fixture, originals):
    code = load("gateway_read_sequence")
    raw = b"\n".join(originals.raw.splitlines()[:-1]) + b"\n"
    with pytest.raises(ValueError, match="completed_original_routes"):
        fixture.code.selection(raw, originals.bundles, code.__dict__, originals.modules)


def test_stale_route_completion_cannot_start_new_transport(fixture, tmp_path):
    now = fixture.code.time.time_ns()
    mono = fixture.code.time.monotonic_ns()
    fixture.code.time.time_ns = lambda: now
    fixture.code.time.monotonic_ns = lambda: mono
    fixture.selected["route_completed"] = {
        k: v - 10_000_000_000 for k, v in fixture.selected["route_completed"].items()
    }
    with pytest.raises(ValueError, match="original_route_window"):
        fixture.code.Journal(
            tmp_path / "ws.jsonl",
            fixture.selected,
            fixture.provenance,
            fixture.frames,
            lambda: None,
        )


@pytest.mark.parametrize("damage", ["bytes", "replace", "mode", "link"])
def test_journal_drift_latches_and_cannot_be_restored(fixture, tmp_path, damage):
    path = tmp_path / "ws.jsonl"
    journal = fixture.code.Journal(
        path, fixture.selected, fixture.provenance, fixture.frames, lambda: None
    )
    old = path.read_bytes()
    try:
        if damage == "bytes":
            path.write_bytes(old + b" ")
        elif damage == "replace":
            path.rename(path.with_suffix(".old"))
            path.write_bytes(old)
            path.chmod(0o600)
        elif damage == "mode":
            path.chmod(0o644)
        else:
            os.link(path, path.with_suffix(".link"))
        with pytest.raises(ValueError, match="archive_changed"):
            journal.append("sockets_closed", {})
        path.write_bytes(old)
        path.chmod(0o600)
        with pytest.raises(ValueError, match="ended_or_foreign_owner"):
            journal.append("sockets_closed", {})
    finally:
        journal.close()


def test_persistence_failure_never_suppresses_kernel_revocation(fixture, tmp_path, monkeypatch):
    journal = fixture.code.Journal(
        tmp_path / "ws.jsonl", fixture.selected, fixture.provenance, fixture.frames, lambda: None
    )
    revoke = Mock()
    trust = b"test trust"
    fixture.selected["tls_trust_sha256"] = fixture.code.digest(trust)
    monkeypatch.setattr(fixture.code.ssl, "SSLContext", Mock(return_value=Mock()))
    monkeypatch.setattr(journal, "append", Mock(side_effect=OSError("fsync")))
    try:
        with pytest.raises(OSError, match="fsync"):
            asyncio.run(
                fixture.code.capture(
                    journal, trust, fixture.frames, lambda: None, Mock(), revoke, Mock()
                )
            )
        revoke.assert_called_once_with()
    finally:
        journal.close()


def test_framing_loads_without_native_import_or_project_import():
    import subprocess
    from pathlib import Path

    raw = Path("apps/strategies_nautilus/portfolio_ws_frames.py").read_text()
    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            "import sys;scope={};exec(sys.stdin.read(),scope);assert not any(n.startswith(('nautilus_trader','apps.')) for n in sys.modules);scope['client_frame'](bytes([3,232]),8);assert scope['ServerFrames']().feed(bytes([129,126,0,126])+b'x'*126)==[(1,b'x'*126)];print(scope['MAX_FRAME'])",
        ],
        input=raw,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "1048576"


@pytest.mark.parametrize("close_failure", [False, True])
def test_failed_channel_cancels_sibling_and_revokes_even_if_close_fails(
    fixture, tmp_path, monkeypatch, close_failure
):
    import socket
    from unittest.mock import AsyncMock

    code = fixture.code
    code.time = time
    fixture.selected["route_completed"] = {
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
    }
    trust = b"fixture trust"
    fixture.selected["tls_trust_sha256"] = code.digest(trust)
    journal = code.Journal(
        tmp_path / "ws.jsonl", fixture.selected, fixture.provenance, fixture.frames, lambda: None
    )
    context = Mock(check_hostname=True, verify_mode=code.ssl.CERT_REQUIRED)
    monkeypatch.setattr(code.ssl, "SSLContext", Mock(return_value=context))
    raw_sockets, writers, cancelled = [], [], []

    def new_socket(*args):
        raw = Mock()
        raw_sockets.append(raw)
        return raw

    code.socket = SimpleNamespace(
        socket=new_socket,
        AF_INET=socket.AF_INET,
        SOCK_STREAM=socket.SOCK_STREAM,
        SOL_SOCKET=socket.SOL_SOCKET,
        SO_MARK=socket.SO_MARK,
    )

    async def exercise():
        reached = asyncio.Event()
        parked = asyncio.Event()
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "sock_connect", AsyncMock())

        async def opened(*, server_hostname, **kwargs):
            role = server_hostname.split(".")[0]
            tls = Mock(server_hostname=server_hostname)
            tls.getpeercert.return_value = b"fixture DER"
            tls.version.return_value = "TLSv1.3"
            tls.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
            writer = Mock()
            writer.drain = AsyncMock()
            writer.get_extra_info.side_effect = lambda name: (
                tls if name == "ssl_object" else code.PEER
            )
            if close_failure and role == "account":
                writer.transport.abort.side_effect = OSError("close failed")
            writers.append(writer)

            async def read(size):
                if role == "market":
                    await reached.wait()
                    raise OSError("peer failed")
                reached.set()
                try:
                    await parked.wait()
                except asyncio.CancelledError:
                    cancelled.append(role)
                    raise

            return SimpleNamespace(read=read), writer

        monkeypatch.setattr(code.asyncio, "open_connection", opened)
        grant, revoke = Mock(), Mock()
        with pytest.raises(OSError, match="peer failed"):
            await code.capture(journal, trust, fixture.frames, lambda: None, grant, revoke, Mock())
        grant.assert_called_once_with()
        revoke.assert_called_once_with()
        assert not any(
            task is not asyncio.current_task() and not task.done() for task in asyncio.all_tasks()
        )

    try:
        asyncio.run(exercise())
        assert cancelled == ["account"]
        assert len(writers) == len(raw_sockets) == 2
        for writer in writers:
            writer.transport.abort.assert_called_once_with()
        for raw in raw_sockets:
            raw.close.assert_called_once_with()
        report = review(fixture, journal.expected)
        assert report["status"] == "incomplete_no_resume"
        assert report["sockets_closed_recorded"] is not close_failure
        assert report["revocation_recorded"] is not close_failure
    finally:
        journal.close()


def test_closed_and_foreign_journal_cannot_append_or_close_original_handles(
    fixture, tmp_path, monkeypatch
):
    code = fixture.code
    journal = code.Journal(
        tmp_path / "ws.jsonl", fixture.selected, fixture.provenance, fixture.frames, lambda: None
    )
    owner = os.getpid()
    monkeypatch.setattr(code.os, "getpid", lambda: owner + 1)
    try:
        with pytest.raises(ValueError, match="foreign_owner"):
            journal.append("sockets_closed", {})
        with pytest.raises(ValueError, match="foreign_owner"):
            journal.close()
        os.fstat(journal.reader)
    finally:
        monkeypatch.setattr(code.os, "getpid", lambda: owner)
        journal.close()
    journal.close()
    with pytest.raises(ValueError, match="ended_or_foreign_owner"):
        journal.append("sockets_closed", {})


def test_system_python_timeout_is_reported_as_refusal():
    import subprocess

    script = """
import asyncio,runpy
scope=runpy.run_path('infra/egress-guard/gateway_concurrent_ws.py')
async def stall(*args):raise asyncio.TimeoutError()
scope['capture_result'].__globals__['capture']=stall
assert scope['capture_result']()=={'status':'concurrent_ws_refused','reason':'TimeoutError','network_admitted':False}
"""
    subprocess.run(
        ["/usr/bin/python3", "-I", "-c", script], check=True, capture_output=True, text=True
    )

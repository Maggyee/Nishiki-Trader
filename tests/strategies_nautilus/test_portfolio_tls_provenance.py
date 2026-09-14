"""Ephemeral TLS peers exercise real certificate verification and original bytes."""

import _socket
import asyncio
import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
from contextlib import suppress

import pytest

from apps.strategies_nautilus import portfolio_tls_provenance as source
from apps.strategies_nautilus.portfolio_rate_evidence import RateEvidenceError, rest_rate_evidence


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp("provenance-certificates")
    output = {}
    for name, hosts in (
        ("selected", [f"{r}.fixture.invalid" for r in source.PATHS]),
        ("foreign", ["foreign.fixture.invalid"]),
    ):
        key, cert = root / f"{name}.key", root / f"{name}.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                f"/CN={hosts[0]}",
                "-addext",
                "subjectAltName=" + ",".join("DNS:" + h for h in hosts),
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        output[name] = context, cert.read_bytes()
    return output


@pytest.fixture
def allow_local(monkeypatch):
    attempts = []

    def connect(sock, address):
        assert address[0] == "127.0.0.1"
        attempts.append(address)
        return _socket.socket.connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    return attempts


def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def rewrite(path, values):
    previous = None
    raw = bytearray()
    for seq, row in enumerate(values):
        row.update(seq=seq, previous_sha256=previous)
        line = source.canonical(row) + b"\n"
        raw.extend(line)
        previous = source.digest(line)
    path.write_bytes(raw)
    return source.digest(raw)


BODY = b'{"rateLimits":[{"rateLimitType":"REQUEST_WEIGHT","interval":"MINUTE","intervalNum":1,"limit":6000}]}'


async def scenario(tmp_path, certificates, *, role="rest", failure=None, timeout=2):
    context, trust = certificates["selected"]
    if failure == "untrusted":
        context = certificates["foreign"][0]
    if failure == "hostname":
        context, trust = certificates["foreign"]
    requests, trailers, finished = [], [], asyncio.Event()
    writers = []

    async def peer(reader, writer):
        writers.append(writer)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            requests.append(request)
            if failure in {"timeout", "cancel"}:
                await reader.read()
                return
            if role == "rest":
                raw = (
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(BODY)).encode()
                    + b"\r\nX-MBX-USED-WEIGHT-1M: 70\r\nx-observation: first\r\nX-Observation: second\r\n\r\n"
                    + BODY
                )
            else:
                nonce = request.split(b"Sec-WebSocket-Key: ", 1)[1].split(b"\r\n", 1)[0]
                accept = base64.b64encode(
                    hashlib.sha1(nonce + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
                )
                raw = (
                    b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
                    + accept
                    + b"\r\n\r\n"
                )
                if failure == "bad_accept":
                    raw = raw.replace(accept, b"foreign")
                elif failure == "duplicate_accept":
                    raw = raw[:-2] + b"sec-websocket-accept: " + accept + b"\r\n\r\n"
                elif failure == "frame_tail":
                    raw += b"\x81\x02{}"
            if failure == "redirect":
                raw = b"HTTP/1.1 302 Found\r\nLocation: https://example.com/\r\nContent-Length: 0\r\n\r\n"
            elif failure == "duplicate_weight":
                raw = raw.replace(b"\r\n\r\n", b"\r\nx-mbx-used-weight-1m: 70\r\n\r\n")
            elif failure == "duplicate_length":
                raw = raw.replace(b"\r\n\r\n", b"\r\nContent-Length: 1\r\n\r\n")
            elif failure == "header_limit":
                raw = b"HTTP/1.1 200 OK\r\nX-Large: " + b"a" * source.MAX_HEADER
            elif failure == "body_limit":
                raw = b"HTTP/1.1 200 OK\r\nContent-Length: 16777217\r\n\r\n"
            elif failure == "partial":
                raw = b"HTTP/1.1 200 OK\r\nX-Partial: yes"
            elif failure == "partial_body":
                raw = raw[:-20]
            elif failure == "framing":
                raw = raw.replace(b"\r\n\r\n", b"\r\nTransfer-Encoding: chunked\r\n\r\n")
            writer.write(raw)
            await writer.drain()
            if failure not in {"partial", "partial_body", "header_limit"}:
                trailers.append(await reader.read())
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            finished.set()

    server = await asyncio.start_server(peer, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    scheme = "https" if role == "rest" else "wss"
    args = dict(
        endpoint=f"{scheme}://{role}.fixture.invalid:{port}{source.PATHS[role]}",
        role=role,
        trust_pem=trust,
        trust_sha256=source.digest(trust),
        timeout=timeout,
    )
    path = tmp_path / "capture.jsonl"
    caught = None
    try:
        task = asyncio.create_task(source.capture_loopback_tls(path, **args))
        if failure == "cancel":
            while not requests:
                await asyncio.sleep(0.005)
            task.cancel()
        try:
            await task
        except (Exception, asyncio.CancelledError) as exc:
            caught = exc
        if writers:
            async with asyncio.timeout(3):
                await finished.wait()
    finally:
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
    return path, requests, trailers, caught, args


@pytest.mark.parametrize("role", list(source.PATHS))
def test_real_tls_original_headers_and_deterministic_replay(
    tmp_path, certificates, allow_local, role
):
    path, requests, trailers, caught, args = asyncio.run(
        scenario(tmp_path, certificates, role=role)
    )
    assert caught is None
    assert len(allow_local) == len(requests) == 1
    assert trailers == [b""]
    assert requests[0].startswith(f"GET {source.PATHS[role]} HTTP/1.1\r\n".encode())
    assert b"X-MBX-APIKEY" not in requests[0] and b"signature" not in requests[0]
    assert path.stat().st_mode & 0o777 == 0o600
    original = path.read_bytes()
    expected = source.digest(original)
    report = source.read_provenance(path, expected_sha256=expected)
    assert report == source.read_provenance(path, expected_sha256=expected)
    assert path.read_bytes() == original
    assert report["tls"]["check_hostname"] is True
    cert_der = ssl.PEM_cert_to_DER_cert(args["trust_pem"].decode())
    assert report["tls"]["peer_certificate_sha256"] == source.digest(cert_der)
    assert not report["actual_exchange_source_verified"]
    assert not report["shared_egress_verified"]
    assert not report["network_admitted"]
    if role == "rest":
        assert report["header_pairs"][-2:] == [
            ["x-observation", "first"],
            ["X-Observation", "second"],
        ]
        assert report["original_body_sha256"] == source.digest(BODY)
        assert rest_rate_evidence(BODY, report["header_pairs"])["rates"][0]["count"] == 70
    with pytest.raises(FileExistsError):
        asyncio.run(source.capture_loopback_tls(path, **args))
    assert len(allow_local) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "untrusted",
        "hostname",
        "redirect",
        "duplicate_length",
        "header_limit",
        "body_limit",
        "partial",
        "partial_body",
        "framing",
        "timeout",
        "cancel",
    ],
)
def test_failed_capture_retains_attempt_and_partial_bytes(
    tmp_path, certificates, allow_local, failure
):
    path, requests, _, caught, args = asyncio.run(
        scenario(
            tmp_path, certificates, failure=failure, timeout=0.1 if failure == "timeout" else 2
        )
    )
    assert caught is not None
    assert len(allow_local) == 1
    data = rows(path)
    assert data[0]["kind"] == "prepared"
    assert data[-1]["kind"] == "aborted"
    assert not any(r["kind"] == "completed" for r in data)
    if failure in {"untrusted", "hostname"}:
        assert isinstance(caught, ssl.SSLCertVerificationError)
        assert requests == []
    if failure in {"partial", "partial_body", "redirect", "header_limit"}:
        assert any(r["kind"] == "response_chunk" for r in data)
    with pytest.raises(FileExistsError):
        asyncio.run(source.capture_loopback_tls(path, **args))
    assert len(allow_local) == 1


@pytest.mark.parametrize("failure", ["bad_accept", "duplicate_accept", "frame_tail"])
def test_upgrade_provenance_and_unprocessed_tail(tmp_path, certificates, allow_local, failure):
    path, requests, trailers, caught, _ = asyncio.run(
        scenario(tmp_path, certificates, role="market", failure=failure)
    )
    assert len(allow_local) == len(requests) == 1
    assert trailers == [b""]
    if failure == "frame_tail":
        assert caught is None
        report = source.read_provenance(path, expected_sha256=source.digest(path.read_bytes()))
        assert report["unprocessed_upgrade_tail_bytes"] == 4
    else:
        assert isinstance(caught, source.ProvenanceError)
        assert rows(path)[-1]["kind"] == "aborted"


def test_duplicate_rate_headers_remain_original_evidence(tmp_path, certificates, allow_local):
    path, _, _, caught, _ = asyncio.run(
        scenario(tmp_path, certificates, failure="duplicate_weight")
    )
    assert caught is None
    report = source.read_provenance(path, expected_sha256=source.digest(path.read_bytes()))
    with pytest.raises(RateEvidenceError, match="duplicate_weight_header"):
        rest_rate_evidence(BODY, report["header_pairs"])


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://testnet.binance.vision/api/v3/exchangeInfo",
        "https://api.binance.com/api/v3/exchangeInfo",
        "https://rest.fixture.invalid:443/api/v3/exchangeInfo?signature=forbidden",
        "https://rest.fixture.invalid:443/api/v3/account",
        "http://rest.fixture.invalid:443/api/v3/exchangeInfo",
        "https://user:secret@rest.fixture.invalid:443/api/v3/exchangeInfo",
        "https://rest.fixture.invalid:443/api/v3/exchangeInfo#fragment",
        "https://127.0.0.1:443/api/v3/exchangeInfo",
    ],
)
def test_nonfixture_or_changed_source_refused_before_network_or_archive(
    tmp_path, certificates, endpoint, monkeypatch
):
    async def unexpected(*args, **kwargs):
        pytest.fail("network was opened before source validation")

    monkeypatch.setattr(asyncio, "open_connection", unexpected)
    trust = certificates["selected"][1]
    path = tmp_path / "forbidden.jsonl"
    with pytest.raises(source.ProvenanceError):
        asyncio.run(
            source.capture_loopback_tls(
                path,
                endpoint=endpoint,
                role="rest",
                trust_pem=trust,
                trust_sha256=source.digest(trust),
            )
        )
    assert not path.exists()


def test_missing_or_changed_trust_refused_before_network(tmp_path, certificates, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("network was opened without selected trust")

    monkeypatch.setattr(asyncio, "open_connection", unexpected)
    for trust, expected in [(b"", source.digest(b"")), (certificates["selected"][1], "0" * 64)]:
        with pytest.raises(source.ProvenanceError):
            asyncio.run(
                source.capture_loopback_tls(
                    tmp_path / "missing.jsonl",
                    endpoint="https://rest.fixture.invalid:443/api/v3/exchangeInfo",
                    role="rest",
                    trust_pem=trust,
                    trust_sha256=expected,
                )
            )
    assert not (tmp_path / "missing.jsonl").exists()


@pytest.mark.parametrize("fail_on", range(1, 11))
def test_persistence_precedes_connect_and_request(
    tmp_path, certificates, allow_local, monkeypatch, fail_on
):
    real_fsync, calls = os.fsync, 0

    def fsync(fd):
        nonlocal calls
        calls += 1
        if calls >= fail_on:
            raise OSError("injected persistence failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    path, requests, _, caught, _ = asyncio.run(scenario(tmp_path, certificates))
    assert isinstance(caught, OSError)
    assert len(requests) == int(fail_on > 4)
    assert len(allow_local) == int(fail_on > 2)
    assert not any(r["kind"] == "completed" for r in rows(path))
    with pytest.raises(source.ProvenanceError):
        source.read_provenance(path, expected_sha256=source.digest(path.read_bytes()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("peer", ["192.0.2.1", 443]),
        ("check_hostname", False),
        ("verify_mode", "CERT_NONE"),
        ("server_hostname", "foreign.fixture.invalid"),
        ("trust_sha256", "0" * 64),
    ],
)
def test_replay_rechecks_tls_source_bindings(tmp_path, certificates, allow_local, field, value):
    path, _, _, caught, _ = asyncio.run(scenario(tmp_path, certificates))
    assert caught is None
    data = rows(path)
    data[1][field] = value
    changed = rewrite(path, data)
    with pytest.raises(source.ProvenanceError):
        source.read_provenance(path, expected_sha256=changed)


def test_replay_refuses_changed_selected_archive(tmp_path, certificates, allow_local):
    path, _, _, _, _ = asyncio.run(scenario(tmp_path, certificates))
    with pytest.raises(source.ProvenanceError, match="original_hash_changed"):
        source.read_provenance(path, expected_sha256="0" * 64)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.pop(),
        lambda r: r[0].update(profile="portfolio.testnet_joint_observation.v1"),
        lambda r: r[2].update(target="/api/v3/account"),
        lambda r: r[-3].update(header_pairs=[]),
        lambda r: r[-1].update(network_admitted=True),
        lambda r: r[-1].update(utc_ns=1),
        lambda r: r.insert(3, r.pop(4)),  # Header interpretation before its original chunk.
    ],
)
def test_replay_requires_complete_original_order_and_semantics(
    tmp_path, certificates, allow_local, mutation
):
    path, _, _, _, _ = asyncio.run(scenario(tmp_path, certificates))
    data = rows(path)
    mutation(data)
    expected = rewrite(path, data)
    with pytest.raises(source.ProvenanceError):
        source.read_provenance(path, expected_sha256=expected)


def test_transport_close_failure_is_not_completed(tmp_path, certificates, allow_local, monkeypatch):
    open_connection = asyncio.open_connection

    async def open_with_failed_close(*args, **kwargs):
        reader, writer = await open_connection(*args, **kwargs)
        close = writer.close

        def failed_close():
            close()
            raise OSError("injected close failure")

        writer.close = failed_close
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", open_with_failed_close)
    path, _, _, caught, _ = asyncio.run(scenario(tmp_path, certificates))
    assert isinstance(caught, OSError)
    assert rows(path)[-1]["kind"] == "aborted"
    with pytest.raises(source.ProvenanceError):
        source.read_provenance(path, expected_sha256=source.digest(path.read_bytes()))


def test_two_fresh_cli_replays_are_identical_and_private(tmp_path, certificates, allow_local):
    path, _, _, _, _ = asyncio.run(scenario(tmp_path, certificates, role="account"))
    original = path.read_bytes()
    reports = []
    for index in range(2):
        report = tmp_path / f"replay-{index}.json"
        args = [
            sys.executable,
            "-m",
            "apps.ops.portfolio_tls_provenance",
            "--archive",
            str(path),
            "--archive-sha256",
            source.digest(original),
            "--report",
            str(report),
        ]
        result = subprocess.run(args, capture_output=True, check=False, timeout=15)
        assert result.returncode == 0, result.stderr.decode()
        assert report.stat().st_mode & 0o777 == 0o600
        reports.append(report.read_bytes())
    assert reports[0] == reports[1]
    assert path.read_bytes() == original


def test_cli_has_no_capture_or_missing_source_fallback(tmp_path, monkeypatch, capsys):
    from apps.ops.portfolio_tls_provenance import main

    async def unexpected(*args, **kwargs):
        pytest.fail("offline replay opened a connection")

    monkeypatch.setattr(asyncio, "open_connection", unexpected)
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "--archive",
                str(tmp_path / "absent.jsonl"),
                "--archive-sha256",
                "0" * 64,
                "--report",
                str(report),
            ]
        )
        == 1
    )
    assert not report.exists()
    assert json.loads(capsys.readouterr().out)["network_admitted"] is False
    with pytest.raises(SystemExit):
        main(["--capture"])

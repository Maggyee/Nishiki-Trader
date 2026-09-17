"""Fixed request ordering, persistence failures and replay semantics at the gateway."""

import importlib.util
import json
import os
import ssl
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger_module
from apps.strategies_nautilus import portfolio_rate_evidence as rates
from apps.strategies_nautilus import portfolio_tls_provenance as provenance

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"
PIN = "a" * 64
TRUST = b"fixture trust handled by fake TLS context in unit tests"


def load(name):
    spec = importlib.util.spec_from_file_location(
        "gateway_tls_test_" + name, DIRECTORY / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path, monkeypatch):
    module, gateway_module = load("gateway_tls"), load("ledger_gateway")
    tmp_path.chmod(0o700)
    ledger = ledger_module.AttemptLedger(
        tmp_path,
        binding=SimpleNamespace(verify=lambda: {"binding_sha256": PIN}),
        binding_sha256=PIN,
    )
    lifecycle = gateway_module.GatewayLifecycle(ledger, ledger_module)
    body = provenance.canonical(
        {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 6000,
                },
                {
                    "rateLimitType": "RAW_REQUESTS",
                    "interval": "MINUTE",
                    "intervalNum": 5,
                    "limit": 61000,
                },
                {
                    "rateLimitType": "CONNECTIONS",
                    "interval": "MINUTE",
                    "intervalNum": 5,
                    "limit": 300,
                },
            ]
        }
    )
    header = (
        b"HTTP/1.1 200 OK\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\nX-MBX-USED-WEIGHT-1M: 20\r\n\r\n"
    )
    path = ledger.path / "tls.jsonl"
    events = []

    class Socket:
        chunks = [header, body]
        delay = 0
        sent = connected = False

        def setsockopt(self, level, option, value):
            assert value == module.MARK

        def settimeout(self, value):
            assert 0 < value <= 4

        def connect(self, peer):
            assert peer == module.PEER
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            assert rows[-1]["kind"] == "connection_prepared"
            assert ledger.state.pending == 0
            assert json.loads(lifecycle.path.read_bytes().splitlines()[-1])["kind"] == "activated"
            self.connected = True
            events.append("connect")

        def sendall(self, raw):
            assert raw == module.REQUEST
            assert json.loads(path.read_bytes().splitlines()[-1])["kind"] == "request_prepared"
            self.sent = True
            events.append("send")

        def recv(self, size):
            assert size == 4096
            if len(self.chunks) == 1 and self.delay:
                time.sleep(self.delay)
            return self.chunks.pop(0) if self.chunks else b""

        def getpeername(self):
            return module.PEER

        def getpeercert(self, **kwargs):
            return b"fixture certificate"

        def version(self):
            return "TLSv1.3"

        def cipher(self):
            return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        def close(self):
            events.append("close")

    connection = Socket()
    context = SimpleNamespace(
        check_hostname=True,
        verify_mode=ssl.CERT_REQUIRED,
        wrap_socket=Mock(return_value=connection),
    )
    monkeypatch.setattr(
        provenance,
        "_selection",
        lambda *args: (SimpleNamespace(hostname="rest.fixture.invalid"), context),
    )
    monkeypatch.setattr(module.socket, "socket", lambda *a, **kw: connection)
    gateway = gateway_module.FixtureLedgerGateway(
        ledger,
        lifecycle=lifecycle,
        authorize=lambda: {"ok": True},
        grant=lambda: events.append("grant"),
        revoke=lambda: events.append("revoke"),
        send=lambda: module.capture(ledger, lifecycle, TRUST, provenance, rates),
    )

    def review(raw=None, **changes):
        raw = path.read_bytes() if raw is None else raw
        args = dict(
            expected_sha256=provenance.digest(raw),
            attempts=ledger.expected,
            lifecycle=lifecycle.expected,
            binding_sha256=PIN,
            trust_sha256=provenance.digest(TRUST),
            ledger_module=ledger_module,
            gateway_module=vars(gateway_module),
            provenance=provenance,
            rates=rates,
        )
        args.update(changes)
        return module.replay(raw, **args)

    yield SimpleNamespace(
        module=module,
        gateway=gateway,
        ledger=ledger,
        lifecycle=lifecycle,
        path=path,
        socket=connection,
        context=context,
        events=events,
        review=review,
        header=header,
        body=body,
    )
    with suppress(Exception):
        gateway.close()


def test_fixed_request_follows_both_journals_and_retains_unknown_usage(case):
    case.gateway.dispatch()
    report = case.review()
    assert report["status"] == "complete"
    assert (
        case.events.index("grant")
        < case.events.index("connect")
        < case.events.index("send")
        < case.events.index("revoke")
    )
    assert report["http_request_prepared"] and report["prepared_tcp_connections"] == 1
    assert report["provider_connection_charge"] is None
    by_kind = {r["rate_limit_type"]: r for r in report["rate_evidence"]["rates"]}
    assert by_kind["REQUEST_WEIGHT"]["count"] == 20
    assert by_kind["RAW_REQUESTS"]["count"] is None and by_kind["CONNECTIONS"]["count"] is None
    assert not report["network_admitted"] and not report["restart_allowed"]
    with pytest.raises(ValueError, match="consumed"):
        case.gateway.dispatch()


def test_body_completion_does_not_refresh_header_receipt(case):
    case.socket.delay = 0.02
    case.gateway.dispatch()
    report = case.review()
    assert report["header_receipt"]["seq"] == 3
    assert report["body_receipt"]["seq"] == 4
    assert report["header_age_at_body_ns"] >= 20_000_000


@pytest.mark.parametrize("sequence", range(8))
def test_each_tls_fsync_failure_keeps_consumption_and_cannot_complete(case, monkeypatch, sequence):
    original = os.fsync

    def fail(fd):
        if os.readlink(f"/proc/self/fd/{fd}") == str(case.path):
            raw = case.path.read_bytes()
            if raw and json.loads(raw.splitlines()[-1])["seq"] == sequence:
                raise OSError("fixture_tls_fsync_failed")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        case.gateway.dispatch()
    assert case.gateway.revoked and case.ledger.state.pending == 0
    assert case.socket.connected == (sequence > 0)
    assert case.socket.sent == (sequence > 2)
    if case.path.read_bytes():
        assert case.review()["status"] == "incomplete_no_resume"
    else:
        with pytest.raises(ValueError):
            case.review()


def test_certificate_failure_never_sends_http_and_preserves_connection_attempt(case):
    case.context.wrap_socket.side_effect = ssl.SSLCertVerificationError("fixture")
    with pytest.raises(ssl.SSLCertVerificationError):
        case.gateway.dispatch()
    report = case.review()
    assert report["status"] == "incomplete_no_resume" and not report["http_request_prepared"]
    assert not case.socket.sent and case.gateway.revoked


@pytest.mark.parametrize(
    "damage",
    ["duplicate_weight", "truncated", "trailing", "redirect", "chunked", "oversized", "bad_json"],
)
def test_bad_response_is_retained_but_cannot_complete(case, damage):
    header, body = case.header, case.body
    if damage == "duplicate_weight":
        header = header.replace(b"\r\n\r\n", b"\r\nx-mbx-used-weight-1m: 20\r\n\r\n")
    elif damage == "truncated":
        body = body[:5]
    elif damage == "trailing":
        body += b"extra"
    elif damage == "redirect":
        header = header.replace(b"200 OK", b"302 Found")
    elif damage == "chunked":
        header = header.replace(b"\r\n\r\n", b"\r\nTransfer-Encoding: chunked\r\n\r\n")
    elif damage == "oversized":
        header = header.replace(str(len(body)).encode(), b"65537")
    else:
        body = b"!" + body[1:]
    case.socket.chunks = [header, body]
    with pytest.raises(ValueError):
        case.gateway.dispatch()
    report = case.review()
    assert report["status"] == "incomplete_no_resume" and report["rate_evidence"] is None
    if damage == "truncated":
        assert report["body_receipt"] is None
    assert case.gateway.revoked and case.ledger.state.pending == 0


def test_tls_archive_mutation_during_fsync_stops_before_connect(case, monkeypatch):
    original = os.fsync

    def mutate(fd):
        original(fd)
        if os.readlink(f"/proc/self/fd/{fd}") == str(case.path) and case.path.stat().st_size:
            os.pwrite(fd, b"!", 0)

    monkeypatch.setattr(os, "fsync", mutate)
    with pytest.raises(ValueError, match="persisted_bytes"):
        case.gateway.dispatch()
    assert not case.socket.connected and case.gateway.revoked
    with pytest.raises(ValueError):
        case.review()


@pytest.mark.parametrize(
    "damage",
    [
        "method",
        "peer",
        "trust",
        "certificate",
        "verification",
        "request_prefix",
        "grant_prefix",
        "header_receipt_override",
        "clock",
        "body_hash",
        "drop_request",
    ],
)
def test_fully_rehashed_semantic_tampering_is_refused(case, damage):
    case.gateway.dispatch()
    rows = [json.loads(line) for line in case.path.read_bytes().splitlines()]
    if damage == "method":
        rows[2].update(provenance.raw_fields(case.module.REQUEST.replace(b"GET", b"POST")))
    elif damage == "peer":
        rows[0]["peer"] = ["8.8.8.8", 443]
    elif damage == "trust":
        rows[0]["trust_sha256"] = "0" * 64
    elif damage == "certificate":
        rows[1]["peer_certificate_sha256"] = "g" * 64
    elif damage == "verification":
        rows[1]["check_hostname"] = False
    elif damage == "request_prefix":
        rows[0]["attempt_prefix_sha256"] = provenance.digest(
            case.ledger.expected.splitlines(keepends=True)[0]
        )
    elif damage == "grant_prefix":
        rows[0]["lifecycle_prefix_sha256"] = provenance.digest(
            case.lifecycle.expected.splitlines(keepends=True)[0]
        )
    elif damage == "header_receipt_override":
        rows[5]["header_receipt"] = rows[4]["monotonic_ns"]
    elif damage == "clock":
        rows[4]["utc_ns"] += 100_000_000
    elif damage == "body_hash":
        rows[5]["body_sha256"] = "0" * 64
    else:
        rows.pop(2)
    raw, previous = b"", None
    for seq, row in enumerate(rows):
        row.update(seq=seq, previous_sha256=previous)
        line = provenance.canonical(row) + b"\n"
        raw += line
        previous = provenance.digest(line)
    with pytest.raises(ValueError):
        case.review(raw)


def test_real_endpoint_never_enters_fixed_capture_api(case):
    with pytest.raises(TypeError):
        case.module.capture(
            case.ledger,
            case.lifecycle,
            TRUST,
            provenance,
            rates,
            endpoint="https://testnet.binance.vision/api/v3/exchangeInfo",
        )
    assert not case.socket.connected


def test_header_receipt_precedes_slow_archive_validation(case, monkeypatch):
    received = []
    waiting = False
    original_recv, original_storage = case.socket.recv, case.ledger._storage

    def recv(size):
        nonlocal waiting
        raw = original_recv(size)
        received.append(time.monotonic_ns())
        waiting = True
        return raw

    def storage():
        nonlocal waiting
        if waiting:
            waiting = False
            time.sleep(0.03)
        original_storage()

    monkeypatch.setattr(case.socket, "recv", recv)
    monkeypatch.setattr(case.ledger, "_storage", storage)
    case.gateway.dispatch()
    report = case.review()
    assert 0 <= report["header_receipt"]["monotonic_ns"] - received[0] < 20_000_000
    assert 0 <= report["body_receipt"]["monotonic_ns"] - received[1] < 20_000_000


def test_header_notification_follows_successful_chunk_fsync(case, monkeypatch):
    original = os.fsync
    persisted = []
    notifications = []

    def fsync(fd):
        original(fd)
        if os.readlink(f"/proc/self/fd/{fd}") == str(case.path) and case.path.stat().st_size:
            persisted.append(json.loads(case.path.read_bytes().splitlines()[-1])["kind"])

    def notified():
        assert persisted[-1] == "response_chunk"
        assert json.loads(case.path.read_bytes().splitlines()[-1])["seq"] == 3
        notifications.append(True)

    monkeypatch.setattr(os, "fsync", fsync)
    case.gateway.send = lambda: case.module.capture(
        case.ledger, case.lifecycle, TRUST, provenance, rates, on_headers=notified
    )
    case.gateway.dispatch()
    assert notifications == [True]

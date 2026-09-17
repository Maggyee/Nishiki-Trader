"""Actual credential-framed payloads preserve root TLS bytes and receipt clocks."""

import array
import base64
import json
import os
import socket
import threading
import time
from contextlib import suppress
from types import SimpleNamespace

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger_module
from apps.strategies_nautilus import portfolio_rate_evidence as rates
from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from tests.ops.test_egress_gateway_tls import PIN, TRUST
from tests.ops.test_egress_gateway_tls import case as case  # Shared TLS/ledger fault harness.
from tests.ops.test_egress_installed_gateway import load

SOCKETPAIR = socket.socketpair
SOCKET = socket.socket


@pytest.fixture
def channels(monkeypatch):
    # The shared TLS fixture replaces socket.socket to inject wire faults.
    with monkeypatch.context() as local:
        local.setattr(socket, "socket", SOCKET)
        left, right = SOCKETPAIR(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    base = load("collector_launcher")
    peer = (os.getpid(), os.getuid(), os.getgid())
    result = [base.ControlChannel(c, peer, timeout=0.2) for c in (left, right)]
    yield result
    for c in result:
        c.close()


@pytest.fixture
def transfer(case, channels):
    extension = load("gateway_tls_receipt")
    collector = SimpleNamespace(channel=channels[0], verify=lambda: None)
    results, errors = [], []
    state = SimpleNamespace(extension=extension, collector=collector, payload=None, report=None)

    def client():
        try:
            results.append(extension.receive_payload(channels[1], provenance, rates))
        except BaseException as exc:
            errors.append(exc)
            channels[1].close()

    thread = threading.Thread(target=client)
    thread.start()

    def completed(raw):
        case.gateway._revoke()
        state.report = case.review(raw)
        state.payload = extension.payload_from_tls(raw, state.report)
        assert case.gateway.revoked and case.ledger.state.pending == 0
        return extension.deliver(collector, case.ledger, case.lifecycle, state.payload, provenance)

    case.gateway.send = lambda: case.module.capture(
        case.ledger, case.lifecycle, TRUST, provenance, rates, on_complete=completed
    )
    state.completed = completed
    state.results, state.errors, state.thread = results, errors, thread
    yield state
    channels[0].close()
    thread.join(timeout=6)
    assert not thread.is_alive()


def review(case, transfer, raw=None):
    path = case.ledger.path / "receipt.jsonl"
    raw = path.read_bytes() if raw is None else raw
    return transfer.extension.replay(
        raw,
        expected_sha256=provenance.digest(raw),
        tls_raw=case.path.read_bytes(),
        attempts=case.ledger.expected,
        lifecycle=case.lifecycle.expected,
        trust_sha256=provenance.digest(TRUST),
        ledger_module=ledger_module,
        gateway_module=vars(load("ledger_gateway")),
        transport=vars(case.module),
        provenance=provenance,
        rates=rates,
        binding_sha256=PIN,
    )


def test_real_packets_deliver_exact_bytes_and_original_header_age(case, transfer):
    case.socket.delay = 0.02
    case.gateway.dispatch()
    transfer.thread.join(timeout=1)
    assert not transfer.errors and transfer.results == [transfer.payload]
    assert case.ledger.state.pending is None and case.gateway.revoked
    value = json.loads(transfer.results[0])
    assert base64.b64decode(value["response_b64"]) == case.header + case.body
    assert (
        value["body_receipt"]["monotonic_ns"] - value["header_receipt"]["monotonic_ns"]
        >= 20_000_000
    )
    result = review(case, transfer)
    assert result["status"] == "acknowledged" and result["attempt_outcome_recorded"]
    assert not result["native_collector_integrated"] and not result["network_admitted"]
    with pytest.raises(ValueError, match="consumed"):
        case.gateway.dispatch()


@pytest.mark.parametrize("seq", [0, 1])
def test_receipt_fsync_failure_preserves_pending_and_revoked(case, transfer, monkeypatch, seq):
    original = os.fsync

    def fail(fd):
        if os.readlink(f"/proc/self/fd/{fd}").endswith("/receipt.jsonl"):
            raw = (case.ledger.path / "receipt.jsonl").read_bytes()
            if raw and json.loads(raw.splitlines()[-1])["seq"] == seq:
                raise OSError("receipt_fsync")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="receipt_fsync"):
        case.gateway.dispatch()
    assert case.ledger.state.pending == 0 and case.gateway.revoked
    assert case.review()["status"] == "complete"  # Wire outcome is distinct from consumer receipt.
    if seq == 0:
        assert transfer.results == []


def test_receipt_storage_mutation_stops_before_first_packet(case, transfer, monkeypatch):
    original = os.fsync

    def mutate(fd):
        original(fd)
        if os.readlink(f"/proc/self/fd/{fd}").endswith("/receipt.jsonl"):
            os.pwrite(fd, b"!", 0)

    monkeypatch.setattr(os, "fsync", mutate)
    with pytest.raises(ValueError, match="receipt_storage_changed"):
        case.gateway.dispatch()
    assert case.ledger.state.pending == 0 and case.gateway.revoked
    assert not transfer.results


def test_channel_loss_after_tls_retains_original_complete_wire_and_pending_attempt(case, transfer):
    original = transfer.extension.deliver

    def lose_channel(*args, **kwargs):
        return original(*args, **kwargs, on_prepared=transfer.collector.channel.close)

    transfer.extension.deliver = lose_channel
    with pytest.raises((OSError, RuntimeError)):
        case.gateway.dispatch()
    assert case.ledger.state.pending == 0 and case.gateway.revoked
    assert case.review()["status"] == "complete"
    assert review(case, transfer)["status"] == "incomplete_no_resume"


@pytest.mark.parametrize(
    "damage",
    [
        "bytes",
        "tls",
        "time",
        "jump",
        "order",
        "extra",
        "duplicate",
        "boolean_seq",
        "attempt_prefix",
        "kernel_prefix",
    ],
)
def test_rehashed_receipt_tampering_is_refused(case, transfer, damage):
    case.gateway.dispatch()
    rows = [
        json.loads(line) for line in (case.ledger.path / "receipt.jsonl").read_bytes().splitlines()
    ]
    if damage == "bytes":
        rows[1]["payload_sha256"] = "0" * 64
    elif damage == "tls":
        rows[1]["tls_sha256"] = "0" * 64
    elif damage == "time":
        rows[1]["monotonic_ns"] = 1
    elif damage == "jump":
        rows[1]["utc_ns"] += 100_000_000
    elif damage == "attempt_prefix":
        rows[0]["attempt_prefix_sha256"] = provenance.digest(case.ledger.expected)
    elif damage == "kernel_prefix":
        rows[0]["lifecycle_prefix_sha256"] = provenance.digest(
            case.lifecycle.expected.splitlines(keepends=True)[0]
        )
    elif damage == "order":
        rows.reverse()
    elif damage == "extra":
        rows[1]["network_admitted"] = True
    elif damage == "duplicate":
        rows.append(rows[-1].copy())
    raw, previous = b"", None
    for seq, row in enumerate(rows):
        row.update(seq=seq if damage != "boolean_seq" else bool(seq), previous_sha256=previous)
        line = provenance.canonical(row) + b"\n"
        raw += line
        previous = provenance.digest(line)
    with pytest.raises(ValueError):
        review(case, transfer, raw)


@pytest.mark.parametrize(
    "damage",
    ["extra", "wrong_profile", "boolean_time", "clock_order", "trailing", "bad_body", "big"],
)
def test_consumer_rejects_malformed_payload(case, transfer, damage):
    case.gateway.dispatch()
    value = json.loads(transfer.payload)
    if damage == "extra":
        value["endpoint"] = "https://api.binance.com"
    elif damage == "wrong_profile":
        value["profile"] = "other"
    elif damage == "boolean_time":
        value["header_receipt"]["utc_ns"] = True
    elif damage == "clock_order":
        value["body_receipt"]["monotonic_ns"] = 1
    elif damage == "trailing":
        value["response_b64"] = base64.b64encode(case.header + case.body + b"extra").decode()
    elif damage == "bad_body":
        value["response_b64"] = base64.b64encode(case.header + b"!" + case.body[1:]).decode()
    raw = b"x" * 180001 if damage == "big" else provenance.canonical(value)
    with pytest.raises(ValueError):
        transfer.extension.validate_payload(raw, provenance, rates)


@pytest.mark.parametrize(
    "token", [None, 2, [], "data:", "data:!", "data:Zh==", "data:" + "YQ==" * 513, "end:wrong"]
)
def test_dynamic_data_allowlist_does_not_bypass_fixed_channel(token):
    assert token not in load("gateway_tls_receipt").DataToken()


@pytest.mark.parametrize("fault", ["seq", "descriptor", "oversize", "credentials", "hash"])
def test_consumer_rejects_invalid_credential_frames(channels, fault):
    extension = load("gateway_tls_receipt")
    root, child = channels
    token, seq = "data:YQ==", 2
    if fault == "seq":
        seq = 3
    elif fault == "credentials":
        child.peer = (os.getpid() + 1, os.getuid(), os.getgid())
    elif fault == "hash":
        token = "end:" + "0" * 64
    raw = provenance.canonical({"v": 1, "op": token, "seq": seq})
    if fault == "descriptor":
        fd = os.open("/dev/null", os.O_RDONLY)
        try:
            root.connection.sendmsg(
                [raw], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))]
            )
        finally:
            os.close(fd)
    else:
        root.connection.send(raw + b" " * 1024 if fault == "oversize" else raw)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(RuntimeError):
        extension.receive_payload(child, provenance, rates)
    assert (
        len(os.listdir("/proc/self/fd")) == before - 1
    )  # Failed endpoint closed; no received FD leak.


def test_total_transfer_deadline_is_not_refreshed_by_each_packet(channels, monkeypatch):
    extension = load("gateway_tls_receipt")
    monkeypatch.setattr(extension, "DEADLINE", 0.04)
    root, child = channels
    errors = []

    def receive():
        try:
            extension.receive_payload(child, provenance, rates)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=receive)
    thread.start()
    for seq in range(2, 6):
        with suppress(OSError, RuntimeError):
            root.send("data:YQ==", seq)
            root.receive({"part"}, seq)
        time.sleep(0.02)
    thread.join(timeout=1)
    assert not thread.is_alive() and isinstance(errors[0], TimeoutError)


def test_lost_final_ack_never_completes_attempt(case, channels):
    extension = load("gateway_tls_receipt")
    collector = SimpleNamespace(channel=channels[0], verify=lambda: None)
    errors = []

    def receive():
        try:
            # Consume the authentic payload, then send a mismatched final digest.
            original = channels[1].send

            def send(token, seq):
                return original(
                    "accepted:" + "0" * 64 if token.startswith("accepted:") else token, seq
                )

            channels[1].send = send
            extension.receive_payload(channels[1], provenance, rates)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=receive)
    thread.start()

    def completed(raw):
        case.gateway._revoke()
        payload = extension.payload_from_tls(raw, case.review(raw))
        return extension.deliver(collector, case.ledger, case.lifecycle, payload, provenance)

    case.gateway.send = lambda: case.module.capture(
        case.ledger, case.lifecycle, TRUST, provenance, rates, on_complete=completed
    )
    try:
        with pytest.raises(RuntimeError, match="channel_protocol"):
            case.gateway.dispatch()
        assert case.gateway.revoked and case.ledger.state.pending == 0
        assert case.review()["status"] == "complete"
        assert len((case.ledger.path / "receipt.jsonl").read_bytes().splitlines()) == 1
    finally:
        channels[0].close()
        thread.join(timeout=1)
    assert not thread.is_alive() and not errors


def test_durable_transfer_requires_revocation_before_first_data(case, transfer):
    original = case.gateway._revoke
    case.gateway._revoke = lambda: setattr(case.gateway, "revoked", True)
    try:
        with pytest.raises(ValueError, match="revoked_kernel_required"):
            case.gateway.dispatch()
        assert case.ledger.state.pending == 0 and not transfer.results
        assert not (case.ledger.path / "receipt.jsonl").exists()
    finally:
        case.gateway._revoke = original
        original()


def _rechain(rows):
    raw, previous = b"", None
    for seq, row in enumerate(rows):
        row = {**row, "seq": seq, "previous_sha256": previous}
        line = provenance.canonical(row) + b"\n"
        raw += line
        previous = provenance.digest(line)
    return raw


def test_receipt_replay_rejects_additional_attempt_in_full_companion(case, transfer):
    case.gateway.dispatch()
    case.ledger.prepare(caller="collector", operation="exchange_info")
    with pytest.raises(ValueError, match="receipt_single_attempt_required"):
        review(case, transfer)


@pytest.mark.parametrize("terminal", ["aborted", "closed"])
def test_receipt_replay_rejects_terminal_pending_prefix(case, transfer, monkeypatch, terminal):
    case.gateway.dispatch()
    receipts = [
        json.loads(line) for line in (case.ledger.path / "receipt.jsonl").read_bytes().splitlines()
    ]
    prefix, rows = b"", []
    for line in case.ledger.expected.splitlines(keepends=True):
        prefix += line
        rows.append(json.loads(line))
        if provenance.digest(prefix) == receipts[0]["attempt_prefix_sha256"]:
            break
    rows.append(
        {
            **rows[-1],
            "kind": terminal,
            "payload": {"reason": "fixture_abort"} if terminal == "aborted" else {},
            **{k: receipts[0][k] for k in ("utc_ns", "monotonic_ns")},
        }
    )
    ended = _rechain(rows)
    # This is a valid generic ledger with a pending index, but no active transfer.
    assert (
        ledger_module.replay(ended, expected_sha256=provenance.digest(ended), binding_sha256=PIN)[
            "pending_attempt"
        ]
        == 0
    )
    for row in receipts:
        row["attempt_prefix_sha256"] = provenance.digest(ended)
    monkeypatch.setattr(case.ledger, "expected", ended)
    with pytest.raises(ValueError, match="receipt_pending_and_revocation_required"):
        review(case, transfer, _rechain(receipts))


@pytest.mark.parametrize("outcome", ["failed", "uncertain"])
def test_receipt_replay_rejects_contradictory_outcome(case, transfer, monkeypatch, outcome):
    case.gateway.dispatch()
    rows = [json.loads(line) for line in case.ledger.expected.splitlines()]
    assert rows[-1]["kind"] == "outcome"
    rows[-1]["payload"]["result"] = outcome
    monkeypatch.setattr(case.ledger, "expected", _rechain(rows))
    with pytest.raises(ValueError, match="receipt_outcome_mismatch"):
        review(case, transfer)


def test_consumer_never_acknowledges_after_validation_exceeds_deadline(
    case, transfer, monkeypatch, channels
):
    original = transfer.extension.validate_payload
    # Advance only this extension's clock; avoid wall-clock sleeps and keep root
    # ledger timestamps and TLS deadlines independent of the injected parse delay.
    elapsed = [0.0]
    clock = SimpleNamespace(
        monotonic=lambda: time.monotonic() + elapsed[0],
        time_ns=time.time_ns,
        monotonic_ns=time.monotonic_ns,
    )
    monkeypatch.setattr(transfer.extension, "time", clock)

    def delayed(*args):
        result = original(*args)
        elapsed[0] = transfer.extension.DEADLINE + 1
        return result

    monkeypatch.setattr(transfer.extension, "validate_payload", delayed)
    sent = []
    original_send = channels[1].send

    def send(token, seq):
        sent.append(token)
        return original_send(token, seq)

    monkeypatch.setattr(channels[1], "send", send)
    with pytest.raises((RuntimeError, TimeoutError)):
        case.gateway.dispatch()
    transfer.thread.join(timeout=1)
    assert not transfer.results
    assert transfer.errors and isinstance(transfer.errors[0], TimeoutError)
    assert case.ledger.state.pending == 0 and case.gateway.revoked
    assert not any(token.startswith("accepted:") for token in sent)


@pytest.mark.parametrize("stage", ["data", "end"])
def test_gateway_recomputes_receive_timeout_after_blocked_send(case, transfer, monkeypatch, stage):
    elapsed = [0.0]
    monkeypatch.setattr(
        transfer.extension,
        "time",
        SimpleNamespace(
            monotonic=lambda: time.monotonic() + elapsed[0],
            time_ns=time.time_ns,
            monotonic_ns=time.monotonic_ns,
        ),
    )
    channel = transfer.collector.channel
    original_send, original_receive = channel.send, channel.receive
    checked = []

    def send(token, seq):
        original_send(token, seq)
        if token.startswith(stage + ":"):
            elapsed[0] = 1.0  # A slow send used one second of the original budget.

    def receive(allowed, seq):
        if elapsed[0]:
            remaining = channel.connection.gettimeout()
            checked.append(remaining)
            assert remaining <= transfer.extension.DEADLINE - 1
        return original_receive(allowed, seq)

    monkeypatch.setattr(channel, "send", send)
    monkeypatch.setattr(channel, "receive", receive)
    case.gateway.dispatch()
    assert checked and case.ledger.state.pending is None


@pytest.mark.parametrize("terminal", ["aborted", "closed"])
def test_receipt_replay_rejects_terminal_record_before_ack(case, transfer, monkeypatch, terminal):
    case.gateway.dispatch()
    receipt_rows = [
        json.loads(line) for line in (case.ledger.path / "receipt.jsonl").read_bytes().splitlines()
    ]
    prefix, rows = b"", []
    for line in case.ledger.expected.splitlines(keepends=True):
        prefix += line
        rows.append(json.loads(line))
        if provenance.digest(prefix) == receipt_rows[0]["attempt_prefix_sha256"]:
            break
    # Keep the valid active prefix but terminate its companion before the ACK.
    rows.append(
        {
            **rows[-1],
            "kind": terminal,
            "payload": {"reason": "fixture_abort"} if terminal == "aborted" else {},
            **{k: receipt_rows[0][k] for k in ("utc_ns", "monotonic_ns")},
        }
    )
    monkeypatch.setattr(case.ledger, "expected", _rechain(rows))
    with pytest.raises(ValueError, match="receipt_terminal_precedes_transfer"):
        review(case, transfer)


@pytest.mark.parametrize("terminal", ["aborted", "closed"])
def test_acknowledged_transfer_without_outcome_retains_later_terminal_state(
    case, transfer, monkeypatch, terminal
):
    def lost_outcome(**kwargs):
        raise OSError("outcome_unpersisted")

    monkeypatch.setattr(case.ledger, "outcome", lost_outcome)
    with pytest.raises(OSError, match="outcome_unpersisted"):
        case.gateway.dispatch()
    if terminal == "aborted":
        case.ledger._abort(ValueError("fixture_drift_after_ack"))
    else:
        case.ledger.close()
    report = review(case, transfer)
    assert report["status"] == "acknowledged" and not report["attempt_outcome_recorded"]
    assert case.ledger.state.pending == 0 and case.gateway.revoked

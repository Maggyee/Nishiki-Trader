"""Fixed multi-operation receipts cannot become arbitrary dispatch authority."""

import array
import json
import os
import socket
import threading
from types import SimpleNamespace

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger
from apps.strategies_nautilus.portfolio_joint_egress import classify
from apps.strategies_nautilus.portfolio_observation_plan import request_budget
from tests.ops.test_egress_installed_gateway import load

PIN = "a" * 64


def replay(writer):
    raw = (writer.path / "events.jsonl").read_bytes()
    return ledger.replay(
        raw, expected_sha256=ledger.digest(raw), binding_sha256=PIN, profile=ledger.IPC_PROFILE
    )


@pytest.fixture
def active(tmp_path):
    ipc = load("gateway_joint_ipc")
    base = load("collector_launcher")
    root = tmp_path / "scope"
    root.mkdir(mode=0o700)
    binding = SimpleNamespace(verify=lambda: {"binding_sha256": PIN})
    writer = ledger.AttemptLedger(
        root, binding=binding, binding_sha256=PIN, profile=ledger.IPC_PROFILE
    )
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    peer = (os.getpid(), os.getuid(), os.getgid())
    channels = [base.ControlChannel(s, peer, timeout=1) for s in (left, right)]
    collector = SimpleNamespace(
        channel=channels[0],
        verify=lambda: None,
        cleanup=channels[0].close,
        process=SimpleNamespace(wait=lambda **kwargs: None),
    )
    yield ipc, collector, channels[1], writer
    for c in channels:
        c.close()
    writer.close()


def exercise(active, fault=None, *, on_prepared=None):
    ipc, collector, child, writer = active
    errors = []
    acknowledged = []

    def client():
        try:
            child.receive({"start"}, 0)
            for index, (token, _) in enumerate(ledger.IPC_STEPS):
                if index == 9 and fault in {
                    "repeat",
                    "skip",
                    "order",
                    "endpoint",
                    "oversize",
                    "fd",
                }:
                    if fault == "repeat":
                        child.send(ledger.IPC_STEPS[8][0], 9)
                    elif fault == "skip":
                        child.send(ledger.IPC_STEPS[10][0], 11)
                    elif fault == "order":
                        child.send("order.place", 10)
                    elif fault == "endpoint":
                        child.connection.send(
                            ledger.canonical(
                                {**ledger.ipc_request(index), "endpoint": "https://api.binance.com"}
                            )
                        )
                    elif fault == "oversize":
                        child.connection.send(b"x" * 2048)
                    else:
                        with open(os.devnull) as f:
                            child.connection.sendmsg(
                                [ledger.canonical(ledger.ipc_request(index))],
                                [
                                    (
                                        socket.SOL_SOCKET,
                                        socket.SCM_RIGHTS,
                                        array.array("i", [f.fileno()]),
                                    )
                                ],
                            )
                    return
                child.send(token, index + 1)
                child.receive({"prepared"}, index + 1)
                report = replay(writer)
                assert report["recorded_attempts"] == index + 1
                assert report["pending_attempt"] == index
                acknowledged.append(index)
                if fault == "lost_ack" and index == 9:
                    return
                child.send("received", index + 1)
            child.send("finished", 21)
            child.receive({"close"}, 21)
            child.send("closed", 21)
        except (RuntimeError, OSError) as exc:
            if fault is None:
                errors.append(exc)
        except BaseException as exc:
            errors.append(exc)
        finally:
            child.close()

    thread = threading.Thread(target=client)
    thread.start()
    try:
        if fault is None:
            result = ipc.run_session(collector, writer, ledger, on_prepared=on_prepared)
            assert result["status"] == "joint_ipc_accounting_completed"
            assert not result["transport_dispatch_verified"]
        else:
            with pytest.raises((ValueError, RuntimeError, OSError)):
                ipc.run_session(collector, writer, ledger, on_prepared=on_prepared)
    finally:
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert not errors, errors
    return acknowledged


def test_full_sequence_durable_receipts_and_fixed_budget(active):
    assert exercise(active) == list(range(20))
    report = replay(active[3])
    assert report["recorded_attempts"] == 20
    assert report["pending_attempt"] is None and report["status"] == "closed"
    assert sum(c["documented_weight"] for c in report["counts"]) == 448
    assert sum(c["raw_requests"] for c in report["counts"]) == 16
    assert sum(c["connection_attempts"] for c in report["counts"]) == 2
    assert sum(c["unknown_charge_attempts"] for c in report["counts"]) == 1
    assert report["used_upper_bound"] is None
    assert not report["transport_dispatch_verified"] and not report["network_admitted"]


@pytest.mark.parametrize(
    "fault", ["repeat", "skip", "order", "endpoint", "oversize", "fd", "lost_ack"]
)
def test_bad_ipc_preserves_prior_consumption_and_refuses_next(active, fault):
    acknowledged = exercise(active, fault)
    report = replay(active[3])
    assert len(acknowledged) == (10 if fault == "lost_ack" else 9)
    assert report["recorded_attempts"] == (10 if fault == "lost_ack" else 9)
    assert report["pending_attempt"] == (9 if fault == "lost_ack" else None)
    assert report["status"] == "gap"
    with pytest.raises(FileExistsError):
        ledger.AttemptLedger(
            active[3].root, binding=None, binding_sha256=PIN, profile=ledger.IPC_PROFILE
        )


@pytest.mark.parametrize("kind", ["prepared", "outcome"])
def test_failed_fsync_cannot_acknowledge_or_advance(active, monkeypatch, kind):
    writer = active[3]
    real = os.fsync

    def fail(fd):
        if fd == writer.journal.fd:
            row = json.loads((writer.path / "events.jsonl").read_bytes().splitlines()[-1])
            if row["kind"] == kind and row["payload"]["index"] == 9:
                raise OSError("fixture fsync failure")
        return real(fd)

    monkeypatch.setattr(os, "fsync", fail)
    acknowledged = exercise(active, "disk")
    assert len(acknowledged) == (9 if kind == "prepared" else 10)
    report = replay(writer)
    assert report["recorded_attempts"] == (9 if kind == "prepared" else 10)
    assert report["pending_attempt"] == (None if kind == "prepared" else 9)


def test_midpoint_drift_after_prepare_prevents_receipt(active):
    def drift(index):
        if index == 9:
            active[3].binding.verify = lambda: {"binding_sha256": "b" * 64}

    assert exercise(active, "drift", on_prepared=drift) == list(range(9))
    assert replay(active[3])["pending_attempt"] == 9


def test_profile_schedule_matches_existing_local_collector_budget():
    budget = request_budget(["BNBUSDT", "BTCUSDT", "ETHUSDT"])
    rest = [{"kind": "rest", **r} for r in budget["rest_requests"]]
    ws = [{"kind": "ws", **r} for r in budget["ws_api_operations"]]
    plan = [
        rest[0],
        *ws[:2],
        *rest[1:7],
        {"kind": "market_connection", "weight": 0},
        *rest[7:],
        ws[2],
    ]
    assert tuple(classify(op) for op in plan) == tuple(op for _, op in ledger.IPC_STEPS)


@pytest.mark.parametrize("damage", ["operation", "caller", "packet", "sequence", "extra"])
def test_ledger_rejects_rehashed_semantic_substitution(active, damage):
    exercise(active)
    writer = active[3]
    rows = [json.loads(line) for line in (writer.path / "events.jsonl").read_bytes().splitlines()]
    row = next(r for r in rows if r["kind"] == "prepared")
    if damage == "operation":
        row["payload"]["operation"] = "exchange_info"
    elif damage == "caller":
        row["payload"]["caller"] = "host"
    elif damage == "packet":
        row["payload"]["request_sha256"] = "0" * 64
    elif damage == "sequence":
        row["payload"]["request_sha256"] = ledger.digest(
            ledger.canonical({"v": 1, "op": "clock_initial", "seq": 2})
        )
    else:
        row["payload"]["joint_prefix_sha256"] = "0" * 64
    raw = b""
    previous = None
    for row in rows:
        row["previous_sha256"] = previous
        line = ledger.canonical(row) + b"\n"
        previous = ledger.digest(line)
        raw += line
    with pytest.raises(ValueError):
        ledger.replay(
            raw, expected_sha256=ledger.digest(raw), binding_sha256=PIN, profile=ledger.IPC_PROFILE
        )


@pytest.mark.parametrize("profile", [ledger.PROFILE, ledger.JOINT_PROFILE])
def test_older_profile_cannot_consume_new_ipc_records(active, profile):
    exercise(active)
    raw = (active[3].path / "events.jsonl").read_bytes()
    with pytest.raises(ValueError, match="profile_or_binding"):
        ledger.replay(raw, expected_sha256=ledger.digest(raw), binding_sha256=PIN, profile=profile)


@pytest.mark.parametrize("index", [-1, 20, True, 1.0])
def test_scope_index_is_bounded(index):
    with pytest.raises(ValueError):
        ledger.ipc_request(index)


def test_ordinary_checkout_entry_has_no_joint_host_mode(monkeypatch):
    entry = load("installed_gateway")
    monkeypatch.setattr(entry.sys, "argv", ["gateway", "--joint-ipc-fixture"])
    monkeypatch.setattr(entry.sys, "flags", SimpleNamespace(isolated=True))
    monkeypatch.setattr(entry, "installation", lambda: pytest.fail("installation opened"))
    with pytest.raises(ValueError, match="fixed_installed"):
        entry.main()


def test_deadline_after_preparation_retains_attempt_without_receipt(active, monkeypatch):
    ipc = active[0]
    late = ipc.time.monotonic() + 31

    def expire(index):
        if index == 9:
            monkeypatch.setattr(ipc.time, "monotonic", lambda: late)

    assert exercise(active, "deadline", on_prepared=expire) == list(range(9))
    assert replay(active[3])["pending_attempt"] == 9


def test_repeated_session_cannot_reopen_closed_ledger(active):
    exercise(active)
    writer = active[3]
    raw = (writer.path / "events.jsonl").read_bytes()
    with pytest.raises(ValueError, match="no_retry"):
        active[0].run_session(active[1], writer, ledger)
    assert (writer.path / "events.jsonl").read_bytes() == raw


@pytest.mark.parametrize("fault", [None, "lost_ack"])
def test_ipc_cli_only_replays_selected_bytes(active, monkeypatch, fault):
    from apps.ops.portfolio_egress_ledger import main

    exercise(active, fault)

    def blocked(*args, **kwargs):
        pytest.fail("replay attempted network or DNS")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    path = active[3].path / "events.jsonl"
    raw = path.read_bytes()
    output = active[3].root / "report.json"
    assert (
        main(
            [
                "--ipc-profile",
                "--archive",
                str(path),
                "--archive-sha256",
                ledger.digest(raw),
                "--binding-sha256",
                PIN,
                "--report",
                str(output),
            ]
        )
        == 2
    )
    assert json.loads(output.read_bytes()) == replay(active[3])
    assert path.read_bytes() == raw

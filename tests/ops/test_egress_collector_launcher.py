"""Kernel credential checks and finite launcher failure behavior, without venue I/O."""

import array
import importlib.util
import json
import os
import socket
from pathlib import Path
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/collector_launcher.py"


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location("collector_launcher_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def channel(launcher):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    result = launcher.ControlChannel(left, (os.getpid(), os.getuid(), os.getgid()), timeout=0.1)
    try:
        yield result, right
    finally:
        result.close()
        right.close()


def packet(launcher, operation="observe", sequence=1):
    return launcher.canonical({"v": 1, "op": operation, "seq": sequence})


def test_actual_kernel_credentials_admit_selected_sender(launcher, channel):
    receiver, sender = channel
    sender.send(packet(launcher))
    assert receiver.receive({"observe"}, 1) == "observe"
    assert not receiver.failed


def test_same_uid_different_process_is_not_the_selected_sender(launcher, channel):
    receiver, sender = channel
    pid = os.fork()
    if pid == 0:
        receiver.connection.close()
        sender.send(packet(launcher))
        os._exit(0)
    try:
        with pytest.raises(RuntimeError, match="credentials"):
            receiver.receive({"observe"}, 1)
        assert receiver.failed
        with pytest.raises(RuntimeError, match="terminal"):
            receiver.receive({"observe"}, 1)
    finally:
        os.waitpid(pid, 0)


@pytest.mark.parametrize("peer_field", [0, 1, 2])
def test_kernel_pid_uid_and_gid_must_all_match(launcher, channel, peer_field):
    receiver, sender = channel
    peer = list(receiver.peer)
    peer[peer_field] += 1
    receiver.peer = tuple(peer)
    sender.send(packet(launcher))
    with pytest.raises(RuntimeError, match="credentials"):
        receiver.receive({"observe"}, 1)


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "pid_claim",
        "bool_seq",
        "bool_version",
        "duplicate_keys",
        "unknown",
        "reordered",
        "truncated",
        "bad_json",
        "list",
        "old_seq",
    ],
)
def test_protocol_rejects_noncanonical_or_unexpected_requests(launcher, channel, damage):
    receiver, sender = channel
    value = {"v": 1, "op": "observe", "seq": 1}
    if damage in {"extra", "pid_claim"}:
        value["path" if damage == "extra" else "pid"] = os.getpid()
    elif damage == "bool_seq":
        value["seq"] = True
    elif damage == "bool_version":
        value["v"] = True
    elif damage == "unknown":
        value["op"] = "activate_window"
    elif damage == "old_seq":
        value["seq"] = 0
    raw = launcher.canonical(value)
    if damage == "duplicate_keys":
        raw = b'{"op":"observe","seq":1,"v":1,"v":1}'
    elif damage == "reordered":
        raw = json.dumps(value).encode()
    elif damage == "truncated":
        raw = b"x" * (launcher.PACKET_LIMIT + 1)
    elif damage == "bad_json":
        raw = b"{"
    elif damage == "list":
        raw = b"[]"
    sender.send(raw)
    with pytest.raises((RuntimeError, ValueError)):
        receiver.receive({"observe"}, 1)
    assert receiver.failed


@pytest.mark.parametrize("count", [1, 32])
def test_received_descriptors_are_rejected_and_closed(launcher, channel, count):
    receiver, sender = channel
    fd = os.open("/dev/null", os.O_RDONLY)
    try:
        before = len(list(Path("/proc/self/fd").iterdir()))
        sender.sendmsg(
            [packet(launcher)],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd] * count))],
        )
        with pytest.raises(RuntimeError, match="credentials"):
            receiver.receive({"observe"}, 1)
        # The receiver socket itself also closed; no received FD can survive.
        assert len(list(Path("/proc/self/fd").iterdir())) == before - 1
    finally:
        os.close(fd)


def test_receive_timeout_is_terminal(channel):
    receiver, _sender = channel
    with pytest.raises(TimeoutError):
        receiver.receive({"observe"}, 1)
    assert receiver.failed
    with pytest.raises(RuntimeError, match="terminal"):
        receiver.send("observe", 1)


def test_peer_eof_is_terminal(channel):
    receiver, sender = channel
    sender.close()
    with pytest.raises(RuntimeError, match="credentials"):
        receiver.receive({"observe"}, 1)
    assert receiver.failed


def test_duplicate_observation_cannot_become_close(launcher, channel):
    receiver, sender = channel
    sender.send(packet(launcher))
    assert receiver.receive({"observe"}, 1) == "observe"
    sender.send(packet(launcher))
    with pytest.raises(RuntimeError, match="protocol"):
        receiver.receive({"close"}, 2)


@pytest.mark.parametrize("root,argv", [(True, ["fixture"]), (False, ["fixture", "--execute"])])
def test_public_cli_refuses_root_and_arguments_before_processes(launcher, monkeypatch, root, argv):
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 0 if root else 998)
    monkeypatch.setattr(launcher.sys, "argv", argv)
    spawn = Mock(side_effect=AssertionError("must not launch"))
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    assert launcher.main() == 2
    spawn.assert_not_called()


@pytest.fixture
def controller(launcher):
    item = object.__new__(launcher.FixtureCollector)
    item.owner_pid = os.getpid()
    item.lock = launcher.threading.Lock()
    item.stop = launcher.threading.Event()
    item.used = item.closed = False
    item.verify = Mock()
    item.channel = Mock()
    item.cleanup = Mock()
    return item


def test_one_observation_and_no_repeat(controller):
    assert controller.observe() == {"ok": True}
    with pytest.raises(RuntimeError, match="consumed"):
        controller.observe()
    controller.channel.send.assert_called_once_with("observe", 1)


@pytest.mark.parametrize("stage", ["before", "send", "receive", "after"])
def test_uncertain_observation_halts_and_cleans_without_retry(controller, stage):
    if stage == "before":
        controller.verify.side_effect = RuntimeError("changed")
    elif stage == "after":
        controller.verify.side_effect = [None, RuntimeError("changed")]
    else:
        getattr(controller.channel, stage).side_effect = TimeoutError("uncertain")
    with pytest.raises((RuntimeError, TimeoutError)):
        controller.observe()
    controller.cleanup.assert_called_once()
    assert controller.used and controller.stop.is_set()
    with pytest.raises(RuntimeError, match="consumed"):
        controller.observe()
    assert controller.channel.send.call_count == int(stage != "before")


def test_fork_inherited_launcher_refuses_before_lock(controller):
    controller.owner_pid += 1
    with pytest.raises(RuntimeError, match="foreign_owner"):
        controller.observe()
    with pytest.raises(RuntimeError, match="foreign_owner"):
        controller.close()
    controller.verify.assert_not_called()


def test_pidfd_failure_reaps_child_and_closes_socket(launcher, monkeypatch):
    process = Mock(pid=12345)
    monkeypatch.setattr(launcher.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(launcher.os, "pidfd_open", Mock(side_effect=OSError("unsupported")))
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises(OSError, match="unsupported"):
        launcher.FixtureCollector("pass", Mock())
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=2)
    assert len(list(Path("/proc/self/fd").iterdir())) == before

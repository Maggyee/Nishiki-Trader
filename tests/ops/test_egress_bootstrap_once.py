"""Bounded privileged-runner channel and durable one-shot consumption tests."""

import array
import importlib.util
import json
import os
import socket
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/bootstrap_once.py"


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location("bootstrap_runner_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def channel(runner):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    receiver = runner.Channel(left, (os.getpid(), os.getuid(), os.getgid()))
    sender = runner.Channel(right, (os.getpid(), os.getuid(), os.getgid()))
    try:
        yield receiver, sender
    finally:
        left.close()
        right.close()


def test_kernel_credentials_and_canonical_frame(channel):
    receiver, sender = channel
    sender.send("ready", 0)
    assert receiver.receive() == {"kind": "ready", "seq": 0, "data": None}


@pytest.mark.parametrize("field", [0, 1, 2])
def test_wrong_kernel_identity_rejected(channel, field):
    receiver, sender = channel
    peer = list(receiver.peer)
    peer[field] += 1
    receiver.peer = tuple(peer)
    sender.send("ready", 0)
    with pytest.raises(ValueError, match="peer"):
        receiver.receive()


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"[]",
        b'{"data":null,"kind":"ready","seq":true}',
        b'{"data":null,"kind":"ready","seq":0,"extra":1}',
        b" " * 16385,
    ],
)
def test_invalid_or_truncated_frame_rejected(channel, raw):
    receiver, sender = channel
    sender.sock.send(raw)
    with pytest.raises(ValueError):
        receiver.receive()


def test_received_file_descriptor_is_closed(channel):
    receiver, sender = channel
    fd = os.open("/dev/null", os.O_RDONLY)
    try:
        before = len(list(Path("/proc/self/fd").iterdir()))
        sender.sock.sendmsg(
            [b"{}"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))]
        )
        with pytest.raises(ValueError):
            receiver.receive()
        assert len(list(Path("/proc/self/fd").iterdir())) == before
    finally:
        os.close(fd)


def test_scope_is_consumed_before_any_network_and_cannot_reopen(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "scope")
    journal = runner.Journal({"source_commit": "fixture"}, b"{}")
    journal.append("tcp_prepared")
    journal.close()
    original = (runner.ROOT / "events.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        runner.Journal({"source_commit": "fixture"}, b"{}")
    rows = [json.loads(line) for line in original.splitlines()]
    assert [row["kind"] for row in rows] == ["scope_consumed", "tcp_prepared"]
    assert rows[1]["previous_sha256"] == runner.digest(original.splitlines(keepends=True)[0])
    assert (runner.ROOT / "events.jsonl").read_bytes() == original


def test_response_bytes_are_durable_before_chunk_receipt(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "scope")
    journal = runner.Journal({"source_commit": "fixture"}, b"{}")
    original = journal.append

    def append(kind, **fields):
        if kind == "response_chunk":
            assert (runner.ROOT / "response.bin").read_bytes() == b"original"
        original(kind, **fields)

    journal.append = append
    try:
        journal.chunk(b"original")
    finally:
        journal.close()


def test_failed_scope_fsync_still_blocks_reinitialization(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "scope")

    def fail(path):
        raise OSError("fsync")

    monkeypatch.setattr(runner, "sync_dir", fail)
    with pytest.raises(OSError):
        runner.Journal({"source_commit": "fixture"}, b"{}")
    with pytest.raises(FileExistsError):
        runner.Journal({"source_commit": "fixture"}, b"{}")


def test_incident_reserve_survives_response_budget_exhaustion(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "scope")
    monkeypatch.setattr(runner, "MAX_ARCHIVE", 8192)
    journal = runner.Journal({"source_commit": "fixture"}, b"{}")
    try:
        with pytest.raises(ValueError, match="limit"):
            journal.chunk(b"x" * 4096)
        journal.append("failed", error_type="ValueError")
        journal.append("cleanup", errors=[])
    finally:
        journal.close()
    assert (
        json.loads((runner.ROOT / "events.jsonl").read_bytes().splitlines()[-1])["kind"]
        == "cleanup"
    )

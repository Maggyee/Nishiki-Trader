"""Fail-before-mutation and cleanup checks for the standalone namespace fixture."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/selftest.py"


@pytest.fixture
def fixture():
    spec = importlib.util.spec_from_file_location("egress_fixture_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("inherited", ["user", "net", "mnt", "pid"])
def test_inherited_namespace_fails_before_commands(fixture, monkeypatch, inherited):
    original = dict.fromkeys(fixture.NAMESPACES, "old")
    current = dict.fromkeys(fixture.NAMESPACES, "new")
    current[inherited] = "old"
    monkeypatch.setattr(fixture, "namespace_ids", lambda: current)
    runner = Mock(side_effect=AssertionError("No command should run"))
    monkeypatch.setattr(fixture, "run", runner)
    with pytest.raises(RuntimeError, match="inherited"):
        fixture.require_isolation(original)
    runner.assert_not_called()


@pytest.mark.parametrize("contamination", ["interface", "ipv4_route", "ipv6_route", "rules"])
def test_nonempty_namespace_fails_using_only_reads(fixture, monkeypatch, contamination):
    original = dict.fromkeys(fixture.NAMESPACES, "old")
    monkeypatch.setattr(fixture, "namespace_ids", lambda: dict.fromkeys(fixture.NAMESPACES, "new"))
    calls = []

    def read_only(*args):
        calls.append(args)
        if args == (fixture.IP, "-j", "link", "show"):
            return json.dumps([{"ifname": "physical" if contamination == "interface" else "lo"}])
        for family, name in (("-4", "ipv4_route"), ("-6", "ipv6_route")):
            if args == (fixture.IP, family, "-j", "route", "show", "table", "all"):
                return json.dumps([{"dst": "default"}] if contamination == name else [])
        assert args == (fixture.NFT, "-j", "list", "ruleset")
        return json.dumps({"nftables": [{"table": {}}] if contamination == "rules" else []})

    monkeypatch.setattr(fixture, "run", read_only)
    with pytest.raises(RuntimeError, match="Fresh fixture namespace"):
        fixture.require_isolation(original)
    assert len(calls) <= 4


@pytest.mark.parametrize("root,argv", [(True, ["fixture"]), (False, ["fixture", "--worker"])])
def test_public_entry_refuses_host_root_or_arguments(fixture, monkeypatch, root, argv):
    monkeypatch.setattr(fixture.os, "geteuid", lambda: 0 if root else 998)
    monkeypatch.setattr(fixture.sys, "argv", argv)
    popen = Mock(side_effect=AssertionError("No process should start"))
    monkeypatch.setattr(fixture.subprocess, "Popen", popen)
    assert fixture.main() == 2
    popen.assert_not_called()


def test_cleanup_kills_child_that_ignores_shutdown(fixture):
    child = object.__new__(fixture.Child)
    child.process = Mock()
    child.process.wait.side_effect = [subprocess.TimeoutExpired("fixture", 3), 0]
    child.stop()
    child.process.stdin.close.assert_called_once()
    child.process.kill.assert_called_once()
    assert child.process.wait.call_count == 2


def test_parent_timeout_kills_entire_fixture_process_group(fixture, monkeypatch):
    monkeypatch.setattr(fixture.os, "geteuid", lambda: 998)
    monkeypatch.setattr(fixture.sys, "argv", ["fixture"])
    monkeypatch.setattr(fixture, "namespace_ids", lambda: dict.fromkeys(fixture.NAMESPACES, "old"))
    process = Mock(pid=12345)
    process.communicate.side_effect = [subprocess.TimeoutExpired("fixture", 100), ("", "")]
    popen = Mock(return_value=process)
    killpg = Mock()
    monkeypatch.setattr(fixture.subprocess, "Popen", popen)
    monkeypatch.setattr(fixture.os, "killpg", killpg)
    with pytest.raises(subprocess.TimeoutExpired):
        fixture.main()
    killpg.assert_called_once_with(12345, fixture.signal.SIGKILL)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert popen.call_args.kwargs["env"] == fixture.ENV


def test_bad_isolation_stops_worker_before_network_mutation(fixture, monkeypatch):
    monkeypatch.setattr(fixture.signal, "signal", Mock())
    monkeypatch.setattr(fixture.signal, "alarm", Mock())
    monkeypatch.setattr(
        fixture, "require_isolation", Mock(side_effect=RuntimeError("not isolated"))
    )
    runner = Mock(side_effect=AssertionError("No mutation allowed"))
    child = Mock(side_effect=AssertionError("No child allowed"))
    monkeypatch.setattr(fixture, "run", runner)
    monkeypatch.setattr(fixture, "Child", child)
    with pytest.raises(RuntimeError, match="not isolated"):
        fixture.worker({}, "")
    runner.assert_not_called()
    child.assert_not_called()


@pytest.fixture
def guard_case(fixture, tmp_path):
    selected = {"namespace": "fixture", "route": "fixture-route", "rules": "fixture-rules"}
    actor = Mock()
    actor.request.return_value = {"ok": True}
    guard = fixture.FixtureDispatchGuard(
        tmp_path / "attempts.jsonl", selected=selected, observe=lambda: selected, actor=actor
    )
    try:
        yield guard, actor, selected
    finally:
        guard.close()


def test_preparation_is_synced_before_transport(fixture, guard_case, monkeypatch):
    guard, actor, _selected = guard_case
    sync = Mock(wraps=os.fsync)
    monkeypatch.setattr(fixture.os, "fsync", sync)

    def send(_request):
        assert sync.call_count == 1
        rows = [json.loads(row) for row in guard.path.read_bytes().splitlines()]
        assert [row["kind"] for row in rows] == ["prepared"]
        assert rows[0]["attempt"] == 1
        return {"ok": True}

    actor.request.side_effect = send
    guard.dispatch()
    assert sync.call_count == 2


@pytest.mark.parametrize("field", ["namespace", "route", "rules"])
def test_identity_loss_sticks_after_restoration(guard_case, field):
    guard, actor, selected = guard_case
    guard.dispatch()
    original = selected[field]
    selected[field] = "changed"
    with pytest.raises(RuntimeError, match="identity_or_guard_changed"):
        guard.dispatch()
    selected[field] = original
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    assert actor.request.call_count == guard.attempts == 1


@pytest.mark.parametrize("damage", ["truncate", "rewrite", "replace", "unlink"])
def test_audit_loss_prevents_next_send(guard_case, damage):
    guard, actor, _selected = guard_case
    guard.dispatch()
    if damage == "truncate":
        guard.path.write_bytes(b"")
    elif damage == "rewrite":
        raw = guard.path.read_bytes()
        guard.path.write_bytes(raw.replace(b"prepared", b"modified"))
    elif damage == "replace":
        other = guard.path.with_suffix(".replacement")
        other.write_bytes(guard.path.read_bytes())
        other.replace(guard.path)
    else:
        guard.path.unlink()
    with pytest.raises((RuntimeError, OSError)):
        guard.dispatch()
    assert guard.halted and guard.attempts == actor.request.call_count == 1


@pytest.mark.parametrize("stage", ["prepare", "outcome"])
def test_fsync_failure_blocks_reuse_and_preserves_attempt(fixture, guard_case, monkeypatch, stage):
    guard, actor, _selected = guard_case
    real_sync = os.fsync
    count = 0

    def sync(fd):
        nonlocal count
        count += 1
        if count == (1 if stage == "prepare" else 2):
            raise OSError("fixture disk failure")
        real_sync(fd)

    monkeypatch.setattr(fixture.os, "fsync", sync)
    with pytest.raises(OSError, match="disk failure"):
        guard.dispatch()
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    assert guard.attempts == 1
    assert actor.request.call_count == (0 if stage == "prepare" else 1)


@pytest.mark.parametrize("change", ["identity", "audit"])
def test_change_after_prepare_refuses_transport(guard_case, change):
    guard, actor, selected = guard_case
    count = 0

    def observe():
        nonlocal count
        count += 1
        if count == 2:
            if change == "identity":
                selected["route"] = "changed"
            else:
                os.ftruncate(guard.fd, 0)
        return selected

    guard.observe = observe
    with pytest.raises(RuntimeError):
        guard.dispatch()
    actor.request.assert_not_called()
    assert guard.attempts == 1 and guard.halted


@pytest.mark.parametrize("failure", ["failed", "uncertain", "identity_after_send"])
def test_failure_after_send_never_refunds_or_retries(guard_case, failure):
    guard, actor, selected = guard_case

    def send(_request):
        if failure == "uncertain":
            raise TimeoutError("uncertain fixture outcome")
        if failure == "identity_after_send":
            selected["rules"] = "changed"
            return {"ok": True}
        return {"ok": False}

    actor.request.side_effect = send
    with pytest.raises((RuntimeError, TimeoutError)):
        guard.dispatch()
    assert guard.attempts == actor.request.call_count == 1
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    rows = [json.loads(row) for row in guard.path.read_bytes().splitlines()]
    assert [row["kind"] for row in rows] == (
        ["prepared", "failed"] if failure == "failed" else ["prepared"]
    )


def test_concurrent_dispatch_is_serialized_and_bounded(guard_case):
    guard, actor, _selected = guard_case
    entered = threading.Event()
    release = threading.Event()

    def send(_request):
        entered.set()
        assert release.wait(timeout=2)
        return {"ok": True}

    actor.request.side_effect = send
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(guard.dispatch)
        assert entered.wait(timeout=2)
        second = executor.submit(guard.dispatch)
        try:
            assert not second.done()
            assert actor.request.call_count == 1
        finally:
            release.set()
        assert first.result(timeout=2) == second.result(timeout=2) == {"ok": True}
    rows = [json.loads(row) for row in guard.path.read_bytes().splitlines()]
    assert [(row["kind"], row["attempt"]) for row in rows] == [
        ("prepared", 1),
        ("succeeded", 1),
        ("prepared", 2),
        ("succeeded", 2),
    ]
    guard.dispatch()
    guard.dispatch()
    with pytest.raises(RuntimeError, match="attempt_bound"):
        guard.dispatch()
    assert actor.request.call_count == guard.attempts == 4


def test_abrupt_process_exit_preserves_prepared_no_reopen(fixture, tmp_path):
    path = tmp_path / "crashed.jsonl"
    code = (
        "import os, runpy\nfrom pathlib import Path\n"
        f"scope = runpy.run_path({str(SOURCE)!r}, run_name='fixture_test')\n"
        "class ExitDuringSend:\n"
        "    def request(self, request): os._exit(17)\n"
        f"guard = scope['FixtureDispatchGuard'](Path({str(path)!r}), "
        "selected={}, observe=lambda: {}, actor=ExitDuringSend())\n"
        "guard.dispatch()\n"
    )
    result = subprocess.run(["/usr/bin/python3", "-I", "-c", code], timeout=5, check=False)
    assert result.returncode == 17
    assert [json.loads(row)["kind"] for row in path.read_bytes().splitlines()] == ["prepared"]
    with pytest.raises(FileExistsError):
        fixture.FixtureDispatchGuard(path, selected={}, observe=lambda: {}, actor=Mock())


@pytest.fixture
def controlled_case(fixture, tmp_path):
    selected = {"rules": "fixture"}
    actor = Mock()
    actor.request.return_value = {"ok": True}
    revoke = Mock()
    guard = fixture.ControlledFixtureGuard(
        tmp_path / "controlled.jsonl",
        selected=selected,
        observe=lambda: selected,
        actor=actor,
        revoke=revoke,
    )
    try:
        yield guard, actor, revoke
    finally:
        try:
            os.fstat(guard.fd)
        except OSError:
            pass
        else:
            fixture.FixtureDispatchGuard.close(guard)


def test_managed_shutdown_waits_and_rejects_queued_send(controlled_case):
    guard, actor, revoke = controlled_case
    entered, release = threading.Event(), threading.Event()

    def send(_request):
        entered.set()
        assert release.wait(timeout=2)
        revoke.assert_not_called()
        return {"ok": True}

    actor.request.side_effect = send
    with ThreadPoolExecutor(max_workers=3) as pool:
        sending = pool.submit(guard.dispatch)
        try:
            assert entered.wait(timeout=2)
            stopping = pool.submit(guard.shutdown)
            assert guard.stop_requested.wait(timeout=2)
            queued = pool.submit(guard.dispatch)
            revoke.assert_not_called()
            assert not stopping.done()
        finally:
            release.set()
        assert sending.result(timeout=2)["ok"]
        stopping.result(timeout=2)
        with pytest.raises(RuntimeError, match="dispatch_halted"):
            queued.result(timeout=2)
    assert actor.request.call_count == guard.attempts == 1
    revoke.assert_called_once()
    assert [json.loads(row)["kind"] for row in guard.path.read_bytes().splitlines()] == [
        "prepared",
        "succeeded",
        "stop_requested",
        "revoked",
    ]


def test_shutdown_before_first_request_does_not_consume_attempt(controlled_case):
    guard, actor, revoke = controlled_case
    guard.shutdown()
    guard.shutdown()
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    actor.request.assert_not_called()
    revoke.assert_called_once()
    assert guard.attempts == 0 and guard.revoked


@pytest.mark.parametrize("damage", ["audit_gap", "fsync", "transport"])
def test_dispatch_failure_revokes_even_if_audit_is_broken(
    fixture, controlled_case, monkeypatch, damage
):
    guard, actor, revoke = controlled_case
    if damage == "audit_gap":
        guard.path.write_bytes(b"unexpected")
    elif damage == "fsync":
        monkeypatch.setattr(fixture.os, "fsync", Mock(side_effect=OSError("fixture disk error")))
    else:
        actor.request.side_effect = TimeoutError("uncertain")
    with pytest.raises((RuntimeError, OSError)):
        guard.dispatch()
    assert guard.halted and guard.revoked
    revoke.assert_called_once()
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    assert actor.request.call_count == (1 if damage == "transport" else 0)


def test_revocation_failure_never_reports_success_or_retries(controlled_case):
    guard, actor, revoke = controlled_case
    revoke.side_effect = OSError("kernel refused change")
    with pytest.raises(OSError, match="kernel refused"):
        guard.shutdown()
    assert guard.halted and not guard.revoked
    with pytest.raises(RuntimeError, match="revocation_incomplete"):
        guard.shutdown()
    with pytest.raises(RuntimeError, match="dispatch_halted"):
        guard.dispatch()
    revoke.assert_called_once()
    actor.request.assert_not_called()
    assert [json.loads(row)["kind"] for row in guard.path.read_bytes().splitlines()] == [
        "stop_requested"
    ]


def test_close_revokes_and_closes_descriptor(controlled_case):
    guard, actor, revoke = controlled_case
    guard.close()
    guard.close()
    revoke.assert_called_once()
    actor.request.assert_not_called()
    with pytest.raises(OSError):
        os.fstat(guard.fd)


@pytest.mark.parametrize("operation", ["dispatch", "shutdown", "close"])
def test_inherited_controller_refused_before_acquiring_lock(controlled_case, operation):
    guard, actor, revoke = controlled_case
    original_owner, original_lock = guard.owner_pid, guard.lock
    guard.owner_pid += 10000
    guard.lock = Mock()
    try:
        with pytest.raises(RuntimeError, match="controller_process_changed"):
            getattr(guard, operation)()
        guard.lock.assert_not_called()
        actor.request.assert_not_called()
        revoke.assert_not_called()
    finally:
        guard.owner_pid, guard.lock = original_owner, original_lock

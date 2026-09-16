"""Fail-before-mutation and cleanup checks for the standalone namespace fixture."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
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


@pytest.fixture
def persistent_case(fixture, tmp_path):
    selected = {"rules": "fixture"}
    actor, revoke = Mock(), Mock()
    actor.request.return_value = {"ok": True}
    guard = fixture.PersistentFixtureGuard(
        tmp_path, selected=selected, observe=lambda: selected, actor=actor, revoke=revoke
    )
    try:
        yield guard, actor, revoke, selected
    finally:
        if not guard.closed:
            with suppress(RuntimeError, OSError):
                guard.close()


def review_persistent(fixture, guard, selected):
    raw = guard.path.read_bytes()
    return fixture.review_fixture_journal(
        raw, selected=selected, expected_sha256=fixture.hashlib.sha256(raw).hexdigest()
    )


def test_persistent_scope_and_journal_synced_before_send(fixture, tmp_path, monkeypatch):
    import stat

    syncs = []
    real_sync = os.fsync

    def sync(fd):
        syncs.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        real_sync(fd)

    monkeypatch.setattr(fixture.os, "fsync", sync)
    actor = Mock()

    def send(_request):
        assert syncs == ["directory", "directory", "file", "file"]
        assert review_persistent(fixture, guard, {})["uncertain_attempt"] == 1
        return {"ok": True}

    actor.request.side_effect = send
    guard = fixture.PersistentFixtureGuard(
        tmp_path, selected={}, observe=lambda: {}, actor=actor, revoke=Mock()
    )
    guard.dispatch()
    guard.close()
    report = review_persistent(fixture, guard, {})
    assert report["recorded_preparations"] == 1
    assert report["revocation_recorded"]
    assert not report["restart_allowed"] and not report["capture_admitted"]


@pytest.mark.parametrize("sync_number", [1, 2, 3])
def test_failed_persistent_initialization_consumes_scope(
    fixture, tmp_path, monkeypatch, sync_number
):
    real_sync = os.fsync
    calls = 0

    def sync(fd):
        nonlocal calls
        calls += 1
        if calls == sync_number:
            raise OSError("disk unavailable")
        real_sync(fd)

    actor = Mock()
    monkeypatch.setattr(fixture.os, "fsync", sync)
    with pytest.raises(OSError, match="disk unavailable"):
        fixture.PersistentFixtureGuard(
            tmp_path, selected={}, observe=lambda: {}, actor=actor, revoke=Mock()
        )
    monkeypatch.setattr(fixture.os, "fsync", real_sync)
    with pytest.raises(FileExistsError):
        fixture.PersistentFixtureGuard(
            tmp_path, selected={}, observe=lambda: {}, actor=actor, revoke=Mock()
        )
    actor.request.assert_not_called()


@pytest.mark.parametrize("damage", ["root_replace", "scope_replace", "permissions", "hardlink"])
def test_persistent_storage_loss_revokes_before_send(persistent_case, damage):
    guard, actor, revoke, _ = persistent_case
    if damage == "root_replace":
        moved = guard.root.with_name(guard.root.name + "-old")
        guard.root.rename(moved)
        guard.root.mkdir(mode=0o700)
    elif damage == "scope_replace":
        guard.path.parent.rename(guard.path.parent.with_name("moved"))
        guard.path.parent.mkdir(mode=0o700)
    elif damage == "permissions":
        guard.root.chmod(0o755)
    else:
        os.link(guard.path, guard.path.with_name("alias"))
    with pytest.raises((RuntimeError, OSError)):
        guard.dispatch()
    actor.request.assert_not_called()
    revoke.assert_called_once()
    assert guard.halted and guard.revoked


@pytest.mark.parametrize("damage", ["symlink", "public"])
def test_persistent_requires_private_root(fixture, tmp_path, damage):
    root = tmp_path
    if damage == "symlink":
        root = tmp_path / "link"
        root.symlink_to(tmp_path, target_is_directory=True)
    else:
        root.chmod(0o755)
    with pytest.raises((RuntimeError, OSError)):
        fixture.PersistentFixtureGuard(
            root, selected={}, observe=lambda: {}, actor=Mock(), revoke=Mock()
        )
    assert not (tmp_path / fixture.PersistentFixtureGuard.SCOPE).exists()


def test_concurrent_initializers_have_only_one_owner(fixture, tmp_path):
    def create():
        try:
            return fixture.PersistentFixtureGuard(
                tmp_path, selected={}, observe=lambda: {}, actor=Mock(), revoke=Mock()
            )
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        guards = list(pool.map(lambda _: create(), range(2)))
    owners = [guard for guard in guards if guard is not None]
    assert len(owners) == 1
    owners[0].close()


@pytest.mark.parametrize("stage", ["scope", "activated", "prepared", "succeeded", "revoked"])
def test_disk_crash_two_fresh_replays_and_restart_refusal(fixture, tmp_path, stage):
    # /tmp is ext4 on the acceptance host, not the namespace harness's private tmpfs.
    loader = (
        "import importlib.util, pathlib, os, json, hashlib\n"
        f"spec = importlib.util.spec_from_file_location('fixture', {str(SOURCE)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"root = pathlib.Path({str(tmp_path)!r})\n"
    )
    actor = "class Actor:\n    def request(self, request):\n" + (
        "        os._exit(71)\n" if stage == "prepared" else "        return {'ok': True}\n"
    )
    setup = ""
    if stage == "scope":
        setup = "m.os.fsync = lambda fd: os._exit(71)\n"
    script = (
        loader
        + actor
        + setup
        + (
            "g = m.PersistentFixtureGuard(root, selected={}, observe=lambda: {}, "
            "actor=Actor(), revoke=lambda: None)\n"
        )
    )
    if stage not in ("scope", "activated"):
        script += "g.dispatch()\n"
    if stage == "revoked":
        script += "g.close()\n"
    script += "os._exit(71)\n"
    result = subprocess.run(["/usr/bin/python3", "-I", "-c", script], timeout=5)
    assert result.returncode == 71
    path = tmp_path / fixture.PersistentFixtureGuard.SCOPE / "attempts.jsonl"
    before = path.read_bytes() if path.exists() else None
    if stage != "scope":
        digest = fixture.hashlib.sha256(before).hexdigest()
        replay = loader + (
            f"raw = (root / m.PersistentFixtureGuard.SCOPE / 'attempts.jsonl').read_bytes()\n"
            f"print(json.dumps(m.review_fixture_journal(raw, selected={{}}, "
            f"expected_sha256={digest!r}), sort_keys=True))\n"
        )
        outputs = [
            subprocess.check_output(["/usr/bin/python3", "-I", "-c", replay], timeout=5)
            for _ in range(2)
        ]
        assert outputs[0] == outputs[1]
        report = json.loads(outputs[0])
        assert report["recorded_preparations"] == (0 if stage == "activated" else 1)
        assert report["uncertain_attempt"] == (1 if stage == "prepared" else None)
        assert report["revocation_recorded"] == (stage == "revoked")
        assert not report["restart_allowed"]
    restart = (
        loader
        + actor
        + (
            "try:\n"
            "    m.PersistentFixtureGuard(root, selected={}, observe=lambda: {}, "
            "actor=Actor(), revoke=lambda: None)\n"
            "except FileExistsError:\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit('scope unexpectedly reopened')\n"
        )
    )
    subprocess.run(["/usr/bin/python3", "-I", "-c", restart], timeout=5, check=True)
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize(
    "damage",
    [
        "hash",
        "identity",
        "partial",
        "result_without_prepare",
        "duplicate",
        "clock",
        "attempt",
        "post_revoke",
    ],
)
def test_persistent_replay_rejects_damage(fixture, persistent_case, damage):
    guard, _, _, selected = persistent_case
    guard.dispatch()
    guard.close()
    raw = guard.path.read_bytes()
    digest = fixture.hashlib.sha256(raw).hexdigest()
    if damage == "hash":
        digest = "0" * 64
    elif damage == "identity":
        selected = {"rules": "different"}
    else:
        rows = [json.loads(line) for line in raw.splitlines()]
        if damage == "partial":
            raw = raw[:-3]
        else:
            if damage == "result_without_prepare":
                del rows[1]
            elif damage == "duplicate":
                rows.insert(1, rows[0].copy())
            elif damage == "clock":
                rows[1]["monotonic_ns"] = rows[0]["monotonic_ns"] - 1
            elif damage == "attempt":
                rows[1]["attempt"] = True
            elif damage == "post_revoke":
                rows.append(rows[1].copy())
                rows[-1]["monotonic_ns"] = rows[-2]["monotonic_ns"] + 1
            raw = b""
            for row in rows:
                row["previous_sha256"] = fixture.hashlib.sha256(raw).hexdigest()
                raw += fixture.canonical(row) + b"\n"
        digest = fixture.hashlib.sha256(raw).hexdigest()
    with pytest.raises(RuntimeError, match="fixture_replay"):
        fixture.review_fixture_journal(raw, selected=selected, expected_sha256=digest)


def test_uncertain_attempt_survives_terminal_revocation(fixture, persistent_case):
    guard, actor, _, selected = persistent_case
    actor.request.side_effect = TimeoutError("unknown outcome")
    with pytest.raises(TimeoutError):
        guard.dispatch()
    guard.close()
    report = review_persistent(fixture, guard, selected)
    assert report["revocation_recorded"] and report["uncertain_attempt"] == 1
    assert report["recorded_preparations"] == 1


@pytest.mark.parametrize("new_net", [True, False])
def test_proxy_and_namespace_children_both_drop_capabilities(fixture, monkeypatch, new_net):
    process = Mock()
    process.stdout.readline.return_value = '{"ready": true}\n'
    popen = Mock(return_value=process)
    monkeypatch.setattr(fixture.subprocess, "Popen", popen)
    fixture.Child("# fixture source", new_net=new_net)
    argv = popen.call_args.args[0]
    assert ("--net" in argv) is new_net
    assert ("/usr/bin/unshare" in argv) is new_net
    assert argv[argv.index("/usr/bin/setpriv") + 1 : argv.index(fixture.PYTHON)] == [
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
    ]
    assert popen.call_args.kwargs["env"] == fixture.ENV


@pytest.mark.parametrize(
    "raw",
    [
        b"{}\n",
        b"[]\n",
        b"not-json\n",
        b"\xff\n",
        b"x" * 256,
        b'{"address":"example.com","port":23456}\n',
        b'{"address":"127.0.0.1","port":23456}\n',
        b'{"address":"198.51.100.2","port":true}\n',
        b'{"address":"198.51.100.2","port":443}\n',
        b'{"address":"198.51.100.2","port":23456,"extra":1}\n',
    ],
)
def test_fixture_proxy_rejects_unselected_targets_before_socket(fixture, monkeypatch, raw):
    client, server = socket.socketpair()
    opener = Mock(side_effect=AssertionError("No upstream socket allowed"))
    monkeypatch.setattr(fixture.socket, "socket", opener)
    try:
        client.settimeout(1)
        client.sendall(raw)
        fixture.Probe.proxy_connection(server)
        assert client.recv(3) == b"NO\n"
        opener.assert_not_called()
    finally:
        client.close()
        server.close()


def test_fixture_line_reassembles_fragmented_input(fixture):
    connection = Mock()
    connection.recv.side_effect = [b"a", b"b", b"\n"]
    assert fixture.Probe.line(connection) == b"ab\n"
    assert connection.recv.call_count == 3


def test_fixture_line_rejects_eof(fixture):
    connection = Mock()
    connection.recv.side_effect = [b"a", b""]
    with pytest.raises(ConnectionError):
        fixture.Probe.line(connection)


def test_embedded_worker_passes_original_source_without_duplicating_it(fixture):
    source = "value = 41\n# distinctive-source-marker"
    script = fixture.embedded(source, "result = (scope['value'], source)\n")
    scope = {}
    exec(script, scope)
    assert scope["result"] == (41, source)
    assert script.count("distinctive-source-marker") == 1

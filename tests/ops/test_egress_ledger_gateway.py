"""The trusted gateway consumes the real ledger before granting or sending."""

import importlib.util
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.strategies_nautilus.portfolio_egress_ledger import AttemptLedger, digest, replay

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/ledger_gateway.py"
PIN = "a" * 64


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("gateway_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(module, tmp_path):
    tmp_path.chmod(0o700)
    binding = SimpleNamespace(verify=lambda: {"binding_sha256": PIN})
    ledger = AttemptLedger(tmp_path, binding=binding, binding_sha256=PIN)
    events = []

    def grant():
        raw = (ledger.path / "events.jsonl").read_bytes()
        report = replay(raw, expected_sha256=digest(raw), binding_sha256=PIN)
        assert report["pending_attempt"] == 0
        events.append("grant")

    gateway = module.FixtureLedgerGateway(
        ledger,
        authorize=lambda: {"ok": True},
        grant=grant,
        send=lambda: events.append("send") or True,
        revoke=lambda: events.append("revoke"),
    )
    yield gateway, ledger, events, binding
    with suppress(Exception):
        gateway.close()


def report(ledger):
    raw = (ledger.path / "events.jsonl").read_bytes()
    return replay(raw, expected_sha256=digest(raw), binding_sha256=PIN)


def test_preparation_before_grant_and_send_and_terminal_revoke(case):
    gateway, ledger, events, _ = case
    assert gateway.dispatch() == {"fixture_sent": True, "network_admitted": False}
    assert events == ["grant", "send", "revoke"]
    assert report(ledger)["counts"][0]["outcomes"]["succeeded"] == 1
    with pytest.raises(ValueError, match="consumed"):
        gateway.dispatch()
    gateway.close()
    gateway.close()
    assert events.count("revoke") == 1


@pytest.mark.parametrize("bad", [False, None, {}, {"ok": False}])
def test_authentication_failure_never_prepares_or_grants(case, bad):
    gateway, ledger, events, _ = case
    gateway.authorize = lambda: bad
    with pytest.raises(ValueError, match="authentication"):
        gateway.dispatch()
    assert events == ["revoke"] and report(ledger)["recorded_attempts"] == 0


@pytest.mark.parametrize("stage", ["prepare", "grant", "send", "outcome"])
def test_fault_never_skips_revoke_or_permits_retry(case, stage):
    gateway, ledger, events, _ = case

    def fail(*args, **kwargs):
        raise OSError("fixture fault")

    if stage in {"prepare", "outcome"}:
        setattr(ledger, stage, fail)
    else:
        setattr(gateway, stage, fail)
    with pytest.raises(OSError):
        gateway.dispatch()
    assert gateway.revoked and events[-1] == "revoke"
    with pytest.raises(ValueError, match="consumed"):
        gateway.dispatch()
    assert report(ledger)["recorded_attempts"] == (stage != "prepare")
    if stage != "prepare":
        assert report(ledger)["counts"][0]["outcomes"]["uncertain"] == 1


@pytest.mark.parametrize("after_grant", [False, True])
def test_stop_during_prepare_or_grant_prevents_socket_call(case, after_grant):
    gateway, ledger, events, _ = case
    target = gateway.grant if after_grant else ledger.prepare

    def stopped(*args, **kwargs):
        result = target(*args, **kwargs)
        gateway.stop.set()
        return result

    if after_grant:
        gateway.grant = stopped
    else:
        ledger.prepare = stopped
    with pytest.raises(ValueError, match="stop_before"):
        gateway.dispatch()
    assert "send" not in events
    assert report(ledger)["pending_attempt"] == 0
    assert gateway.revoked


def test_binding_drift_after_grant_prevents_socket_call(case):
    gateway, ledger, events, binding = case
    original = gateway.grant

    def drift():
        original()
        binding.verify = lambda: {"binding_sha256": "b" * 64}

    gateway.grant = drift
    with pytest.raises(ValueError, match="binding_changed"):
        gateway.dispatch()
    assert events == ["grant", "revoke"]
    assert report(ledger)["status"] == "gap"


def test_failed_response_retains_consumption(case):
    gateway, ledger, events, _ = case
    gateway.send = lambda: False
    with pytest.raises(RuntimeError, match="transport_failed"):
        gateway.dispatch()
    assert report(ledger)["counts"][0]["outcomes"]["failed"] == 1
    assert gateway.revoked


def test_revocation_failure_never_claims_success_or_retries(case):
    gateway, ledger, _, _ = case
    revoke = Mock(side_effect=OSError("kernel failure"))
    gateway.revoke = revoke
    with pytest.raises(OSError):
        gateway.dispatch()
    assert not gateway.revoked and gateway.revocation_attempted
    with pytest.raises(RuntimeError, match="revocation_incomplete"):
        gateway.shutdown()
    assert revoke.call_count == 1
    assert report(ledger)["counts"][0]["outcomes"]["succeeded"] == 1


def test_shutdown_queued_against_inflight_send(case):
    gateway, ledger, events, _ = case
    entered, release = threading.Event(), threading.Event()

    def blocked():
        events.append("send")
        entered.set()
        assert release.wait(3)
        assert "revoke" not in events
        return True

    gateway.send = blocked
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(gateway.dispatch)
        try:
            assert entered.wait(2)
            stop = pool.submit(gateway.shutdown)
            assert gateway.stop.wait(2)
            queued = pool.submit(gateway.dispatch)
        finally:
            release.set()
        assert first.result(timeout=3)["fixture_sent"]
        stop.result(timeout=3)
        with pytest.raises(ValueError, match="consumed"):
            queued.result(timeout=3)
    assert events == ["grant", "send", "revoke"]
    assert report(ledger)["recorded_attempts"] == 1


def test_shutdown_before_dispatch(case):
    gateway, ledger, events, _ = case
    gateway.shutdown()
    with pytest.raises(ValueError):
        gateway.dispatch()
    assert events == ["revoke"] and report(ledger)["recorded_attempts"] == 0


def test_failed_preparation_fsync_never_grants(case, monkeypatch):
    gateway, ledger, events, _ = case
    original, calls = os.fsync, 0

    def fail(fd):
        nonlocal calls
        if fd == ledger.journal.fd:
            calls += 1
            if calls == 2:
                raise OSError("fsync")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        gateway.dispatch()
    assert events == ["revoke"] and ledger.failed


def test_fork_refuses_before_inherited_lock(case):
    gateway, _, events, _ = case
    gateway.lock.acquire()
    try:
        child = os.fork()
        if child == 0:
            try:
                for action in (gateway.dispatch, gateway.shutdown, gateway.close):
                    try:
                        action()
                    except ValueError as exc:
                        assert str(exc) == "gateway_foreign_owner"
                    else:
                        os._exit(3)
                os._exit(0)
            except BaseException:
                os._exit(2)
        assert os.waitpid(child, 0)[1] == 0
    finally:
        gateway.lock.release()
    assert events == []


@pytest.mark.parametrize("root,argv", [(0, ["fixture"]), (998, ["fixture", "--send"])])
def test_public_entrypoint_refuses_root_or_arguments(module, monkeypatch, root, argv):
    monkeypatch.setattr(module.os, "geteuid", lambda: root)
    monkeypatch.setattr(module.sys, "argv", argv)
    popen = Mock(side_effect=AssertionError("no child"))
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    assert module.main() == 2
    popen.assert_not_called()


def test_isolation_refusal_precedes_any_mutation(module, monkeypatch):
    run = Mock(side_effect=AssertionError("no mutation"))
    guards = {"require_isolation": Mock(side_effect=RuntimeError("inherited")), "run": run}
    monkeypatch.setattr(module, "load", lambda source: guards)
    monkeypatch.setattr(module.signal, "signal", Mock())
    monkeypatch.setattr(module.signal, "alarm", Mock())
    with pytest.raises(RuntimeError, match="inherited"):
        module.worker({"sources": {"selftest.py": "fixture"}, "original": {}})
    run.assert_not_called()


def test_parent_timeout_kills_group(module, monkeypatch):
    monkeypatch.setattr(module.os, "geteuid", lambda: 998)
    monkeypatch.setattr(module.sys, "argv", ["fixture"])
    process = Mock(pid=12345)
    process.communicate.side_effect = [subprocess.TimeoutExpired("fixture", 45), ("", "")]
    monkeypatch.setattr(module.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(module.os, "killpg", kill)
    with pytest.raises(subprocess.TimeoutExpired):
        module.main()
    kill.assert_called_once_with(12345, module.signal.SIGKILL)

"""Fail-before-mutation and cleanup checks for the standalone namespace fixture."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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

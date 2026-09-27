"""Host namespace inventory stays a bounded, read-only point-in-time census."""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/host_namespace_inventory.py"


@pytest.fixture
def inventory_module():
    spec = importlib.util.spec_from_file_location("host_namespace_inventory_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_census_reconciles_docker_and_dual_stack_without_admission(inventory_module, monkeypatch):
    module = inventory_module
    container = "a" * 64
    calls = []
    monkeypatch.setattr(module.os, "readlink", lambda _: "net:[100]")

    def command(argv):
        argv = tuple(argv)
        assert module.allowed(argv)
        calls.append(argv)
        if argv == module.LSNS_CMD:
            raw = json.dumps({"namespaces": [{"ns": 100, "pid": 1}, {"ns": 200, "pid": 2}]})
        elif argv == module.DOCKER_CMD:
            raw = json.dumps(container) + "\n"
        elif argv[:4] == (module.SUDO, "-n", module.DOCKER, "inspect"):
            raw = "2\n"
        elif argv[2] == module.READLINK:
            raw = "net:[100]\n" if argv[3].startswith("/proc/1/") else "net:[200]\n"
        elif argv[2] == module.NSENTER:
            pid, family = argv[4], argv[8]
            raw = (
                json.dumps([{"dst": "default", "dev": "eth0"}])
                if (pid, family) in {("1", "-4"), ("1", "-6"), ("2", "-4")}
                else "[]"
            )
        else:
            pytest.fail("unexpected command")
        return {"status": "ok", "sha256": "a" * 64, "raw": raw}

    monkeypatch.setattr(module, "command", command)
    report = module.inventory()
    assert report["summary"] == {
        "namespace_count": 2,
        "docker_count": 1,
        "ipv4_default_namespaces": 2,
        "ipv6_default_namespaces": 1,
        "read_failures_or_churn": 0,
    }
    assert report["docker"] == [{"id": container, "pid": 2, "ns": 200}]
    assert len(calls) == len(report["observations"])
    assert report["complete_caller_coverage_verified"] is False
    assert report["network_admitted"] is False


def test_pid_reuse_or_unreadable_namespace_fails_closed(inventory_module, monkeypatch):
    module = inventory_module
    monkeypatch.setattr(module.os, "readlink", lambda _: "net:[100]")
    links = 0

    def command(argv):
        nonlocal links
        argv = tuple(argv)
        if argv == module.LSNS_CMD:
            raw = '{"namespaces":[{"ns":100,"pid":1}]}'
        elif argv == module.DOCKER_CMD:
            raw = ""
        elif argv[2] == module.READLINK:
            links += 1
            raw = "net:[999]\n" if links == 2 else "net:[100]\n"
        elif argv[2] == module.NSENTER:
            if argv[8] == "-6":
                return {"status": "command_failed", "sha256": "b" * 64, "raw": ""}
            raw = '[{"dst":"default","dev":"eth0"}]'
        else:
            pytest.fail("unexpected command")
        return {"status": "ok", "sha256": "a" * 64, "raw": raw}

    monkeypatch.setattr(module, "command", command)
    report = module.inventory()
    assert "namespace_representative_changed:100" in report["blockers"]
    assert "read_failed:namespace_100_ipv6:command_failed" in report["blockers"]
    assert report["namespaces"][0]["defaults"]["ipv6"] is None
    assert report["summary"]["ipv6_default_namespaces"] is None
    assert report["summary"]["read_failures_or_churn"] == 2
    assert report["network_admitted"] is False


def test_command_allowlist_and_bounded_shapes(inventory_module):
    module = inventory_module
    assert not module.allowed((module.SUDO, "-n", "/usr/sbin/nft", "flush", "ruleset"))
    assert not module.allowed((module.SUDO, "-n", module.NSENTER, "--target", "-1", "--net"))
    with pytest.raises(ValueError, match="not_read_only"):
        module.command((module.SUDO, "-n", module.IP, "link", "set", "eth0", "down"))
    with pytest.raises(ValueError, match="namespace_identity"):
        module.namespaces('{"namespaces":[{"ns":100,"pid":1},{"ns":100,"pid":2}]}')
    with pytest.raises(ValueError, match="docker_id_list"):
        module.ids('"untrusted-id"\n')


def test_report_is_exclusive_and_private(inventory_module, tmp_path, monkeypatch, capsys):
    module = inventory_module
    path = tmp_path / "inventory.json"
    monkeypatch.setattr(
        module,
        "inventory",
        lambda: {
            "status": "read_only_snapshot_unqualified",
            "summary": {},
            "network_admitted": False,
        },
    )
    assert module.main(["--report", str(path)]) == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(capsys.readouterr().out)["network_admitted"] is False
    before = path.read_bytes()
    assert module.main(["--report", str(path)]) == 1
    assert path.read_bytes() == before

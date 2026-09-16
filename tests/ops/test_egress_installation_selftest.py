"""Fail before privileged fixture writes when namespace/pinned inputs are wrong."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/installation_selftest.py"


@pytest.fixture
def harness():
    spec = importlib.util.spec_from_file_location("installation_selftest_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("damage", ["uid", "euid", "pid", "mnt", "net", "pid_namespace", "missing"])
def test_unsafe_worker_context_fails_before_mounts(harness, monkeypatch, damage):
    before = {"mnt": "original-mnt", "net": "original-net", "pid": "original-pid"}
    after = {key: "fresh-" + key for key in before}
    monkeypatch.setattr(harness.os, "getuid", lambda: 1 if damage == "uid" else 0)
    monkeypatch.setattr(harness.os, "geteuid", lambda: 1 if damage == "euid" else 0)
    monkeypatch.setattr(harness.os, "getpid", lambda: 2 if damage == "pid" else 1)
    if damage in {"mnt", "net", "pid_namespace"}:
        key = "pid" if damage == "pid_namespace" else damage
        after[key] = before[key]
    elif damage == "missing":
        del before["mnt"]
    monkeypatch.setattr(harness, "namespaces", lambda: after)
    monkeypatch.setattr(harness.signal, "signal", lambda *args: None)
    monkeypatch.setattr(harness.signal, "alarm", lambda *args: None)
    monkeypatch.setattr(
        harness, "run", lambda *args, **kwargs: pytest.fail("unsafe mount attempted")
    )
    with pytest.raises(RuntimeError):
        harness.worker({"original": before})


def test_root_public_cli_is_refused(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(harness.os, "geteuid", lambda: 0)
    path = tmp_path / "result"
    with pytest.raises(SystemExit):
        harness.main(["--report", str(path)])
    assert not path.exists()


def test_existing_report_refused_before_privilege_use(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(harness.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(harness.subprocess, "Popen", lambda *a, **kw: pytest.fail("sudo attempted"))
    path = tmp_path / "result"
    path.write_bytes(b"previous evidence")
    with pytest.raises(FileExistsError):
        harness.main(["--report", str(path)])
    assert path.read_bytes() == b"previous evidence"


def test_changed_installer_refused_before_privilege_use(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(harness.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(harness, "INSTALLER_PIN", "0" * 64)
    monkeypatch.setattr(harness.subprocess, "Popen", lambda *a, **kw: pytest.fail("sudo attempted"))
    path = tmp_path / "result"
    with pytest.raises(ValueError, match="installer_changed"):
        harness.main(["--report", str(path)])
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_bytes() == b""


def test_checked_in_bundle_reproduces_accepted_pin(harness):
    path = SOURCE.with_name("package.py")
    assert harness.sha(path.read_bytes()) == harness.INSTALLER_PIN
    scope = harness.load(path.read_bytes())
    scope["build"].__globals__["__file__"] = str(path)
    raw = scope["build"]()
    assert harness.sha(raw) == harness.PIN
    assert scope["inspect"](raw, harness.PIN)["install.py"] == path.read_bytes()


def test_command_failure_preserves_fixture_diagnostic(harness, monkeypatch):
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout='{"status":"blocked"}', stderr="synthetic diagnostic"
        ),
    )
    with pytest.raises(RuntimeError, match="synthetic diagnostic"):
        harness.run("/usr/bin/true")


def test_host_observation_exposes_hashes_and_metadata_only(harness):
    result = harness.host_observation()
    assert set(result["account_hashes"]) == {"/etc/passwd", "/etc/group"}
    assert all(len(value) == 64 for value in result["account_hashes"].values())
    assert "shadow" not in json.dumps(result)
    assert len(result["installation_paths"]) == 3


def test_report_symlink_cannot_overwrite_target(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(harness.os, "geteuid", lambda: 1000)
    target = tmp_path / "target"
    target.write_bytes(b"preserve")
    path = tmp_path / "report"
    path.symlink_to(target)
    with pytest.raises(OSError):
        harness.main(["--report", str(path)])
    assert target.read_bytes() == b"preserve"

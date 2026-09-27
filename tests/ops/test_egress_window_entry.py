"""Read-only joint-window entry bootstrap with staged, never installed files."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load(name):
    spec = importlib.util.spec_from_file_location(name + "_entry_test", DIRECTORY / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HeldFiles:
    manifest_sha256 = "a" * 64

    def __init__(self, paths):
        self.paths = paths
        self.fds = {}
        self.closed = False

    def verify(self):
        if self.closed:
            raise ValueError("staged_entry_holder_closed")
        for path, (fd, info, raw) in self.fds.items():
            current = os.stat(path, follow_symlinks=False)
            if (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns) != (
                current.st_dev,
                current.st_ino,
                current.st_mtime_ns,
                current.st_ctime_ns,
            ) or os.pread(fd, len(raw) + 1, 0) != raw:
                raise ValueError("staged_entry_holder_changed")

    def open_file(self, path, mode):
        self.verify()
        if path not in self.paths or stat.S_IMODE(os.stat(path).st_mode) != mode:
            raise ValueError("staged_entry_wrong_file_or_mode")
        if path not in self.fds:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(fd)
            self.fds[path] = (fd, info, os.pread(fd, info.st_size + 1, 0))
        return self.fds[path][0]

    def close(self):
        if not self.closed:
            self.closed = True
            for fd, _, _ in self.fds.values():
                os.close(fd)


@pytest.fixture
def staged(tmp_path, monkeypatch):
    entry, sources = load("gateway_window_entry"), load("gateway_window_sources")
    code = tmp_path / "code"
    code.mkdir()
    paths = {}
    for name in sources.FILES:
        file = code / name
        file.write_bytes((DIRECTORY / name).read_bytes())
        file.chmod(0o444)
        paths[str(file)] = 0o444
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": sources.PROFILE,
                "base_manifest_sha256": HeldFiles.manifest_sha256,
                "files": {
                    name: hashlib.sha256((code / name).read_bytes()).hexdigest()
                    for name in sources.FILES
                },
            }
        )
    )
    manifest.chmod(0o600)
    paths[str(manifest)] = 0o600
    holder = HeldFiles(paths)
    monkeypatch.setattr(entry, "CODE", str(code))
    monkeypatch.setattr(entry, "MANIFEST", str(manifest))
    monkeypatch.setattr(entry, "_load_base", lambda: lambda: holder)
    actual_loader = entry._load_sources

    def test_loader(raw):
        scope = actual_loader(raw)
        scope["_require_root"] = lambda: None
        return scope

    monkeypatch.setattr(entry, "_load_sources", test_loader)
    return entry, holder, manifest, code


def test_fixed_entry_pins_base_and_current_source_bytes():
    entry = load("gateway_window_entry")
    assert (
        hashlib.sha256((DIRECTORY / "helper_entry.py").read_bytes()).hexdigest() == entry.BASE_PIN
    )
    assert (
        hashlib.sha256((DIRECTORY / "gateway_window_sources.py").read_bytes()).hexdigest()
        == entry.SOURCE_PIN
    )
    assert "gateway_window_entry.py" in load("gateway_window_sources").FILES


def test_checkout_entry_refuses_before_loading_base(monkeypatch, capsys):
    entry = load("gateway_window_entry")
    monkeypatch.setattr(entry, "_load_base", lambda: pytest.fail("base verifier should not open"))
    assert entry.main(["--check"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "fixed_joint_window_entry_required"
    assert all(value is False for field, value in report.items() if field != "status")


def test_staged_entry_uses_fixed_inventory_and_always_exits_unqualified(
    staged, monkeypatch, capsys
):
    entry, holder, _, _ = staged
    monkeypatch.setattr(entry, "_eligible", lambda args: args == ["--check"])
    assert entry.main(["--check"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "fixed_joint_window_sources_observed_unqualified"
    assert all(value is False for field, value in report.items() if field != "status")
    assert holder.closed


@pytest.mark.parametrize("damage", ["source_pin", "source_bytes", "manifest_pin", "entry_bytes"])
def test_bad_pins_or_source_drift_close_holder(staged, monkeypatch, capsys, damage):
    entry, holder, manifest, code = staged
    monkeypatch.setattr(entry, "_eligible", lambda args: args == ["--check"])
    if damage == "source_pin":
        monkeypatch.setattr(entry, "SOURCE_PIN", "0" * 64)
    elif damage == "source_bytes":
        target = code / "gateway_window_sources.py"
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
        target.chmod(0o444)
    elif damage == "entry_bytes":
        target = code / "gateway_window_entry.py"
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
        target.chmod(0o444)
    else:
        document = json.loads(manifest.read_text())
        document["files"]["gateway_window_entry.py"] = "0" * 64
        manifest.write_text(json.dumps(document))
    assert entry.main(["--check"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "joint_window_sources_missing_or_changed"
    assert report["network_admitted"] is False
    assert holder.closed

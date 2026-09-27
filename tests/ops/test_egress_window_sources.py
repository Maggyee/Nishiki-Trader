"""Fixed joint-window source inventory through a staged descriptor holder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load():
    spec = importlib.util.spec_from_file_location(
        "joint_window_sources_test", DIRECTORY / "gateway_window_sources.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HeldFiles:
    """Test-only path/byte custody, not the installed root verifier."""

    manifest_sha256 = "a" * 64

    def __init__(self, selected):
        self.selected = selected
        self.fds = {}
        self.closed = False

    def verify(self):
        if self.closed:
            raise ValueError("held_files_closed")
        for path, (fd, info, raw) in self.fds.items():
            current = os.stat(path, follow_symlinks=False)
            if (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns) != (
                current.st_dev,
                current.st_ino,
                current.st_mtime_ns,
                current.st_ctime_ns,
            ) or os.pread(fd, len(raw) + 1, 0) != raw:
                raise ValueError("held_files_drift")

    def open_file(self, path, mode):
        self.verify()
        if path not in self.selected or stat.S_IMODE(os.stat(path).st_mode) != mode:
            raise ValueError("held_files_wrong_path_or_mode")
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
    module = load()
    code = tmp_path / "code"
    code.mkdir()
    selected = {}
    for name in module.FILES:
        path = code / name
        path.write_bytes((DIRECTORY / name).read_bytes())
        path.chmod(0o444)
        selected[str(path)] = 0o444
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": module.PROFILE,
                "base_manifest_sha256": HeldFiles.manifest_sha256,
                "files": {
                    name: hashlib.sha256((code / name).read_bytes()).hexdigest()
                    for name in module.FILES
                },
            }
        )
    )
    manifest.chmod(0o600)
    selected[str(manifest)] = 0o600
    monkeypatch.setattr(module, "CODE", str(code))
    monkeypatch.setattr(module, "MANIFEST", str(manifest))
    monkeypatch.setattr(module, "_require_root", lambda: None)
    return module, HeldFiles(selected), manifest, code


def test_fixed_inventory_holds_exact_sources_without_executing_or_admitting(staged):
    module, authority, _, _ = staged
    held = module.RootSelectedWindowSources(authority)
    assert not hasattr(held, "sources")
    for name in module.FILES:
        assert held.source(name) == (DIRECTORY / name).read_bytes()
    with pytest.raises(ValueError, match="joint_window_sources_unknown_file"):
        held.source("installed_gateway.py")
    assert not hasattr(held, "activate")
    held.close()
    assert authority.closed
    with pytest.raises(ValueError, match="joint_window_sources_closed"):
        held.source(module.FILES[0])


@pytest.mark.parametrize("damage", ["base", "schema", "missing", "extra", "pin", "duplicate"])
def test_manifest_mismatch_refused_before_code_read(staged, damage):
    module, authority, manifest, _ = staged
    raw = manifest.read_text()
    if damage == "duplicate":
        raw = raw.replace('"schema_version":', '"schema_version": "other", "schema_version":')
    else:
        document = json.loads(raw)
        if damage == "base":
            document["base_manifest_sha256"] = "b" * 64
        elif damage == "schema":
            document["schema_version"] = "other"
        elif damage == "missing":
            document["files"].pop(module.FILES[0])
        elif damage == "extra":
            document["files"]["caller.py"] = "b" * 64
        else:
            document["files"][module.FILES[0]] = "not-a-digest"
        raw = json.dumps(document)
    manifest.write_text(raw)
    with pytest.raises(ValueError, match="joint_window_sources"):
        module.RootSelectedWindowSources(authority)
    assert authority.closed
    assert set(authority.fds) == {str(manifest)}


@pytest.mark.parametrize("damage", ["wrong_hash", "source_changed", "manifest_changed", "mode"])
def test_source_or_held_drift_closes_authority(staged, damage):
    module, authority, manifest, code = staged
    if damage == "wrong_hash":
        document = json.loads(manifest.read_text())
        document["files"][module.FILES[-1]] = "b" * 64
        manifest.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="joint_window_sources_pin_changed"):
            module.RootSelectedWindowSources(authority)
    elif damage == "mode":
        (code / module.FILES[-1]).chmod(0o666)
        with pytest.raises(ValueError, match="held_files_wrong_path_or_mode"):
            module.RootSelectedWindowSources(authority)
    else:
        held = module.RootSelectedWindowSources(authority)
        target = code / module.FILES[0] if damage == "source_changed" else manifest
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
        with pytest.raises(ValueError, match="held_files_drift"):
            held.source(module.FILES[0])
    assert authority.closed


def test_unisolated_user_cannot_select_sources(staged):
    _, authority, _, _ = staged
    module = load()
    with pytest.raises(ValueError, match="joint_window_sources_isolated_root_required"):
        module.RootSelectedWindowSources(authority)
    assert authority.closed


def test_held_sources_close_if_root_identity_is_lost(staged, monkeypatch):
    module, authority, _, _ = staged
    held = module.RootSelectedWindowSources(authority)

    def refused():
        raise ValueError("joint_window_sources_isolated_root_required")

    monkeypatch.setattr(module, "_require_root", refused)
    with pytest.raises(ValueError, match="joint_window_sources_isolated_root_required"):
        held.source(module.FILES[0])
    assert authority.closed

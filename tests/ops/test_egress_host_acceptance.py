"""Permanent acceptance records are separate from all real collection scopes."""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/host_acceptance.py"


@pytest.fixture
def record(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("host_acceptance_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "STORAGE", tmp_path)
    monkeypatch.setattr(module, "RECORD_ROOT", tmp_path / "installation-acceptance-v1")
    monkeypatch.setattr(module, "RECORD", module.RECORD_ROOT / "consumed.json")
    monkeypatch.setattr(module, "AUTHORITY_UID", os.getuid())
    authority = SimpleNamespace(
        verify=lambda: None,
        manifest_sha256="a" * 64,
        account={"name": "trader-egress", "uid": 997, "gid": 997},
    )
    return module, authority


def test_record_survives_reviewer_and_refuses_reprepare(record):
    module, authority = record
    pin = module.prepare_record(authority)
    first = module.RECORD.read_bytes()
    assert module.read_record(pin)["consumed"] is True
    with pytest.raises(FileExistsError):
        module.prepare_record(authority)
    assert module.RECORD.read_bytes() == first


@pytest.mark.parametrize(
    "damage", ["directory_mode", "file_mode", "hash", "symlink", "hardlink", "fifo"]
)
def test_record_refuses_changed_or_special_paths(record, damage):
    module, authority = record
    pin = module.prepare_record(authority)
    if damage == "directory_mode":
        module.RECORD_ROOT.chmod(0o755)
    elif damage == "file_mode":
        module.RECORD.chmod(0o644)
    elif damage == "hash":
        module.RECORD.write_bytes(b"changed")
    elif damage == "hardlink":
        os.link(module.RECORD, module.RECORD_ROOT / "alias")
    else:
        module.RECORD.unlink()
        if damage == "symlink":
            module.RECORD.symlink_to(module.RECORD_ROOT / "README.md")
        else:
            os.mkfifo(module.RECORD)
    with pytest.raises((OSError, ValueError)):
        module.read_record(pin)


def test_failed_preparation_leaves_permanent_directory(record, monkeypatch):
    module, authority = record

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(module, "write_exclusive", fail)
    with pytest.raises(OSError):
        module.prepare_record(authority)
    assert module.RECORD_ROOT.is_dir()
    with pytest.raises(FileExistsError):
        module.prepare_record(authority)

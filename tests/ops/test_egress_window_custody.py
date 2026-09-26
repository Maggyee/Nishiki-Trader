"""The root-held selection does not turn a kernel snapshot into admission."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "infra/egress-guard/gateway_window_custody.py"
KERNEL = ROOT / "infra/egress-guard/gateway_window_kernel.py"
WITNESS = ROOT / "infra/egress-guard/gateway_window_witness.py"
KERNEL_TEST = Path(__file__).with_name("test_egress_window_kernel.py")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HeldFiles:
    """Test-only descriptor custody; production requires TrustedInstallation."""

    manifest_sha256 = "a" * 64

    def __init__(self, paths):
        self.paths = paths
        self.selected = {}
        self.closed = False

    def verify(self):
        if self.closed:
            raise ValueError("held_files_closed")
        for path, (fd, info, raw) in self.selected.items():
            if (
                os.fstat(fd) != info
                or os.stat(path, follow_symlinks=False) != info
                or os.pread(fd, len(raw) + 1, 0) != raw
            ):
                raise ValueError("held_files_changed")

    def open_file(self, path, mode):
        self.verify()
        if path not in self.paths or stat.S_IMODE(os.stat(path).st_mode) != mode:
            raise ValueError("held_files_fixed_mode_required")
        if path not in self.selected:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(fd)
            self.selected[path] = (fd, info, os.pread(fd, info.st_size + 1, 0))
        return self.selected[path][0]

    def close(self):
        if not self.closed:
            self.closed = True
            for fd, _, _ in self.selected.values():
                os.close(fd)


@pytest.fixture
def selection(tmp_path, monkeypatch):
    custody = load(SOURCE, "joint_window_custody_test")
    kernel = load(KERNEL, "joint_window_kernel_custody_test")
    fixture = load(KERNEL_TEST, "joint_window_fixture_test")
    tables = {family: fixture.table(family) for family in ("inet", "netdev")}
    pins = {
        family: kernel.digest(kernel._static(value["nftables"])) for family, value in tables.items()
    }
    source = KERNEL.read_bytes()
    plan = {
        "schema_version": custody.PROFILE,
        "base_manifest_sha256": HeldFiles.manifest_sha256,
        "observer_sha256": hashlib.sha256(source).hexdigest(),
        "boot_id": custody._identity()["boot_id"],
        "host_net_namespace": custody._identity()["host_net_namespace"],
        "host_user_namespace": custody._identity()["host_user_namespace"],
        "wan_interface": "wan",
        "collector": None,
        "static_rules_sha256": pins,
    }
    plan_path = tmp_path / "policy.json"
    code_path = tmp_path / "observer.py"
    plan_path.write_text(json.dumps(plan))
    code_path.write_bytes(source)
    plan_path.chmod(0o600)
    code_path.chmod(0o444)
    monkeypatch.setattr(custody, "PLAN", str(plan_path))
    monkeypatch.setattr(custody, "OBSERVER", str(code_path))
    monkeypatch.setattr(custody, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=True)))
    monkeypatch.setattr(custody.os, "getuid", lambda: 0)
    monkeypatch.setattr(custody.os, "geteuid", lambda: 0)

    def nft_run(args, **_kwargs):
        if args[1:4] == ["-j", "list", "table"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(tables[args[-2]]).encode(), b"")
        if args[1:4] == ["list", "chain", "netdev"]:
            return subprocess.CompletedProcess(args, 0, fixture.CHAIN.encode(), b"")
        raise AssertionError(f"unexpected nft command: {args!r}")

    monkeypatch.setattr(subprocess, "run", nft_run)
    return custody, HeldFiles({str(plan_path): 0o600, str(code_path): 0o444}), plan_path, code_path


def test_protected_selection_observes_but_never_admits(selection):
    custody, authority, _, _ = selection
    held = custody.RootSelectedWindowSnapshot(authority)
    report = held.observe()
    assert report["status"] == "root_selected_kernel_snapshot_unqualified"
    assert report["kernel_snapshot"]["remaining_ns_lower_bound"] > 0
    assert report["activation_history_verified"] is False
    assert report["source_authenticated"] is False
    assert report["complete_caller_coverage_verified"] is False
    assert report["network_admitted"] is False
    held.close()
    assert authority.closed


def test_held_selection_can_be_journaled_without_activation(selection, tmp_path, monkeypatch):
    custody, authority, _, _ = selection
    module = load(WITNESS, "joint_window_witness_custody_test")
    root = tmp_path / "witness-root"
    root.mkdir(mode=0o700)
    held = custody.RootSelectedWindowSnapshot(authority)
    fixture = load(KERNEL_TEST, "joint_window_witness_nft_fixture")
    tables = {family: fixture.table(family) for family in ("inet", "netdev")}
    observer = held.observe_kernel
    held.observe_kernel = lambda **kwargs: observer(
        **kwargs, reader=lambda family: tables[family], chain_reader=lambda: fixture.CHAIN
    )
    monkeypatch.setattr(custody.os, "geteuid", lambda: root.stat().st_uid)
    try:
        witness = module.WindowWitness(root, held)
        try:
            report = witness.observe()
            assert report["observations"] == 2
            assert report["first_selection_sha256"] == hashlib.sha256(held.plan_raw).hexdigest()
            assert report["activation_history_verified"] is False
            assert report["network_admitted"] is False
            assert witness.expected == (root / module.SCOPE / "events.jsonl").read_bytes()
        finally:
            witness.close()
    finally:
        held.close()


def test_protected_collector_selection_is_forwarded_without_admission(selection):
    custody, authority, plan_path, _ = selection
    collector = {"host_link": "gw-jc1", "child_ipv4": "169.254.254.2", "source_ipv4": "10.0.0.136"}
    plan = json.loads(plan_path.read_text())
    plan["collector"] = collector
    plan_path.write_text(json.dumps(plan))
    held = custody.RootSelectedWindowSnapshot(authority)
    seen = []

    def observe_kernel(**kwargs):
        seen.append(kwargs)
        return {
            "status": "local_kernel_timers_observed_unqualified",
            "static_rules_sha256": plan["static_rules_sha256"],
            "source_authenticated": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
        }

    held.observe_kernel = observe_kernel
    report = held.observe()
    assert seen[0]["collector"] == collector
    assert report["network_admitted"] is False
    held.close()


def test_invalid_protected_collector_selection_is_refused(selection):
    custody, authority, plan_path, _ = selection
    plan = json.loads(plan_path.read_text())
    plan["collector"] = {
        "host_link": "wan",
        "child_ipv4": "169.254.254.2",
        "source_ipv4": "10.0.0.136",
    }
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="kernel_window_fixed_collector_selection_required"):
        custody.RootSelectedWindowSnapshot(authority)
    assert authority.closed


@pytest.mark.parametrize("damage", ["pin", "manifest", "namespace", "schema", "duplicate_key"])
def test_bad_protected_plan_refused_before_kernel_read(selection, damage):
    custody, authority, plan_path, _ = selection
    raw = plan_path.read_text()
    if damage == "duplicate_key":
        raw = raw.replace('"schema_version":', '"schema_version": "other", "schema_version":')
    else:
        plan = json.loads(raw)
        key = {
            "pin": "observer_sha256",
            "manifest": "base_manifest_sha256",
            "namespace": "host_net_namespace",
            "schema": "schema_version",
        }[damage]
        plan[key] = "wrong"
        raw = json.dumps(plan)
    plan_path.write_text(raw)
    with pytest.raises(ValueError, match="joint_window"):
        custody.RootSelectedWindowSnapshot(authority)
    assert authority.closed


def test_changed_installed_observer_refused_before_execution(selection):
    custody, authority, plan_path, code_path = selection
    code_path.chmod(0o644)
    code_path.write_text("def observe(**kwargs): raise AssertionError('must not execute')\n")
    code_path.chmod(0o444)
    with pytest.raises(ValueError, match="joint_window_observer_source_changed"):
        custody.RootSelectedWindowSnapshot(authority)
    assert authority.closed


@pytest.mark.parametrize("damage", ["plan", "code", "identity", "snapshot"])
def test_drift_or_forged_kernel_permission_closes_held_authority(selection, monkeypatch, damage):
    custody, authority, plan_path, code_path = selection
    held = custody.RootSelectedWindowSnapshot(authority)
    if damage in {"plan", "code"}:
        target = plan_path if damage == "plan" else code_path
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
    elif damage == "identity":
        original = custody._identity
        monkeypatch.setattr(
            custody, "_identity", lambda: {**original(), "host_net_namespace": "net:[other]"}
        )
    else:
        held.observe_kernel = lambda **_kwargs: {
            "status": "local_kernel_timers_observed_unqualified",
            "static_rules_sha256": held.plan["static_rules_sha256"],
            "source_authenticated": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": True,
        }
    with pytest.raises(ValueError):
        held.observe()
    assert authority.closed
    with pytest.raises(ValueError, match="joint_window_selection_closed"):
        held.observe()

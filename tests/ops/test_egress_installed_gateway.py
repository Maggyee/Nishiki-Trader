"""Installed gateway custody, fixed scope and disposable-wrapper refusal boundaries."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load(name):
    spec = importlib.util.spec_from_file_location(
        "installed_gateway_test_" + name, DIRECTORY / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module():
    return load("installed_gateway")


@pytest.fixture
def tree(module, monkeypatch, tmp_path):
    policy = load("installation")
    monkeypatch.setattr(policy, "AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(policy, "_root_fd", lambda: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY))
    user = SimpleNamespace(
        pw_name=policy.ACCOUNT,
        pw_uid=12345,
        pw_gid=12346,
        pw_dir="/nonexistent",
        pw_shell="/usr/sbin/nologin",
    )
    group = SimpleNamespace(gr_name=policy.ACCOUNT, gr_gid=12346, gr_mem=[])
    groups = [group]
    monkeypatch.setattr(policy.pwd, "getpwall", lambda: [user])
    monkeypatch.setattr(policy.grp, "getgrall", lambda: groups)
    for path in (policy.CODE_ROOT, str(Path(policy.MANIFEST).parent), policy.STORAGE_ROOT, "/run"):
        (tmp_path / path.lstrip("/")).mkdir(parents=True, mode=0o700)
    pins = {}
    for name in (*policy.FILES, *module.FILES):
        path = tmp_path / policy.CODE_ROOT.lstrip("/") / name
        raw = ("# installed fixture: " + name + "\n").encode()
        path.write_bytes(raw)
        path.chmod(0o444)
        pins[name] = module.digest(raw)
    base = {
        "schema_version": policy.PROFILE,
        "collector": {"name": policy.ACCOUNT, "uid": user.pw_uid, "gid": user.pw_gid},
        "files": {name: pins[name] for name in policy.FILES},
    }
    base_path = tmp_path / policy.MANIFEST.lstrip("/")
    base_path.write_text(json.dumps(base))
    base_path.chmod(0o600)
    manifest = tmp_path / module.MANIFEST.lstrip("/")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": module.PROFILE,
                "base_manifest_sha256": module.digest(base_path.read_bytes()),
                "files": {name: pins[name] for name in module.FILES},
            }
        )
    )
    manifest.chmod(0o600)
    authority = policy.TrustedInstallation()
    yield SimpleNamespace(
        root=tmp_path, authority=authority, manifest=manifest, user=user, groups=groups
    )
    authority.close()


def test_fixed_source_inventory_uses_held_root_authority(module, tree):
    selected = module.InstalledGatewaySources(tree.authority)
    assert selected.source("ledger_gateway.py").startswith(b"# installed fixture")
    assert set(selected.sources) == set(module.FILES)
    with pytest.raises(KeyError):
        selected.source("../../arbitrary.py")
    tree.authority.close()
    with pytest.raises(ValueError, match="closed"):
        selected.source("ledger_gateway.py")


@pytest.mark.parametrize(
    "damage",
    [
        "profile",
        "base_pin",
        "missing",
        "extra",
        "source_hash",
        "symlink",
        "hardlink",
        "fifo",
        "mode",
        "manifest_mode",
    ],
)
def test_extension_rejected_before_loading_untrusted_source(module, tree, damage):
    path = tree.root / module.CODE.lstrip("/") / "ledger_gateway.py"
    manifest = json.loads(tree.manifest.read_bytes())
    if damage == "profile":
        manifest["schema_version"] = "other"
    elif damage == "base_pin":
        manifest["base_manifest_sha256"] = "0" * 64
    elif damage == "missing":
        del manifest["files"]["ledger_gateway.py"]
    elif damage == "extra":
        manifest["files"]["arbitrary.py"] = "0" * 64
    elif damage == "source_hash":
        manifest["files"]["ledger_gateway.py"] = "0" * 64
    elif damage == "symlink":
        path.rename(path.with_suffix(".old"))
        path.symlink_to(path.with_suffix(".old"))
    elif damage == "hardlink":
        os.link(path, path.with_suffix(".link"))
    elif damage == "fifo":
        path.unlink()
        os.mkfifo(path, 0o444)
    elif damage == "mode":
        path.chmod(0o644)
    else:
        tree.manifest.chmod(0o644)
    tree.manifest.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        module.InstalledGatewaySources(tree.authority)
    assert tree.authority.closed


@pytest.mark.parametrize("damage", ["bytes", "replace", "manifest", "account", "storage"])
def test_restored_installation_cannot_revive_held_sources(module, tree, damage):
    selected = module.InstalledGatewaySources(tree.authority)
    path = tree.root / module.CODE.lstrip("/") / "ledger_gateway.py"
    raw = path.read_bytes()
    if damage == "bytes":
        path.chmod(0o644)
        path.write_bytes(b"# changed\n")
        path.chmod(0o444)
    elif damage == "replace":
        path.rename(path.with_suffix(".old"))
        path.write_bytes(raw)
        path.chmod(0o444)
    elif damage == "manifest":
        tree.manifest.write_text(tree.manifest.read_text() + "\n")
    elif damage == "account":
        tree.groups.append(
            SimpleNamespace(gr_name="foreign", gr_gid=22000, gr_mem=["trader-egress"])
        )
    else:
        (tree.root / module.STORAGE.lstrip("/")).chmod(0o755)
    with pytest.raises(ValueError):
        selected.source("portfolio_egress_ledger.py")
    if damage == "bytes":
        path.chmod(0o644)
        path.write_bytes(raw)
        path.chmod(0o444)
    elif damage == "replace":
        path.unlink()
        path.with_suffix(".old").rename(path)
    elif damage == "account":
        tree.groups.pop()
    elif damage == "storage":
        (tree.root / module.STORAGE.lstrip("/")).chmod(0o700)
    with pytest.raises(ValueError, match="closed"):
        selected.source("ledger_gateway.py")


@pytest.mark.parametrize(
    "damage", ["uid", "euid", "parent", "profile", "mnt", "net", "pid", "original", "missing"]
)
def test_context_requires_root_child_of_isolated_pid1(module, tree, monkeypatch, damage):
    current = {k: os.readlink("/proc/self/ns/" + k) for k in ("mnt", "net", "pid")}
    context = {
        "profile": module.PROFILE,
        "isolated": current.copy(),
        "original": {k: "old-" + k for k in current},
    }
    if damage == "profile":
        context["profile"] = "other"
    elif damage in current:
        context["isolated"][damage] = "changed"
    elif damage == "original":
        context["original"]["net"] = current["net"]
    elif damage == "missing":
        del context["original"]["net"]
    path = tree.root / module.CONTEXT.lstrip("/")
    path.write_text(json.dumps(context))
    path.chmod(0o600)
    monkeypatch.setattr(module.os, "getuid", lambda: 1 if damage == "uid" else 0)
    monkeypatch.setattr(module.os, "geteuid", lambda: 1 if damage == "euid" else 0)
    monkeypatch.setattr(module.os, "getppid", lambda: 2 if damage == "parent" else 1)
    with pytest.raises(ValueError):
        module.fixture_context(tree.authority)


def test_valid_context_is_retained_and_rechecked(module, tree, monkeypatch):
    current = {k: os.readlink("/proc/self/ns/" + k) for k in ("mnt", "net", "pid")}
    path = tree.root / module.CONTEXT.lstrip("/")
    path.write_text(
        json.dumps(
            {
                "profile": module.PROFILE,
                "isolated": current,
                "original": {k: "old-" + k for k in current},
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setattr(module.os, "getuid", lambda: 0)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "getppid", lambda: 1)
    module.fixture_context(tree.authority)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError):
        tree.authority.verify()


def test_binding_failure_is_permanent_even_after_observation_restored(module):
    authority = SimpleNamespace(verify=Mock(), close=Mock(), manifest_sha256="base")
    collector = SimpleNamespace(verify=Mock(), selected={"process": {"uid": 12345}})
    network = {"nftables": [{"set": {"elem": [1]}}]}
    guards = {
        "run": lambda *args: json.dumps(network),
        "NFT": "nft",
        "IP": "ip",
        "stable_rules": lambda value: value,
    }
    binding = module.InstalledBinding(
        authority, SimpleNamespace(manifest_sha256="gateway"), collector, guards
    )
    assert binding.verify()["binding_sha256"] == binding.pin
    collector.verify.side_effect = ValueError("child changed")
    with pytest.raises(ValueError):
        binding.verify()
    authority.close.assert_called_once()
    collector.verify.side_effect = None
    with pytest.raises(ValueError, match="ended"):
        binding.verify()


@pytest.mark.parametrize("damage", ["arguments", "path", "isolation"])
def test_checkout_controller_refused_before_installation_load(module, monkeypatch, damage):
    monkeypatch.setattr(
        module,
        "__file__",
        module.CODE + "/installed_gateway.py" if damage != "path" else "/tmp/installed_gateway.py",
    )
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["gateway", "--fixture"] if damage != "arguments" else ["gateway", "--run"],
    )
    monkeypatch.setattr(module.sys, "flags", SimpleNamespace(isolated=damage != "isolation"))
    monkeypatch.setattr(module, "run_controller", lambda: pytest.fail("controller was started"))
    with pytest.raises(ValueError):
        module.main()


@pytest.mark.parametrize("damage", ["root", "existing_report", "symlink_report", "installer_pin"])
def test_wrapper_refuses_before_sudo(tmp_path, monkeypatch, damage):
    harness = load("installed_gateway_selftest")
    monkeypatch.setattr(harness.os, "geteuid", lambda: 0 if damage == "root" else 1000)
    monkeypatch.setattr(harness.subprocess, "Popen", lambda *a, **kw: pytest.fail("sudo called"))
    path = tmp_path / "report.json"
    if damage == "existing_report":
        path.write_bytes(b"original")
    elif damage == "symlink_report":
        original = tmp_path / "original"
        original.write_bytes(b"original")
        path.symlink_to(original)
    elif damage == "installer_pin":
        original_load = harness.load

        def bad_pin(raw):
            scope = original_load(raw)
            scope["INSTALLER_PIN"] = "0" * 64
            return scope

        monkeypatch.setattr(harness, "load", bad_pin)
    with pytest.raises((ValueError, OSError, SystemExit)):
        harness.main(["--report", str(path)])
    if damage in {"existing_report", "symlink_report"}:
        assert path.read_bytes() == b"original"

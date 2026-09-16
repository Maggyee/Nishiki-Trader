"""Fixed installation authority must fail before untrusted source can be loaded."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/installation.py"


@pytest.fixture
def policy():
    spec = importlib.util.spec_from_file_location("egress_installation_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def staged(policy, monkeypatch, tmp_path):
    # Unit-test filesystem root/owner, never an alternate production CLI root.
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
    users, groups = [user], [group]
    monkeypatch.setattr(policy.pwd, "getpwall", lambda: users)
    monkeypatch.setattr(policy.grp, "getgrall", lambda: groups)
    for path in (policy.CODE_ROOT, str(Path(policy.MANIFEST).parent), policy.STORAGE_ROOT):
        (tmp_path / path.lstrip("/")).mkdir(parents=True, mode=0o700)
    sources = {}
    for name in policy.FILES:
        raw = ("# fixture source: " + name + "\n").encode()
        path = tmp_path / policy.CODE_ROOT.lstrip("/") / name
        path.write_bytes(raw)
        path.chmod(0o444)
        sources[name] = hashlib.sha256(raw).hexdigest()
    manifest = tmp_path / policy.MANIFEST.lstrip("/")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": policy.PROFILE,
                "collector": {"name": policy.ACCOUNT, "uid": user.pw_uid, "gid": user.pw_gid},
                "files": sources,
            }
        )
    )
    manifest.chmod(0o600)
    return tmp_path, users, groups


def local_path(policy, staged, path):
    return staged[0] / path.lstrip("/")


def test_valid_installation_holds_selected_bytes_and_allows_owned_scope_creation(policy, staged):
    install = policy.TrustedInstallation()
    try:
        assert install.source("collector_launcher.py").startswith(b"# fixture")
        assert install.account["uid"] == 12345
        (local_path(policy, staged, policy.STORAGE_ROOT) / "consumed-scope").mkdir()
        install.verify()  # Directory link/mtime changes are not identity changes.
        with pytest.raises(ValueError, match="unknown_source"):
            install.source("../../arbitrary.py")
    finally:
        install.close()
    with pytest.raises(ValueError, match="closed"):
        install.source("collector_launcher.py")


@pytest.mark.parametrize(
    "damage",
    [
        "ancestor_symlink",
        "file_symlink",
        "hardlink",
        "fifo",
        "code_mode",
        "manifest_mode",
        "storage_mode",
        "ancestor_write",
        "hash",
        "missing",
        "extra_source",
        "bool_uid",
    ],
)
def test_invalid_installation_is_refused_and_closes_all_descriptors(policy, staged, damage):
    root = staged[0]
    code = local_path(policy, staged, policy.CODE_ROOT + "/collector_launcher.py")
    manifest = local_path(policy, staged, policy.MANIFEST)
    if damage == "ancestor_symlink":
        original = root / "usr"
        original.rename(root / "moved")
        original.symlink_to(root / "moved", target_is_directory=True)
    elif damage == "file_symlink":
        code.rename(code.with_name("moved.py"))
        code.symlink_to(code.with_name("moved.py"))
    elif damage == "hardlink":
        os.link(code, code.with_name("alias.py"))
    elif damage == "fifo":
        code.unlink()
        os.mkfifo(code, 0o444)
    elif damage == "code_mode":
        code.chmod(0o644)
    elif damage == "manifest_mode":
        manifest.chmod(0o644)
    elif damage == "storage_mode":
        local_path(policy, staged, policy.STORAGE_ROOT).chmod(0o755)
    elif damage == "ancestor_write":
        (root / "usr").chmod(0o777)
    elif damage == "hash":
        code.chmod(0o644)
        code.write_bytes(b"changed")
        code.chmod(0o444)
    elif damage == "missing":
        code.unlink()
    else:
        value = json.loads(manifest.read_bytes())
        if damage == "extra_source":
            value["files"]["arbitrary.py"] = "0" * 64
        else:
            value["collector"]["uid"] = True
        manifest.write_text(json.dumps(value))
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises((OSError, ValueError)):
        policy.TrustedInstallation()
    assert len(list(Path("/proc/self/fd").iterdir())) == before


@pytest.mark.parametrize(
    "damage",
    [
        "replace_code",
        "change_bytes",
        "replace_directory",
        "permissions",
        "account_uid",
        "extra_group",
        "mount_namespace",
    ],
)
def test_changed_authority_permanently_invalidates_open_installation(
    policy, staged, monkeypatch, damage
):
    install = policy.TrustedInstallation()
    code = local_path(policy, staged, policy.CODE_ROOT + "/collector_launcher.py")
    if damage == "replace_code":
        raw = code.read_bytes()
        code.unlink()
        code.write_bytes(raw)
        code.chmod(0o444)
    elif damage == "change_bytes":
        code.chmod(0o644)
        code.write_bytes(b"changed")
        code.chmod(0o444)
    elif damage == "replace_directory":
        directory = local_path(policy, staged, policy.CODE_ROOT)
        directory.rename(directory.with_name("old"))
        directory.mkdir()
    elif damage == "permissions":
        local_path(policy, staged, policy.STORAGE_ROOT).chmod(0o777)
    elif damage == "account_uid":
        staged[1][0].pw_uid += 1
    elif damage == "extra_group":
        staged[2].append(SimpleNamespace(gr_name="docker", gr_gid=12347, gr_mem=[policy.ACCOUNT]))
    else:
        monkeypatch.setattr(policy.os, "readlink", lambda path: "mnt:changed")
    with pytest.raises((OSError, ValueError)):
        install.verify()
    assert install.closed
    with pytest.raises(ValueError, match="closed"):
        install.source("collector_launcher.py")


@pytest.mark.parametrize(
    "damage",
    [
        "root_uid",
        "root_gid",
        "login_shell",
        "home",
        "alias_uid",
        "shared_gid",
        "group_alias",
        "other_member",
    ],
)
def test_account_must_be_dedicated_and_noninteractive(policy, staged, damage):
    _, users, groups = staged
    user = users[0]
    if damage == "root_uid":
        user.pw_uid = 0
    elif damage == "root_gid":
        user.pw_gid = 0
    elif damage == "login_shell":
        user.pw_shell = "/bin/bash"
    elif damage == "home":
        user.pw_dir = "/home/user"
    elif damage in {"alias_uid", "shared_gid"}:
        users.append(
            SimpleNamespace(
                pw_name="other",
                pw_uid=user.pw_uid if damage == "alias_uid" else 9999,
                pw_gid=user.pw_gid if damage == "shared_gid" else 9999,
            )
        )
    elif damage == "group_alias":
        groups.append(SimpleNamespace(gr_name="alias", gr_gid=user.pw_gid, gr_mem=[]))
    else:
        groups[0].gr_mem = ["other"]
    with pytest.raises(ValueError, match="account_policy"):
        policy._account()


def test_owner_mismatch_is_rejected(policy, staged, monkeypatch):
    monkeypatch.setattr(policy, "AUTHORITY_UID", os.getuid() + 1)
    with pytest.raises(ValueError, match="directory_authority"):
        policy.TrustedInstallation()


def test_cli_is_read_only_private_and_never_admits(policy, staged, tmp_path, capsys):
    output = tmp_path / "report.json"
    assert policy.main(["--report", str(output)]) == 2
    raw = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    result = json.loads(raw)
    assert result["status"] == "local_installation_observed_not_authorized"
    assert not result["network_admitted"] and not result["host_deployment_qualified"]
    assert result["venue_requests_made"] == 0
    assert json.loads(capsys.readouterr().out)["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert policy.main(["--report", str(output)]) == 1
    assert output.read_bytes() == raw


def test_cli_missing_installation_reports_without_provisioning(policy, staged, tmp_path):
    local_path(policy, staged, policy.MANIFEST).unlink()
    output = tmp_path / "report"
    assert policy.main(["--report", str(output)]) == 2
    assert json.loads(output.read_bytes())["status"] == "installation_missing_unreadable_or_invalid"
    assert not local_path(policy, staged, policy.MANIFEST).exists()


def test_foreign_process_cannot_use_or_close_authority_handles(policy, staged):
    install = policy.TrustedInstallation()
    owner = install.owner_pid
    try:
        install.owner_pid += 1
        with pytest.raises(ValueError, match="foreign_owner"):
            install.verify()
        with pytest.raises(ValueError, match="foreign_owner"):
            install.close()
    finally:
        install.owner_pid = owner
        install.close()

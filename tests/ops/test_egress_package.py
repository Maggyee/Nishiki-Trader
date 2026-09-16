"""Bundle rejection and private-root provisioning; never provision the real host."""

import importlib.util
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load(name):
    spec = importlib.util.spec_from_file_location("test_egress_" + name, DIRECTORY / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package():
    return load("package")


def test_reproducible_bundle_with_only_reviewed_sources(package):
    raw = package.build()
    assert raw == package.build()
    contents = package.inspect(raw, package.digest(raw))
    assert tuple(contents) == package.MEMBERS
    for name in package.FILES:
        assert contents[name] == (DIRECTORY / name).read_bytes()
    assert contents["install.py"] == (DIRECTORY / "package.py").read_bytes()
    assert json.loads(contents["bundle.json"])["manifest_schema_version"].endswith(".v2")


def changed_archive(raw, damage):
    target = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as old,
        tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as new,
    ):
        for index, member in enumerate(old):
            data = old.extractfile(member).read()
            if index == 0:
                if damage == "missing":
                    continue
                if damage in {"traversal", "absolute", "alias"}:
                    member.name = {
                        "traversal": "../escape",
                        "absolute": "/escape",
                        "alias": "./collector_launcher.py",
                    }[damage]
                elif damage in {"symlink", "hardlink", "fifo", "directory"}:
                    member.type = {
                        "symlink": tarfile.SYMTYPE,
                        "hardlink": tarfile.LNKTYPE,
                        "fifo": tarfile.FIFOTYPE,
                        "directory": tarfile.DIRTYPE,
                    }[damage]
                    member.linkname = "/tmp/escape"
                    member.size = 0
                    data = b""
                elif damage == "mode":
                    member.mode = 0o777
                elif damage == "owner":
                    member.uid = 1000
                elif damage == "time":
                    member.mtime = 1
                elif damage == "oversize":
                    member.size = 1024 * 1024 + 1
                    data = b"x" * member.size
                elif damage == "content":
                    data = b"x" * len(data)
            new.addfile(member, io.BytesIO(data))
            if index == 0 and damage == "duplicate":
                new.addfile(member, io.BytesIO(data))
        if damage == "extra":
            new.addfile(tarfile.TarInfo("extra"), io.BytesIO())
    return target.getvalue()


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "traversal",
        "absolute",
        "alias",
        "symlink",
        "hardlink",
        "fifo",
        "directory",
        "mode",
        "owner",
        "time",
        "oversize",
        "content",
        "duplicate",
        "extra",
        "trailing",
        "truncated",
        "pin",
    ],
)
def test_archive_rejected_without_extraction(package, tmp_path, damage):
    raw = package.build()
    if damage == "trailing":
        raw += b"hidden"
    elif damage == "truncated":
        raw = raw[:700]
    elif damage != "pin":
        raw = changed_archive(raw, damage)
    expected = "0" * 64 if damage == "pin" else package.digest(raw)
    with pytest.raises((ValueError, tarfile.TarError)):
        package.inspect(raw, expected)
    assert not list(tmp_path.iterdir())


def test_cli_build_exclusive_and_inspect_is_inactive(package, tmp_path, capsys):
    path = tmp_path / "bundle.tar"
    assert package.main(["build", "--output", str(path)]) == 0
    raw = path.read_bytes()
    result = json.loads(capsys.readouterr().out)
    assert not result["network_admitted"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert package.main(["build", "--output", str(path)]) == 1
    assert path.read_bytes() == raw
    assert package.main(["inspect", "--bundle", str(path), "--sha256", package.digest(raw)]) == 0


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversize"])
def test_input_file_is_bounded_regular_nofollow(package, tmp_path, kind):
    path = tmp_path / "input"
    if kind == "symlink":
        path.symlink_to(DIRECTORY / "installation.py")
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"a" * 10)
    with pytest.raises((OSError, ValueError)):
        package.read_file(path, 9)


def test_checkout_cannot_act_as_privileged_installer(package):
    raw = package.build()
    with pytest.raises(ValueError):
        package.trusted_installer(package.inspect(raw, package.digest(raw)))


@pytest.fixture
def staged(package, monkeypatch, tmp_path):
    # Real file operations in a private directory with simulated account commands.
    # No claim of root ownership, actual useradd or cross-UID isolation follows.
    def root_fd():
        return os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    monkeypatch.setattr(package, "AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(package, "_root_fd", root_fd)
    monkeypatch.setattr(package, "trusted_installer", lambda contents: None)
    policy = load("installation")
    monkeypatch.setattr(policy, "AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(policy, "_root_fd", root_fd)
    monkeypatch.setattr(package, "verifier", lambda contents: policy)
    users, groups, commands = [], [], []
    monkeypatch.setattr(package.pwd, "getpwall", lambda: users)
    monkeypatch.setattr(package.grp, "getgrall", lambda: groups)

    def command(args):
        commands.append(args)
        if args[0] == "/usr/sbin/useradd":
            users.append(
                SimpleNamespace(
                    pw_name=package.ACCOUNT,
                    pw_uid=12345,
                    pw_gid=12346,
                    pw_dir="/nonexistent",
                    pw_shell="/usr/sbin/nologin",
                )
            )
            groups.append(SimpleNamespace(gr_name=package.ACCOUNT, gr_gid=12346, gr_mem=[]))
            return ""
        assert args == ["/usr/bin/passwd", "-S", package.ACCOUNT]
        return package.ACCOUNT + " L 2026-09-16 0 99999 7 -1\n"

    monkeypatch.setattr(package, "command", command)
    raw = package.build()
    return SimpleNamespace(
        root=tmp_path,
        contents=package.inspect(raw, package.digest(raw)),
        policy=policy,
        commands=commands,
        users=users,
        groups=groups,
    )


def local(staged, path):
    return staged.root / path.lstrip("/")


def test_install_publishes_manifest_last_preserves_consumed_storage(package, staged, monkeypatch):
    storage = local(staged, package.STORAGE)
    storage.mkdir(parents=True, mode=0o700)
    consumed = storage / "consumed"
    consumed.write_bytes(b"do not reset")
    writes = []
    write = package.Tree.write

    def traced(tree, parent, name, raw, mode):
        writes.append(name)
        if name != "egress-install.json":
            assert not local(staged, package.MANIFEST).exists()
        write(tree, parent, name, raw, mode)

    monkeypatch.setattr(package.Tree, "write", traced)
    package.apply(staged.contents)
    assert writes == [*package.FILES, "egress-install.json"]
    assert consumed.read_bytes() == b"do not reset"
    installation = staged.policy.TrustedInstallation()
    installation.close()
    assert [args[0] for args in staged.commands].count("/usr/sbin/useradd") == 1
    before = list(staged.commands)
    with pytest.raises(ValueError, match="existing_or_partial"):
        package.apply(staged.contents)
    assert before == staged.commands
    assert local(staged, package.CODE).stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(
    "damage",
    [
        "code",
        "manifest",
        "symlink",
        "writable_parent",
        "storage_mode",
        "group_only",
        "user_policy",
        "unlocked",
    ],
)
def test_preflight_refuses_before_mutation(package, staged, monkeypatch, damage):
    if damage == "code":
        local(staged, package.CODE).mkdir(parents=True)
    elif damage == "manifest":
        path = local(staged, package.MANIFEST)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"old")
    elif damage == "symlink":
        local(staged, "/usr").symlink_to(staged.root / "outside")
    elif damage == "writable_parent":
        local(staged, "/usr").mkdir(mode=0o777)
        local(staged, "/usr").chmod(0o777)
    elif damage == "storage_mode":
        local(staged, package.STORAGE).mkdir(parents=True, mode=0o755)
    elif damage == "group_only":
        staged.groups.append(SimpleNamespace(gr_name=package.ACCOUNT))
    else:
        package.command(["/usr/sbin/useradd"])
        staged.commands.clear()
        if damage == "user_policy":
            staged.users[0].pw_shell = "/bin/bash"
        else:
            monkeypatch.setattr(package, "command", lambda args: package.ACCOUNT + " P date")
    before = sorted(str(p.relative_to(staged.root)) for p in staged.root.rglob("*"))
    with pytest.raises((OSError, ValueError)):
        package.apply(staged.contents)
    after = sorted(str(p.relative_to(staged.root)) for p in staged.root.rglob("*"))
    assert after == before
    assert not staged.commands


@pytest.mark.parametrize("stage", ["account", "code_write", "manifest_write", "final_check"])
def test_failure_retains_partial_marker_and_forbids_retry(package, staged, monkeypatch, stage):
    command, write = package.command, package.Tree.write

    def fail_command(args):
        if args[0] == "/usr/sbin/useradd":
            raise subprocess.CalledProcessError(1, args)
        return command(args)

    def fail_write(tree, parent, name, raw, mode):
        if name == ("egress-install.json" if stage == "manifest_write" else package.FILES[1]):
            raise OSError("injected disk failure")
        write(tree, parent, name, raw, mode)

    if stage == "account":
        monkeypatch.setattr(package, "command", fail_command)
    elif stage == "final_check":
        monkeypatch.setattr(
            staged.policy,
            "TrustedInstallation",
            lambda: (_ for _ in ()).throw(ValueError("check failed")),
        )
    else:
        monkeypatch.setattr(package.Tree, "write", fail_write)
    before_fds = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises((OSError, ValueError, subprocess.SubprocessError)):
        package.apply(staged.contents)
    assert len(list(Path("/proc/self/fd").iterdir())) == before_fds
    assert local(staged, package.CODE).is_dir()
    if stage != "final_check":
        assert not local(staged, package.MANIFEST).exists()
    with pytest.raises(ValueError, match="existing_or_partial"):
        package.apply(staged.contents)


def test_existing_correct_account_is_reused(package, staged):
    package.command(["/usr/sbin/useradd"])
    staged.commands.clear()
    package.apply(staged.contents)
    assert all(args[0] == "/usr/bin/passwd" for args in staged.commands)


def test_bundle_pin_failure_precedes_apply(package, tmp_path, monkeypatch):
    path = tmp_path / "bundle"
    path.write_bytes(package.build())
    monkeypatch.setattr(package, "apply", lambda _: pytest.fail("unverified apply"))
    assert package.main(["apply", "--bundle", str(path), "--sha256", "0" * 64]) == 1


@pytest.mark.parametrize("argument", [[], ["--check"], ["--launch"]])
def test_entry_refuses_checkout_even_with_isolated_python(argument):
    result = subprocess.run(
        ["/usr/bin/python3", "-I", str(DIRECTORY / "helper_entry.py"), *argument],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "fixed_installed_check_required"


@pytest.fixture
def entry(monkeypatch, tmp_path):
    module = load("helper_entry")
    monkeypatch.setattr(module, "AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(module, "_root_fd", lambda: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY))
    code = tmp_path / module.DIRECTORY.lstrip("/")
    code.mkdir(parents=True)
    verifier = code / "installation.py"
    verifier.write_text("class TrustedInstallation: pass\n")
    verifier.chmod(0o444)
    return module, code


def test_entry_reads_trusted_verifier_and_closes_fds(entry):
    module, _ = entry
    before = len(list(Path("/proc/self/fd").iterdir()))
    assert module.load_verifier().__name__ == "TrustedInstallation"
    assert before == len(list(Path("/proc/self/fd").iterdir()))


@pytest.mark.parametrize("damage", ["ancestor", "owner", "mode", "symlink", "hardlink", "fifo"])
def test_entry_rejects_untrusted_verifier_before_execution(entry, monkeypatch, damage):
    module, code = entry
    path = code / "installation.py"
    if damage == "ancestor":
        code.chmod(0o777)
    elif damage == "owner":
        monkeypatch.setattr(module, "AUTHORITY_UID", os.getuid() + 1)
    elif damage == "mode":
        path.chmod(0o644)
    elif damage == "hardlink":
        os.link(path, code / "alias")
    else:
        path.unlink()
        if damage == "symlink":
            path.symlink_to(DIRECTORY / "installation.py")
        else:
            os.mkfifo(path)
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises((OSError, ValueError)):
        module.load_verifier()
    assert before == len(list(Path("/proc/self/fd").iterdir()))


@pytest.mark.parametrize("valid", [True, False])
def test_installed_check_never_admits_or_starts_collector(entry, monkeypatch, capsys, valid):
    module, _ = entry
    calls = []

    class Installation:
        def verify(self):
            calls.append("verify")
            if not valid:
                raise ValueError("blocked")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(
        module,
        "sys",
        SimpleNamespace(argv=[module.ENTRY, "--check"], flags=SimpleNamespace(isolated=True)),
    )
    monkeypatch.setattr(module, "__file__", module.ENTRY)
    monkeypatch.setattr(module, "load_verifier", lambda: Installation)
    assert module.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == (
        "installation_verified_inactive" if valid else "installation_check_blocked"
    )
    assert not result["network_admitted"] and not result["collector_started"]
    assert not result["host_deployment_qualified"]
    assert calls == ["verify", "close"]


@pytest.mark.parametrize(
    "damage", [None, "bytes", "mode", "hardlink", "parent", "symlink", "not_isolated", "not_root"]
)
def test_installer_requires_protected_matching_source(package, monkeypatch, tmp_path, damage):
    raw = package.build()
    contents = package.inspect(raw, package.digest(raw))
    directory = tmp_path / "review"
    directory.mkdir()
    path = directory / "install.py"
    path.write_bytes(contents["install.py"])
    path.chmod(0o444)
    monkeypatch.setattr(package, "__file__", "/review/install.py")
    monkeypatch.setattr(package, "AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(
        package, "_root_fd", lambda: os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    )
    monkeypatch.setattr(
        package, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=damage != "not_isolated"))
    )
    monkeypatch.setattr(package.os, "getuid", lambda: 1 if damage == "not_root" else 0)
    monkeypatch.setattr(package.os, "geteuid", lambda: 1 if damage == "not_root" else 0)
    if damage == "bytes":
        path.chmod(0o644)
        path.write_bytes(b"changed")
        path.chmod(0o444)
    elif damage == "mode":
        path.chmod(0o644)
    elif damage == "hardlink":
        os.link(path, directory / "alias")
    elif damage == "parent":
        directory.chmod(0o777)
    elif damage == "symlink":
        path.rename(directory / "original")
        path.symlink_to(directory / "original")
    before = len(list(Path("/proc/self/fd").iterdir()))
    if damage is None:
        package.trusted_installer(contents)
    else:
        with pytest.raises((OSError, ValueError)):
            package.trusted_installer(contents)
    assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_directory_fsync_failure_closes_new_descriptor(package, staged, monkeypatch):
    fsync = package.os.fsync
    calls = []

    def fail(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError("directory fsync failed")
        fsync(fd)

    monkeypatch.setattr(package.os, "fsync", fail)
    before = len(list(Path("/proc/self/fd").iterdir()))
    tree = package.Tree()
    try:
        with pytest.raises(OSError, match="fsync failed"):
            tree.directory("/new", create=True)
    finally:
        tree.close()
    assert before == len(list(Path("/proc/self/fd").iterdir()))


def test_installer_manifest_schema_and_loaded_verifier_agree(package):
    contents = package.inspect(package.build(), package.digest(package.build()))
    policy = package.verifier(contents)
    assert json.loads(contents["bundle.json"])["manifest_schema_version"] == policy.PROFILE
    assert policy.FILES == package.FILES

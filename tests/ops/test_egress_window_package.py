"""First-install-only joint-window archive and private filesystem acceptance."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load():
    spec = importlib.util.spec_from_file_location(
        "test_joint_window_package", DIRECTORY / "gateway_window_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package():
    return load()


def test_fixed_bundle_reproducible_and_no_extra_sources(package):
    raw = package.build()
    assert raw == package.build()
    contents = package.inspect(raw, package.digest(raw))
    assert tuple(contents) == package.MEMBERS
    assert all(contents[name] == (DIRECTORY / name).read_bytes() for name in package.FILES)
    assert contents["install.py"] == (DIRECTORY / "gateway_window_package.py").read_bytes()
    document = json.loads(contents["bundle.json"])
    assert document["base_helper_sha256"] == package.BASE_PIN
    assert document["manifest_schema_version"] == package.PROFILE
    assert document["files"]["gateway_window_entry.py"] == package.ENTRY_PIN


@pytest.mark.parametrize(
    "damage",
    ["wrong_pin", "alias", "mode", "missing", "extra", "trailing", "symlink", "duplicate"],
)
def test_archive_rejects_unselected_or_noncanonical_bytes(package, damage):
    raw = package.build()
    if damage == "wrong_pin":
        with pytest.raises(ValueError, match="joint_bundle_size_or_sha256"):
            package.inspect(raw, "0" * 64)
        return
    if damage == "trailing":
        raw += b"unreviewed"
    else:
        output = io.BytesIO()
        with (
            tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as old,
            tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as new,
        ):
            for index, member in enumerate(old):
                data = old.extractfile(member).read()
                if index == 0:
                    if damage == "missing":
                        continue
                    if damage == "alias":
                        member.name = "./" + member.name
                    elif damage == "mode":
                        member.mode = 0o777
                    elif damage == "symlink":
                        member.type = tarfile.SYMTYPE
                        member.linkname = "../outside"
                        member.size = 0
                        data = b""
                new.addfile(member, io.BytesIO(data))
                if index == 0 and damage == "duplicate":
                    new.addfile(member, io.BytesIO(data))
            if damage == "extra":
                new.addfile(tarfile.TarInfo("extra"), io.BytesIO())
        raw = output.getvalue()
    with pytest.raises((ValueError, tarfile.TarError)):
        package.inspect(raw, package.digest(raw))


@pytest.mark.parametrize("damage", ["symlink", "oversize"])
def test_source_input_requires_bounded_regular_file(package, tmp_path, damage):
    path = tmp_path / "source"
    if damage == "symlink":
        path.symlink_to(DIRECTORY / "gateway_window_entry.py")
    else:
        path.write_bytes(b"a" * 10)
    with pytest.raises((OSError, ValueError)):
        package.read_file(path, 9)


def test_reinventoried_entry_drift_still_rejected(package):
    raw = package.build()
    contents = package.inspect(raw, package.digest(raw))
    contents["gateway_window_entry.py"] += b"\n"
    contents["bundle.json"] = package.json_bytes(package.inventory(contents))
    changed = package.archive(contents)
    with pytest.raises(ValueError, match="joint_bundle_noncanonical_or_inventory_changed"):
        package.inspect(changed, package.digest(changed))


def test_protected_installer_refuses_noncanonical_path(package):
    with pytest.raises(ValueError, match="joint_installer_canonical_path_required"):
        package.protected_bytes("/run/../run/window-install.py")


def test_cli_build_inspect_and_checkout_apply_refused(package, tmp_path, capsys):
    path = tmp_path / "bundle.tar"
    assert package.main(["build", "--output", str(path)]) == 0
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(capsys.readouterr().out)["network_admitted"] is False
    assert package.main(["build", "--output", str(path)]) == 1
    raw = path.read_bytes()
    assert package.main(["inspect", "--bundle", str(path), "--sha256", package.digest(raw)]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as missing:
        package.main(["apply", "--bundle", str(path), "--sha256", package.digest(raw)])
    assert missing.value.code == 2
    assert (
        package.main(
            [
                "apply",
                "--bundle",
                str(path),
                "--sha256",
                package.digest(raw),
                "--base-sha256",
                FakeAuthority.manifest_sha256,
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "joint_window_bundle_operation_failed"
    assert path.read_bytes() == raw


class FakeAuthority:
    manifest_sha256 = "a" * 64

    def __init__(self, root):
        self.root = root
        self.fds = []
        self.closed = False

    def open_directory(self, path):
        self.verify()
        fd = os.open(self.root / path.lstrip("/"), os.O_RDONLY | os.O_DIRECTORY)
        self.fds.append(fd)
        return fd

    def verify(self):
        if self.closed:
            raise ValueError("fake_base_closed")

    def close(self):
        if not self.closed:
            self.closed = True
            for fd in reversed(self.fds):
                os.close(fd)


@pytest.fixture
def staged(package, tmp_path, monkeypatch):
    for directory in (package.CODE, str(Path(package.MANIFEST).parent)):
        (tmp_path / directory.lstrip("/")).mkdir(parents=True)
    contents = package.inspect(package.build(), package.digest(package.build()))
    authorities = []

    def authority():
        instance = FakeAuthority(tmp_path)
        authorities.append(instance)
        return instance

    monkeypatch.setattr(
        package, "os", SimpleNamespace(**{**vars(os), "getuid": lambda: 0, "geteuid": lambda: 0})
    )
    monkeypatch.setattr(package, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(package, "protected_bytes", lambda path: contents["install.py"])
    monkeypatch.setattr(package, "held_base", authority)
    published = []
    monkeypatch.setattr(package, "verify_published", lambda holder, raw: published.append(raw))
    return SimpleNamespace(
        package=package,
        root=tmp_path,
        contents=contents,
        authorities=authorities,
        published=published,
    )


def local(staged, path):
    return staged.root / path.lstrip("/")


def test_first_install_publishes_manifest_last_and_rejects_second(staged, monkeypatch):
    package = staged.package
    calls = []
    original = package.write

    def traced(parent, name, raw, mode):
        calls.append(name)
        if name != Path(package.MANIFEST).name:
            assert not local(staged, package.MANIFEST).exists()
        original(parent, name, raw, mode)

    monkeypatch.setattr(package, "write", traced)
    package.apply(staged.contents, FakeAuthority.manifest_sha256)
    assert calls == [*package.FILES, Path(package.MANIFEST).name]
    assert staged.published == [staged.contents["gateway_window_sources.py"]]
    assert all(authority.closed for authority in staged.authorities)
    document = json.loads(local(staged, package.MANIFEST).read_bytes())
    assert document == {
        "schema_version": package.PROFILE,
        "base_manifest_sha256": FakeAuthority.manifest_sha256,
        "files": {name: package.digest(staged.contents[name]) for name in package.FILES},
    }
    assert local(staged, package.MANIFEST).stat().st_mode & 0o777 == 0o600
    assert all(
        local(staged, package.CODE + "/" + name).stat().st_mode & 0o777 == 0o444
        for name in package.FILES
    )
    before = local(staged, package.MANIFEST).read_bytes()
    with pytest.raises(ValueError, match="joint_existing_or_partial"):
        package.apply(staged.contents, FakeAuthority.manifest_sha256)
    assert local(staged, package.MANIFEST).read_bytes() == before
    assert all(authority.closed for authority in staged.authorities)


@pytest.mark.parametrize("base_pin", ["0" * 64, "A" * 64, "a" * 63, "g" * 64])
def test_base_manifest_selection_refused_before_write(staged, monkeypatch, base_pin):
    package = staged.package
    monkeypatch.setattr(package, "write", lambda *args: pytest.fail("write before base pin"))
    with pytest.raises(ValueError, match="joint_base_manifest_sha256"):
        package.apply(staged.contents, base_pin)
    assert not local(staged, package.MANIFEST).exists()
    assert not local(staged, package.CODE + "/" + package.FILES[0]).exists()
    assert all(authority.closed for authority in staged.authorities)


@pytest.mark.parametrize("damage", ["source", "manifest", "symlink"])
def test_preflight_refuses_existing_or_partial_state_before_write(staged, monkeypatch, damage):
    package = staged.package
    target = local(
        staged, package.MANIFEST if damage == "manifest" else package.CODE + "/" + package.FILES[0]
    )
    if damage == "symlink":
        target.symlink_to(staged.root / "outside")
    else:
        target.write_bytes(b"preexisting")
    monkeypatch.setattr(package, "write", lambda *args: pytest.fail("write before preflight"))
    with pytest.raises(ValueError, match="joint_existing_or_partial"):
        package.apply(staged.contents, FakeAuthority.manifest_sha256)
    assert all(authority.closed for authority in staged.authorities)


@pytest.mark.parametrize("stage", ["source", "manifest", "verify"])
def test_partial_failure_blocks_retry_without_clobbering_base(staged, monkeypatch, stage):
    package = staged.package
    original = package.write

    def failed_write(parent, name, raw, mode):
        if name == (Path(package.MANIFEST).name if stage == "manifest" else package.FILES[1]):
            raise OSError("injected_write_failure")
        original(parent, name, raw, mode)

    if stage == "verify":
        monkeypatch.setattr(
            package,
            "verify_published",
            lambda *args: (_ for _ in ()).throw(ValueError("invalid_install")),
        )
    else:
        monkeypatch.setattr(package, "write", failed_write)
    with pytest.raises((OSError, ValueError)):
        package.apply(staged.contents, FakeAuthority.manifest_sha256)
    assert local(staged, package.CODE + "/" + package.FILES[0]).exists()
    assert all(authority.closed for authority in staged.authorities)
    with pytest.raises(ValueError, match="joint_existing_or_partial"):
        package.apply(staged.contents, FakeAuthority.manifest_sha256)

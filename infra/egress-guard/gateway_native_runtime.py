"""Freeze a minimal native child runtime; root only copies and verifies opaque bytes."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = "/run/trader-native-runtime"
PYTHON = ROOT + "/bin/python3.12"
PROFILE = "portfolio.fixture_native_runtime.v1"
VERSION = "1.226.0"
LIMIT = 256 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def valid_name(name):
    parts = PurePosixPath(name).parts
    return (
        isinstance(name, str)
        and parts
        and not name.startswith("/")
        and all(part not in {".", "..", ""} for part in name.split("/"))
        and (name == "bin/python3.12" or name.startswith("lib/"))
        and str(PurePosixPath(name)) == name
    )


def build():
    """Ordinary-user project Python only; never call from the root worker."""
    if os.geteuid() == 0 or sys.version_info[:2] != (3, 12):
        raise ValueError("ordinary_project_python312_required")
    from nautilus_trader.core import nautilus_pyo3

    if nautilus_pyo3.NAUTILUS_VERSION != VERSION:
        raise ValueError("native_version_changed")
    base = Path(sys.base_prefix).resolve()
    paths = {"bin/python3.12": Path(sys.executable).resolve()}
    for path in (base / "lib").rglob("*"):
        relative = path.relative_to(base).as_posix()
        if any(p in {"__pycache__", "site-packages", "ensurepip"} for p in path.parts):
            continue
        if path.is_file() and (path.suffix == ".py" or ".so" in path.name):
            if not path.resolve().is_relative_to(base):
                raise ValueError("runtime_source_escape")
            paths[relative] = path
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename or "/site-packages/nautilus_trader/" not in filename:
            continue
        suffix = filename.split("/site-packages/", 1)[1]
        paths["lib/python3.12/site-packages/" + suffix] = Path(filename)
    pins, total = {}, 0
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, path in sorted(paths.items()):
            if not valid_name(name):
                raise ValueError("runtime_name")
            raw = path.read_bytes()
            total += len(raw)
            if total > LIMIT:
                raise ValueError("runtime_size")
            pins[name] = digest(raw)
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
        raw = canonical({"profile": PROFILE, "native_version": VERSION, "files": pins})
        info = tarfile.TarInfo("manifest.json")
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


def stage(raw, expected_sha256, run):
    """Disposable namespace worker only; no tar extraction or executable imports."""
    if os.geteuid() != 0 or len(raw) > LIMIT or digest(raw) != expected_sha256:
        raise ValueError("selected_native_bundle_required")
    root = Path(ROOT)
    root.mkdir(mode=0o755)  # /run itself is already private fixture tmpfs.
    run("/usr/bin/mount", "-t", "tmpfs", "-o", "size=384m,nosuid,nodev", "tmpfs", ROOT)
    seen, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            name = member.name
            if (
                not member.isfile()
                or name in seen
                or len(seen) >= 2000
                or (name != "manifest.json" and not valid_name(name))
                or member.size < 0
                or member.size > LIMIT - total
            ):
                raise ValueError("native_bundle_member")
            data = archive.extractfile(member).read(member.size + 1)
            if len(data) != member.size:
                raise ValueError("native_bundle_size")
            total += len(data)
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            with path.open("xb") as out:
                out.write(data)
            path.chmod(0o555 if name == "bin/python3.12" else 0o444)
            seen[name] = digest(data)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if (
        set(manifest) != {"profile", "native_version", "files"}
        or manifest["profile"] != PROFILE
        or manifest["native_version"] != VERSION
        or manifest["files"] != {k: v for k, v in seen.items() if k != "manifest.json"}
        or "bin/python3.12" not in manifest["files"]
    ):
        raise ValueError("native_bundle_inventory")
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    root.chmod(0o555)
    run("/usr/bin/mount", "-o", "remount,ro,nosuid,nodev", ROOT)
    return {
        "manifest_sha256": seen["manifest.json"],
        "files": len(manifest["files"]),
        "bytes": total,
    }


class NativeRuntime:
    """Hold hashed files and reject path/inode/metadata or readonly-mount changes."""

    def __init__(self, authority):
        self.fds = []
        try:
            fd = authority.open_file(ROOT + "/manifest.json", 0o444)
            raw = os.pread(fd, 1024 * 1024 + 1, 0)
            self.pin = digest(raw)
            manifest = json.loads(raw)
            if (
                set(manifest) != {"profile", "native_version", "files"}
                or manifest["profile"] != PROFILE
                or manifest["native_version"] != VERSION
                or not isinstance(manifest["files"], dict)
                or not 1 <= len(manifest["files"]) <= 2000
            ):
                raise ValueError("native_runtime_manifest")
            total = 0
            for name, pin in manifest["files"].items():
                if not valid_name(name):
                    raise ValueError("native_runtime_path")
                path = ROOT + "/" + name
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                info = os.fstat(fd)
                self.fds.append((path, fd, self.identity(info)))
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != 0
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != (0o555 if name == "bin/python3.12" else 0o444)
                ):
                    raise ValueError("native_runtime_ownership")
                total += info.st_size
                if total > LIMIT:
                    raise ValueError("native_runtime_size")
                hashed = hashlib.sha256()
                for offset in range(0, info.st_size, 1024 * 1024):
                    hashed.update(os.pread(fd, 1024 * 1024, offset))
                if hashed.hexdigest() != pin:
                    raise ValueError("native_runtime_digest")
            self.mount = self.mount_identity()
            self.verify()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def identity(info):
        return tuple(
            getattr(info, k)
            for k in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        )

    @staticmethod
    def mount_identity():
        rows = [
            line
            for line in Path("/proc/self/mountinfo").read_text().splitlines()
            if line.split()[4] == ROOT
        ]
        if len(rows) != 1 or not {"ro", "nosuid", "nodev"} <= set(rows[0].split()[5].split(",")):
            raise ValueError("native_readonly_mount_required")
        return rows[0]

    def verify(self):
        if not self.fds or self.mount_identity() != self.mount:
            raise ValueError("native_runtime_closed_or_remounted")
        for path, fd, expected in self.fds:
            if (
                self.identity(os.stat(path, follow_symlinks=False)) != expected
                or self.identity(os.fstat(fd)) != expected
            ):
                raise ValueError("native_runtime_changed")

    def close(self):
        for _, fd, _ in self.fds:
            os.close(fd)
        self.fds = []


if __name__ == "__main__":
    print(base64.b64encode(build()).decode())

"""Fixed joint-window bundle and first-install-only read-only extension."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path

CODE = "/usr/local/lib/trader-egress"
MANIFEST = "/etc/trader/joint-window-sources-v1.json"
BASE_HELPER = CODE + "/helper_entry.py"
BASE_PIN = "2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b"
ENTRY_PIN = "db9bacd6778111afdc4a163f305361bef6da8fecab56d5ec724b0d1cb66cdc7a"
SOURCES_PIN = "2c923d4b546fd0dbcbcf57fbfc4bafdb80e103611f0f38dcd9358cb6b6dea27f"
PROFILE = "portfolio.joint_window_sources.v1"
FILES = (
    "gateway_window_entry.py",
    "gateway_window_sources.py",
    "gateway_window_kernel.py",
    "gateway_window_custody.py",
    "gateway_window_witness.py",
    "gateway_window_activation.py",
)
MEMBERS = (*FILES, "install.py", "README.md", "bundle.json")
LIMIT = 1024 * 1024
BUNDLE_LIMIT = 10 * LIMIT
README = b"""# Read-only joint-window extension

Purpose: publish a fixed source inventory for the existing base installation.
Phase: offline review; deployment does not qualify egress or trading.
Boundaries: no nft changes, network request, collector, activation or retry.
Next entrypoint after separately reviewed first installation:
/usr/bin/python3 -I /usr/local/lib/trader-egress/gateway_window_entry.py --check
The check always exits 2 and keeps every admission field false.

Inspect and pin the complete archive and the existing base manifest independently.
Stage its install.py at a protected root-owned 0444 path outside the checkout.
Apply only with both reviewed SHA256 values; partial files block a second
attempt and require manual inspection.
The read-only audit compares installed sources with that selected archive;
it cannot attest the process that started the joint entry.
The check-entry operation executes selected entry bytes in this protected
process after and before source audits. It cannot attest other entry processes.
"""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(document):
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()


def read_file(path, limit=LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("joint_bundle_file_type_or_size")
        raw = os.pread(fd, limit + 1, 0)
        if len(raw) != before.st_size or identity(os.fstat(fd)) != identity(before):
            raise ValueError("joint_bundle_file_changed")
        return raw
    finally:
        os.close(fd)


def archive(contents):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in MEMBERS:
            info = tarfile.TarInfo(name)
            info.mode = 0o444
            info.size = len(contents[name])
            tar.addfile(info, io.BytesIO(contents[name]))
    return output.getvalue()


def inventory(contents):
    return {
        "schema_version": "portfolio.joint_window_bundle.v1",
        "manifest_schema_version": PROFILE,
        "base_helper_sha256": BASE_PIN,
        "files": {name: digest(contents[name]) for name in MEMBERS if name != "bundle.json"},
    }


def build():
    directory = Path(__file__).resolve().parent
    contents = {name: read_file(directory / name) for name in FILES}
    if (
        digest(contents["gateway_window_entry.py"]) != ENTRY_PIN
        or digest(contents["gateway_window_sources.py"]) != SOURCES_PIN
    ):
        raise ValueError("joint_bundle_inventory_pin_changed")
    contents.update({"install.py": read_file(__file__), "README.md": README})
    contents["bundle.json"] = json_bytes(inventory(contents))
    return archive(contents)


def inspect(raw, expected):
    if len(raw) > BUNDLE_LIMIT or digest(raw) != expected:
        raise ValueError("joint_bundle_size_or_sha256")
    contents = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        for name in MEMBERS:
            member = tar.next()
            if (
                member is None
                or member.name != name
                or not member.isreg()
                or member.size > LIMIT
                or member.size <= 0
            ):
                raise ValueError("joint_bundle_members")
            with tar.extractfile(member) as stream:
                contents[name] = stream.read(LIMIT + 1)
        if tar.next() is not None:
            raise ValueError("joint_bundle_extra_member")
    if (
        archive(contents) != raw
        or contents["bundle.json"] != json_bytes(inventory(contents))
        or contents["README.md"] != README
        or digest(contents["gateway_window_entry.py"]) != ENTRY_PIN
        or digest(contents["gateway_window_sources.py"]) != SOURCES_PIN
    ):
        raise ValueError("joint_bundle_noncanonical_or_inventory_changed")
    return contents


def identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def protected_bytes(path):
    path = str(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or str(Path(path)) != path
        or ".." in Path(path).parts
    ):
        raise ValueError("joint_installer_canonical_path_required")
    fds = []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fds.append(parent)
        for part in Path(path).parts[1:-1]:
            info = os.fstat(parent)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("joint_installer_untrusted_ancestor")
            parent = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            fds.append(parent)
        info = os.fstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("joint_installer_untrusted_parent")
        fd = os.open(
            Path(path).name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        fds.append(fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o444
            or not 0 < before.st_size <= LIMIT
        ):
            raise ValueError("joint_installer_untrusted_file")
        raw = os.pread(fd, LIMIT + 1, 0)
        if len(raw) != before.st_size or identity(os.fstat(fd)) != identity(before):
            raise ValueError("joint_installer_file_changed")
        return raw
    finally:
        for fd in reversed(fds):
            os.close(fd)


def held_base():
    raw = protected_bytes(BASE_HELPER)
    if digest(raw) != BASE_PIN:
        raise ValueError("joint_installer_base_helper_pin_changed")
    scope = {"__name__": "joint_window_installed_base"}
    exec(compile(raw, BASE_HELPER, "exec"), scope)
    return scope["load_verifier"]()()


def absent(parent, name):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ValueError("joint_existing_or_partial_installation")


def write(parent, name, raw, mode):
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
        dir_fd=parent,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())
    os.fsync(parent)


def verify_published(authority, raw):
    scope = {"__name__": "joint_window_installed_inventory"}
    exec(compile(raw, CODE + "/gateway_window_sources.py", "exec"), scope)
    held = scope["RootSelectedWindowSources"](authority)
    try:
        held.source("gateway_window_entry.py")
    finally:
        held.close()


def selected_base(contents, base_sha256):
    if len(base_sha256) != 64 or any(char not in "0123456789abcdef" for char in base_sha256):
        raise ValueError("joint_base_manifest_sha256_format")
    if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
        raise ValueError("joint_root_isolated_installer_required")
    if protected_bytes(__file__) != contents["install.py"]:
        raise ValueError("joint_installer_source_changed")
    authority = held_base()
    try:
        authority.verify()
        if authority.manifest_sha256 != base_sha256:
            raise ValueError("joint_base_manifest_sha256_mismatch")
        return authority
    except BaseException:
        authority.close()
        raise


def audit(contents, base_sha256):
    authority = selected_base(contents, base_sha256)
    try:
        scope = {"__name__": "joint_window_selected_inventory"}
        exec(
            compile(
                contents["gateway_window_sources.py"], CODE + "/gateway_window_sources.py", "exec"
            ),
            scope,
        )
        held = scope["RootSelectedWindowSources"](authority)
        try:
            for name in FILES:
                if held.source(name) != contents[name]:
                    raise ValueError("joint_installed_source_not_selected_bundle")
        finally:
            held.close()
    finally:
        authority.close()


def check_entry(contents, base_sha256):
    audit(contents, base_sha256)
    scope = {"__name__": "joint_window_selected_entry"}
    exec(
        compile(contents["gateway_window_entry.py"], CODE + "/gateway_window_entry.py", "exec"),
        scope,
    )
    try:
        if scope["_check"]() != "fixed_joint_window_sources_observed_unqualified":
            raise ValueError("joint_window_selected_entry_unexpected_status")
    finally:
        audit(contents, base_sha256)


def apply(contents, base_sha256):
    authority = selected_base(contents, base_sha256)
    try:
        code_fd = authority.open_directory(CODE)
        manifest_fd = authority.open_directory(str(Path(MANIFEST).parent))
        authority.verify()
        for name in FILES:
            absent(code_fd, name)
        absent(manifest_fd, Path(MANIFEST).name)
        for name in FILES:
            authority.verify()
            write(code_fd, name, contents[name], 0o444)
        authority.verify()
        write(
            manifest_fd,
            Path(MANIFEST).name,
            json_bytes(
                {
                    "schema_version": PROFILE,
                    "base_manifest_sha256": authority.manifest_sha256,
                    "files": {name: digest(contents[name]) for name in FILES},
                }
            ),
            0o600,
        )
        authority.verify()
        verify_published(authority, contents["gateway_window_sources.py"])
    finally:
        authority.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("build").add_argument("--output", type=Path, required=True)
    for action in ("inspect", "apply", "audit", "check-entry"):
        selected = commands.add_parser(action)
        selected.add_argument("--bundle", type=Path, required=True)
        selected.add_argument("--sha256", required=True)
        if action in ("apply", "audit", "check-entry"):
            selected.add_argument("--base-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            raw = build()
            inspect(raw, digest(raw))
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            status = "joint_window_bundle_built_inactive"
        else:
            raw = read_file(args.bundle, BUNDLE_LIMIT)
            contents = inspect(raw, args.sha256)
            if args.action == "apply":
                apply(contents, args.base_sha256)
                status = "joint_window_installed_inactive"
            elif args.action == "audit":
                audit(contents, args.base_sha256)
                status = "joint_window_installed_sources_observed_inactive"
            elif args.action == "check-entry":
                check_entry(contents, args.base_sha256)
                status = "joint_window_selected_entry_executed_unqualified"
            else:
                status = "joint_window_bundle_verified_inactive"
        print(
            json.dumps(
                {
                    "status": status,
                    "sha256": digest(raw),
                    "host_deployment_qualified": False,
                    "network_admitted": False,
                    "activation_history_verified": False,
                },
                sort_keys=True,
            )
        )
        return 2 if args.action == "check-entry" else 0
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError):
        print(
            json.dumps(
                {
                    "status": "joint_window_bundle_operation_failed",
                    "network_admitted": False,
                    "partial_installation_requires_inspection": args.action == "apply",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

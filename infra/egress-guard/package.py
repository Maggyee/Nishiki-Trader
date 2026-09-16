"""Offline bundle builder/reviewer and explicit first-install-only provisioner."""

from __future__ import annotations

import argparse
import grp
import hashlib
import io
import json
import os
import pwd
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

FILES = ("collector_launcher.py", "inspect_binding.py", "installation.py", "helper_entry.py")
MEMBERS = (*FILES, "install.py", "README.md", "bundle.json")
LIMIT = 1024 * 1024
BUNDLE_LIMIT = 8 * LIMIT
AUTHORITY_UID = 0
CODE = "/usr/local/lib/trader-egress"
MANIFEST = "/etc/trader/egress-install.json"
STORAGE = "/var/lib/trader/egress"
ACCOUNT = "trader-egress"
README = b"""# Inactive egress installation bundle

Purpose: stage fixed, reviewed code and a dedicated noninteractive account.
Phase: offline implementation; installation does not qualify host deployment.
Boundaries: no collector, network request, firewall, sudoers, service or scope reset.
Next entrypoint after separately authorized installation:
/usr/bin/python3 -I /usr/local/lib/trader-egress/helper_entry.py --check
The check always exits 2 and never grants admission.

Review the SHA256-pinned archive with package.py inspect before provisioning.
After review, an operator must stage the reviewed install.py as a root-owned,
single-link 0444 file under root-owned directories without group/other write.
Invoke /usr/bin/python3 -I /PROTECTED/install.py apply --bundle /BUNDLE --sha256 HASH.
The installer checks that its own bytes match the pinned bundle. Do not run the
checkout as root. It creates trader-egress only if both user and group are absent,
requires a locked password, writes four fixed sources and publishes the manifest
last. Existing code/manifest or any partial installation blocks another attempt.
Existing 0700 root-owned storage and consumed records are preserved. Failures
leave partial state for manual inspection; no automatic rollback or state deletion.
"""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def read_file(path, limit=LIMIT):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("bundle_file_type_or_size")
        raw = os.pread(fd, limit + 1, 0)
        if len(raw) > limit or len(raw) != info.st_size:
            raise ValueError("bundle_file_changed")
        return raw
    finally:
        os.close(fd)


def archive(contents):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in MEMBERS:
            info = tarfile.TarInfo(name)
            info.mode = 0o444
            info.size = len(contents[name])
            tar.addfile(info, io.BytesIO(contents[name]))
    return stream.getvalue()


def build():
    directory = Path(__file__).resolve().parent
    contents = {name: read_file(directory / name) for name in FILES}
    contents.update({"install.py": read_file(__file__), "README.md": README})
    contents["bundle.json"] = json_bytes(
        {
            "schema_version": "portfolio.egress_bundle.v1",
            "manifest_schema_version": "portfolio.egress_installation.v2",
            "files": {name: digest(raw) for name, raw in contents.items()},
        }
    )
    return archive(contents)


def inspect(raw, expected):
    if len(raw) > BUNDLE_LIMIT or digest(raw) != expected:
        raise ValueError("bundle_size_or_sha256")
    contents = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        for name in MEMBERS:
            member = tar.next()
            if (
                member is None
                or member.name != name
                or not member.isreg()
                or member.size > LIMIT
                or member.size < 0
            ):
                raise ValueError("bundle_members")
            with tar.extractfile(member) as stream:
                contents[name] = stream.read(LIMIT + 1)
        if tar.next() is not None:
            raise ValueError("bundle_extra_member")
    # Byte equality also rejects aliases, extensions, unsafe modes, links,
    # duplicates, noncanonical metadata, trailing payloads and padding changes.
    if archive(contents) != raw:
        raise ValueError("bundle_noncanonical")
    expected_document = {
        "schema_version": "portfolio.egress_bundle.v1",
        "manifest_schema_version": "portfolio.egress_installation.v2",
        "files": {name: digest(data) for name, data in contents.items() if name != "bundle.json"},
    }
    if contents["bundle.json"] != json_bytes(expected_document) or contents["README.md"] != README:
        raise ValueError("bundle_inventory")
    return contents


def _root_fd():
    return os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


class Tree:
    """Mutate only fixed locations through protected, held directory descriptors."""

    def __init__(self):
        self.fds = []
        self.root = _root_fd()
        self.fds.append(self.root)
        try:
            self.check(self.root)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def check(fd):
        info = os.fstat(fd)
        if info.st_uid != AUTHORITY_UID or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("untrusted_install_parent")

    def directory(self, path, *, create=False, missing_ok=False, mode=0o755):
        parent = self.root
        parts = Path(path).parts[1:]
        for index, part in enumerate(parts):
            created = False
            try:
                fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
                )
            except FileNotFoundError:
                if not create:
                    if missing_ok:
                        return None
                    raise
                selected_mode = mode if index == len(parts) - 1 else 0o755
                os.mkdir(part, selected_mode, dir_fd=parent)
                os.fsync(parent)
                fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
                )
                created = True
            self.fds.append(fd)
            if created:
                os.fchmod(fd, selected_mode)
                os.fsync(fd)
            self.check(fd)
            parent = fd
        return parent

    def absent(self, path):
        path = Path(path)
        parent = self.directory(str(path.parent), missing_ok=True)
        if parent is None:
            return
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ValueError("existing_or_partial_installation")

    def write(self, parent, name, raw, mode):
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

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


def trusted_installer(contents):
    if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
        raise ValueError("root_isolated_reviewed_installer_required")
    tree = Tree()
    try:
        path = Path(os.path.abspath(__file__))
        parent = tree.directory(str(path.parent))
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != AUTHORITY_UID
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o444
                or info.st_size > LIMIT
                or os.pread(fd, LIMIT + 1, 0) != contents["install.py"]
            ):
                raise ValueError("installer_authority_or_hash")
        finally:
            os.close(fd)
    finally:
        tree.close()


def verifier(contents):
    scope = {"__name__": "reviewed_installation"}
    exec(compile(contents["installation.py"], "installation.py", "exec"), scope)
    return SimpleNamespace(**scope)


def command(args):
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    ).stdout


def locked_account(policy):
    account = policy._account()
    fields = command(["/usr/bin/passwd", "-S", ACCOUNT]).split()
    if len(fields) < 2 or fields[:2] != [ACCOUNT, "L"]:
        raise ValueError("collector_password_not_locked")
    return account


def account_preflight(policy):
    users = [user for user in pwd.getpwall() if user.pw_name == ACCOUNT]
    groups = [group for group in grp.getgrall() if group.gr_name == ACCOUNT]
    if not users and not groups:
        return False
    locked_account(policy)
    return True


def apply(contents):
    trusted_installer(contents)
    policy = verifier(contents)
    tree = Tree()
    try:
        tree.absent(CODE)
        tree.absent(MANIFEST)
        storage = tree.directory(STORAGE, missing_ok=True)
        if storage is not None and stat.S_IMODE(os.fstat(storage).st_mode) != 0o700:
            raise ValueError("existing_storage_mode")
        exists = account_preflight(policy)
        # Exclusive code-root creation is the persistent partial-install marker.
        parent = tree.directory(str(Path(CODE).parent), create=True)
        os.mkdir(Path(CODE).name, 0o700, dir_fd=parent)
        os.fsync(parent)
        code_fd = tree.directory(CODE)
        if not exists:
            command(
                [
                    "/usr/sbin/useradd",
                    "--system",
                    "--user-group",
                    "--home-dir",
                    "/nonexistent",
                    "--no-create-home",
                    "--no-log-init",
                    "-K",
                    "CREATE_MAIL_SPOOL=no",
                    "--shell",
                    "/usr/sbin/nologin",
                    ACCOUNT,
                ]
            )
        account = locked_account(policy)
        for name in FILES:
            tree.write(code_fd, name, contents[name], 0o444)
        tree.directory(STORAGE, create=True, mode=0o700)
        os.fchmod(code_fd, 0o755)
        os.fsync(code_fd)
        manifest_parent = tree.directory(str(Path(MANIFEST).parent), create=True)
        # Recheck policy after writes; manifest is the final publication.
        if locked_account(policy) != account:
            raise ValueError("collector_account_changed")
        tree.write(
            manifest_parent,
            Path(MANIFEST).name,
            json_bytes(
                {
                    "schema_version": policy.PROFILE,
                    "collector": account,
                    "files": {name: digest(contents[name]) for name in FILES},
                }
            ),
            0o600,
        )
        installation = policy.TrustedInstallation()
        try:
            installation.verify()
        finally:
            installation.close()
    finally:
        tree.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("build").add_argument("--output", type=Path, required=True)
    for action in ("inspect", "apply"):
        sub = commands.add_parser(action)
        sub.add_argument("--bundle", type=Path, required=True)
        sub.add_argument("--sha256", required=True)
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
            status = "bundle_built_inactive"
        else:
            raw = read_file(args.bundle, BUNDLE_LIMIT)
            contents = inspect(raw, args.sha256)
            if args.action == "apply":
                apply(contents)
                status = "installed_inactive"
            else:
                status = "bundle_verified_inactive"
        print(
            json.dumps(
                {
                    "status": status,
                    "sha256": digest(raw),
                    "network_admitted": False,
                    "host_deployment_qualified": False,
                    "collector_started": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError):
        print(
            json.dumps(
                {
                    "status": "bundle_operation_failed",
                    "network_admitted": False,
                    "partial_installation_requires_inspection": args.action == "apply",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only validation of the fixed future helper installation; never provision it."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import stat
from pathlib import Path

AUTHORITY_UID = 0
ACCOUNT = "trader-egress"
CODE_ROOT = "/usr/local/lib/trader-egress"
MANIFEST = "/etc/trader/egress-install.json"
STORAGE_ROOT = "/var/lib/trader/egress"
FILES = ("collector_launcher.py", "inspect_binding.py", "installation.py", "helper_entry.py")
PROFILE = "portfolio.egress_installation.v2"
LIMIT = 1024 * 1024


def _root_fd():
    return os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _account():
    users, groups = pwd.getpwall(), grp.getgrall()
    selected = [user for user in users if user.pw_name == ACCOUNT]
    if len(selected) != 1:
        raise ValueError("dedicated_account_missing_or_ambiguous")
    user = selected[0]
    primary = [group for group in groups if group.gr_name == ACCOUNT]
    if (
        user.pw_uid <= 0
        or user.pw_gid <= 0
        or user.pw_dir != "/nonexistent"
        or user.pw_shell != "/usr/sbin/nologin"
        or len(primary) != 1
        or primary[0].gr_gid != user.pw_gid
        or any(
            other.pw_name != ACCOUNT
            and (other.pw_uid == user.pw_uid or other.pw_gid == user.pw_gid)
            for other in users
        )
        or any(
            group.gr_name != ACCOUNT and (group.gr_gid == user.pw_gid or ACCOUNT in group.gr_mem)
            for group in groups
        )
        or any(member != ACCOUNT for member in primary[0].gr_mem)
    ):
        raise ValueError("dedicated_account_policy_mismatch")
    return {"name": ACCOUNT, "uid": user.pw_uid, "gid": user.pw_gid}


def metadata(info):
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "type": stat.S_IFMT(info.st_mode),
        "links": info.st_nlink if stat.S_ISREG(info.st_mode) else None,
    }


def read_fd(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
        raise ValueError("installation_file_type_links_or_size")
    raw = os.pread(fd, LIMIT + 1, 0)
    if len(raw) > LIMIT or len(raw) != info.st_size:
        raise ValueError("installation_file_size_changed")
    return raw


class TrustedInstallation:
    """Hold no-follow directory/file descriptors; no caller-selected paths or code."""

    def __init__(self):
        self.owner_pid = os.getpid()
        self.fds, self.entries, self.contents = [], [], {}
        self.directories, self.files = {}, {}
        self.closed = False
        try:
            self.root = _root_fd()
            self.fds.append(self.root)
            self.root_identity = metadata(os.fstat(self.root))
            self.check_directory(os.fstat(self.root))
            self.mount_namespace = os.readlink("/proc/self/ns/mnt")
            self.directories["/"] = self.root
            manifest_fd = self.open_file(MANIFEST, 0o600)
            raw = read_fd(manifest_fd)
            document = json.loads(raw)
            if (
                not isinstance(document, dict)
                or set(document) != {"schema_version", "collector", "files"}
                or document["schema_version"] != PROFILE
                or not isinstance(document["files"], dict)
                or set(document["files"]) != set(FILES)
            ):
                raise ValueError("installation_manifest_schema")
            self.account = _account()
            if document["collector"] != self.account or any(
                type(document["collector"].get(key)) is not int for key in ("uid", "gid")
            ):
                raise ValueError("installation_account_binding")
            self.sources = {}
            for name in FILES:
                fd = self.open_file(CODE_ROOT + "/" + name, 0o444)
                source = read_fd(fd)
                if hashlib.sha256(source).hexdigest() != document["files"][name]:
                    raise ValueError("installation_source_hash")
                self.sources[name] = source
            storage_fd = self.open_directory(STORAGE_ROOT)
            if stat.S_IMODE(os.fstat(storage_fd).st_mode) != 0o700:
                raise ValueError("installation_storage_mode")
            self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
            self.verify()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def check_directory(info):
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != AUTHORITY_UID
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise ValueError("installation_directory_authority")

    @staticmethod
    def selected_path(path):
        value = str(path)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or str(Path(value)) != value
            or ".." in Path(value).parts
        ):
            raise ValueError("installation_canonical_absolute_path_required")
        return value

    def open_directory(self, path):
        try:
            self.verify()
            path = self.selected_path(path)
            parent, selected = self.root, ""
            for name in Path(path).parts[1:]:
                selected += "/" + name
                if selected in self.directories:
                    parent = self.directories[selected]
                    continue
                fd = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=parent,
                )
                self.fds.append(fd)
                info = os.fstat(fd)
                self.check_directory(info)
                self.entries.append((parent, name, fd, metadata(info)))
                self.directories[selected] = fd
                parent = fd
            self.verify()
            return parent
        except BaseException:
            self.close()
            raise

    def open_file(self, path, mode):
        try:
            self.verify()
            selected = self.selected_path(path)
            if selected in self.files:
                fd, expected_mode = self.files[selected]
                if mode != expected_mode:
                    raise ValueError("installation_selected_mode_changed")
                return fd  # Borrowed until close(); never transferred to callers.
            path = Path(selected)
            parent = self.open_directory(str(path.parent))
            fd = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=parent,
            )
            self.fds.append(fd)
            info = os.fstat(fd)
            if info.st_uid != AUTHORITY_UID or stat.S_IMODE(info.st_mode) != mode:
                raise ValueError("installation_file_authority")
            raw = read_fd(fd)
            self.entries.append((parent, path.name, fd, metadata(info)))
            self.contents[fd] = raw
            self.files[selected] = fd, mode
            self.verify()
            return fd
        except BaseException:
            self.close()
            raise

    def verify(self):
        if os.getpid() != self.owner_pid or self.closed:
            raise ValueError("installation_closed_or_foreign_owner")
        try:
            if (
                os.readlink("/proc/self/ns/mnt") != self.mount_namespace
                or metadata(os.fstat(self.root)) != self.root_identity
                or (hasattr(self, "account") and _account() != self.account)
            ):
                raise ValueError("installation_authority_changed")
            for parent, name, fd, selected in self.entries:
                if (
                    metadata(os.fstat(fd)) != selected
                    or metadata(os.stat(name, dir_fd=parent, follow_symlinks=False)) != selected
                ):
                    raise ValueError("installation_path_replaced_or_changed")
                if fd in self.contents and read_fd(fd) != self.contents[fd]:
                    raise ValueError("installation_bytes_changed")
        except BaseException:
            self.close()
            raise

    def source(self, name):
        if name not in FILES:
            raise ValueError("installation_unknown_source")
        self.verify()
        return self.sources[name]

    def close(self):
        if os.getpid() != self.owner_pid:
            raise ValueError("installation_foreign_owner")
        if not self.closed:
            self.closed = True
            for fd in reversed(self.fds):
                os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            installation = None
            try:
                installation = TrustedInstallation()
                report = {
                    "status": "local_installation_observed_not_authorized",
                    "manifest_sha256": installation.manifest_sha256,
                    "collector": installation.account,
                    "sources": {
                        name: hashlib.sha256(value).hexdigest()
                        for name, value in installation.sources.items()
                    },
                }
            except (OSError, ValueError):
                report = {"status": "installation_missing_unreadable_or_invalid"}
            finally:
                if installation is not None:
                    installation.close()
            report.update(
                {
                    "schema_version": "portfolio.egress_installation_check.v1",
                    "host_deployment_qualified": False,
                    "network_admitted": False,
                    "venue_requests_made": 0,
                }
            )
            raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "report_sha256": hashlib.sha256(raw).hexdigest(),
                    "network_admitted": False,
                },
                sort_keys=True,
            )
        )
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "installation_report_failed", "network_admitted": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Staged fixed read-only joint-window source check; no activation interface."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys

CODE = "/usr/local/lib/trader-egress"
ENTRY = CODE + "/gateway_window_entry.py"
MANIFEST = "/etc/trader/joint-window-sources-v1.json"
BASE_PIN = "2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b"
SOURCE_PIN = "2c923d4b546fd0dbcbcf57fbfc4bafdb80e103611f0f38dcd9358cb6b6dea27f"
LIMIT = 1024 * 1024


def _identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _load_base():
    fds = []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fds.append(parent)
        for part in ("usr", "local", "lib", "trader-egress"):
            info = os.fstat(parent)
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("joint_window_entry_untrusted_base_ancestor")
            parent = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
            )
            fds.append(parent)
        info = os.fstat(parent)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("joint_window_entry_untrusted_base_code")
        fd = os.open(
            "helper_entry.py",
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
            raise ValueError("joint_window_entry_untrusted_base_helper")
        raw = os.pread(fd, LIMIT + 1, 0)
        if (
            len(raw) != before.st_size
            or _identity(os.fstat(fd)) != _identity(before)
            or hashlib.sha256(raw).hexdigest() != BASE_PIN
        ):
            raise ValueError("joint_window_entry_base_pin_changed")
        scope = {"__name__": "joint_window_base_verifier"}
        exec(compile(raw, CODE + "/helper_entry.py", "exec"), scope)
        return scope["load_verifier"]()
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _held_sources(authority):
    authority.verify()
    fd = authority.open_file(CODE + "/gateway_window_sources.py", 0o444)
    before = os.fstat(fd)
    if not 0 < before.st_size <= LIMIT:
        raise ValueError("joint_window_entry_source_size")
    raw = os.pread(fd, LIMIT + 1, 0)
    if (
        len(raw) != before.st_size
        or _identity(os.fstat(fd)) != _identity(before)
        or hashlib.sha256(raw).hexdigest() != SOURCE_PIN
    ):
        raise ValueError("joint_window_entry_source_pin_changed")
    authority.verify()
    scope = _load_sources(raw)
    return scope["RootSelectedWindowSources"](authority)


def _load_sources(raw):
    scope = {"__name__": "joint_window_fixed_sources"}
    exec(compile(raw, CODE + "/gateway_window_sources.py", "exec"), scope)
    scope["CODE"], scope["MANIFEST"] = CODE, MANIFEST
    return scope


def _check():
    authority = held = None
    try:
        authority = _load_base()()
        held = _held_sources(authority)
        held.source("gateway_window_entry.py")
        return "fixed_joint_window_sources_observed_unqualified"
    finally:
        if held is not None:
            held.close()
        elif authority is not None:
            authority.close()


def _eligible(args):
    return (
        args == ["--check"]
        and os.getuid() == 0
        and os.geteuid() == 0
        and sys.flags.isolated
        and os.path.abspath(__file__) == ENTRY
    )


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not _eligible(args):
        status = "fixed_joint_window_entry_required"
    else:
        try:
            status = _check()
        except (OSError, ValueError, KeyError, TypeError):
            status = "joint_window_sources_missing_or_changed"
    print(
        json.dumps(
            {
                "status": status,
                "host_deployment_qualified": False,
                "activation_history_verified": False,
                "source_authenticated": False,
                "complete_caller_coverage_verified": False,
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

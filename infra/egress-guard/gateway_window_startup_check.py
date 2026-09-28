"""Protected, read-only startup selection for the installed joint window.

This one-shot check has no nft writer, collector grant, or admission interface.
The operator must pin the staged file separately before launching it as root.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

ENTRY = "/run/trader-egress-window-startup-v1/startup-check.py"
CODE = "/usr/local/lib/trader-egress"
SOURCES = {
    "gateway_window_entry.py": "db9bacd6778111afdc4a163f305361bef6da8fecab56d5ec724b0d1cb66cdc7a",
    "gateway_window_sources.py": "2c923d4b546fd0dbcbcf57fbfc4bafdb80e103611f0f38dcd9358cb6b6dea27f",
    "gateway_window_kernel.py": "16c68156e22dac19b28531550ec9376bd7608f9d0d8fcb22bb2c50a9cbb37e3d",
    "gateway_window_custody.py": "0470ec888c5abae07d60e8e3aaca0cd36851eb97eccda14c04bd36b47b2d8090",
    "gateway_window_witness.py": "508b5ca1405db861f196af313e9aafe591a2377db1c806527e63da296d0154b4",
    "gateway_window_activation.py": "7408b8199add8cc1cf5fc53d7b43fea69e8e4492e1a34b82ad2adca911090554",
}
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


def protected_bytes(path):
    if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
        raise ValueError("joint_startup_protected_entry_required")
    fds = []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fds.append(parent)
        for part in Path(path).parts[1:-1]:
            info = os.fstat(parent)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("joint_startup_untrusted_ancestor")
            parent = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            fds.append(parent)
        info = os.fstat(parent)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("joint_startup_untrusted_parent")
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
            raise ValueError("joint_startup_untrusted_file")
        raw = os.pread(fd, LIMIT + 1, 0)
        if len(raw) != before.st_size or _identity(os.fstat(fd)) != _identity(before):
            raise ValueError("joint_startup_entry_changed")
        return raw
    finally:
        for fd in reversed(fds):
            os.close(fd)


def protected_entry():
    if __file__ != ENTRY:
        raise ValueError("joint_startup_protected_entry_required")
    return protected_bytes(ENTRY)


def select(expected_base):
    if not isinstance(expected_base, str) or re.fullmatch("[0-9a-f]{64}", expected_base) is None:
        raise ValueError("joint_startup_independent_base_pin_required")
    initial = protected_entry()
    entry_raw = protected_bytes(CODE + "/gateway_window_entry.py")
    if hashlib.sha256(entry_raw).hexdigest() != SOURCES["gateway_window_entry.py"]:
        raise ValueError("joint_startup_fixed_entry_changed")
    scope = {"__name__": "joint_window_selected_startup_entry"}
    exec(compile(entry_raw, CODE + "/gateway_window_entry.py", "exec"), scope)
    verifier = scope["_load_base"]()
    authority = verifier()
    selected = None
    try:
        if authority.manifest_sha256 != expected_base:
            raise ValueError("joint_startup_base_manifest_changed")
        selected = scope["_held_sources"](authority)
        for name, expected in SOURCES.items():
            if hashlib.sha256(selected.source(name)).hexdigest() != expected:
                raise ValueError("joint_startup_selected_source_changed")
        if selected.source("gateway_window_entry.py") != entry_raw:
            raise ValueError("joint_startup_executed_entry_changed")
        if scope["_check"]() != "fixed_joint_window_sources_observed_unqualified":
            raise ValueError("joint_startup_entry_status_changed")
        selected.verify()
        if protected_entry() != initial:
            raise ValueError("joint_startup_entry_changed")
    finally:
        if selected is not None:
            selected.close()
        else:
            authority.close()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) != 3 or args[:2] != ["--check", "--base-sha256"]:
            raise ValueError("joint_startup_fixed_check_required")
        select(args[2])
        status = "joint_window_protected_startup_observed_unqualified"
    except (OSError, ValueError, KeyError, TypeError):
        status = "joint_window_protected_startup_refused"
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

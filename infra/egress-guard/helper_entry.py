"""Installed fixed --check entrypoint. No collector launch or network operation."""

import json
import os
import stat
import sys

DIRECTORY = "/usr/local/lib/trader-egress"
ENTRY = DIRECTORY + "/helper_entry.py"
LIMIT = 1024 * 1024
AUTHORITY_UID = 0


def _root_fd():
    return os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def load_verifier():
    # Establish filesystem authority before executing the validator itself.
    fds = []
    try:
        parent = _root_fd()
        fds.append(parent)
        for part in ("usr", "local", "lib", "trader-egress"):
            info = os.fstat(parent)
            if info.st_uid != AUTHORITY_UID or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("untrusted_installation_ancestor")
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(parent)
        info = os.fstat(parent)
        if info.st_uid != AUTHORITY_UID or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("untrusted_code_directory")
        fd = os.open("installation.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != AUTHORITY_UID
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o444
            or info.st_size > LIMIT
        ):
            raise ValueError("untrusted_verifier")
        raw = os.pread(fd, LIMIT + 1, 0)
        after = os.fstat(fd)
        fields = (
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
        if len(raw) != info.st_size or any(
            getattr(after, key) != getattr(info, key) for key in fields
        ):
            raise ValueError("verifier_changed")
        scope = {"__name__": "installed_egress_verifier"}
        exec(compile(raw, DIRECTORY + "/installation.py", "exec"), scope)
        return scope["TrustedInstallation"]
    finally:
        for fd in reversed(fds):
            os.close(fd)


def main():
    if sys.argv[1:] != ["--check"] or not sys.flags.isolated or os.path.abspath(__file__) != ENTRY:
        print(json.dumps({"status": "fixed_installed_check_required", "network_admitted": False}))
        return 2
    installation = None
    try:
        installation = load_verifier()()
        installation.verify()
        status = "installation_verified_inactive"
    except (OSError, ValueError):
        status = "installation_check_blocked"
    finally:
        if installation is not None:
            installation.close()
    print(
        json.dumps(
            {
                "status": status,
                "network_admitted": False,
                "host_deployment_qualified": False,
                "collector_started": False,
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

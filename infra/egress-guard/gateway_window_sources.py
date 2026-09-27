"""Read-only fixed joint-window source inventory; no installed entrypoint.

The caller must supply the independently pinned base TrustedInstallation.
This module is not installed or independently pinned and grants no authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys

CODE = "/usr/local/lib/trader-egress"
MANIFEST = "/etc/trader/joint-window-sources-v1.json"
PROFILE = "portfolio.joint_window_sources.v1"
FILES = (
    "gateway_window_entry.py",
    "gateway_window_sources.py",
    "gateway_window_kernel.py",
    "gateway_window_custody.py",
    "gateway_window_witness.py",
    "gateway_window_activation.py",
)
LIMIT = 1024 * 1024


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("joint_window_sources_duplicate_manifest_key")
        result[key] = value
    return result


def _read(authority, path, mode):
    authority.verify()
    fd = authority.open_file(path, mode)
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= LIMIT:
        raise ValueError("joint_window_sources_file_type_or_size")
    raw = os.pread(fd, LIMIT + 1, 0)
    after = os.fstat(fd)

    def identity(info):
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

    if len(raw) != before.st_size or identity(before) != identity(after):
        raise ValueError("joint_window_sources_file_changed")
    authority.verify()
    return raw


def _require_root():
    if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
        raise ValueError("joint_window_sources_isolated_root_required")


class RootSelectedWindowSources:
    """Hold one fixed manifest and exact source bytes through base custody."""

    def __init__(self, authority):
        self.authority = authority
        self.owner = os.getpid()
        self.closed = False
        try:
            _require_root()
            self.manifest_raw = _read(authority, MANIFEST, 0o600)
            manifest = json.loads(self.manifest_raw, object_pairs_hook=_pairs)
            if (
                not isinstance(manifest, dict)
                or set(manifest) != {"schema_version", "base_manifest_sha256", "files"}
                or manifest["schema_version"] != PROFILE
                or manifest["base_manifest_sha256"] != authority.manifest_sha256
                or not isinstance(manifest["files"], dict)
                or set(manifest["files"]) != set(FILES)
                or any(
                    not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None
                    for value in manifest["files"].values()
                )
            ):
                raise ValueError("joint_window_sources_fixed_manifest_required")
            self._sources = {}
            for name in FILES:
                source = _read(authority, CODE + "/" + name, 0o444)
                if hashlib.sha256(source).hexdigest() != manifest["files"][name]:
                    raise ValueError("joint_window_sources_pin_changed")
                self._sources[name] = source
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        if self.closed or os.getpid() != self.owner:
            raise ValueError("joint_window_sources_closed_or_foreign_owner")
        try:
            _require_root()
            if _read(self.authority, MANIFEST, 0o600) != self.manifest_raw or any(
                _read(self.authority, CODE + "/" + name, 0o444) != self._sources[name]
                for name in FILES
            ):
                raise ValueError("joint_window_sources_held_bytes_changed")
        except BaseException:
            self.close()
            raise

    def source(self, name):
        if name not in FILES:
            raise ValueError("joint_window_sources_unknown_file")
        self.verify()
        return self._sources[name]

    def close(self):
        if os.getpid() != self.owner:
            raise ValueError("joint_window_sources_foreign_owner")
        if not self.closed:
            self.closed = True
            self.authority.close()

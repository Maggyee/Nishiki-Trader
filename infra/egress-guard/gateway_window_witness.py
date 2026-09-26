"""One-shot local custody for joint kernel snapshots, without activation authority.

This is not a rule writer or a guard.verify implementation. A journal and sampled
timers cannot establish uninterrupted kernel coverage between observations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

SCOPE = "joint-window-witness-v1"
PROFILE = "portfolio.joint_window_witness.v1"
LIMIT = 1024 * 1024
SECOND = 1_000_000_000
MAX_DURATION_MS = 3_725_000
README = (
    b"Purpose: one-shot local joint-window snapshot witness. Phase: offline custody. "
    b"Boundary: an external controller may attempt one isolated blackout; "
    b"no uninterrupted coverage or network admission follows. "
    b"Next: protected root controller and full caller/source verification. "
    b"Do not remove or reopen this consumed scope.\n"
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    row = {}
    for key, value in items:
        if key in row:
            raise ValueError("joint_witness_duplicate_key")
        row[key] = value
    return row


def _pinned(selection, pins):
    return (
        isinstance(selection, str)
        and re.fullmatch("[0-9a-f]{64}", selection) is not None
        and isinstance(pins, dict)
        and set(pins) == {"inet", "netdev"}
        and all(
            isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None
            for value in pins.values()
        )
    )


def _selection(snapshot):
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != "portfolio.root_selected_joint_window_snapshot.v1"
        or snapshot.get("status") != "root_selected_kernel_snapshot_unqualified"
        or any(
            snapshot.get(field) is not False
            for field in (
                "activation_history_verified",
                "source_authenticated",
                "complete_caller_coverage_verified",
                "network_admitted",
            )
        )
    ):
        raise ValueError("joint_witness_held_selection_required")
    kernel = snapshot.get("kernel_snapshot")
    if (
        not isinstance(kernel, dict)
        or kernel.get("schema_version") != "portfolio.local_kernel_window_observation.v1"
        or kernel.get("status") != "local_kernel_timers_observed_unqualified"
        or any(
            kernel.get(field) is not False
            for field in (
                "source_authenticated",
                "complete_caller_coverage_verified",
                "network_admitted",
            )
        )
        or not _pinned(snapshot.get("selection_sha256"), kernel.get("static_rules_sha256"))
        or not isinstance(kernel.get("observed_monotonic_ns"), list)
        or len(kernel["observed_monotonic_ns"]) != 2
    ):
        raise ValueError("joint_witness_kernel_snapshot_required")
    started, finished = kernel["observed_monotonic_ns"]
    expiry = kernel.get("minimum_blackout_through_monotonic_ns")
    if (
        type(started) is not int
        or type(finished) is not int
        or type(expiry) is not int
        or not 0 < started <= finished < expiry
        or finished - started > SECOND
        or kernel.get("remaining_ns_lower_bound") != expiry - finished
    ):
        raise ValueError("joint_witness_kernel_clock_invalid")
    return snapshot["selection_sha256"], kernel["static_rules_sha256"], started, finished, expiry


def replay(raw, *, expected_sha256):
    """Read-only local consistency check; a caller-chosen hash has no authority."""
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= LIMIT
        or digest(raw) != expected_sha256
        or not raw.endswith(b"\n")
    ):
        raise ValueError("joint_witness_archive_incomplete")
    previous, last_time, selection, pins, expiry, observations = None, 0, None, None, None, 0
    prepared = None
    for seq, line in enumerate(raw.splitlines()):
        row = json.loads(line, object_pairs_hook=_pairs)
        fields = {"seq", "previous_sha256", "kind", "monotonic_ns"}
        activation = row.get("kind") == "activation_prepared" and seq == 1
        observed = seq > 0 and not activation
        if activation:
            fields |= {"selection_sha256", "static_rules_sha256", "duration_ms"}
        if observed:
            fields |= {"selection_sha256", "static_rules_sha256", "expiry_ns"}
        if (
            not isinstance(row, dict)
            or set(row) != fields
            or type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous_sha256"] != previous
            or row["kind"]
            != ("activation_prepared" if activation else "observed" if observed else "claimed")
            or type(row["monotonic_ns"]) is not int
            or row["monotonic_ns"] <= last_time
            or canonical(row) != line
        ):
            raise ValueError("joint_witness_archive_sequence_invalid")
        last_time = row["monotonic_ns"]
        if activation:
            if (
                not _pinned(row["selection_sha256"], row["static_rules_sha256"])
                or type(row["duration_ms"]) is not int
                or not 1000 <= row["duration_ms"] <= MAX_DURATION_MS
            ):
                raise ValueError("joint_witness_archive_activation_invalid")
            prepared = (row["selection_sha256"], row["static_rules_sha256"])
        if observed:
            selected, static, current_expiry = (
                row["selection_sha256"],
                row["static_rules_sha256"],
                row["expiry_ns"],
            )
            if (
                not _pinned(selected, static)
                or type(current_expiry) is not int
                or current_expiry <= last_time
            ):
                raise ValueError("joint_witness_archive_sample_invalid")
            if (
                (selection is not None and selected != selection)
                or (pins is not None and static != pins)
                or (prepared is not None and (selected, static) != prepared)
            ):
                raise ValueError("joint_witness_archive_selection_changed")
            if expiry is not None and current_expiry > expiry + SECOND:
                raise ValueError("joint_witness_archive_timer_extended")
            selection, pins = selected, static
            expiry = current_expiry if expiry is None else min(expiry, current_expiry)
            observations += 1
        previous = digest(line + b"\n")
    return {
        "schema_version": PROFILE,
        "status": "local_window_samples_unqualified",
        "observations": observations,
        "first_selection_sha256": selection,
        "minimum_observed_expiry_ns": expiry,
        "activation_prepared": prepared is not None,
        "activation_history_verified": False,
        "source_authenticated": False,
        "complete_caller_coverage_verified": False,
        "network_admitted": False,
    }


class WindowWitness:
    """Consume a private scope before reading any held kernel snapshot."""

    def __init__(self, root, snapshotter, *, clock=time.monotonic_ns):
        self.root = Path(root)
        self.snapshotter, self.clock, self.owner = snapshotter, clock, os.getpid()
        self.fds = []
        self.closed = self.failed = False
        self.expected = b""
        self.seq, self.previous = 0, None
        self.selection = self.pins = self.expiry = None
        self.prepared = None
        self.last_time = 0
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(root_fd)
            info = os.fstat(root_fd)
            current = self.root.stat(follow_symlinks=False)
            if (
                not stat.S_ISDIR(current.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("joint_witness_private_root_required")
            os.mkdir(SCOPE, 0o700, dir_fd=root_fd)
            os.fsync(root_fd)
            scope_fd = os.open(SCOPE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            self.fds.append(scope_fd)
            self.path = self.root / SCOPE
            self._write_file(scope_fd, "README.md", README)
            fd = os.open(
                "events.jsonl",
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=scope_fd,
            )
            self.fds.append(fd)
            info = os.fstat(fd)
            self.file_id = (info.st_dev, info.st_ino)
            os.fsync(scope_fd)
            self._append("claimed", self.clock())
        except BaseException:
            self.failed = True
            self._release()
            raise

    def _write_file(self, directory_fd, name, raw):
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def _release(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()

    def _storage(self):
        if os.getpid() != self.owner or self.closed or self.failed:
            raise ValueError("joint_witness_closed_or_foreign_owner")
        for path, fd in ((self.root, self.fds[0]), (self.path, self.fds[1])):
            held, current = os.fstat(fd), path.stat(follow_symlinks=False)
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o700
                or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("joint_witness_storage_changed")
        info = self.path.joinpath("events.jsonl").stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != self.file_id
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or os.pread(self.fds[2], LIMIT + 1, 0) != self.expected
        ):
            raise ValueError("joint_witness_archive_changed")

    def _append(self, kind, now, **fields):
        self._storage()
        if type(now) is not int or now <= self.last_time:
            raise ValueError("joint_witness_monotonic_clock_regressed")
        row = {
            "seq": self.seq,
            "previous_sha256": self.previous,
            "kind": kind,
            "monotonic_ns": now,
            **fields,
        }
        raw = canonical(row) + b"\n"
        if len(self.expected) + len(raw) > LIMIT:
            raise ValueError("joint_witness_archive_limit")
        view = memoryview(raw)
        while view:
            written = os.write(self.fds[2], view)
            if written <= 0:
                raise OSError("joint_witness_short_write")
            view = view[written:]
        os.fsync(self.fds[2])
        self.expected += raw
        self.seq += 1
        self.previous = digest(raw)
        self.last_time = now

    def prepare_activation(self, *, selection_sha256, static_rules_sha256, duration_ms):
        """Persist a single fixed-intent record before any kernel write."""
        try:
            if (
                self.seq != 1
                or self.prepared is not None
                or not _pinned(selection_sha256, static_rules_sha256)
                or type(duration_ms) is not int
                or not 1000 <= duration_ms <= MAX_DURATION_MS
            ):
                raise ValueError("joint_witness_fixed_activation_preparation_required")
            self._append(
                "activation_prepared",
                self.clock(),
                selection_sha256=selection_sha256,
                static_rules_sha256=static_rules_sha256,
                duration_ms=duration_ms,
            )
            self.prepared = (selection_sha256, static_rules_sha256)
        except BaseException:
            self.failed = True
            raise

    def observe(self):
        """Persist one sample; never attest the gaps between samples."""
        try:
            self._storage()
            snapshot = self.snapshotter.observe()
            selected, pins, started, finished, expiry = _selection(snapshot)
            now = self.clock()
            if (
                type(now) is not int
                or started < self.last_time
                or not finished <= now < expiry
                or now > finished + SECOND
            ):
                raise ValueError("joint_witness_observation_clock_invalid")
            if (
                (self.selection is not None and selected != self.selection)
                or (self.pins is not None and pins != self.pins)
                or (self.prepared is not None and (selected, pins) != self.prepared)
            ):
                raise ValueError("joint_witness_selection_changed")
            if self.expiry is not None and expiry > self.expiry + SECOND:
                raise ValueError("joint_witness_timer_extended")
            self._append(
                "observed",
                now,
                selection_sha256=selected,
                static_rules_sha256=pins,
                expiry_ns=expiry,
            )
            self.selection, self.pins = selected, pins
            self.expiry = expiry if self.expiry is None else min(self.expiry, expiry)
            return replay(self.expected, expected_sha256=digest(self.expected))
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if os.getpid() != self.owner:
            raise ValueError("joint_witness_foreign_owner")
        if not self.closed:
            self.closed = True
            self._release()

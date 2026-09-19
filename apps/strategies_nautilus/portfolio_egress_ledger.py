"""Durable prospective attempt accounting with explicit observation gaps.

No transport or admission API. Local caller labels and sampled binding checks do
not prove complete egress coverage. Missing history never supplies a usage bound.
"""

from __future__ import annotations

import copy
import os
import re
import stat
import threading
import time
from contextlib import suppress
from pathlib import Path

from apps.strategies_nautilus.portfolio_rate_evidence import _body, _integer
from apps.strategies_nautilus.portfolio_tls_provenance import _Journal, canonical, digest

PROFILE = "portfolio.local_egress_attempt_ledger.v1"
SCOPE = "local-egress-attempts-v1"
LIMIT = 2 * 1024 * 1024
# Labels are selected local bookkeeping identities, not authenticated processes.
CALLERS = {"collector", "host", "container", "tailscale", "proxy"}
OPERATIONS = {
    "exchange_info": {"role": "rest", "documented_weight": 20, "raw_requests": 1, "connections": 0},
    "account_connect": {
        "role": "account",
        "documented_weight": 2,
        "raw_requests": 0,
        "connections": 1,
    },
    "account_subscribe": {
        "role": "account",
        "documented_weight": 2,
        "raw_requests": 0,
        "connections": 0,
    },
    "market_connect": {
        "role": "market",
        "documented_weight": None,
        "raw_requests": 0,
        "connections": 1,
    },
}


JOINT_PROFILE = "portfolio.local_joint_egress_attempt_ledger.v1"
JOINT_SCOPE = "local-joint-egress-attempts-v1"
JOINT_OPERATIONS = {
    **OPERATIONS,
    **{
        name: {"role": "rest", "documented_weight": weight, "raw_requests": 1, "connections": 0}
        for name, weight in (
            ("time", 1),
            ("account_read", 20),
            ("open_orders", 80),
            ("book_ticker", 4),
            ("depth_100", 5),
        )
    },
    "account_unsubscribe": {
        "role": "account",
        "documented_weight": 2,
        "raw_requests": 0,
        "connections": 0,
    },
}


IPC_PROFILE = "portfolio.fixture_joint_ipc_ledger.v1"
IPC_SCOPE = "fixture-joint-ipc-v1"
REQUEST_PROFILE = "portfolio.fixture_native_requests_ledger.v1"
REQUEST_SCOPE = "fixture-native-requests-v1"
ACCOUNT_PROFILE = "portfolio.fixture_signed_account_tls_ledger.v1"
ACCOUNT_SCOPE = "fixture-signed-account-tls-v1"
ORDERS_PROFILE = "portfolio.fixture_signed_orders_tls_ledger.v1"
ORDERS_SCOPE = "fixture-signed-orders-tls-v1"
# Fixed maximum local pilot classification. Tokens contain no endpoint/payload/signature.
IPC_STEPS = (
    ("clock_initial", "time"),
    ("account_connect", "account_connect"),
    ("account_subscribe", "account_subscribe"),
    ("account_before_0", "account_read"),
    ("account_before_1", "open_orders"),
    ("account_before_2", "open_orders"),
    ("account_before_3", "account_read"),
    ("metadata", "exchange_info"),
    ("books", "book_ticker"),
    ("market_connect", "market_connect"),
    ("depth_0", "depth_100"),
    ("depth_1", "depth_100"),
    ("depth_2", "depth_100"),
    ("clock_linked", "time"),
    ("account_after_0", "account_read"),
    ("account_after_1", "open_orders"),
    ("account_after_2", "open_orders"),
    ("account_after_3", "account_read"),
    ("clock_final", "time"),
    ("account_unsubscribe", "account_unsubscribe"),
)


def ipc_request(index):
    if type(index) is not int or not 0 <= index < len(IPC_STEPS):
        raise ValueError("ipc_operation_scope_consumed")
    return {"v": 1, "op": IPC_STEPS[index][0], "seq": index + 1}


def clock():
    return time.time_ns(), time.monotonic_ns()


class State:
    def __init__(self, binding_sha256, *, profile=PROFILE):
        if profile not in {
            PROFILE,
            JOINT_PROFILE,
            IPC_PROFILE,
            REQUEST_PROFILE,
            ACCOUNT_PROFILE,
            ORDERS_PROFILE,
        }:
            raise ValueError("unknown_ledger_profile")
        self.profile = profile
        self.operations = OPERATIONS if profile == PROFILE else JOINT_OPERATIONS
        if not isinstance(binding_sha256, str) or not re.fullmatch("[0-9a-f]{64}", binding_sha256):
            raise ValueError("selected_binding_digest_required")
        self.binding_sha256 = binding_sha256
        self.last_kind = None
        self.last = self.start = None
        self.last_observation = None
        self.pending = None
        self.attempts = []
        self.terminal = None
        self.gap = None

    def feed(self, row):
        if self.terminal:
            raise ValueError("ledger_already_ended")
        if row["profile"] != self.profile or row["binding_sha256"] != self.binding_sha256:
            raise ValueError("ledger_profile_or_binding")
        now, mono = (_integer(row[k], positive=True) for k in ("utc_ns", "monotonic_ns"))
        if self.last and (
            now < self.last[0]
            or mono < self.last[1]
            or abs((now - self.start[0]) - (mono - self.start[1])) > 50_000_000
        ):
            raise ValueError("ledger_clock_discontinuity")
        kind, payload = row["kind"], row["payload"]
        if not isinstance(payload, dict):
            raise ValueError("ledger_payload_invalid")
        if self.start is None:
            if kind != "started" or payload != {}:
                raise ValueError("ledger_start_required")
            self.start = (now, mono)
        elif kind == "observed":
            if payload != {}:
                raise ValueError("ledger_observation_fields")
            self.last_observation = mono
        elif kind == "prepared":
            if (
                self.pending is not None
                or len(self.attempts)
                >= (len(IPC_STEPS) if self.profile in {IPC_PROFILE, REQUEST_PROFILE} else 256)
                or set(payload) != ({"index", "caller", "operation"} | self.link_fields())
                or type(payload["index"]) is not int
                or payload["index"] != len(self.attempts)
                or payload["caller"] not in CALLERS
                or payload["operation"] not in self.operations
                or self.last_observation is None
                or self.last_kind != "observed"
            ):
                raise ValueError("ledger_preparation_invalid")
            self.validate_link(payload)
            if self.profile in {IPC_PROFILE, REQUEST_PROFILE} and (
                payload["caller"] != "collector"
                or payload["operation"] != IPC_STEPS[len(self.attempts)][1]
                or (
                    self.profile == IPC_PROFILE
                    and payload["request_sha256"]
                    != digest(canonical(ipc_request(len(self.attempts))))
                )
            ):
                raise ValueError("ipc_fixed_operation_required")
            if self.profile in {ACCOUNT_PROFILE, ORDERS_PROFILE} and (
                self.attempts
                or payload["caller"] != "collector"
                or payload["operation"]
                != ("account_read" if self.profile == ACCOUNT_PROFILE else "open_orders")
            ):
                raise ValueError("single_signed_account_attempt_required")
            self.pending = payload["index"]
            self.attempts.append({**payload, "prepared_monotonic_ns": mono, "outcome": "uncertain"})
        elif kind == "outcome":
            if (
                set(payload) != ({"index", "result"} | self.link_fields())
                or type(payload["index"]) is not int
                or self.pending is None
                or payload["index"] != self.pending
                or payload["result"] not in {"succeeded", "failed", "uncertain"}
                or self.last_kind != "observed"
            ):
                raise ValueError("ledger_outcome_invalid")
            self.validate_link(payload)
            if (
                self.profile in {IPC_PROFILE, REQUEST_PROFILE, ACCOUNT_PROFILE, ORDERS_PROFILE}
                and payload["request_sha256"] != self.attempts[self.pending]["request_sha256"]
            ):
                raise ValueError("ipc_outcome_request_changed")
            self.attempts[self.pending]["outcome"] = payload["result"]
            self.pending = None
            if payload["result"] != "succeeded":
                self.terminal = payload["result"]
        elif kind == "aborted":
            if set(payload) != {"reason"} or not isinstance(payload["reason"], str):
                raise ValueError("ledger_gap_invalid")
            self.gap = {
                "from_monotonic_ns": self.last_observation or self.start[1],
                "through_monotonic_ns": None,
                "reason": payload["reason"],
            }
            self.terminal = "gap"
        elif kind == "closed" and payload == {}:
            self.terminal = "closed"
        else:
            raise ValueError("ledger_transition")
        self.last = now, mono
        self.last_kind = kind

    def link_fields(self):
        if self.profile in {IPC_PROFILE, REQUEST_PROFILE, ACCOUNT_PROFILE, ORDERS_PROFILE}:
            return {"request_sha256"}
        return {"joint_prefix_sha256"} if self.profile == JOINT_PROFILE else set()

    def validate_link(self, payload):
        for key in self.link_fields():
            if not isinstance(payload[key], str) or not re.fullmatch("[0-9a-f]{64}", payload[key]):
                raise ValueError(
                    "joint_prefix_digest_required"
                    if self.profile == JOINT_PROFILE
                    else "ipc_request_digest_required"
                )

    def report(self, start_ns=None, through_ns=None):
        if self.start is None:
            raise ValueError("empty_ledger")
        start_ns = self.start[1] if start_ns is None else _integer(start_ns, positive=True)
        through_ns = self.last[1] if through_ns is None else _integer(through_ns, positive=True)
        if through_ns < start_ns:
            raise ValueError("invalid_ledger_interval")
        selected = [
            r for r in self.attempts if start_ns <= r["prepared_monotonic_ns"] <= through_ns
        ]
        counts = []
        for caller in sorted(CALLERS):
            for role in ("rest", "account", "market"):
                attempts = [
                    r
                    for r in selected
                    if r["caller"] == caller and self.operations[r["operation"]]["role"] == role
                ]
                if not attempts:
                    continue
                units = [self.operations[r["operation"]] for r in attempts]
                counts.append(
                    {
                        "caller_label": caller,
                        "role": role,
                        "prepared_attempts": len(attempts),
                        "documented_weight": sum(r["documented_weight"] or 0 for r in units),
                        "unknown_charge_attempts": sum(
                            r["documented_weight"] is None for r in units
                        ),
                        "raw_requests": sum(r["raw_requests"] for r in units),
                        "connection_attempts": sum(r["connections"] for r in units),
                        "outcomes": {
                            k: sum(r["outcome"] == k for r in attempts)
                            for k in ("succeeded", "failed", "uncertain")
                        },
                    }
                )
        return {
            **(
                {
                    "evidence_kind": "local_ipc_preparations_only",
                    "transport_dispatch_verified": False,
                    "provider_usage_inferred": False,
                }
                if self.profile in {IPC_PROFILE, REQUEST_PROFILE}
                else {}
            ),
            "schema_version": self.profile,
            "binding_sha256": self.binding_sha256,
            "status": self.terminal or "incomplete_no_resume",
            "pending_attempt": self.pending,
            "recorded_attempts": len(self.attempts),
            "interval_monotonic_ns": [start_ns, through_ns],
            "interval_boundary": "both_edges_inclusive_local_clock_not_provider_bucket",
            "counts": counts,
            "observed_gap": self.gap,
            "history_before_start_available": False,
            "history_after_last_observation_available": False,
            "coverage_between_observations_verified": False,
            "complete_caller_coverage_verified": False,
            "caller_labels_authenticated": False,
            "used_upper_bound": None,
            "other_callers_upper_bound": None,
            "future_enforcement_verified": False,
            "restart_allowed": False,
            "network_admitted": False,
            "trading_admitted": False,
        }


class AttemptLedger:
    """Single owned archive; prepare is bookkeeping, never a dispatch capability."""

    def __init__(self, root, *, binding, binding_sha256, clock=clock, profile=PROFILE):
        self.root = Path(root).absolute()
        self.binding, self.clock = binding, clock
        self.state = State(binding_sha256, profile=profile)
        scope = {
            PROFILE: SCOPE,
            JOINT_PROFILE: JOINT_SCOPE,
            IPC_PROFILE: IPC_SCOPE,
            REQUEST_PROFILE: REQUEST_SCOPE,
            ACCOUNT_PROFILE: ACCOUNT_SCOPE,
            ORDERS_PROFILE: ORDERS_SCOPE,
        }[profile]
        self.owner = os.getpid()
        self.lock = threading.Lock()
        self.fds = []
        self.journal = None
        self.closed = self.failed = False
        self.expected = b""
        try:
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(root_fd)
            info = os.fstat(root_fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError("private_owned_ledger_root_required")
            os.mkdir(scope, mode=0o700, dir_fd=root_fd)
            os.fsync(root_fd)
            self.path = self.root / scope
            scope_fd = os.open(scope, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            self.fds.append(scope_fd)
            fd = os.open(
                "README.md",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=scope_fd,
            )
            with os.fdopen(fd, "wb") as f:
                f.write(
                    b"Prospective local attempt ledger. Consumed on creation; never reopen or resume. Sampled bindings and caller labels are not complete traffic coverage. Next: pinned offline replay only.\n"
                )
                f.flush()
                os.fsync(f.fileno())
            self.journal = _Journal(self.path / "events.jsonl", limit=LIMIT, reserve=4096)
            self.reader = os.open("events.jsonl", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=scope_fd)
            self.fds.append(self.reader)
            self.file_identity = os.fstat(self.reader).st_dev, os.fstat(self.reader).st_ino
            self._append("started", {})
            self._observe()
        except BaseException:
            self._release()
            raise

    def _owner(self):
        if os.getpid() != self.owner:
            raise ValueError("foreign_ledger_owner")

    def _storage(self):
        self._owner()
        for path, fd in zip((self.root, self.path), self.fds[:2], strict=True):
            held, current = os.fstat(fd), path.stat(follow_symlinks=False)
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o700
                or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("ledger_storage_changed")
        info = (self.path / "events.jsonl").stat(follow_symlinks=False)
        if (
            (info.st_dev, info.st_ino) != self.file_identity
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or os.pread(self.reader, LIMIT + 1, 0) != self.expected
        ):
            raise ValueError("ledger_archive_changed")

    def _append(self, kind, payload, *, at=None):
        self._storage()
        now, mono = self.clock() if at is None else at
        row = {
            "seq": self.journal.seq,
            "previous_sha256": self.journal.previous,
            "kind": kind,
            "utc_ns": now,
            "monotonic_ns": mono,
            "profile": self.state.profile,
            "binding_sha256": self.state.binding_sha256,
            "payload": payload,
        }
        future = copy.deepcopy(self.state)
        future.feed(row)
        self.journal.append(
            kind, **{k: v for k, v in row.items() if k not in {"kind", "seq", "previous_sha256"}}
        )
        self.expected += canonical(row) + b"\n"
        self.state = future

    def _observe(self):
        self._storage()
        report = self.binding.verify()
        if report["binding_sha256"] != self.state.binding_sha256:
            raise ValueError("observed_binding_changed")
        self._append("observed", {})

    def _abort(self, exc):
        self.failed = True
        with suppress(Exception):
            self._append("aborted", {"reason": type(exc).__name__}, at=self.state.last)

    def prepare(self, *, caller, operation, joint_prefix_sha256=None, request_sha256=None):
        self._owner()
        with self.lock:
            if self.closed or self.failed or self.state.terminal:
                raise ValueError("ledger_ended_no_retry")
            try:
                self._observe()
                index = len(self.state.attempts)
                self._append(
                    "prepared",
                    {
                        "index": index,
                        "caller": caller,
                        "operation": operation,
                        **(
                            {"request_sha256": request_sha256}
                            if self.state.profile
                            in {IPC_PROFILE, REQUEST_PROFILE, ACCOUNT_PROFILE, ORDERS_PROFILE}
                            or request_sha256 is not None
                            else {}
                        ),
                        **(
                            {"joint_prefix_sha256": joint_prefix_sha256}
                            if self.state.profile == JOINT_PROFILE
                            or joint_prefix_sha256 is not None
                            else {}
                        ),
                    },
                )
                self._observe()  # Drift during fsync blocks handoff; consumption stays.
                return {"index": index, "preparation_persisted": True, "network_admitted": False}
            except BaseException as exc:
                self._abort(exc)
                raise

    def outcome(self, *, index, result, joint_prefix_sha256=None, request_sha256=None):
        self._owner()
        with self.lock:
            if self.closed or self.failed or self.state.terminal:
                raise ValueError("ledger_ended_no_retry")
            try:
                self._observe()
                self._append(
                    "outcome",
                    {
                        "index": index,
                        "result": result,
                        **(
                            {"request_sha256": request_sha256}
                            if self.state.profile
                            in {IPC_PROFILE, REQUEST_PROFILE, ACCOUNT_PROFILE, ORDERS_PROFILE}
                            or request_sha256 is not None
                            else {}
                        ),
                        **(
                            {"joint_prefix_sha256": joint_prefix_sha256}
                            if self.state.profile == JOINT_PROFILE
                            or joint_prefix_sha256 is not None
                            else {}
                        ),
                    },
                )
            except BaseException as exc:
                self._abort(exc)
                raise

    def checkpoint(self):
        self._owner()
        with self.lock:
            if self.closed or self.failed or self.state.terminal:
                raise ValueError("ledger_ended_no_retry")
            try:
                self._observe()
            except BaseException as exc:
                self._abort(exc)
                raise

    def _release(self):
        if not self.closed:
            self.closed = True
            if self.journal is not None:
                os.close(self.journal.fd)
            for fd in reversed(self.fds):
                os.close(fd)

    def close(self):
        self._owner()
        with self.lock:
            if not self.closed:
                try:
                    if not self.failed and not self.state.terminal:
                        self._observe()
                        self._append("closed", {})
                except BaseException as exc:
                    self._abort(exc)
                    raise
                finally:
                    self._release()


def replay(
    raw, *, expected_sha256, binding_sha256, start_ns=None, through_ns=None, profile=PROFILE
):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT or digest(raw) != expected_sha256:
        raise ValueError("selected_ledger_bytes_changed")
    state, previous = State(binding_sha256, profile=profile), None
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        row = _body(line)
        if (
            set(row)
            != {
                "seq",
                "previous_sha256",
                "kind",
                "utc_ns",
                "monotonic_ns",
                "profile",
                "binding_sha256",
                "payload",
            }
            or type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous_sha256"] != previous
            or canonical(row) + b"\n" != line
        ):
            raise ValueError("ledger_chain_invalid")
        state.feed(row)
        previous = digest(line)
    return {"archive_sha256": expected_sha256, **state.report(start_ns, through_ns)}

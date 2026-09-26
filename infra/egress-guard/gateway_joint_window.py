"""Prospective joint-window barrier over a held guard and consumed local ledger.

The guard must be provided by a future installed root controller, not by a JSON
report. This module cannot establish that guard's authority, grant kernel access,
dispatch, or qualify source/egress coverage on its own.
"""

from __future__ import annotations

import os
import re
import time
from contextlib import suppress

SECOND = 1_000_000_000
MIN_LOOKBACK = 300 * SECOND
MAX_LOOKBACK = 3600 * SECOND
CLOSE_HORIZON = 125 * SECOND
FIELDS = {
    "binding_sha256",
    "installation_manifest_sha256",
    "boot_id",
    "window_started_monotonic_ns",
    "exclusive_through_monotonic_ns",
    "all_other_callers_denied",
    "collector_quarantined",
}


class WindowError(ValueError):
    """The current window cannot support another local preparation."""


class ProspectiveJointWindow:
    """Require guard-reported exclusion time before a local preparation.

    The installed controller must independently verify its kernel rules, all
    applicable egress paths and persistent activation record in ``guard.verify``.
    Synthetic guards exercise ordering only; their results cannot enter admission.
    """

    def __init__(self, guard, ledger, *, lookback_ns, clock=time.monotonic_ns):
        if (
            type(lookback_ns) is not int
            or not MIN_LOOKBACK <= lookback_ns <= MAX_LOOKBACK
            or ledger.state.profile != "portfolio.local_joint_egress_attempt_ledger.v1"
            or ledger.state.attempts
            or ledger.state.terminal
            or ledger.closed
            or ledger.failed
        ):
            with suppress(BaseException):
                guard.revoke()
            raise WindowError("joint_window_fixed_new_ledger_and_lookback_required")
        self.guard, self.ledger, self.clock = guard, ledger, clock
        self.lookback_ns = lookback_ns
        self.owner = os.getpid()
        self.closed = self.failed = False
        try:
            self.selected = self._observation()
            if self.selected["binding_sha256"] != ledger.state.binding_sha256:
                raise WindowError("joint_window_ledger_binding_changed")
            self.last_now = self.clock()
            if (
                type(self.last_now) is not int
                or self.last_now < self.selected["window_started_monotonic_ns"]
                or self.selected["exclusive_through_monotonic_ns"]
                - self.selected["window_started_monotonic_ns"]
                < lookback_ns + CLOSE_HORIZON
            ):
                raise WindowError("joint_window_full_horizon_missing")
        except BaseException as exc:
            self._halt(exc)
            raise

    def _owner(self):
        if os.getpid() != self.owner or self.closed or self.failed:
            raise WindowError("joint_window_closed_or_foreign_owner")

    def _observation(self):
        row = self.guard.verify()
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise WindowError("joint_window_guard_fields")
        for key in ("binding_sha256", "installation_manifest_sha256"):
            if not isinstance(row[key], str) or re.fullmatch("[0-9a-f]{64}", row[key]) is None:
                raise WindowError("joint_window_guard_identity")
        if not isinstance(row["boot_id"], str) or not row["boot_id"]:
            raise WindowError("joint_window_boot_identity")
        for key in ("window_started_monotonic_ns", "exclusive_through_monotonic_ns"):
            if type(row[key]) is not int or row[key] <= 0:
                raise WindowError("joint_window_guard_clock")
        if row["all_other_callers_denied"] is not True or row["collector_quarantined"] is not True:
            raise WindowError("joint_window_exclusion_or_quarantine_missing")
        return row

    def _check(self):
        self._owner()
        now = self.clock()
        if type(now) is not int or now < self.last_now:
            raise WindowError("joint_window_monotonic_clock_regressed")
        self.last_now = now
        if self._observation() != self.selected:
            raise WindowError("joint_window_guard_drift_or_renewal")
        if now + CLOSE_HORIZON > self.selected["exclusive_through_monotonic_ns"]:
            raise WindowError("joint_window_future_exclusion_expired")
        return now

    def readiness(self):
        """A local timing check only; never a network permit or source attestation."""
        self._owner()
        try:
            now = self._check()
        except BaseException as exc:
            self._halt(exc)
            raise
        return {
            "status": "local_window_mature"
            if now - self.selected["window_started_monotonic_ns"] >= self.lookback_ns
            else "waiting_for_exclusion_history",
            "lookback_ns": self.lookback_ns,
            "elapsed_ns": now - self.selected["window_started_monotonic_ns"],
            "future_exclusion_remaining_ns": self.selected["exclusive_through_monotonic_ns"] - now,
            "source_authenticated": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
        }

    def _halt(self, exc):
        if os.getpid() != self.owner or self.closed:
            return
        self.failed = True
        # A failed observation cannot leave an open collector permission. The
        # future guard must revoke atomically with release of other callers.
        with suppress(BaseException):
            self.guard.revoke()
        if not self.ledger.closed and not self.ledger.failed:
            self.ledger._abort(exc)

    def prepare(self, *, operation, joint_prefix_sha256):
        """Consume one local preparation; no transport is handed a permit."""
        ready = self.readiness()
        if ready["status"] != "local_window_mature":
            raise WindowError("joint_window_history_not_mature")
        try:
            units = self.ledger.state.operations.get(operation)
            if units is None or units["documented_weight"] is None:
                raise WindowError("joint_window_unknown_operation_charge")
            if operation != "time" or self.ledger.state.attempts:
                raise WindowError("joint_window_first_operation_only")
            self.ledger.checkpoint()
            self._check()
            result = self.ledger.prepare(
                caller="collector", operation=operation, joint_prefix_sha256=joint_prefix_sha256
            )
            self._check()
            self.ledger.checkpoint()
            return {
                **result,
                "source_authenticated": False,
                "complete_caller_coverage_verified": False,
                "network_admitted": False,
            }
        except BaseException as exc:
            self._halt(exc)
            raise

    def close(self):
        if os.getpid() != self.owner:
            raise WindowError("joint_window_foreign_owner")
        if not self.closed:
            self.closed = True
            try:
                self.guard.revoke()
            finally:
                self.ledger.close()

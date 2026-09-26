"""Prospective guard-window timing against the real consumed local ledger."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus.portfolio_tls_provenance import digest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_joint_window.py"
START = 1_000_000_000_000
UTC = 1_800_000_000_000_000_000
PIN = "a" * 64
SECOND = 1_000_000_000


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("gateway_joint_window_test", SOURCE)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Clock:
    def __init__(self):
        self.now = START

    def mono(self):
        return self.now

    def pair(self):
        return UTC + self.now - START, self.now


class Guard:
    def __init__(self, *, duration=426):
        self.revocations = 0
        self.row = {
            "binding_sha256": PIN,
            "installation_manifest_sha256": "b" * 64,
            "boot_id": "synthetic-boot",
            "window_started_monotonic_ns": START,
            "exclusive_through_monotonic_ns": START + duration * SECOND,
            "all_other_callers_denied": True,
            "collector_quarantined": True,
        }

    def verify(self):
        return dict(self.row)

    def revoke(self):
        self.revocations += 1


class Binding:
    def verify(self):
        return {"binding_sha256": PIN}


@pytest.fixture
def scope(module, tmp_path):
    clock, guard = Clock(), Guard()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    ledger = attempts.AttemptLedger(
        root,
        binding=Binding(),
        binding_sha256=PIN,
        clock=clock.pair,
        profile=attempts.JOINT_PROFILE,
    )
    window = module.ProspectiveJointWindow(
        guard,
        ledger,
        lookback_ns=300 * SECOND,
        clock=clock.mono,
    )
    try:
        yield window, guard, ledger, clock
    finally:
        window.close()


def test_waits_for_full_history_then_consumes_one_local_preparation(scope):
    window, guard, ledger, clock = scope
    assert window.readiness()["status"] == "waiting_for_exclusion_history"
    clock.now += 299 * SECOND
    with pytest.raises(ValueError, match="joint_window_history_not_mature"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert not ledger.state.attempts and guard.revocations == 0
    clock.now += SECOND
    assert window.readiness()["status"] == "local_window_mature"
    result = window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert result == {
        "index": 0,
        "preparation_persisted": True,
        "network_admitted": False,
        "source_authenticated": False,
        "complete_caller_coverage_verified": False,
    }
    assert ledger.state.pending == 0
    raw = (ledger.path / "events.jsonl").read_bytes()
    report = attempts.replay(
        raw, expected_sha256=digest(raw), binding_sha256=PIN, profile=attempts.JOINT_PROFILE
    )
    assert report["recorded_attempts"] == 1
    assert report["pending_attempt"] == 0
    assert report["complete_caller_coverage_verified"] is False
    assert report["network_admitted"] is False
    with pytest.raises(ValueError, match="joint_window_first_operation_only"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert guard.revocations == 1


@pytest.mark.parametrize(
    "change",
    ["boot_id", "binding_sha256", "exclusive_through_monotonic_ns", "all_other_callers_denied"],
)
def test_any_guard_drift_or_renewal_halts_permanently(scope, change):
    window, guard, ledger, clock = scope
    clock.now += 300 * SECOND
    original = guard.row[change]
    guard.row[change] = (
        not original
        if isinstance(original, bool)
        else original + SECOND
        if isinstance(original, int)
        else "changed"
    )
    with pytest.raises(ValueError, match="joint_window"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert not ledger.state.attempts and guard.revocations == 1
    guard.row[change] = original
    with pytest.raises(ValueError, match="joint_window_closed_or_foreign_owner"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)


def test_expired_horizon_and_unknown_market_charge_never_prepare(scope):
    window, guard, ledger, clock = scope
    clock.now += 302 * SECOND
    with pytest.raises(ValueError, match="joint_window_future_exclusion_expired"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert guard.revocations == 1 and not ledger.state.attempts


def test_market_charge_unknown_refuses_before_ledger_preparation(scope):
    window, guard, ledger, clock = scope
    clock.now += 300 * SECOND
    with pytest.raises(ValueError, match="joint_window_unknown_operation_charge"):
        window.prepare(operation="market_connect", joint_prefix_sha256="c" * 64)
    assert not ledger.state.attempts and guard.revocations == 1


def test_known_operation_out_of_order_refuses_before_ledger_preparation(scope):
    window, guard, ledger, clock = scope
    clock.now += 300 * SECOND
    with pytest.raises(ValueError, match="joint_window_first_operation_only"):
        window.prepare(operation="account_read", joint_prefix_sha256="c" * 64)
    assert not ledger.state.attempts and guard.revocations == 1


def test_journal_failure_halts_and_revokes_without_dispatch(scope, monkeypatch):
    window, guard, ledger, clock = scope
    clock.now += 300 * SECOND
    append = ledger.journal.append

    def fail(kind, **fields):
        if kind == "prepared":
            raise OSError("disk_failure")
        return append(kind, **fields)

    monkeypatch.setattr(ledger.journal, "append", fail)
    with pytest.raises(OSError, match="disk_failure"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert guard.revocations == 1 and ledger.failed
    with pytest.raises(ValueError, match="joint_window_closed_or_foreign_owner"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)


def test_foreign_process_identity_refuses_before_guard_or_ledger(scope):
    window, guard, ledger, clock = scope
    clock.now += 300 * SECOND
    window.owner = os.getpid() + 1
    try:
        with pytest.raises(ValueError, match="joint_window_closed_or_foreign_owner"):
            window.prepare(operation="time", joint_prefix_sha256="c" * 64)
        assert not ledger.state.attempts and not ledger.failed and guard.revocations == 0
    finally:
        window.owner = os.getpid()


def test_monotonic_regression_halts_before_any_preparation(scope):
    window, guard, ledger, clock = scope
    clock.now -= 1
    with pytest.raises(ValueError, match="joint_window_monotonic_clock_regressed"):
        window.prepare(operation="time", joint_prefix_sha256="c" * 64)
    assert guard.revocations == 1 and not ledger.state.attempts


def test_invalid_lookback_revokes_without_reusing_consumed_scope(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    clock, guard = Clock(), Guard()
    ledger = attempts.AttemptLedger(
        root,
        binding=Binding(),
        binding_sha256=PIN,
        clock=clock.pair,
        profile=attempts.JOINT_PROFILE,
    )
    try:
        with pytest.raises(ValueError, match="joint_window_fixed_new_ledger_and_lookback_required"):
            module.ProspectiveJointWindow(guard, ledger, lookback_ns=299 * SECOND, clock=clock.mono)
        assert guard.revocations == 1 and not ledger.state.attempts
        with pytest.raises(FileExistsError):
            attempts.AttemptLedger(
                root,
                binding=Binding(),
                binding_sha256=PIN,
                clock=clock.pair,
                profile=attempts.JOINT_PROFILE,
            )
    finally:
        ledger.close()


def test_short_initial_exclusion_consumes_scope_and_revokes(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    clock, guard = Clock(), Guard(duration=424)
    ledger = attempts.AttemptLedger(
        root,
        binding=Binding(),
        binding_sha256=PIN,
        clock=clock.pair,
        profile=attempts.JOINT_PROFILE,
    )
    try:
        with pytest.raises(ValueError, match="joint_window_full_horizon_missing"):
            module.ProspectiveJointWindow(guard, ledger, lookback_ns=300 * SECOND, clock=clock.mono)
        assert guard.revocations == 1 and ledger.failed
        with pytest.raises(FileExistsError):
            attempts.AttemptLedger(
                root,
                binding=Binding(),
                binding_sha256=PIN,
                clock=clock.pair,
                profile=attempts.JOINT_PROFILE,
            )
    finally:
        ledger.close()

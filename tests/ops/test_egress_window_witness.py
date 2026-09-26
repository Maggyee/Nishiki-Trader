"""One-shot window snapshots remain local samples, never activation proof."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "infra/egress-guard/gateway_window_witness.py"
START = 1_000_000_000_000
SECOND = 1_000_000_000


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("egress_window_witness_test", SOURCE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        self.now += 1
        return self.now


class Snapshotter:
    def __init__(self, clock):
        self.clock = clock
        self.calls = 0
        self.selection = "a" * 64
        self.pins = {"inet": "b" * 64, "netdev": "c" * 64}
        self.expiry = START + 426 * SECOND

    def observe(self):
        self.calls += 1
        finished = self.clock()
        return {
            "schema_version": "portfolio.root_selected_joint_window_snapshot.v1",
            "status": "root_selected_kernel_snapshot_unqualified",
            "selection_sha256": self.selection,
            "kernel_snapshot": {
                "schema_version": "portfolio.local_kernel_window_observation.v1",
                "status": "local_kernel_timers_observed_unqualified",
                "static_rules_sha256": self.pins,
                "observed_monotonic_ns": [finished - 1, finished],
                "minimum_blackout_through_monotonic_ns": self.expiry,
                "remaining_ns_lower_bound": self.expiry - finished,
                "source_authenticated": False,
                "complete_caller_coverage_verified": False,
                "network_admitted": False,
            },
            "activation_history_verified": False,
            "source_authenticated": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
        }


@pytest.fixture
def scope(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    clock = Clock()
    snapshotter = Snapshotter(clock)
    witness = module.WindowWitness(root, snapshotter, clock=clock)
    try:
        yield module, witness, snapshotter, clock, root
    finally:
        witness.close()


def test_claim_precedes_snapshot_and_scope_never_reopens(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    clock = Clock()
    snapshotter = Snapshotter(clock)
    original = snapshotter.observe
    counts = []

    def verify_claim_first():
        raw = (root / module.SCOPE / "events.jsonl").read_bytes()
        counts.append(module.replay(raw, expected_sha256=module.digest(raw))["observations"])
        return original()

    snapshotter.observe = verify_claim_first
    witness = module.WindowWitness(root, snapshotter, clock=clock)
    try:
        result = witness.observe()
        assert counts == [0, 1]
        assert result["observations"] == 2
        assert result["activation_history_verified"] is False
        assert result["complete_caller_coverage_verified"] is False
        assert result["network_admitted"] is False
        raw = witness.expected
        assert module.replay(raw, expected_sha256=module.digest(raw)) == result
    finally:
        witness.close()
    with pytest.raises(FileExistsError):
        module.WindowWitness(root, snapshotter, clock=clock)


def test_elapsed_lookback_and_future_timer_do_not_promote_samples(scope):
    _, witness, _, clock, _ = scope
    clock.now += 300 * SECOND
    report = witness.observe()
    assert report["minimum_observed_expiry_ns"] > clock.now + 125 * SECOND
    assert report["activation_history_verified"] is False
    assert report["source_authenticated"] is False
    assert report["complete_caller_coverage_verified"] is False
    assert report["network_admitted"] is False


@pytest.mark.parametrize("damage", ["before_claim", "expired"])
def test_stale_or_expired_observation_halts(scope, damage):
    _, witness, snapshotter, clock, _ = scope
    original = snapshotter.observe

    def stale():
        row = original()
        row["kernel_snapshot"]["observed_monotonic_ns"][0] = START
        return row

    if damage == "before_claim":
        snapshotter.observe = stale
    else:
        snapshotter.expiry = clock.now + 2
    with pytest.raises(ValueError, match="joint_witness_observation_clock_invalid"):
        witness.observe()
    assert witness.failed


@pytest.mark.parametrize("change", ["selection", "pins", "expiry"])
def test_selection_or_timer_renewal_halts_without_reopening(scope, change):
    _, witness, snapshotter, _, _ = scope
    if change == "selection":
        snapshotter.selection = "d" * 64
    elif change == "pins":
        snapshotter.pins = {"inet": "d" * 64, "netdev": "c" * 64}
    else:
        snapshotter.expiry += 2 * SECOND
    with pytest.raises(ValueError, match="joint_witness"):
        witness.observe()
    assert witness.failed
    with pytest.raises(ValueError, match="joint_witness_closed_or_foreign_owner"):
        witness.observe()


def test_rehashed_archive_with_changed_selection_is_rejected(scope):
    module, witness, _, _, _ = scope
    witness.observe()
    lines = witness.expected.splitlines()
    changed = json.loads(lines[-1])
    changed["selection_sha256"] = "d" * 64
    lines[-1] = module.canonical(changed)
    raw = b"\n".join(lines) + b"\n"
    with pytest.raises(ValueError, match="joint_witness_archive_selection_changed"):
        module.replay(raw, expected_sha256=module.digest(raw))


def test_foreign_owner_halts_permanently(scope, monkeypatch):
    module, witness, _, _, _ = scope
    monkeypatch.setattr(module.os, "getpid", lambda: witness.owner + 1)
    with pytest.raises(ValueError, match="joint_witness_closed_or_foreign_owner"):
        witness.observe()
    monkeypatch.undo()
    assert witness.failed
    with pytest.raises(ValueError, match="joint_witness_closed_or_foreign_owner"):
        witness.observe()


def test_storage_replacement_refused(scope):
    _, witness, _, _, _ = scope
    raw = witness.expected
    witness.path.joinpath("events.jsonl").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="joint_witness_archive_changed"):
        witness.observe()
    assert witness.failed


def test_failed_fsync_consumes_scope_without_qualification(scope, monkeypatch):
    module, witness, _, _, root = scope
    original = os.fsync

    def fail_journal(fd):
        if fd == witness.fds[2]:
            raise OSError("fsync_failed")
        return original(fd)

    monkeypatch.setattr(module.os, "fsync", fail_journal)
    with pytest.raises(OSError, match="fsync_failed"):
        witness.observe()
    assert witness.failed
    with pytest.raises(FileExistsError):
        module.WindowWitness(root, Snapshotter(Clock()))


def test_snapshot_failure_keeps_claimed_scope(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    class Broken:
        def observe(self):
            raise RuntimeError("unavailable")

    with pytest.raises(RuntimeError, match="unavailable"):
        module.WindowWitness(root, Broken(), clock=Clock())
    raw = (root / module.SCOPE / "events.jsonl").read_bytes()
    report = module.replay(raw, expected_sha256=module.digest(raw))
    assert report["observations"] == 0 and report["network_admitted"] is False
    with pytest.raises(FileExistsError):
        module.WindowWitness(root, Broken(), clock=Clock())


def test_abrupt_process_exit_retains_consumed_claim(module, tmp_path):
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    child = """
import importlib.util,os,sys
spec=importlib.util.spec_from_file_location('joint_window_crash_probe',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Crash:
 def observe(self): os._exit(23)
module.WindowWitness(sys.argv[2],Crash())
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", child, str(SOURCE), str(root)],
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 23
    raw = (root / module.SCOPE / "events.jsonl").read_bytes()
    report = module.replay(raw, expected_sha256=module.digest(raw))
    assert report["observations"] == 0 and report["network_admitted"] is False
    with pytest.raises(FileExistsError):
        module.WindowWitness(root, Snapshotter(Clock()))

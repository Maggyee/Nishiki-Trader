"""Durability, drift and replay acceptance without venue or DNS access."""

import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.ops.portfolio_egress_ledger import main
from apps.strategies_nautilus import portfolio_egress_ledger as ledger
from tests.ops.test_egress_authority_binding import binder as binder
from tests.ops.test_egress_authority_binding import open_binding
from tests.ops.test_egress_authority_binding import prepared as prepared
from tests.ops.test_egress_installation import policy as policy
from tests.ops.test_egress_installation import staged as staged

PIN = "a" * 64


class Tick:
    def __init__(self):
        self.utc = 1_000_000_000
        self.mono = 1_000_000_000

    def __call__(self):
        self.utc += 1_000_000
        self.mono += 1_000_000
        return self.utc, self.mono


@pytest.fixture
def active(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("network/DNS forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    binding = SimpleNamespace(verify=lambda: {"binding_sha256": PIN})
    writer = ledger.AttemptLedger(root, binding=binding, binding_sha256=PIN, clock=Tick())
    yield writer
    writer.close()


def review(writer, **kwargs):
    raw = (writer.path / "events.jsonl").read_bytes()
    return ledger.replay(raw, expected_sha256=ledger.digest(raw), binding_sha256=PIN, **kwargs)


def prepare(writer, caller="collector", operation="exchange_info"):
    return writer.prepare(caller=caller, operation=operation)["index"]


def test_mixed_callers_roles_and_unknown_charges(active):
    for caller, operation in zip(
        sorted(ledger.CALLERS),
        [
            "exchange_info",
            "account_connect",
            "account_subscribe",
            "market_connect",
            "exchange_info",
        ],
        strict=True,
    ):
        index = prepare(active, caller, operation)
        active.outcome(index=index, result="succeeded")
    active.close()
    report = review(active)
    assert report["recorded_attempts"] == 5
    assert sum(c["documented_weight"] for c in report["counts"]) == 44
    assert sum(c["unknown_charge_attempts"] for c in report["counts"]) == 1
    assert sum(c["connection_attempts"] for c in report["counts"]) == 2
    assert sum(c["raw_requests"] for c in report["counts"]) == 2
    assert report["used_upper_bound"] is None
    assert report["other_callers_upper_bound"] is None
    assert not any(
        report[k]
        for k in (
            "network_admitted",
            "trading_admitted",
            "complete_caller_coverage_verified",
            "coverage_between_observations_verified",
            "caller_labels_authenticated",
            "future_enforcement_verified",
            "restart_allowed",
        )
    )


@pytest.mark.parametrize("result", ["failed", "uncertain", None])
def test_failed_or_pending_never_refund_or_reopen(active, result):
    index = prepare(active)
    if result:
        active.outcome(index=index, result=result)
        with pytest.raises(ValueError, match="no_retry"):
            prepare(active)
    active.close()
    report = review(active)
    assert report["counts"][0]["documented_weight"] == 20
    assert report["counts"][0]["outcomes"][result or "uncertain"] == 1
    with pytest.raises(FileExistsError):
        ledger.AttemptLedger(active.root, binding=active.binding, binding_sha256=PIN)


def test_inclusive_interval_and_empty_interval_not_zero_usage(active):
    prepare(active)
    edge = active.state.attempts[0]["prepared_monotonic_ns"]
    assert review(active, start_ns=edge, through_ns=edge)["counts"][0]["prepared_attempts"] == 1
    empty = review(active, start_ns=edge + 1, through_ns=edge + 2)
    assert empty["counts"] == [] and empty["used_upper_bound"] is None
    assert not empty["complete_caller_coverage_verified"]
    with pytest.raises(ValueError, match="interval"):
        review(active, start_ns=edge + 1, through_ns=edge)


@pytest.mark.parametrize("after_persist", [False, True])
def test_binding_drift_consumes_only_durable_preparation(active, after_persist):
    calls = 0

    def drift():
        nonlocal calls
        calls += 1
        return {"binding_sha256": PIN if after_persist and calls == 1 else "b" * 64}

    active.binding.verify = drift
    with pytest.raises(ValueError, match="binding_changed"):
        prepare(active)
    active.binding.verify = lambda: {"binding_sha256": PIN}
    with pytest.raises(ValueError, match="no_retry"):
        prepare(active)
    report = review(active)
    assert report["recorded_attempts"] == int(after_persist)
    assert report["status"] == "gap"
    assert report["observed_gap"]["through_monotonic_ns"] is None


@pytest.mark.parametrize("damage", ["regress", "wall_jump", "monotonic_jump"])
def test_clock_discontinuity_halts(active, damage):
    prepare(active)
    if damage == "regress":
        active.clock.mono -= 10_000_000
        active.clock.utc -= 10_000_000
    elif damage == "wall_jump":
        active.clock.utc += 100_000_000
    else:
        active.clock.mono += 100_000_000
    with pytest.raises(ValueError, match="clock"):
        active.outcome(index=0, result="succeeded")
    assert review(active)["counts"][0]["outcomes"]["uncertain"] == 1


@pytest.mark.parametrize(
    "damage", ["bytes", "missing", "replace", "hardlink", "symlink", "mode", "directory"]
)
def test_storage_drift_halts_and_descriptors_close(active, damage):
    prepare(active)
    archive = active.path / "events.jsonl"
    raw = archive.read_bytes()
    if damage == "bytes":
        archive.write_bytes(raw + b"corrupt")
    elif damage == "missing":
        archive.unlink()
    elif damage == "replace":
        archive.unlink()
        archive.write_bytes(raw)
        archive.chmod(0o600)
    elif damage == "hardlink":
        os.link(archive, archive.with_name("alias"))
    elif damage == "symlink":
        archive.rename(archive.with_name("original"))
        archive.symlink_to("original")
    elif damage == "mode":
        archive.chmod(0o644)
    else:
        active.path.chmod(0o755)
    with pytest.raises((ValueError, OSError)):
        active.checkpoint()
    assert active.failed
    held = [*active.fds, active.journal.fd]
    active.close()
    for fd in held:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_outcome_fsync_failure_retains_uncertain_attempt(active, monkeypatch):
    prepare(active)
    original = os.fsync
    calls = 0

    def fail(fd):
        nonlocal calls
        if fd == active.journal.fd:
            calls += 1
            if calls == 2:  # observation persists, outcome does not
                raise OSError("fixture fsync failure")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        active.outcome(index=0, result="succeeded")
    report = review(active)
    assert report["status"] == "incomplete_no_resume"
    assert report["pending_attempt"] == 0
    assert report["counts"][0]["outcomes"]["uncertain"] == 1
    with pytest.raises(ValueError, match="no_retry"):
        prepare(active)


def test_concurrent_preparations_only_one_record(active):
    def attempt(_):
        try:
            return prepare(active)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results, key=lambda x: x is None) == [0, None]
    assert review(active)["recorded_attempts"] == 1
    assert active.failed


def test_fork_cannot_use_or_close_parent_writer(active):
    child = os.fork()
    if child == 0:
        try:
            for action in (lambda: prepare(active), active.close):
                try:
                    action()
                except ValueError as exc:
                    if str(exc) != "foreign_ledger_owner":
                        os._exit(4)
                else:
                    os._exit(3)
            os._exit(0)
        except BaseException:
            os._exit(2)
    assert os.waitpid(child, 0)[1] == 0
    assert prepare(active) == 0


@pytest.mark.parametrize("damage", ["source", "route"])
def test_real_held_binding_drives_ledger_refusal(tmp_path, binder, policy, prepared, damage):
    binding = open_binding(binder, policy, prepared)
    pin = binding.verify()["binding_sha256"]
    root = tmp_path / "attempts"
    root.mkdir(mode=0o700)
    writer = ledger.AttemptLedger(root, binding=binding, binding_sha256=pin)
    try:
        prepare(writer)
        if damage == "source":
            source = prepared[0] / (binder.BOOTSTRAP_CODE + "/http_parser.py").lstrip("/")
            source.chmod(0o600)
            source.write_bytes(b"changed source")
        else:
            prepared[2]["selected_route"][0]["prefsrc"] = "10.0.0.137"
        with pytest.raises(ValueError):
            writer.outcome(index=0, result="succeeded")
        assert binding.closed and writer.failed
        raw = (writer.path / "events.jsonl").read_bytes()
        report = ledger.replay(raw, expected_sha256=ledger.digest(raw), binding_sha256=pin)
        assert report["status"] == "gap" and report["pending_attempt"] == 0
    finally:
        writer.close()
        binding.close()


def rechain(rows):
    result, previous = b"", None
    for seq, row in enumerate(rows):
        row.update(seq=seq, previous_sha256=previous)
        line = ledger.canonical(row) + b"\n"
        result += line
        previous = ledger.digest(line)
    return result


@pytest.mark.parametrize(
    "damage",
    [
        "hash",
        "canonical",
        "chain",
        "index",
        "caller",
        "operation",
        "outcome",
        "binding",
        "after_end",
        "payload",
    ],
)
def test_replay_rejects_byte_chain_and_semantic_mutations(active, damage):
    prepare(active)
    active.outcome(index=0, result="succeeded")
    active.close()
    raw = (active.path / "events.jsonl").read_bytes()
    selected = ledger.digest(raw)
    rows = [json.loads(line) for line in raw.splitlines()]
    prep = next(r for r in rows if r["kind"] == "prepared")
    if damage == "hash":
        selected = "0" * 64
    elif damage == "canonical":
        raw = raw.replace(b'"kind":', b'"kind": ', 1)
    elif damage == "chain":
        rows[1]["previous_sha256"] = "f" * 64
        raw = b"".join(ledger.canonical(r) + b"\n" for r in rows)
    else:
        if damage == "index":
            prep["payload"]["index"] = True
        elif damage in ("caller", "operation"):
            prep["payload"][damage] = "invented"
        elif damage == "outcome":
            next(r for r in rows if r["kind"] == "outcome")["payload"]["index"] = 5
        elif damage == "binding":
            prep["binding_sha256"] = "b" * 64
        elif damage == "after_end":
            rows.append(dict(rows[-1]))
        else:
            prep["payload"] = []
        raw = rechain(rows)
    if damage != "hash":
        selected = ledger.digest(raw)
    with pytest.raises(ValueError):
        ledger.replay(raw, expected_sha256=selected, binding_sha256=PIN)


def cli_args(archive, report):
    return [
        "--archive",
        str(archive),
        "--archive-sha256",
        ledger.digest(archive.read_bytes()),
        "--binding-sha256",
        PIN,
        "--report",
        str(report),
    ]


def test_sigkill_and_two_independent_replays(tmp_path):
    root = tmp_path / "killed"
    root.mkdir(mode=0o700)
    code = """
import os, signal, sys
from types import SimpleNamespace
from apps.strategies_nautilus.portfolio_egress_ledger import AttemptLedger
pin = "a" * 64
writer = AttemptLedger(sys.argv[1], binding=SimpleNamespace(verify=lambda: {"binding_sha256": pin}), binding_sha256=pin)
writer.prepare(caller="proxy", operation="exchange_info")
os.kill(os.getpid(), signal.SIGKILL)
"""
    killed = subprocess.run([sys.executable, "-c", code, str(root)], timeout=20)
    assert killed.returncode == -signal.SIGKILL
    archive = root / ledger.SCOPE / "events.jsonl"
    outputs = []
    for number in (1, 2):
        path = tmp_path / f"report-{number}.json"
        result = subprocess.run(
            [sys.executable, "-m", "apps.ops.portfolio_egress_ledger", *cli_args(archive, path)],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 2, result.stderr
        outputs.append(path.read_bytes())
    assert outputs[0] == outputs[1]
    report = json.loads(outputs[0])
    assert report["pending_attempt"] == 0 and report["status"] == "incomplete_no_resume"
    assert report["counts"][0]["documented_weight"] == 20
    with pytest.raises(FileExistsError):
        ledger.AttemptLedger(root, binding=None, binding_sha256=PIN)


def test_cli_interval_pair_and_no_overwrite(active, tmp_path):
    prepare(active)
    active.close()
    archive, report = active.path / "events.jsonl", tmp_path / "report.json"
    args = cli_args(archive, report)
    assert main([*args, "--start-monotonic-ns", "1"]) == 1
    assert not report.exists()
    assert main(args) == 2
    original = report.read_bytes()
    assert main(args) == 1
    assert report.read_bytes() == original
    assert main(cli_args(archive, archive)) == 1


def test_initialization_failure_leaks_no_descriptors_and_consumes_scope(tmp_path):
    tmp_path.chmod(0o700)
    before = len(list(Path("/proc/self/fd").iterdir()))
    bad = SimpleNamespace(verify=lambda: {"binding_sha256": "b" * 64})
    with pytest.raises(ValueError, match="binding_changed"):
        ledger.AttemptLedger(tmp_path, binding=bad, binding_sha256=PIN)
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    with pytest.raises(FileExistsError):
        ledger.AttemptLedger(tmp_path, binding=bad, binding_sha256=PIN)


def test_preparation_fsync_failure_never_returns_receipt(active, monkeypatch):
    original = os.fsync
    calls = 0

    def fail(fd):
        nonlocal calls
        if fd == active.journal.fd:
            calls += 1
            if calls == 2:
                raise OSError("preparation not acknowledged")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        prepare(active)
    assert review(active)["recorded_attempts"] == 0
    assert active.failed and active.journal.failed
    with pytest.raises(ValueError, match="no_retry"):
        prepare(active)
    with pytest.raises(FileExistsError):
        ledger.AttemptLedger(active.root, binding=active.binding, binding_sha256=PIN)


def test_journal_ceiling_keeps_incident_reserve(active):
    active.journal.limit = active.journal.size + active.journal.reserve
    with pytest.raises(ValueError, match="archive_limit"):
        active.checkpoint()
    assert review(active)["status"] == "gap"
    assert active.failed


def test_observations_do_not_qualify_coverage(active):
    for _ in range(3):
        active.checkpoint()
    report = review(active)
    assert report["counts"] == []
    assert report["used_upper_bound"] is None
    assert not report["coverage_between_observations_verified"]


@pytest.mark.parametrize("mode", [0o755, 0o770])
def test_nonprivate_root_refused(tmp_path, mode):
    tmp_path.chmod(mode)
    with pytest.raises(ValueError, match="private_owned"):
        ledger.AttemptLedger(tmp_path, binding=None, binding_sha256=PIN)
    assert not (tmp_path / ledger.SCOPE).exists()

"""Fail closed at the gap between joint preparation, persistence and transport."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_joint_egress import (
    JointAccounting,
    classify,
    replay_accounted,
)
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence, Wire
from apps.strategies_nautilus.portfolio_joint_tls_transport import TLSBackend
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_joint_observation import Clock
from tests.strategies_nautilus.test_portfolio_joint_tls_evidence import selection


@pytest.fixture
def active(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("unexpected network")

    monkeypatch.setattr(asyncio, "open_connection", forbidden)
    clock = Clock()
    journal = joint.JointJournal(
        tmp_path / "joint.jsonl",
        manifest=selection(clock, b"fixture"),
        clock=clock,
        evidence_type=TLSJointEvidence,
    )
    root = tmp_path / "attempts"
    root.mkdir(mode=0o700)
    accounting = JointAccounting(journal, root)
    yield accounting
    accounting.close(succeeded=False)
    journal.close()


def prepare(accounting):
    j = accounting.journal
    op, index = j.state.next_operation(), j.state.prepared_count
    j.append("operation_prepared", operation=op, operation_id=index, request_id=f"loopback-{index}")
    accounting.prepare(op, index)


def report(accounting):
    raw = (accounting.ledger.path / "events.jsonl").read_bytes()
    return attempts.replay(
        raw,
        expected_sha256=joint.digest(raw),
        binding_sha256=accounting.pin,
        profile=attempts.JOINT_PROFILE,
    )


def test_unprepared_transport_rejected(active):
    with pytest.raises(DepthError, match="unprepared"):
        active.before_wire("connect")
    assert report(active)["recorded_attempts"] == 0


@pytest.mark.parametrize("stage", ["connect", "request"])
def test_repeated_send_has_no_second_attempt(active, stage):
    prepare(active)
    active.before_wire("connect")
    if stage == "request":
        active.before_wire("request")
    with pytest.raises(DepthError, match="repeated"):
        active.before_wire(stage)
    assert report(active)["recorded_attempts"] == 1
    assert report(active)["pending_attempt"] == 0
    with pytest.raises(DepthError, match="no_retry"):
        active.before_wire("connect")


def test_request_cannot_precede_connect(active):
    prepare(active)
    with pytest.raises(DepthError, match="wire_order"):
        active.before_wire("request")


def test_no_outcome_before_validated_response(active):
    prepare(active)
    active.before_wire("connect")
    active.before_wire("request")
    with pytest.raises(DepthError, match="response_required"):
        active.outcome()
    assert report(active)["counts"][0]["outcomes"]["uncertain"] == 1


def test_preparation_not_repeated(active):
    prepare(active)
    with pytest.raises(DepthError, match="preparation_order"):
        active.prepare(active.journal.state.prepared["operation"], 0)
    assert report(active)["recorded_attempts"] == 1


@pytest.mark.parametrize("damage", ["path", "mode", "bytes", "manifest"])
def test_binding_drift_between_prepare_and_connect(active, damage):
    prepare(active)
    if damage == "path":
        raw = active.path.read_bytes()
        active.path.unlink()
        active.path.write_bytes(raw)
        active.path.chmod(0o600)
    elif damage == "mode":
        active.path.chmod(0o644)
    elif damage == "bytes":
        with active.path.open("ab") as f:
            f.write(b" ")
    else:
        active.journal.state.manifest["tls_trust_sha256"] = "b" * 64
    with pytest.raises((DepthError, ValueError)):
        active.before_wire("connect")
    assert report(active)["recorded_attempts"] == 1
    assert report(active)["status"] == "gap"


def test_stale_after_durable_preparation_consumes_but_cannot_connect(active, monkeypatch):
    prepare(active)
    original = active.journal.clock

    # The ledger shares the same clock origin; advancing both clocks is not drift.
    def later():
        now, mono = original()
        return now + 5_100_000_000, mono + 5_100_000_000

    active.journal.clock = active.ledger.clock = later
    with pytest.raises(DepthError, match="stale_dispatch"):
        active.before_wire("connect")
    assert report(active)["pending_attempt"] == 0


@pytest.mark.parametrize(
    "operation",
    [
        {"kind": "rest", "method": "POST", "path": "/api/v3/order", "weight": 1},
        {
            "kind": "rest",
            "method": "GET",
            "path": "/api/v3/depth",
            "params": {"limit": "5000"},
            "weight": 5,
        },
        {"kind": "rest", "method": "GET", "path": "/api/v3/account", "weight": 1},
        {"kind": "ws", "operation": "order.place", "weight": 2},
        {"kind": "market_connection", "weight": False},
    ],
)
def test_misclassified_or_trading_operation_rejected(operation):
    with pytest.raises(DepthError):
        classify(operation)


def test_profile_is_explicit_and_old_scope_remains_fixed(active):
    prepare(active)
    raw = (active.ledger.path / "events.jsonl").read_bytes()
    with pytest.raises(ValueError, match="profile_or_binding"):
        attempts.replay(raw, expected_sha256=joint.digest(raw), binding_sha256=active.pin)
    assert active.ledger.path.name == attempts.JOINT_SCOPE
    assert attempts.OPERATIONS.get("time") is None
    assert attempts.JOINT_OPERATIONS["market_connect"]["documented_weight"] is None


def test_incomplete_joint_cannot_claim_complete_accounting(active):
    prepare(active)
    raw = (active.ledger.path / "events.jsonl").read_bytes()
    with pytest.raises(DepthError, match="completed_joint"):
        replay_accounted(
            active.path.read_bytes(),
            raw,
            joint_sha256=joint.digest(active.path.read_bytes()),
            ledger_sha256=joint.digest(raw),
        )


def test_chunk_samples_clock_before_raw_encoding_or_disk(active, monkeypatch):
    journal = active.journal
    backend = object.__new__(TLSBackend)
    backend.journal = journal
    result = {}
    moment = journal.clock()
    monkeypatch.setattr(journal, "clock", lambda: moment)
    monkeypatch.setattr(journal, "append", lambda kind, **fields: result.update(fields))

    async def read(size):
        return b"chunk"

    def encode(raw):
        monkeypatch.setattr(
            journal, "clock", lambda: (moment[0] + 6_000_000_000, moment[1] + 6_000_000_000)
        )
        return joint.raw_fields(raw)

    monkeypatch.setattr("apps.strategies_nautilus.portfolio_joint_tls_transport.raw_fields", encode)
    asyncio.run(backend.chunk(0, SimpleNamespace(read=read)))
    assert (result["received_ns"], result["monotonic_ns"]) == moment


def test_header_receipt_not_refreshed_by_slow_body():
    wire = Wire({"role": "http", "websocket_nonce": None})
    headers = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX-MBX-USED-WEIGHT-1M: 1\r\n\r\n"
    wire.feed({"received_ns": 1, **joint.raw_fields(headers)})
    wire.feed({"received_ns": 6_000_000_001, **joint.raw_fields(b"{}")})
    assert wire.header_receipt_ns == 1
    state = TLSJointEvidence()
    state.manifest = {"budget_sample": {"observed_ns": 1}}
    state.usage = 0
    state.original_usage_receipt = wire.header_receipt_ns
    state.observe_usage(1, 6_000_000_001)
    assert state.usage_ns == 1


def assert_rehashed_links_refused(raw, ledger_raw):
    """Invoked by the shared real TLS acceptance, using its complete original pair."""
    for damage in ("prefix", "operation", "caller", "outcome", "early", "future_prefix"):
        rows = [json.loads(line) for line in ledger_raw.splitlines()]
        prepared = next(r for r in rows if r["kind"] == "prepared")
        outcome = next(r for r in rows if r["kind"] == "outcome")
        if damage == "prefix":
            prepared["payload"]["joint_prefix_sha256"] = "0" * 64
        elif damage == "operation":
            prepared["payload"]["operation"] = "exchange_info"
        elif damage == "caller":
            prepared["payload"]["caller"] = "host"
        elif damage == "outcome":
            outcome["payload"]["joint_prefix_sha256"] = prepared["payload"]["joint_prefix_sha256"]
        elif damage == "future_prefix":
            prepared["payload"]["joint_prefix_sha256"] = outcome["payload"]["joint_prefix_sha256"]
        else:
            for row in rows:
                row["utc_ns"] -= 1_000_000_000
                row["monotonic_ns"] -= 1_000_000_000
        previous = None
        encoded = []
        for row in rows:
            row["previous_sha256"] = previous
            line = canonical(row) + b"\n"
            previous = joint.digest(line)
            encoded.append(line)
        altered = b"".join(encoded)
        with pytest.raises((DepthError, ValueError)):
            replay_accounted(
                raw, altered, joint_sha256=joint.digest(raw), ledger_sha256=joint.digest(altered)
            )


def test_abrupt_exit_preserves_preparation_and_refuses_reopen(tmp_path):
    import signal
    import subprocess
    import sys

    root = tmp_path / "attempts"
    root.mkdir(mode=0o700)
    script = """
import os,signal,sys
from pathlib import Path
from apps.strategies_nautilus.portfolio_joint_egress import JointAccounting
from apps.strategies_nautilus.portfolio_joint_observation import JointJournal
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
from tests.strategies_nautilus.test_portfolio_joint_tls_evidence import selection
from tests.strategies_nautilus.test_portfolio_joint_observation import Clock
clock = Clock()
root = Path(sys.argv[1])
j = JointJournal(root.parent / 'joint.jsonl', manifest=selection(clock,b'fixture'), clock=clock, evidence_type=TLSJointEvidence)
a = JointAccounting(j,root)
op = j.state.next_operation()
j.append('operation_prepared',operation=op,operation_id=0,request_id='loopback-0')
a.prepare(op,0)
os.kill(os.getpid(),signal.SIGKILL)
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(root)], capture_output=True, timeout=30
    )
    assert proc.returncode == -signal.SIGKILL, proc.stderr
    path = root / attempts.JOINT_SCOPE / "events.jsonl"
    raw = path.read_bytes()
    pin = json.loads(raw.splitlines()[0])["binding_sha256"]
    result = attempts.replay(
        raw, expected_sha256=joint.digest(raw), binding_sha256=pin, profile=attempts.JOINT_PROFILE
    )
    assert result["pending_attempt"] == 0
    assert result["recorded_attempts"] == 1
    assert result["status"] == "incomplete_no_resume"
    with pytest.raises(FileExistsError):
        attempts.AttemptLedger(
            root, binding=None, binding_sha256=pin, profile=attempts.JOINT_PROFILE
        )
    assert path.read_bytes() == raw

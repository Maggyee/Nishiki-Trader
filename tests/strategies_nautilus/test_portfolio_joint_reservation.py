"""Signed per-step accounting and crash-safe, network-free rehearsal acceptance."""

import base64
import json
import os
import socket
import subprocess
import sys

import pytest
from nautilus_trader.core.nautilus_pyo3 import ed25519_signature

from apps.ops.portfolio_joint_reservation import main
from apps.strategies_nautilus import portfolio_joint_attestation as proof
from apps.strategies_nautilus import portfolio_joint_reservation as rehearsal
from apps.strategies_nautilus.portfolio_joint_admission import sha
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_joint_admission import MONO, NOW, S, candidate
from tests.strategies_nautilus.test_portfolio_joint_attestation import SCOPE, keys, selected

keys = keys  # Reuse the ephemeral native-signing fixture; never load trading keys.
TICK = 50_000_000


class Clock:
    def __init__(self):
        self.tick = 0
        self.wall_shift = 0

    def __call__(self):
        return NOW + self.tick * TICK + self.wall_shift, MONO + self.tick * TICK


def evidence(keys, index, *, tick=None, base_used=80, change=None):
    tick = index if tick is None else tick
    now, mono = NOW + tick * TICK, MONO + tick * TICK
    consumed = rehearsal.maximum_operations()[:index]
    weight = sum(r.get("weight", 0) for r in consumed)
    rests = sum(r["kind"] == "rest" for r in consumed)
    counts = {
        r: sum(
            o.get("operation") in {"ws_api_connection", "market_connection"} and o["kind"] == r
            for o in consumed
        )
        for r in ("account", "market")
    }
    value = candidate()
    for role, samples in value["samples"].items():
        sample = samples[0]
        sample.update(received_ns=now, monotonic_ns=mono, server_time_ns=[now, now + 10_000_000])
        if role == "rest":
            sample["headers"][0][1] = str(70 + weight)
        else:
            body = json.loads(base64.b64decode(sample["raw_b64"]))
            body["rateLimits"][0]["count"] = 70 + weight
            raw = canonical(body)
            sample.update(raw_b64=base64.b64encode(raw).decode(), body_sha256=sha(raw))
    ledger = value["ledger"]
    ledger.update(covered_through_ns=now + 10_000_000, future_through_ns=now + 126 * S)
    for row in ledger["usage_bounds"]:
        if row["rate_limit_type"] == "REQUEST_WEIGHT":
            row["used_upper_bound"] = base_used + weight
        elif row["rate_limit_type"] == "RAW_REQUESTS":
            row["used_upper_bound"] += rests
        else:
            row["used_upper_bound"] += counts[row["role"]]
    for i, operation in enumerate(consumed):
        if operation.get("operation") in {"ws_api_connection", "market_connection"}:
            ledger["connection_attempts"].append(
                {
                    "id": f"local-{i}",
                    "role": operation["kind"],
                    "server_time_ns": [NOW + i * TICK, NOW + i * TICK],
                    "outcome": "succeeded",
                }
            )
    if change:
        change(value)
    inputs = selected(keys, value=value)
    policy = json.loads(inputs["policy_raw"])
    policy["not_after_ns"] = NOW + 180 * S
    inputs.update(policy_raw=canonical(policy), policy_sha256=sha(canonical(policy)))
    bundle = json.loads(inputs["bundle_raw"])
    for role in proof.ROLES:
        claim = json.loads(base64.b64decode(bundle[role]["payload_b64"]))
        claim.update(
            issued_at_ns=now, expires_at_ns=now + 5 * S, policy_sha256=inputs["policy_sha256"]
        )
        raw = canonical(claim)
        bundle[role] = {
            "payload_b64": base64.b64encode(raw).decode(),
            "signature_b64": ed25519_signature(keys[role][0], (proof.DOMAIN + raw).decode()),
        }
    inputs.update(bundle_raw=canonical(bundle), bundle_sha256=sha(canonical(bundle)))
    return inputs


def create(tmp_path, keys, clock, *, filename="rehearsal.jsonl"):
    inputs = evidence(keys, 0)
    path = tmp_path / filename
    journal = rehearsal.ReservationRehearsal(
        path,
        policy_raw=inputs["policy_raw"],
        policy_sha256=inputs["policy_sha256"],
        scope_id=SCOPE,
        clock=clock,
    )
    return journal, path, inputs["policy_sha256"]


def prepare(journal, inputs, *, index=None, operation=None):
    index = journal.state.index if index is None else index
    return journal.prepare(
        index=index,
        operation=journal.state.operations[index] if operation is None else operation,
        **{
            k: inputs[k]
            for k in ("candidate_raw", "candidate_sha256", "bundle_raw", "bundle_sha256")
        },
    )


def replay(path, policy):
    raw = path.read_bytes()
    return rehearsal.replay(raw, expected_sha256=sha(raw), policy_sha256=policy, scope_id=SCOPE)


def finished(tmp_path, keys, *, base_used=80):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    try:
        for index in range(21):
            clock.tick = index
            prepare(journal, evidence(keys, index, base_used=base_used))
            journal.outcome(index=index, result="succeeded")
        journal.complete()
    finally:
        journal.close()
    return path, policy


def blocked_flags(report):
    for key in (
        "network_admitted",
        "source_authenticated",
        "shared_egress_verified",
        "capacity_reserved",
        "scope_consumed",
    ):
        assert report[key] is False
    assert report["venue_requests_made"] == 0
    assert not any(report["qualification"].values())
    assert all(
        v is None
        for k, v in report.items()
        if k.startswith("qualified_") or k == "common_account_market_revision"
    )


def test_full_maximum_scope_is_durable_and_still_not_network_admission(tmp_path, keys):
    path, policy = finished(tmp_path, keys)
    report = replay(path, policy)
    assert report["status"] == "completed"
    assert report["prepared_operations"] == 21
    assert report["rest_gets_consumed"] == 17
    assert report["documented_weight_consumed"] == 468
    assert report["connections_consumed"] == 2
    assert report["pending_operation_index"] is None
    assert set(report["last_remaining_review"]["blockers"]) == rehearsal.UNQUALIFIED
    assert "weight" not in next(o for o in rehearsal.maximum_operations() if o["kind"] == "market")
    assert path.stat().st_mode & 0o777 == 0o600
    blocked_flags(report)


def test_remaining_budget_does_not_charge_consumed_operations_twice(tmp_path, keys):
    path, policy = finished(tmp_path, keys, base_used=5522)
    report = replay(path, policy)
    last = report["last_remaining_review"]
    assert last["documented_weight_remaining"] == 2
    weights = [r for r in last["interval_reviews"] if r["rate_limit_type"] == "REQUEST_WEIGHT"]
    assert all(r["headroom_after_documented_reservation"] == 0 for r in weights)
    assert any(
        "remaining_scope_or_other_clients_exceed_limit" in b
        for b in last["full_scope_authorship_review"]["blockers"]
    )
    blocked_flags(report)


@pytest.mark.parametrize("result", ["failed", "uncertain"])
def test_failure_never_refunds_or_retries_preparation(tmp_path, keys, result):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    inputs = evidence(keys, 0)
    prepare(journal, inputs)
    journal.outcome(index=0, result=result)
    original = path.read_bytes()
    with pytest.raises(rehearsal.ReservationError, match="closed_no_retry"):
        prepare(journal, inputs)
    journal.close()
    assert path.read_bytes() == original
    report = replay(path, policy)
    assert report["status"] == result
    assert report["prepared_operations"] == 1 and report["documented_weight_consumed"] == 1
    with pytest.raises(FileExistsError):
        create(tmp_path, keys, clock)


@pytest.mark.parametrize(
    "change", ["pending", "index", "selector", "outcome", "premature_complete"]
)
def test_duplicate_or_reordered_lifecycle_stops_without_second_attempt(tmp_path, keys, change):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    inputs = evidence(keys, 0)
    prepare(journal, inputs)
    with pytest.raises(rehearsal.ReservationError):
        if change == "pending":
            prepare(journal, evidence(keys, 1))
        elif change == "outcome":
            journal.outcome(index=1, result="succeeded")
        elif change == "premature_complete":
            journal.complete()
        else:
            journal.outcome(index=0, result="succeeded")
            prepare(
                journal,
                evidence(keys, 1),
                index=0 if change == "index" else 1,
                operation={"method": "POST"} if change == "selector" else None,
            )
    journal.close()
    report = replay(path, policy)
    assert report["status"] == "aborted" and report["prepared_operations"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "used_bound",
        "other_clients",
        "usage_missing",
        "coverage",
        "rate_limit",
        "server_count",
        "source",
        "bad_signature",
    ],
)
def test_each_step_rechecks_signed_capacity_and_prior_preparations(tmp_path, keys, change):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    prepare(journal, evidence(keys, 0))
    journal.outcome(index=0, result="succeeded")
    clock.tick = 1

    def alter(value):
        bound = value["ledger"]["usage_bounds"][0]
        if change == "used_bound":
            bound["used_upper_bound"] -= 1  # Signed but omits the durable preceding GET.
        elif change == "other_clients":
            bound["other_clients_upper_bound"] = 6000
        elif change == "usage_missing":
            value["ledger"]["usage_bounds"].pop(1)
        elif change == "coverage":
            value["ledger"]["all_callers"] = False
        elif change == "rate_limit":
            sample = value["samples"]["rest"][0]
            raw = json.loads(base64.b64decode(sample["raw_b64"]))
            raw["rateLimits"][0]["limit"] += 1
            raw = canonical(raw)
            sample.update(raw_b64=base64.b64encode(raw).decode(), body_sha256=sha(raw))
        elif change == "server_count":
            value["samples"]["rest"][0]["headers"][0][1] = "69"
        elif change == "source":
            value["ledger"]["bindings"]["market"]["egress_ip"] = "198.51.100.2"

    inputs = evidence(keys, 1, change=alter)
    if change == "bad_signature":
        bundle = json.loads(inputs["bundle_raw"])
        bundle["source"]["signature_b64"] = base64.b64encode(b"x" * 64).decode()
        inputs.update(bundle_raw=canonical(bundle), bundle_sha256=sha(canonical(bundle)))
    with pytest.raises(ValueError):
        prepare(journal, inputs)
    assert journal.failed
    journal.close()
    assert replay(path, policy)["prepared_operations"] == 1


def test_expired_evidence_is_refused_at_preparation_time(tmp_path, keys):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    old = evidence(keys, 0)
    clock.tick = 100  # The claim expires exactly at this clock value.
    with pytest.raises(proof.AttestationError, match="expired"):
        prepare(journal, old)
    journal.close()
    assert replay(path, policy)["prepared_operations"] == 0


@pytest.mark.parametrize(
    "which", ["wall_jump", "request_timeout", "bucket", "capture_deadline", "shutdown_deadline"]
)
def test_dispatch_clock_deadlines_and_bucket_boundaries(tmp_path, keys, which):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    prepare(journal, evidence(keys, 0))
    if which != "request_timeout":
        journal.outcome(index=0, result="succeeded")
    if which == "wall_jump":
        clock.wall_shift = S
    else:
        clock.tick = {
            "request_timeout": 201,
            "bucket": 800,
            "capture_deadline": 2401,
            "shutdown_deadline": 2501,
        }[which]
    with pytest.raises(ValueError):
        if which == "request_timeout":
            journal.outcome(index=0, result="succeeded")
        else:
            prepare(journal, evidence(keys, 1, tick=clock.tick))
    journal.close()
    # A discontinuous/overlong archive is itself refused, never interpreted as a new scope.
    if which in {"wall_jump", "shutdown_deadline"}:
        with pytest.raises(ValueError):
            replay(path, policy)
    else:
        assert replay(path, policy)["prepared_operations"] == 1


def test_preparation_is_on_disk_before_it_returns(tmp_path, keys, monkeypatch):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    actual = os.fsync
    seen = []

    def inspect(fd):
        seen.append(path.read_bytes())
        actual(fd)

    monkeypatch.setattr(rehearsal.os, "fsync", inspect)
    prepare(journal, evidence(keys, 0))
    journal.close()
    assert any(json.loads(raw.splitlines()[-1])["kind"] == "prepared" for raw in seen)
    report = replay(path, policy)
    assert report["status"] == "incomplete_no_resume" and report["pending_operation_index"] == 0


def test_failed_fsync_never_returns_success_or_allows_retry(tmp_path, keys, monkeypatch):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)

    def fail(fd):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(rehearsal.os, "fsync", fail)
    with pytest.raises(OSError):
        prepare(journal, evidence(keys, 0))
    with pytest.raises(rehearsal.ReservationError, match="closed_no_retry"):
        prepare(journal, evidence(keys, 0))
    journal.close()
    with pytest.raises(ValueError):
        replay(path, policy)


def test_archive_bound_preserves_incident_and_blocks_followup(tmp_path, keys, monkeypatch):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    monkeypatch.setattr(rehearsal, "MAX_ARCHIVE", journal.size + rehearsal.INCIDENT_RESERVE)
    with pytest.raises(rehearsal.ReservationError, match="archive_full"):
        prepare(journal, evidence(keys, 0))
    journal.close()
    assert replay(path, policy)["status"] == "aborted"


def rehash(rows):
    previous = "0" * 64
    for seq, row in enumerate(rows):
        row.pop("sha256", None)
        row.update(seq=seq, previous=previous)
        previous = sha(canonical(row))
        row["sha256"] = previous
    return b"".join(canonical(r) + b"\n" for r in rows)


@pytest.mark.parametrize(
    "change", ["operation", "drop_preparation", "fake_complete", "evidence", "scope", "torn"]
)
def test_rehashed_archive_cannot_rewrite_scope_or_preparations(tmp_path, keys, change):
    clock = Clock()
    journal, path, policy = create(tmp_path, keys, clock)
    prepare(journal, evidence(keys, 0))
    journal.outcome(index=0, result="succeeded")
    journal.close()
    rows = [json.loads(r) for r in path.read_bytes().splitlines()]
    if change == "operation":
        rows[1]["payload"]["operation"]["weight"] = 0
    elif change == "drop_preparation":
        rows.pop(1)
    elif change == "fake_complete":
        rows[-1].update(kind="completed", payload={})
    elif change == "evidence":
        rows[1]["payload"]["candidate_sha256"] = "0" * 64
    elif change == "scope":
        rows[0]["payload"]["scope_id"] = "other"
    raw = rehash(rows)
    if change == "torn":
        raw = raw[:-1]
    with pytest.raises(ValueError):
        rehearsal.replay(raw, expected_sha256=sha(raw), policy_sha256=policy, scope_id=SCOPE)


def cli_args(path, policy, output):
    return [
        "--archive",
        str(path),
        "--archive-sha256",
        sha(path.read_bytes()),
        "--policy-sha256",
        policy,
        "--scope-id",
        SCOPE,
        "--report",
        str(output),
    ]


def test_fresh_cli_replays_match_and_do_not_activate_or_mutate_inputs(tmp_path, keys):
    path, policy = finished(tmp_path, keys)
    before = path.read_bytes()
    reports = []
    for i in range(2):
        output = tmp_path / f"report-{i}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_reservation",
                *cli_args(path, policy, output),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 2, proc.stdout + proc.stderr
        reports.append(output.read_bytes())
    assert reports[0] == reports[1]
    assert path.read_bytes() == before
    blocked_flags(json.loads(reports[0]))


def test_process_crash_retains_pending_attempt_and_cannot_reopen(tmp_path, keys):
    inputs = evidence(keys, 0)
    handoff = tmp_path / "public-fixture.json"
    handoff.write_bytes(
        canonical(
            {
                k: base64.b64encode(v).decode() if isinstance(v, bytes) else v
                for k, v in inputs.items()
            }
        )
    )
    path = tmp_path / "rehearsal.jsonl"
    script = """
import base64, json, os, sys
from pathlib import Path
from apps.strategies_nautilus.portfolio_joint_reservation import ReservationRehearsal
x=json.loads(Path(sys.argv[1]).read_bytes())
for k in list(x):
    if k.endswith('_raw'): x[k]=base64.b64decode(x[k])
j=ReservationRehearsal(Path(sys.argv[2]), policy_raw=x['policy_raw'], policy_sha256=x['policy_sha256'], scope_id=x['scope_id'], clock=lambda:(x['at_ns'], x['monotonic_ns']))
j.prepare(index=0, operation=j.state.operations[0], **{k:x[k] for k in ('candidate_raw','candidate_sha256','bundle_raw','bundle_sha256')})
os._exit(17)
"""
    proc = subprocess.run(
        [sys.executable, "-c", script, str(handoff), str(path)], capture_output=True, timeout=30
    )
    assert proc.returncode == 17, proc.stdout + proc.stderr
    report = replay(path, inputs["policy_sha256"])
    assert report["status"] == "incomplete_no_resume" and report["pending_operation_index"] == 0
    with pytest.raises(FileExistsError):
        create(tmp_path, keys, Clock())


def test_existing_owner_and_symlink_are_refused(tmp_path, keys):
    clock = Clock()
    first, path, _ = create(tmp_path, keys, clock)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        create(tmp_path, keys, clock)
    first.close()
    assert path.read_bytes() == before
    (tmp_path / "link.jsonl").symlink_to(path)
    with pytest.raises(FileExistsError):
        create(tmp_path, keys, clock, filename="link.jsonl")


def test_all_rehearsal_and_cli_paths_are_network_free(tmp_path, keys, monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("offline rehearsal attempted network I/O")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    path, policy = finished(tmp_path, keys)
    output = tmp_path / "report.json"
    assert main(cli_args(path, policy, output)) == 2
    before = output.read_bytes()
    assert main(cli_args(path, policy, output)) == 1
    assert output.read_bytes() == before
    assert set(tmp_path.iterdir()) == {path, output}

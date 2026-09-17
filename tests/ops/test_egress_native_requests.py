"""Fixed signed selectors must pass native generation, root verification and custody."""

import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger
from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_tls_receipt import channels as channels

PIN = "a" * 64


def challenge(index):
    return {
        "index": index,
        "nonce": "a" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
    }


@pytest.mark.parametrize("index", range(20))
def test_native_selectors_and_signatures(index):
    module = load("gateway_native_requests")
    selected = challenge(index)
    raw = module.native_request(selected)
    assert module.validate_request(
        raw, selected, received=(time.time_ns(), time.monotonic_ns())
    ) == module.digest(raw)
    assert len(module.canonical({"v": 1, "op": raw.decode(), "seq": index + 1})) <= 1024


@pytest.mark.parametrize(
    "damage",
    [
        "path",
        "method",
        "param",
        "key",
        "signature",
        "nonce",
        "index",
        "stale",
        "clock",
        "canonical",
        "unsigned",
    ],
)
def test_signed_request_refuses_mutation(damage):
    module = load("gateway_native_requests")
    selected = challenge(3)
    raw = module.native_request(selected)
    value = json.loads(raw)
    received = (time.time_ns(), time.monotonic_ns())
    if damage == "path":
        value["request"]["path"] = "/api/v3/order"
    elif damage == "method":
        value["request"]["method"] = "POST"
    elif damage == "param":
        value["request"]["params"]["symbol"] = "BTCUSDT"
    elif damage == "key":
        value["request"]["headers"]["X-MBX-APIKEY"] = "other"
    elif damage == "signature":
        signature = value["request"]["params"]["signature"]
        value["request"]["params"]["signature"] = ("A" if signature[0] != "A" else "B") + signature[
            1:
        ]
    elif damage == "unsigned":
        del value["request"]["params"]["signature"]
    elif damage == "nonce":
        selected["nonce"] = "b" * 32
    elif damage == "index":
        selected["index"] = 6
    elif damage == "stale":
        received = tuple(selected[k] + 5_000_000_001 for k in ("utc_ns", "monotonic_ns"))
    elif damage == "clock":
        received = (selected["utc_ns"] + 100_000_000, selected["monotonic_ns"])
    raw = module.canonical(value) + (b" " if damage == "canonical" else b"")
    with pytest.raises(ValueError):
        module.validate_request(raw, selected, received=received)


def test_native_request_refuses_root(monkeypatch):
    module = load("gateway_native_requests")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_signing_as_root_refused"):
        module.native_request(challenge(3))


@pytest.fixture
def session(tmp_path, channels):
    module = load("gateway_native_requests")
    # Match the production consumer budget; this test replays every prefix before ACK.
    channels[1].connection.settimeout(5)
    tmp_path.chmod(0o700)
    attempt = ledger.AttemptLedger(
        tmp_path,
        binding=SimpleNamespace(verify=lambda: {"binding_sha256": PIN}),
        binding_sha256=PIN,
        profile=ledger.REQUEST_PROFILE,
    )
    errors = []

    def child():
        try:
            for index in range(20):
                selected = json.loads(channels[1].receive(module.JsonToken(), index + 1))
                raw = module.native_request(selected)
                channels[1].send(raw.decode(), index + 1)
                channels[1].receive({"prepared:" + module.digest(raw)}, index + 1)
                channels[1].send("received:" + module.digest(raw), index + 1)
            channels[1].receive({"close"}, 21)
            channels[1].send("closed", 21)
        except BaseException as exc:
            errors.append(exc)
        finally:
            channels[1].close()

    thread = threading.Thread(target=child)
    collector = SimpleNamespace(
        channel=channels[0],
        verify=lambda: None,
        process=SimpleNamespace(wait=lambda timeout: thread.join(timeout)),
        cleanup=channels[0].close,
    )

    def run(callback=None):
        thread.start()
        return module.run_session(collector, attempt, ledger, provenance, on_prepared=callback)

    def review(raw=None, attempts=None):
        raw = (attempt.path / "requests.jsonl").read_bytes() if raw is None else raw
        return module.replay(
            raw,
            expected_sha256=module.digest(raw),
            attempts=attempt.expected if attempts is None else attempts,
            binding_sha256=PIN,
            module=ledger,
        )

    yield SimpleNamespace(run=run, review=review, module=module, ledger=attempt, errors=errors)
    channels[0].close()
    if thread.ident:
        thread.join(6)
        assert not thread.is_alive()
    if not attempt.closed:
        attempt.close()


def test_twenty_requests_persist_before_receipt_and_replay(session):
    def prepared(index):
        report = session.review()
        assert report["prepared_requests"] == index + 1
        assert report["acknowledged_requests"] == index
        assert session.ledger.state.pending == index

    result = session.run(prepared)
    assert result["operations"] == 20 and not session.errors
    report = session.review()
    assert report["status"] == "complete" and report["verified_signatures"] == 9
    assert not report["transport_dispatch_verified"] and not report["network_admitted"]
    assert session.ledger.state.profile == ledger.REQUEST_PROFILE


def test_request_persistence_failure_keeps_pending_no_ack(session, monkeypatch):
    original = session.module.RequestJournal.append

    def fail(self, kind, **fields):
        original(self, kind, **fields)
        if kind == "prepared" and fields["index"] == 9:
            raise OSError("fixture fsync boundary")

    monkeypatch.setattr(session.module.RequestJournal, "append", fail)
    with pytest.raises(OSError):
        session.run()
    result = session.review()
    assert result["prepared_requests"] == 10 and result["acknowledged_requests"] == 9
    assert session.ledger.state.pending == 9 and result["status"] == "incomplete_no_resume"


def rechain(module, rows):
    raw, previous = b"", None
    for index, row in enumerate(rows):
        row.update(seq=index, previous_sha256=previous)
        line = module.canonical(row) + b"\n"
        raw += line
        previous = module.digest(line)
    return raw


@pytest.mark.parametrize(
    "damage",
    [
        "request",
        "signature",
        "prefix",
        "received",
        "ack",
        "missing_ack",
        "extra_challenge",
        "terminal_order",
        "outcome_order",
        "preparation_before_receive",
    ],
)
def test_rehashed_custody_tampering_refused(session, damage):
    session.run()
    raw = (session.ledger.path / "requests.jsonl").read_bytes()
    rows = list(map(json.loads, raw.splitlines()))
    attempts = session.ledger.expected
    if damage == "request":
        rows[10]["request"]["request"]["path"] = "/api/v3/order"
    elif damage == "signature":
        rows[7]["request"]["request"]["params"]["signature"] = "A" * 88
    elif damage == "prefix":
        rows[10]["attempt_prefix_sha256"] = "0" * 64
    elif damage == "received":
        rows[10]["received"][1] -= 6_000_000_000
    elif damage == "preparation_before_receive":
        prepared = next(
            r
            for r in map(json.loads, attempts.splitlines())
            if r["kind"] == "prepared" and r["payload"]["index"] == 3
        )
        rows[10]["received"] = [prepared[k] + 1 for k in ("utc_ns", "monotonic_ns")]
    elif damage == "ack":
        rows[11]["request_sha256"] = "0" * 64
    elif damage == "missing_ack":
        rows.pop()
    elif damage == "extra_challenge":
        rows.append(dict(rows[-3]))
    else:
        source = rows[-2] if damage == "terminal_order" else rows[10]
        target = rows[-1] if damage == "terminal_order" else rows[11]
        # Keep request chain clocks monotone but place acknowledgement after ledger outcome/close.
        original = list(map(json.loads, attempts.splitlines()))
        boundary = next(
            r
            for r in original
            if r["kind"] == ("closed" if damage == "terminal_order" else "outcome")
            and (damage == "terminal_order" or r["payload"]["index"] == 3)
        )
        for k in ("utc_ns", "monotonic_ns"):
            target[k] = boundary[k] + 1
        assert source["kind"] == "prepared"
    with pytest.raises(ValueError):
        session.review(rechain(session.module, rows), attempts)


def test_missing_final_outcome_stays_explicit(session):
    session.run()
    rows = session.ledger.expected.splitlines(keepends=True)
    end = next(
        i
        for i, line in enumerate(rows)
        if json.loads(line)["kind"] == "outcome" and json.loads(line)["payload"]["index"] == 19
    )
    result = session.review(attempts=b"".join(rows[:end]))
    assert result["acknowledged_requests"] == 20 and result["request_outcomes_recorded"] == 19
    assert result["status"] == "incomplete_no_resume"


@pytest.mark.parametrize("value", [[], None, {"request": []}, {"request": {"params": None}}])
def test_untrusted_request_shape_rejected(value):
    module = load("gateway_native_requests")
    selected = challenge(3)
    with pytest.raises(ValueError):
        module.validate_request(
            module.canonical(value), selected, received=(time.time_ns(), time.monotonic_ns())
        )


@pytest.mark.parametrize("damage", ["order", "weight", "unknown_charge"])
def test_fixed_budget_cannot_be_relaxed(session, monkeypatch, damage):
    if damage == "order":
        monkeypatch.setattr(ledger, "IPC_STEPS", tuple(reversed(ledger.IPC_STEPS)))
    else:
        operations = {k: dict(v) for k, v in ledger.JOINT_OPERATIONS.items()}
        operations["account_read" if damage == "weight" else "market_connect"][
            "documented_weight"
        ] = 0
        monkeypatch.setattr(ledger, "JOINT_OPERATIONS", operations)
    with pytest.raises(ValueError, match="native_request_fixed_budget"):
        session.module.validate_budget(ledger, session.ledger)

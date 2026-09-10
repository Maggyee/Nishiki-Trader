from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal as D

import pytest

from apps.strategies_nautilus.portfolio_adapter_checkpoint import (
    NUMERIC_MODE,
    checkpoint_bytes,
    reconcile_adapter_checkpoint,
    write_new_checkpoint,
)
from apps.strategies_nautilus.portfolio_recovery import (
    RecoveryError,
    reconstruct_native,
    verify_checkpoint,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, UserStreamJournal
from apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance import (
    ANCHOR,
    BINDING,
    fixture_checkpoint,
    fixture_collected,
    run_acceptance,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


@pytest.fixture
def case(tmp_path):
    loop = asyncio.new_event_loop()
    raw = fixture_checkpoint(loop)
    original = tmp_path / "original.json"
    write_new_checkpoint(original, raw)
    now = BASE_NS + 8 * SECOND
    stream = UserStreamJournal(tmp_path / "stream.jsonl", BINDING, clock_ns=lambda: now)
    stream.subscribed(7, BINDING)
    collected = fixture_collected(stream, now)
    yield raw, collected, stream, loop, original
    stream.close()
    loop.close()


def recover(case, **updates):
    raw, collected, stream, loop, _ = case
    fields = dict(
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        anchor=ANCHOR,
        collected=collected,
        stream=stream,
        now_ns=BASE_NS + 8 * SECOND,
        loop=loop,
    )
    fields.update(updates)
    return reconcile_adapter_checkpoint(raw, **fields)


def change_response(collected, field, mutation):
    response = getattr(collected.evidence, field)
    body = json.loads(response.body)
    mutation(body)
    return replace(
        collected,
        evidence=replace(collected.evidence, **{field: replace(response, body=json.dumps(body))}),
    )


def test_native_checkpoint_reconciliation_preserves_state_and_original_bytes(case):
    raw, _, _, _, path = case
    before = verify_checkpoint(raw)
    result = recover(case)
    after = verify_checkpoint(result.checkpoint)
    assert before["state"] == after["state"]
    assert before["sha256"] == after["sha256"]
    assert path.read_bytes() == raw
    assert after["native"]["ts_ns"] == BASE_NS + 8 * SECOND
    assert result.checks_passed and result.risk_latched
    assert not result.runtime_ready and not result.real_account_verified
    assert result.downtime_risk_review_required
    assert len(result.account_evidence_sha256) == 4
    assert result.stream_fence == case[1].stream_fence
    assert result.wire_sha256 == case[1].wire_sha256
    assert result.input_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.output_sha256 == hashlib.sha256(result.checkpoint).hexdigest()


@pytest.mark.parametrize(
    "field,mutation",
    [
        ("account", lambda b: b["balances"][1].update(free="333.41")),
        ("account", lambda b: b["balances"][1].update(free="333.3", locked="0.1")),
        ("account", lambda b: b["balances"][0].update(free="0.00166351")),
        ("account", lambda b: b.update(uid=456)),
        ("orders", lambda b: b.pop()),
        ("orders", lambda b: b[0].update(clientOrderId="unknown")),
        ("trades", lambda b: b.pop()),
        ("trades", lambda b: b.append(b[0])),
        ("trades", lambda b: b[0].update(commission="0.00000049")),
        ("trades", lambda b: b[-1].update(commissionAsset="BNB")),
        ("open_orders", lambda b: b.append({"clientOrderId": "unrelated"})),
    ],
)
def test_conflicting_exchange_observations_do_not_produce_recovery(case, field, mutation):
    raw, collected, _, _, path = case
    with pytest.raises(ValueError):
        recover(case, collected=change_response(collected, field, mutation))
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "failure",
    ["digest", "anchor", "stale", "coverage", "no_fence", "new_epoch", "disconnected", "time"],
)
def test_recovery_requires_selected_checkpoint_and_fresh_source_fence(case, failure):
    _, collected, stream, _, _ = case
    updates = {}
    if failure == "digest":
        updates["expected_sha256"] = "0" * 64
    elif failure == "anchor":
        updates["anchor"] = replace(ANCHOR, quote=D("501"))
    elif failure == "stale":
        updates["now_ns"] = BASE_NS + 100 * SECOND
    elif failure == "coverage":
        updates["collected"] = replace(
            collected, evidence=replace(collected.evidence, end_ns=BASE_NS + SECOND)
        )
    elif failure == "no_fence":
        updates["collected"] = replace(collected, stream_fence=None)
    elif failure == "new_epoch":
        stream.subscribed(7, BINDING)
    elif failure == "disconnected":
        stream.disconnect()
    else:
        updates["now_ns"] = BASE_NS + SECOND
    with pytest.raises(ValueError):
        recover(case, **updates)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda w: w["native"].update(venue_id_mode="native_uuid"),
        lambda w: w["native"].update(nautilus_version="wrong"),
        lambda w: w["native"].update(ts_ns=BASE_NS),
        lambda w: w["state"].update(halt_reason="unresolved incident"),
        lambda w: w["state"].update(risk_latched="false"),
        lambda w: w["state"]["orders"].update(unknown={}),
        lambda w: w["state"]["orders"]["adapter-v18"].update(position_id="another-sleeve"),
    ],
)
def test_rehashed_incompatible_checkpoint_is_still_rejected(case, mutation):
    raw, *rest = case
    wrapped = verify_checkpoint(raw)
    mutation(wrapped)
    changed = checkpoint_bytes(wrapped["state"], wrapped["native"])
    with pytest.raises(ValueError):
        recover((changed, *rest))


def test_numeric_snapshot_cannot_enter_default_simulation_reconstruction(case):
    with pytest.raises(RecoveryError, match="version mismatch"):
        reconstruct_native(verify_checkpoint(case[0])["native"])


def test_stream_change_during_native_reconciliation_discards_result(case, monkeypatch):
    import apps.strategies_nautilus.portfolio_adapter_checkpoint as module

    original = module.reconcile_binance_reports

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        case[2].disconnect()

    monkeypatch.setattr(module, "reconcile_binance_reports", interrupt)
    with pytest.raises(StreamError):
        recover(case)
    assert case[4].read_bytes() == case[0]


def test_new_checkpoint_publication_never_overwrites_original(case, tmp_path):
    result = recover(case)
    with pytest.raises(FileExistsError):
        write_new_checkpoint(case[4], result.checkpoint)
    output = tmp_path / "reconciled.json"
    write_new_checkpoint(output, result.checkpoint)
    assert output.read_bytes() == result.checkpoint
    assert output.stat().st_mode & 0o777 == 0o600
    assert case[4].read_bytes() == case[0]
    assert verify_checkpoint(output.read_bytes())["native"]["venue_id_mode"] == NUMERIC_MODE


def test_failed_file_fsync_does_not_publish_a_partial_checkpoint(case, tmp_path, monkeypatch):
    import apps.strategies_nautilus.portfolio_adapter_checkpoint as module

    result = recover(case)
    output = tmp_path / "reconciled.json"
    monkeypatch.setattr(module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        write_new_checkpoint(output, result.checkpoint)
    assert not output.exists()
    assert case[4].read_bytes() == case[0]


def test_three_process_crash_reconcile_and_idempotent_replay(tmp_path):
    report = run_acceptance(tmp_path)
    assert report["distinct_processes"] and report["producer_exit_code"] == 23
    assert report["original_preserved"] and report["strategy_state_preserved"]
    assert report["replay_idempotent"] and report["risk_latched"]
    assert D(report["total_usdt"]) == D("333.4")
    assert D(report["total_btc"]) == D("0.00166350")
    assert report["orders"] == {"adapter-v16": "FILLED", "adapter-v18": "CANCELED"}
    assert not report["runtime_ready"] and report["downtime_risk_review_required"]

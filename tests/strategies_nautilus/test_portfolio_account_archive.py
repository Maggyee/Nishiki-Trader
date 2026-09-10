from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from nautilus_trader.common.component import TestClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.ops.portfolio_account_archive_check import main
from apps.strategies_nautilus.portfolio_account_archive import (
    AccountArchiveError,
    replay_account_collection,
)
from apps.strategies_nautilus.portfolio_account_collector import (
    BinanceAccountReadOnlyHttpClient,
    BinanceReadOnlyAccountCollector,
)
from apps.strategies_nautilus.portfolio_stream import UserStreamJournal, canonical
from apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance import (
    ANCHOR,
    BINDING,
    fixture_collected,
)
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


def capture(path, mutate=None, crash_after=None):
    now = BASE_NS + 8 * SECOND
    clock = TestClock()
    clock.set_time(now)
    client = BinanceAccountReadOnlyHttpClient(
        clock, "fixture-key", "fixture-secret", BINDING.endpoint
    )
    journal = UserStreamJournal(path, BINDING, clock_ns=clock.timestamp_ns)
    journal.subscribed(7, BINDING)
    evidence = fixture_collected(SimpleNamespace(fence=lambda: None), now).evidence
    bodies = {
        "/sapi/v1/account/apiRestrictions": json.dumps(
            {
                "enableReading": True,
                "enableSpotAndMarginTrading": False,
            }
        ),
        "/api/v3/account": evidence.account.body,
        "/api/v3/openOrders": evidence.open_orders.body,
        "/api/v3/allOrders": evidence.orders.body,
        "/api/v3/myTrades": evidence.trades.body,
    }
    calls = []

    async def wire(method, path, *, payload, **kwargs):
        assert method == HttpMethod.GET
        unsigned = {k: v for k, v in payload.items() if k != "signature"}
        assert hmac.compare_digest(
            payload["signature"],
            hmac.new(
                b"fixture-secret",
                urlencode(unsigned).encode(),
                hashlib.sha256,
            ).hexdigest(),
        )
        calls.append(path)
        if crash_after == len(calls):
            os._exit(23)
        raw = bodies[path].encode()
        return mutate(path, raw, journal, len(calls)) if mutate else raw

    client.send_request = wire
    try:
        result = asyncio.run(
            BinanceReadOnlyAccountCollector(
                client,
                clock_ns=clock.timestamp_ns,
                stream=journal,
            ).collect(ANCHOR)
        )
        if crash_after == 0:
            print(result.collection_id, flush=True)
            os._exit(23)
        return result
    finally:
        journal.close()


def replay(raw, collection_id, **kwargs):
    return asyncio.run(
        replay_account_collection(
            raw,
            collection_id=collection_id,
            source=kwargs.get("source", BINDING),
            anchor=kwargs.get("anchor", ANCHOR),
            expected_sha256=kwargs.get("expected_sha256", hashlib.sha256(raw).hexdigest()),
        )
    )


def rechain(rows):
    previous = "0" * 64
    raw = b""
    for i, row in enumerate(rows):
        row.pop("sha256", None)
        row.update(seq=i, previous=previous)
        previous = hashlib.sha256(canonical(row)).hexdigest()
        raw += canonical({**row, "sha256": previous}) + b"\n"
    return raw


@pytest.fixture
def saved(tmp_path):
    path = tmp_path / "private.jsonl"
    collected = capture(path)
    return path, collected, path.read_bytes()


def test_native_signed_receipts_replay_exact_evidence_without_fence(saved):
    path, original, raw = saved
    result = replay(raw, original.collection_id)
    assert result.collected.evidence == original.evidence
    assert result.collected.wire_sha256 == original.wire_sha256
    assert result.collected.stream_fence is None
    assert result.collected.collection_id is None
    assert not result.collected.atomic_revision_verified
    assert result.summary()["response_count"] == 7
    assert not any(
        result.summary()[key]
        for key in (
            "runtime_ready",
            "real_account_verified",
            "atomic_revision_verified",
            "downtime_history_complete",
        )
    )
    assert path.read_bytes() == raw
    assert path.stat().st_mode & 0o777 == 0o600
    for secret in (
        b"fixture-key",
        b"fixture-secret",
        b"signature",
        b"apiKey",
        b"timestamp",
        b"recvWindow",
    ):
        assert secret not in raw


@pytest.mark.parametrize("crash_after", [0, 4])
def test_abrupt_process_exit_preserves_complete_or_incomplete_receipts(tmp_path, crash_after):
    path = tmp_path / "crashed.jsonl"
    script = (
        "import runpy, sys\nfrom pathlib import Path\n"
        "module = runpy.run_path(sys.argv[1])\n"
        "module['capture'](Path(sys.argv[2]), crash_after=int(sys.argv[3]))\n"
    )
    worker = subprocess.run(
        [sys.executable, "-c", script, __file__, str(path), str(crash_after)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert worker.returncode == 23, worker.stderr
    raw = path.read_bytes()
    collection_id = next(
        row["collection_id"]
        for row in map(json.loads, raw.splitlines())
        if row["kind"] == "rest_started"
    )
    if crash_after == 0:
        assert replay(raw, collection_id).summary()["response_count"] == 7
    else:
        with pytest.raises(AccountArchiveError):
            replay(raw, collection_id)
    restarted = UserStreamJournal(path, BINDING, clock_ns=lambda: BASE_NS + 9 * SECOND)
    try:
        assert not restarted.connected
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "change", ["body", "tail", "whole_record", "source", "baseline", "selection"]
)
def test_selected_hash_and_independent_source_reject_changes(saved, change):
    _, original, raw = saved
    expected = hashlib.sha256(raw).hexdigest()
    kwargs = {"expected_sha256": expected}
    if change == "body":
        raw = raw.replace(b"333.40000000", b"334.40000000")
    elif change == "tail":
        raw = raw[:-1]
    elif change == "whole_record":
        raw = b"\n".join(raw.splitlines()[:-1]) + b"\n"
    elif change == "source":
        kwargs["source"] = replace(BINDING, key_sha256="a" * 64)
    elif change == "baseline":
        kwargs["anchor"] = replace(ANCHOR, quote=ANCHOR.quote + 1)
    else:
        original = replace(original, collection_id="unselected")
    with pytest.raises(AccountArchiveError):
        replay(raw, original.collection_id, **kwargs)


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "cursor",
        "path",
        "time",
        "uid",
        "permission",
        "drift",
        "missing",
        "extra",
        "interrupted",
        "duplicate_complete",
        "unsealed",
        "completion_hash",
    ],
)
def test_rehashed_archive_still_requires_valid_collection_semantics(saved, change):
    _, original, raw = saved
    rows = list(map(json.loads, raw.splitlines()))
    responses = [row for row in rows if row["kind"] == "rest_response"]
    first, last = responses[0], responses[-1]
    if change == "hash":
        last["raw"] += " "
    elif change == "cursor":
        responses[3]["params"]["startTime"] = "0"
    elif change == "path":
        first["path"] = "/api/v3/order"
    elif change == "time":
        last["response_ns"] -= SECOND
    elif change in {"uid", "drift", "permission"}:
        row = first if change == "permission" else last
        body = json.loads(row["raw"])
        body[{"uid": "uid", "drift": "canTrade", "permission": "enableReading"}[change]] = False
        row["raw"] = json.dumps(body)
        row["response_sha256"] = hashlib.sha256(row["raw"].encode()).hexdigest()
    elif change == "missing":
        rows.remove(responses[3])
    elif change == "extra":
        rows.insert(-1, dict(last))
    elif change == "interrupted":
        rows.insert(-1, {**last, "kind": "event"})
    elif change == "duplicate_complete":
        rows.append(dict(rows[-1]))
    elif change == "unsealed":
        rows.pop()
    else:
        rows[-1]["response_sha256"][0][1] = "0" * 64
    with pytest.raises(AccountArchiveError):
        replay(rechain(rows), original.collection_id)


@pytest.mark.parametrize("failure", ["json", "disconnect", "disk"])
def test_failed_collection_never_seals_an_archive(tmp_path, monkeypatch, failure):
    path = tmp_path / "failed.jsonl"

    def mutate(endpoint, raw, journal, count):
        if count == 4:
            if failure == "json":
                return b"invalid-private-json"
            if failure == "disconnect":
                journal.disconnect()
            else:
                monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
        return raw

    with pytest.raises(ValueError):
        capture(path, mutate)
    raw = path.read_bytes()
    rows = list(map(json.loads, raw.splitlines()))
    assert not any(row["kind"] == "rest_collection" for row in rows)
    if failure == "json":
        assert b"invalid-private-json" in raw  # saved before parsing
    with pytest.raises(AccountArchiveError):
        replay(raw, next(row["collection_id"] for row in rows if row["kind"] == "rest_started"))


def test_cli_replays_private_files_without_exposing_bodies(saved, tmp_path, capsys):
    path, original, raw = saved
    source_path, anchor_path = tmp_path / "source.json", tmp_path / "anchor.json"
    source_path.write_text(json.dumps(asdict(BINDING)))
    anchor_path.write_text(
        json.dumps({**asdict(ANCHOR), "quote": str(ANCHOR.quote), "base": str(ANCHOR.base)})
    )
    args = [
        str(path),
        "--sha256",
        hashlib.sha256(raw).hexdigest(),
        "--collection-id",
        original.collection_id,
        "--source-binding",
        str(source_path),
        "--anchor",
        str(anchor_path),
    ]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["runtime_ready"] is False
    assert "333.4" not in output
    assert path.read_bytes() == raw
    args[2] = "0" * 64
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


@pytest.mark.parametrize(
    "path,id_key", [("/api/v3/allOrders", "orderId"), ("/api/v3/myTrades", "id")]
)
def test_pagination_replays_all_wire_pages_and_cursor(tmp_path, path, id_key):
    archive = tmp_path / "pages.jsonl"
    page = 0

    def paginate(endpoint, raw, journal, count):
        nonlocal page
        if endpoint == path:
            start = page * 1000
            page += 1
            return json.dumps(
                [{id_key: n} for n in range(start, start + (1000 if page == 1 else 1))]
            ).encode()
        return raw

    collected = capture(archive, paginate)
    result = replay(archive.read_bytes(), collected.collection_id)
    assert result.collected.evidence == collected.evidence
    assert result.summary()["response_count"] == 8
    response = (
        result.collected.evidence.orders
        if id_key == "orderId"
        else result.collected.evidence.trades
    )
    assert len(json.loads(response.body)) == 1001


def test_legacy_hash_only_collection_cannot_be_replayed(saved):
    _, original, raw = saved
    rows = [
        row
        for row in map(json.loads, raw.splitlines())
        if row["kind"] not in {"rest_started", "rest_response"}
    ]
    rows[-1].pop("collection_id")
    with pytest.raises(AccountArchiveError):
        replay(rechain(rows), original.collection_id)


def test_separate_collections_select_exact_receipts(saved):
    path, first, _ = saved
    second = capture(path)
    raw = path.read_bytes()
    assert first.collection_id != second.collection_id
    assert replay(raw, first.collection_id).collected.evidence == first.evidence
    assert replay(raw, second.collection_id).collected.evidence == second.evidence


def test_replayed_evidence_reconciles_native_state_but_cannot_reuse_a_live_fence(saved, tmp_path):
    from apps.strategies_nautilus.portfolio_account import reconcile_account
    from apps.strategies_nautilus.portfolio_adapter_checkpoint import (
        NUMERIC_MODE,
        reconcile_adapter_checkpoint,
    )
    from apps.strategies_nautilus.portfolio_recovery import (
        RecoveryError,
        reconstruct_native,
        verify_checkpoint,
    )
    from apps.strategies_nautilus.runners.portfolio_adapter_checkpoint_acceptance import (
        fixture_checkpoint,
        resume,
    )

    _, collected, archive = saved
    archived = replay(archive, collected.collection_id).collected
    loop = asyncio.new_event_loop()
    journal = UserStreamJournal(
        tmp_path / "fresh.jsonl", BINDING, clock_ns=lambda: BASE_NS + 8 * SECOND
    )
    try:
        raw = fixture_checkpoint(loop)
        digest = hashlib.sha256(raw).hexdigest()
        result = resume(raw, digest, tmp_path / "native.jsonl", BASE_NS + 8 * SECOND)
        restored = verify_checkpoint(result.checkpoint)
        _, account, orders, positions = reconstruct_native(
            restored["native"], venue_id_mode=NUMERIC_MODE
        )
        assert reconcile_account(
            archived.evidence,
            anchor=ANCHOR,
            native=(account, orders, positions),
            intents=restored["state"]["orders"],
            now_ns=BASE_NS + 8 * SECOND,
            max_age_ns=60 * SECOND,
        ).checks_passed
        journal.subscribed(7, BINDING)
        with pytest.raises(RecoveryError, match="source-bound"):
            reconcile_adapter_checkpoint(
                raw,
                expected_sha256=digest,
                anchor=ANCHOR,
                collected=archived,
                stream=journal,
                now_ns=BASE_NS + 8 * SECOND,
                loop=loop,
            )
    finally:
        journal.close()
        loop.close()

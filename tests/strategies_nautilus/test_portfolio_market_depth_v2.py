"""Prospective successor-ID linkage without reinterpreting the v1 evidence."""

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from apps.strategies_nautilus import portfolio_market_depth as core
from apps.strategies_nautilus import portfolio_market_depth_archive as archive
from tests.strategies_nautilus.test_portfolio_market_depth import (
    BASE,
    ReceiptClock,
    body_fields,
    complete_archive,
    delta,
    event,
    metadata,
    rechain,
    response,
    snapshot,
)


@pytest.mark.parametrize("last_id", range(1, 16))
def test_snapshot_alignment_matches_unbatched_reference_book(last_id):
    # Build an authoritative book one update at a time, independently of the
    # collector's batched range/linkage logic. Batch payloads contain final sizes.
    bids = {Decimal("98"): Decimal("2"), Decimal("99"): Decimal("1")}
    asks = {Decimal("101"): Decimal("4"), Decimal("102"): Decimal("5")}
    states, batches, pending = {}, [], {"b": {}, "a": {}}
    for update in range(1, 17):
        side = "b" if update % 2 else "a"
        price = Decimal("99" if side == "b" else "101")
        size = Decimal(update + 1)
        (bids if side == "b" else asks)[price] = size
        pending[side][str(price)] = str(size)
        states[update] = (dict(bids), dict(asks))
        if update % 4 == 0:
            batches.append(
                delta(
                    update - 3,
                    update,
                    E=BASE // 1_000_000 + update,
                    b=[[p, q] for p, q in pending["b"].items()],
                    a=[[p, q] for p, q in pending["a"].items()],
                )
            )
            pending = {"b": {}, "a": {}}
    book = core.DepthBook(metadata(), revision=2)
    for batch in batches:
        event(book, batch, now=BASE + batch["u"] * 1_000_000)
    snap_bids, snap_asks = states[last_id]
    book.snapshot(
        snapshot(
            lastUpdateId=last_id,
            bids=[[str(p), str(q)] for p, q in sorted(snap_bids.items(), reverse=True)],
            asks=[[str(p), str(q)] for p, q in sorted(snap_asks.items())],
        ),
        now_ns=BASE + 20_000_000,
    )
    expected = []
    for end in (4, 8, 12, 16):
        if end <= last_id:
            continue
        b, a = states[end]
        expected.append(
            (
                f"{max(b):.2f}",
                f"{b[max(b)]:.8f}",
                f"{min(a):.2f}",
                f"{a[min(a)]:.8f}",
                BASE + end * 1_000_000,
            )
        )
    actual = [
        (q["bid_price"], q["bid_size"], q["ask_price"], q["ask_size"], q["ts_event"])
        for q in book.quotes
    ]
    assert actual == expected
    assert book.bids == states[16][0] and book.asks == states[16][1]
    assert book.summary()["locally_linked"]


@pytest.mark.parametrize(
    "first,last,code",
    [
        (101, 103, None),
        (100, 103, None),
        (102, 103, "depth_sequence_gap"),
        (104, 104, "depth_sequence_gap"),
    ],
)
def test_first_remaining_next_id_and_gap(first, last, code):
    book = core.DepthBook(metadata(), revision=2)
    event(book, delta(99, 100))
    book.snapshot(snapshot(), now_ns=BASE)
    if code:
        with pytest.raises(core.DepthError, match=code):
            event(book, delta(first, last))
        assert not book.quotes and not book.summary()["locally_linked"]
    else:
        event(book, delta(first, last))
        assert len(book.quotes) == 1
        # Duplicates never produce another quote or refresh E.
        event(book, delta(first, last), now=BASE + core.SECOND)
        assert len(book.quotes) == 1 and book.obsolete == 2
        with pytest.raises(core.DepthError, match="depth_sequence_gap"):
            event(book, delta(last + 2, last + 3))
        assert len(book.quotes) == 1


def test_v2_retains_first_buffer_snapshot_guard():
    book = core.DepthBook(metadata(), revision=2)
    event(book, delta(101, 103))
    with pytest.raises(core.DepthError, match="snapshot_behind_first_buffered_event"):
        book.snapshot(snapshot(), now_ns=BASE)
    assert not book.quotes


@pytest.mark.parametrize("revision", [0, 3, True, False, 1.0, "2", None])
def test_unsupported_revision_cannot_create_archive(tmp_path, revision):
    with pytest.raises(core.DepthError):
        archive.DepthJournal(
            tmp_path / "invalid.jsonl", epoch="fixture", clock=ReceiptClock(), revision=revision
        )
    assert not (tmp_path / "invalid.jsonl").exists()
    with pytest.raises(core.DepthError):
        core.DepthBook(metadata(), revision=revision)


def v2_archive(tmp_path):
    path = tmp_path / "v2.jsonl"
    journal = archive.DepthJournal(path, epoch="new-v2-fixture", clock=ReceiptClock(), revision=2)
    response(journal, None)
    response(journal, metadata())
    journal.append("connected")
    journal.append("depth_frame", **body_fields(delta(99, 100)))
    response(journal, snapshot())
    journal.append("depth_frame", **body_fields(delta(101, 103)))
    response(journal, None)
    journal.append("depth_frame", **body_fields(delta(104, 105)))
    response(journal, None)
    journal.append("transport_closed")
    journal.append("completed", result=journal.state.summary())
    journal.close()
    return path.read_bytes()


def test_explicit_v2_two_fresh_process_replays(tmp_path):
    raw = v2_archive(tmp_path)
    digest = hashlib.sha256(raw).hexdigest()
    expected = archive.replay_depth(raw, expected_sha256=digest, revision=2)
    assert expected["summary"]["profile"] == "testnet_public_depth_evidence_v2"
    assert expected["summary"]["contract_sha256"] == archive.CONTRACT_SHA256_V2
    assert expected["summary"]["native_quote_count"] == 2
    assert all(expected[k] is False for k in archive.flags())
    outputs = []
    for n in range(2):
        report = tmp_path / f"replay{n}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_market_depth",
                "--replay",
                "--revision",
                "2",
                "--archive",
                str(tmp_path / "v2.jsonl"),
                "--archive-sha256",
                digest,
                "--report",
                str(report),
            ],
            capture_output=True,
            timeout=20,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        outputs.append(report.read_bytes())
    assert outputs[0] == outputs[1] and json.loads(outputs[0]) == expected
    assert (tmp_path / "v2.jsonl").read_bytes() == raw
    with pytest.raises(core.DepthError):
        archive.replay_depth(raw, expected_sha256=digest)  # Default remains v1.


@pytest.mark.parametrize(
    "damage",
    ["row_profile", "header_contract", "seal_contract", "extra_connection", "unsealed", "abort"],
)
def test_cross_revision_and_incomplete_v2_refused(tmp_path, damage):
    rows = [json.loads(line) for line in v2_archive(tmp_path).splitlines()]
    if damage == "row_profile":
        rows[4]["profile"] = core.PROFILE
    elif damage == "header_contract":
        rows[0]["contract_sha256"] = archive.CONTRACT_SHA256
    elif damage == "seal_contract":
        rows[-1]["result"]["contract_sha256"] = archive.CONTRACT_SHA256
    elif damage == "extra_connection":
        rows[-2]["kind"] = "connected"
    elif damage == "unsealed":
        rows.pop()
    elif damage == "abort":
        rows[-1]["kind"] = "aborted"
    raw = rechain(rows)
    with pytest.raises(core.DepthError):
        archive.replay_depth(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), revision=2)


def test_v1_default_quote_and_seal_still_replay_without_migration(tmp_path):
    raw = complete_archive(tmp_path)
    digest = hashlib.sha256(raw).hexdigest()
    # Produced independently with the original implementation at 16b1af6.
    assert digest == "23f6baa0ca2af45e152a2cba5a6899a500b13cbb3c4543b211d31c2341c0a009"
    before = archive.replay_depth(raw, expected_sha256=digest)
    assert before["summary"]["profile"] == core.PROFILE
    assert before["summary"]["contract_sha256"] == archive.CONTRACT_SHA256
    with pytest.raises(core.DepthError):
        archive.replay_depth(raw, expected_sha256=digest, revision=2)
    assert (tmp_path / "depth.jsonl").read_bytes() == raw
    book = core.DepthBook(metadata())
    event(book, delta(99, 100))
    book.snapshot(snapshot(), now_ns=BASE)
    with pytest.raises(core.DepthError, match="bootstrap_boundary_unqualified"):
        event(book, delta(101, 103))


def test_frozen_v2_changes_only_profile_and_bootstrap_semantics():
    root = Path("docs/progress")
    base_raw = (root / "portfolio-testnet-provider-coverage-2026-09-13.json").read_bytes()
    raw = (root / "portfolio-testnet-public-depth-v2-contract-2026-09-13.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == archive.CONTRACT_SHA256_V2
    contract = json.loads(raw)
    assert (
        contract["base_contract_sha256"]
        == hashlib.sha256(base_raw).hexdigest()
        == archive.CONTRACT_SHA256
    )
    old = json.loads(base_raw)["first_diagnostic"]
    old.pop("implemented")
    new = contract["diagnostic"]
    assert old.keys() == new.keys()
    differences = {key for key in old if old[key] != new[key]}
    assert differences == {"profile", "bootstrap_overlap", "bootstrap_boundary_U_eq_L_plus_1"}
    assert contract["prospective_attempt"]["max_attempts"] == 1
    assert contract["decision_basis"]["historical_trigger_remains_failed"]

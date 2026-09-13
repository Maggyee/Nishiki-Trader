"""Historical archives cannot become current transport receipts or trading permission."""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from decimal import Decimal

import pytest

from apps.ops.portfolio_session_archive import review_archive
from apps.strategies_nautilus.portfolio_session_archive import replay_session_collection
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_transport import HISTORY_NS, collect_session
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from tests.strategies_nautilus import test_portfolio_session_transport as transport_tests

case = transport_tests.case
collect = transport_tests.collect


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replay(case, raw=None, **overrides):
    raw = case.archive.read_bytes() if raw is None else raw
    return replay_session_collection(raw, case.ledger.path.read_bytes(), **({
        "archive_sha256": sha(raw), "checkpoint_sha256": case.ledger.sha256,
        "collection_id": case.receipt.collection_id,
    } | overrides))


def rechain(rows):
    previous, output = "0" * 64, []
    for seq, row in enumerate(rows):
        row.pop("sha256", None)
        row.update(seq=seq, previous=previous)
        previous = sha(canonical(row))
        output.append(canonical(row | {"sha256": previous}) + b"\n")
    return b"".join(output)


def sealed(case):
    case.receipt = collect(case)
    return [json.loads(line) for line in case.archive.read_bytes().splitlines()]


def body(row, value):
    row["raw"] = canonical(value).decode()
    row["response_sha256"] = sha(row["raw"].encode())


def test_reproduces_exact_original_evidence_without_live_fence_after_expiry(case):
    sealed(case)
    original = case.ledger.path.read_bytes()
    calls = list(case.calls)
    archived = replay(case)
    assert archived.evidence_raw == canonical(case.receipt.evidence)
    assert archived.summary()["evidence_sha256"] == case.receipt.evidence_sha256
    assert not hasattr(archived, "fence") and not hasattr(archived, "assert_current")
    case.owner.clock.set_time(case.owner.clock.timestamp_ns() + 2 * HISTORY_NS)
    with pytest.raises(StreamError):
        case.receipt.assert_current(case.journal, case.ledger.sha256)
    with pytest.raises(StreamError):
        collect(case)
    result = review_archive(case.archive.read_bytes(), original,
        archive_sha256=sha(case.archive.read_bytes()), checkpoint_sha256=sha(original),
        collection_id=case.receipt.collection_id, reviewed_ns=case.owner.clock.timestamp_ns(), loop=case.loop)
    assert result["collector_history_window_expired"]
    assert result["full_account_reconciled"] and result["native_reports_reconciled"]
    assert len(result["historical_view"]["fills"]) == 1
    for flag in ("current_venue_state_verified", "source_authenticated", "global_continuity_verified",
                 "new_orders_authorized", "cancel_retry_allowed", "runtime_ready", "fixed_checkpoint_written"):
        assert result[flag] is False
    assert case.calls == calls and case.ledger.path.read_bytes() == original


@pytest.mark.parametrize("change", ["truncated", "missing_seal", "hash_only", "missing_receipt",
    "changed_bytes", "wrong_hash", "checkpoint_hash", "wrong_collection", "duplicate_key",
    "bad_chain", "boolean_sequence", "source", "epoch", "duplicate_epoch", "orphan",
    "restart", "disconnect", "business_event", "abort", "other_collection", "reused_identity",
    "clock", "response_clock", "response_hash", "deadline", "old_history", "anchor",
    "seal", "extra_response", "bad_tail"])
def test_archive_structure_and_historical_binding_fail_closed(case, change):
    rows = sealed(case)
    start = next(i for i, r in enumerate(rows) if r["kind"] == "rest_started")
    first = start + 1
    options = {}
    if change == "truncated":
        raw = case.archive.read_bytes()[:-1]
    elif change == "changed_bytes":
        raw = case.archive.read_bytes().replace(b'"seq":0', b'"seq":9', 1)
    elif change == "duplicate_key":
        raw = case.archive.read_bytes().replace(b'"seq":0', b'"seq":0,"seq":0', 1)
    elif change in {"wrong_hash", "checkpoint_hash", "wrong_collection"}:
        key = {"wrong_hash": "archive_sha256", "checkpoint_hash": "checkpoint_sha256",
               "wrong_collection": "collection_id"}[change]
        options[key] = "f" * 64
        raw = case.archive.read_bytes()
    else:
        if change == "missing_seal":
            rows.pop()
        elif change == "missing_receipt":
            rows.pop(first)
        elif change == "hash_only":
            rows[first].pop("raw")
        elif change == "source":
            for r in rows:
                r["binding"]["account_uid"] = "999"
        elif change == "epoch":
            rows[first]["epoch"] = "foreign"
        elif change == "duplicate_epoch":
            rows.insert(start, dict(rows[1]))
        elif change == "orphan":
            rows.insert(start, dict(rows[first]))
        elif change in {"restart", "disconnect", "business_event", "abort", "other_collection"}:
            r = dict(rows[first])
            r["kind"] = {"restart": "process_started", "disconnect": "disconnected",
                "business_event": "testnet_event", "abort": "rest_aborted",
                "other_collection": "rest_response"}[change]
            if change == "other_collection":
                r["collection_id"] = "foreign"
            rows.insert(first, r)
        elif change == "reused_identity":
            rows.append(dict(rows[-1]))
        elif change == "clock":
            rows[first]["received_ns"] -= 1
        elif change == "response_clock":
            rows[first]["response_ns"] += 1
        elif change == "response_hash":
            rows[first]["response_sha256"] = "0" * 64
        elif change == "deadline":
            rows[-1]["received_ns"] += 60_000_000_001
        elif change == "old_history":
            for r in rows:
                for k in ("received_ns", "response_ns", "started_ns"):
                    if k in r:
                        r[k] += 2 * HISTORY_NS
        elif change == "anchor":
            rows[start]["anchor"]["checkpoint_sha256"] = "f" * 64
        elif change == "seal":
            rows[-1]["evidence_sha256"] = "0" * 64
        elif change == "extra_response":
            rows.insert(-1, dict(rows[-2]))
        elif change == "bad_tail":
            rows.append({**rows[-1], "kind": "disconnected", "collection_id": None})
        raw = rechain(rows)
        if change == "bad_chain":
            raw = raw.replace(b'"previous":"' + b'0' * 64, b'"previous":"' + b'1' * 64, 1)
        elif change == "boolean_sequence":
            raw = raw.replace(b'"seq":0', b'"seq":false', 1)
        elif change == "bad_tail":
            raw = raw[:-2] + b"x\n"
    with pytest.raises(StreamError, match="failed validation"):
        replay(case, raw, **options)


@pytest.mark.parametrize("change", ["account_selector", "signed_selector", "order_selector",
    "trade_selector", "wrong_order", "wrong_trade", "full_page", "bracket_account",
    "bracket_open", "foreign_open", "response_sequence", "production_path"])
def test_rechained_response_semantics_fail_closed(case, change):
    rows = sealed(case)
    receipts = [r for r in rows if r["kind"] == "rest_response"]
    if change == "account_selector":
        receipts[0]["params"]["omitZeroBalances"] = "true"
    elif change == "signed_selector":
        receipts[0]["params"]["signature"] = "do-not-expose"
    elif change == "order_selector":
        receipts[2]["params"]["origClientOrderId"] = "foreign"
    elif change == "trade_selector":
        receipts[3]["params"]["orderId"] = "999"
    elif change == "wrong_order":
        body(receipts[2], json.loads(receipts[2]["raw"]) | {"clientOrderId": "foreign"})
    elif change == "wrong_trade":
        fills = json.loads(receipts[3]["raw"])
        fills[0]["orderId"] = 999
        body(receipts[3], fills)
    elif change == "full_page":
        body(receipts[3], json.loads(receipts[3]["raw"]) * 1000)
    elif change == "bracket_account":
        account = json.loads(receipts[-1]["raw"])
        account["balances"][0]["free"] = "9"
        body(receipts[-1], account)
    elif change in {"bracket_open", "foreign_open"}:
        orders = [json.loads(receipts[2]["raw"]) | {"orderId": 999, "status": "NEW"}]
        body(receipts[4], orders)
        if change == "foreign_open":
            body(receipts[1], orders)
    elif change == "response_sequence":
        receipts[0]["path"], receipts[1]["path"] = receipts[1]["path"], receipts[0]["path"]
    else:
        receipts[0]["path"] = "https://api.binance.com/api/v3/account"
    with pytest.raises(StreamError):
        replay(case, rechain(rows))


def test_heartbeat_inside_and_disconnect_after_seal_are_historical_only(case):
    rows = sealed(case)
    first = next(i for i, r in enumerate(rows) if r["kind"] == "rest_response")
    rows.insert(first, {k: v for k, v in rows[first].items() if k in
                       {"received_ns", "binding", "epoch"}} | {"kind": "testnet_transport_alive"})
    rows.append({k: v for k, v in rows[-1].items() if k in
                 {"received_ns", "binding", "epoch"}} | {"kind": "disconnected"})
    result = replay(case, rechain(rows))
    assert result.evidence_raw == canonical(case.receipt.evidence)
    assert result.summary()["current_venue_state_verified"] is False


@pytest.mark.parametrize("change", ["missing_trade", "unrelated_balance"])
def test_consistent_seal_does_not_substitute_for_native_economic_reconciliation(case, change):
    if change == "missing_trade":
        case.response["/api/v3/myTrades"] = []
    else:
        account = case.response["/api/v3/account"]
        next(r for r in account["balances"] if r["asset"] == "ETH")["free"] = "6"
    sealed(case)
    archived = replay(case)  # Transport/seal integrity alone is insufficient.
    with pytest.raises(ValueError):
        review_archive(case.archive.read_bytes(), case.ledger.path.read_bytes(),
            archive_sha256=archived.archive_sha256, checkpoint_sha256=case.ledger.sha256,
            collection_id=archived.collection_id, reviewed_ns=archived.completed_ns + HISTORY_NS,
            loop=case.loop)


def command(archive, checkpoint, collection_id, output):
    return [sys.executable, "-m", "apps.ops.portfolio_session_archive", "--archive", str(archive),
        "--archive-sha256", sha(archive.read_bytes()), "--checkpoint", str(checkpoint),
        "--checkpoint-sha256", sha(checkpoint.read_bytes()), "--collection-id", collection_id,
        "--output", str(output)]


def test_two_standalone_cli_processes_preserve_original_state_and_publish_no_checkpoint(case, tmp_path):
    sealed(case)
    checkpoint, archive = case.ledger.path, case.archive
    original = {p: p.read_bytes() for p in (checkpoint, archive)}
    reports = []
    for i in range(2):
        output = tmp_path / f"review-{i}.json"
        args = command(archive, checkpoint, case.receipt.collection_id, output)
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        summary = json.loads(proc.stdout)
        assert summary["collector_history_window_expired"]
        assert summary["venue_requests_made"] == 0
        assert "account_uid" not in proc.stdout and "PRIVATE KEY" not in proc.stdout
        report = json.loads(output.read_bytes())
        assert "checkpoint" not in report and "native" not in report
        assert output.stat().st_mode & 0o777 == 0o600
        reports.append(report)
    assert reports[0]["historical_view"] == reports[1]["historical_view"]
    assert all(p.read_bytes() == raw for p, raw in original.items())
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1 and json.loads(proc.stdout)["status"] == "historical_replay_failed"
    assert json.loads(output.read_bytes()) == reports[-1]


@pytest.mark.parametrize("missed", [False, True])
def test_sell_archive_replays_exact_owned_residual_locks_and_consumed_attempts(tmp_path, missed):
    from tests.strategies_nautilus.test_portfolio_session_cancel_recovery import close
    from tests.strategies_nautilus.test_portfolio_session_sell_recovery import interrupted_sell

    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope", missed=missed)
        try:
            original = ctx.lease.checkpoint_path.read_bytes()
            receipt = await collect_session(ctx.http, ctx.journal, read_session(original)["state"], sha(original))
            archive, = (tmp_path / "scope").glob("reader-*.jsonl")
            output = tmp_path / "sell-review.json"
            proc = subprocess.run(command(archive, ctx.lease.checkpoint_path, receipt.collection_id, output),
                                  capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            result = json.loads(output.read_bytes())
            view = result["historical_view"]
            assert Decimal(view["owned_btc"]) == Decimal("0.00007")
            assert Decimal(view["expected_locked"]["BTC"]) == Decimal("0.00006")
            assert len(view["fills"]) == 2 and result["historical_dispatches_recorded"] == 2
            assert view["buy_allowance_consumed"] and view["sell_allowance_consumed"]
            assert result["historical_halt_reasons"] == read_session(original)["state"]["halt_reasons"]
            assert ctx.lease.checkpoint_path.read_bytes() == original and not ctx.calls
        finally:
            await close(ctx)
    asyncio.run(scenario())


def test_cli_without_credentials_network_or_session_writer(case, tmp_path):
    sealed(case)
    output = tmp_path / "no-io-review.json"
    args = command(case.archive, case.ledger.path, case.receipt.collection_id, output)
    guard = '''
import os
import sys

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen"}:
        raise AssertionError("network/process access forbidden")
    if event == "open" and isinstance(args[0], str) and "/.config/trader/" in args[0]:
        raise AssertionError("credential read forbidden")
sys.addaudithook(audit)
from apps.ops.portfolio_session_archive import main
from apps.strategies_nautilus import portfolio_session_transport as transport

def forbidden(*args, **kwargs):
    raise AssertionError("live transport/lease forbidden")
transport.SessionLease.__init__ = forbidden
transport.SessionReadHttpClient.__init__ = forbidden
transport.SessionJournal.__init__ = forbidden
raise SystemExit(main())
'''
    proc = subprocess.run([sys.executable, "-c", guard, *args[3:]],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["venue_requests_made"] == 0


@pytest.mark.parametrize("change", ["missing_checkpoint", "wrong_checkpoint", "symlink", "public_file"])
def test_cli_refuses_unavailable_or_unselected_private_inputs(case, tmp_path, change):
    sealed(case)
    output = tmp_path / "failed-review.json"
    args = command(case.archive, case.ledger.path, case.receipt.collection_id, output)
    path = tmp_path / "unavailable-checkpoint.json"
    if change == "wrong_checkpoint":
        path.write_bytes(b'{"secret":"must-not-appear-in-errors"}')
        path.chmod(0o600)
    elif change == "symlink":
        path.symlink_to(case.ledger.path)
    elif change == "public_file":
        path.write_bytes(case.ledger.path.read_bytes())
        path.chmod(0o644)
    args[args.index("--checkpoint") + 1] = str(path)
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1 and not output.exists()
    assert "must-not-appear" not in proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["current_venue_state_verified"] is False


@pytest.mark.parametrize("fee", ["0", "0.00000001"])
def test_terminal_sell_archive_keeps_late_fills_fees_and_consumed_cancel(tmp_path, fee):
    from nautilus_trader.model.identifiers import ClientOrderId

    from apps.strategies_nautilus.portfolio_session_runtime import await_terminal
    from tests.strategies_nautilus.test_portfolio_session_cancel_recovery import close, restore
    from tests.strategies_nautilus.test_portfolio_session_sell_recovery import (
        interrupted_sell,
        terminal_sink,
    )

    async def scenario():
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx, fee=fee)
            if Decimal(fee):
                with pytest.raises(ValueError):
                    await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
            else:
                await await_terminal(ctx.owner, ctx.owner.cache.order(ClientOrderId(ctx.oid)))
            original = ctx.lease.checkpoint_path.read_bytes()
            receipt = await collect_session(ctx.http, ctx.journal, read_session(original)["state"], sha(original))
            archive, = (tmp_path / "scope").glob("reader-*.jsonl")
            output = tmp_path / "terminal-review.json"
            proc = subprocess.run(command(archive, ctx.lease.checkpoint_path, receipt.collection_id, output),
                                  capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            result = json.loads(output.read_bytes())
            view = result["historical_view"]
            assert view == read_session(original)["state"]["view"]
            assert Decimal(view["owned_btc"]) == Decimal("0.00004")
            assert Decimal(view["sell_proceeds_usdt"]) == Decimal("4.2") - Decimal(fee)
            assert Decimal(view["expected_locked"]["BTC"]) == 0
            assert result["historical_dispatches_recorded"] == 3
            assert ("unexpected_nonzero_commission" in result["historical_halt_reasons"]) == bool(Decimal(fee))
            assert ctx.lease.checkpoint_path.read_bytes() == original
        finally:
            await close(ctx)
    asyncio.run(scenario())

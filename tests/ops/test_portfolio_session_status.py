"""Operator status preserves uncertainty and never creates execution permission."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from apps.ops import portfolio_session_run as runner
from apps.ops import portfolio_session_status as status
from apps.strategies_nautilus.portfolio_adapter_checkpoint import checkpoint_bytes
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from tests.strategies_nautilus.test_portfolio_session_sell_recovery import (
    close,
    interrupted_sell,
    restore,
    terminal_sink,
)


@pytest.fixture
def record(tmp_path):
    ctx = asyncio.run(interrupted_sell(tmp_path / "scope"))
    asyncio.run(close(ctx))
    return ctx


def read_status(ctx, **kwargs):
    return status.local_status(root=ctx.lease.root, now_ns=ctx.clock.timestamp_ns(), **kwargs)


def test_local_active_sell_summary_distinguishes_intents_attempts_and_owned_inventory(record):
    before = {p.name: p.read_bytes() for p in record.lease.root.iterdir() if p.is_file()}
    result = read_status(record)
    assert result["outcome"] == "recorded_active_requires_reconciliation"
    assert result["evidence_basis"] == "local_checkpoint_record"
    assert result["recorded_owned_btc"] == "0.00007"
    assert result["buy_allowance_consumed"] and result["sell_allowance_consumed"]
    assert result["dispatches_recorded"] == 2
    assert result["orders"][1]["recorded_status"] == "PARTIALLY_FILLED"
    assert not result["orders"][1]["cancel_allowance_consumed"]
    assert not result["current_venue_state_verified"] and not result["new_orders_authorized"]
    assert result["next_step"] == "signed_get_reconciliation_before_any_action"
    assert "ETH" not in json.dumps(result) and "key_sha256" not in json.dumps(result)
    after = {p.name: p.read_bytes() for p in record.lease.root.iterdir() if p.is_file()}
    assert after == before


def test_prepared_cancel_is_consumed_even_without_dispatch(record):
    wrapped = read_session(record.raw)
    wrapped["state"]["cancel_intents"][record.oid] = record.clock.timestamp_ns()
    raw = checkpoint_bytes(wrapped["state"], wrapped["native"])
    result = status.checkpoint_status(raw, now_ns=record.clock.timestamp_ns())
    assert result["outcome"] == "unresolved_cancellation_no_retry"
    sell = result["orders"][1]
    assert sell["cancel_intent_consumed"] and sell["cancel_allowance_consumed"]
    assert not sell["cancel_dispatch_recorded"]
    assert result["dispatches_recorded"] == 2 and not result["cancel_retry_allowed"]


@pytest.mark.parametrize("terminal", [False, True])
def test_native_pending_cancel_or_terminal_reconciliation_keeps_evidence_basis(tmp_path, terminal):
    async def scenario():
        from nautilus_trader.model.identifiers import ClientOrderId

        from apps.strategies_nautilus.portfolio_session_ledger import SessionLedgerError
        from apps.strategies_nautilus.portfolio_session_runtime import await_terminal
        from tests.strategies_nautilus.test_portfolio_session_sell_recovery import reconcile
        ctx = await interrupted_sell(tmp_path / "scope")
        try:
            await restore(ctx)
            terminal_sink(ctx, timeout=not terminal)
            order = ctx.owner.cache.order(ClientOrderId(ctx.oid))
            if terminal:
                await await_terminal(ctx.owner, order)
                reconciled = await reconcile(ctx)
                raw = reconciled["checkpoint"]
            else:
                with pytest.raises(SessionLedgerError):
                    await await_terminal(ctx.owner, order)
                raw = ctx.lease.checkpoint_path.read_bytes()
            result = status.checkpoint_status(raw, now_ns=ctx.clock.timestamp_ns())
            assert result["dispatches_recorded"] == 3
            assert result["orders"][1]["cancel_allowance_consumed"]
            assert result["outcome"] == ("recorded_terminal_with_residual" if terminal else "unresolved_cancellation_no_retry")
            assert result["recorded_owned_btc"] == ("0.00004" if terminal else "0.00007")
            assert not result["current_venue_state_verified"]
            assert not result["new_orders_authorized"] and not result["cancel_retry_allowed"]
        finally:
            await close(ctx)
    asyncio.run(scenario())


@pytest.mark.parametrize("offset,expired", [(status.HISTORY_NS, False), (status.HISTORY_NS + 1, True)])
def test_history_bound_is_visible_without_network_or_deadline_extension(record, offset, expired):
    state = read_session(record.raw)["state"]
    result = status.local_status(root=record.lease.root, now_ns=state["started_ns"] + offset)
    assert result["collector_history_window_expired"] is expired
    assert result["new_order_deadline_expired"]
    if expired:
        assert result["next_step"] == "review_archived_evidence_history_window_exceeded"
    assert record.lease.checkpoint_path.read_bytes() == record.raw


@pytest.mark.parametrize("damage", ["missing_checkpoint", "bad_checkpoint", "activation", "scope", "symlink", "permissions"])
def test_unreadable_or_mismatched_scope_never_becomes_fresh_allowance(record, damage):
    path = record.lease.checkpoint_path
    if damage == "missing_checkpoint":
        path.unlink()
    elif damage == "bad_checkpoint":
        path.write_text("signed-secret-URL-must-not-escape")
    elif damage in {"scope", "activation"}:
        target = record.lease.root / ("scope.json" if damage == "scope" else "activated.json")
        target.write_text("{}")
    elif damage == "symlink":
        path.unlink()
        path.symlink_to(record.lease.root / "scope.json")
    else:
        path.chmod(0o644)
    result = read_status(record)
    assert result["outcome"] == "unknown_preserve_scope"
    assert result["recorded_owned_btc"] is None and result["orders"] is None
    assert not result["new_orders_authorized"]
    assert "signed-secret" not in json.dumps(result)


def test_concurrent_checkpoint_change_is_reported_as_unknown(record, monkeypatch):
    original = status.private_read
    calls = 0
    def read(path):
        nonlocal calls
        calls += 1
        raw = original(path)
        return raw + b" " if calls == 6 else raw
    monkeypatch.setattr(status, "private_read", read)
    assert read_status(record)["outcome"] == "unknown_preserve_scope"
    assert record.lease.checkpoint_path.read_bytes() == record.raw


def test_clock_regression_and_invalid_checkpoint_are_sanitized(record):
    state = read_session(record.raw)["state"]
    result = status.checkpoint_status(record.raw, now_ns=state["updated_ns"] - 1)
    assert result["outcome"] == "unknown_preserve_scope"
    assert status.checkpoint_status(b"secret", now_ns=1) == status.unavailable_status()


def test_status_cli_never_loads_credentials_git_lease_or_transport(record, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("status attempted a forbidden side effect")
    for name in ("load_testnet_ed25519_credentials", "SessionLease", "SessionReadHttpClient", "clean_revision"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.subprocess, "check_output", forbidden)
    monkeypatch.setattr(runner, "local_status", lambda **kw: status.local_status(root=record.lease.root, **kw))
    monkeypatch.setattr("sys.argv", ["portfolio_session_run", "--status", "--credentials", "/missing-key"])
    before = hashlib.sha256(record.raw).hexdigest()
    assert runner.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checkpoint_sha256"] == before
    assert not result["current_venue_state_verified"]
    assert hashlib.sha256(record.lease.checkpoint_path.read_bytes()).hexdigest() == before


def test_missing_status_cli_fails_without_exposing_exception(monkeypatch, capsys):
    monkeypatch.setattr(runner, "local_status", lambda **kwargs: status.unavailable_status())
    monkeypatch.setattr("sys.argv", ["portfolio_session_run", "--status"])
    assert runner.main() == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "unknown_preserve_scope"


def test_failure_stdout_points_to_safe_status_command_without_exception_text(monkeypatch, capsys):
    async def fail(args):
        raise ValueError("secret signature URL")
    monkeypatch.setattr(runner, "run", fail)
    monkeypatch.setattr("sys.argv", ["portfolio_session_run", "--recover"])
    assert runner.main() == 1
    output = capsys.readouterr().out
    assert "secret signature" not in output
    assert json.loads(output)["next_command"].endswith(" --status")


def test_empty_prepared_and_submitted_records_never_claim_no_order_risk(tmp_path):
    from apps.strategies_nautilus.portfolio_session_runtime import stop_matching
    from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import drain
    from tests.strategies_nautilus.test_portfolio_session_runtime import create_owner, submit
    async def scenario():
        owner = create_owner(tmp_path / "scope")
        try:
            def snapshot():
                return status.checkpoint_status(owner.ledger.path.read_bytes(), now_ns=owner.clock.timestamp_ns())
            assert snapshot()["outcome"] == "activated_without_order_record"
            assert not snapshot()["new_orders_authorized"]
            submit(owner)
            prepared = snapshot()
            assert prepared["outcome"] == "unresolved_submission_no_resubmit"
            assert prepared["buy_allowance_consumed"] and prepared["dispatches_recorded"] == 0
            await drain(owner)
            submitted = snapshot()
            assert submitted["orders"][0]["recorded_status"] == "SUBMITTED"
            assert submitted["dispatches_recorded"] == 1
            assert submitted["outcome"] == "unresolved_submission_no_resubmit"
        finally:
            await stop_matching(owner)
            owner.journal.close()
            owner.lease.close()
    asyncio.run(scenario())

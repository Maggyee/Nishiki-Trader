"""One fixed ADR-017 testnet lifecycle; --recover is signed GET-only reconciliation."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from dataclasses import asdict
from decimal import ROUND_FLOOR
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4

from nautilus_trader.common.component import LiveClock

from apps.ops.portfolio_session_transport import PROJECT, SELECTION_SHA256, metadata_capture
from apps.strategies_nautilus.portfolio_session_bootstrap import reconcile_collected
from apps.strategies_nautilus.portfolio_session_cancel_recovery import restore_cancel_runtime
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_runtime import (
    RUNTIME_PROFILE,
    await_terminal,
    fixture_signal,
    matching_account,
    start_matching,
    stop_matching,
)
from apps.strategies_nautilus.portfolio_session_transport import (
    SessionJournal,
    SessionLease,
    SessionReadHttpClient,
    collect_session,
    private_read,
    write_private_new,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_capabilities import (
    TestnetCapabilityHttpClient,
    capability_rules,
    collect_capabilities,
)
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    load_testnet_ed25519_credentials,
)
from apps.strategies_nautilus.portfolio_testnet_observation import (
    account_balances,
    select_initial_observation,
)
from apps.strategies_nautilus.portfolio_testnet_session import validation_price


def clean_revision():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=PROJECT, text=True).strip()
    revision = git("rev-parse", "HEAD")
    if git("status", "--porcelain") or revision != git("rev-parse", "@{upstream}"):
        raise StreamError("matching requires clean committed code synchronized with upstream")
    return revision


async def review_native(http, journal, raw):
    state = read_session(raw)["state"]
    http.client_order_ids = frozenset(state["intents"])
    receipt = await collect_session(http, journal, state, hashlib.sha256(raw).hexdigest())
    result = reconcile_collected(raw, receipt, journal, loop=asyncio.get_running_loop())
    return receipt, result


async def fresh_terms(http, initial, selection, clock, journal, path):
    fence = journal.fence()
    capture = await collect_capabilities(http, initial, selection, clock.timestamp_ns)
    write_private_new(path, canonical(capture))
    journal.assert_fence(fence)
    price = D(validation_price(capture, clock.timestamp_ns()))
    rules = capability_rules(capture, now_ns=clock.timestamp_ns(), max_age_ns=5_000_000_000)
    return capture, rules, price


def check_account(capture, account, binding):
    observed = json.loads(capture["captures"][-1]["body"])
    if account_balances(observed, binding.account_uid) != account_balances(account, binding.account_uid):
        raise StreamError("fresh capabilities and complete native account differ")


async def run(args):
    cancel_recovery = getattr(args, "recover_cancel", False)
    revision = clean_revision() if args.execute or cancel_recovery else subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    clock = LiveClock()
    credentials = load_testnet_ed25519_credentials(args.credentials)
    initial = private_read(PROJECT / "data/spot-testnet-initial-account-20260911T014024Z.json")
    http = SessionReadHttpClient(clock, credentials.api_key, None, TESTNET_REST,
                                ed25519_private_key=credentials.private_key_pem)
    binding = select_initial_observation(initial, SELECTION_SHA256, http)
    lease = SessionLease(binding, SELECTION_SHA256)
    journal = stream = owner = None
    prefix = ("matching-" if args.execute else "cancel-recovery-" if cancel_recovery else "recovery-") + uuid4().hex[:12]
    def artifact(name):
        return lease.root / f"{prefix}-{name}"
    stage = "fixed_scope_check"
    try:
        if args.execute and ((lease.root / "activated.json").exists() or lease.checkpoint_path.exists()):
            raise StreamError("fixed matching scope already activated; use GET-only recovery")
        if not args.execute:
            lease.assert_active()
            raw = private_read(lease.checkpoint_path)
            state = read_session(raw)["state"]
            if state.get("runtime_profile") != RUNTIME_PROFILE or state["session_id"] != lease.state["session_id"]:
                raise StreamError("fixed matching checkpoint required")
            http.client_order_ids = frozenset(state["intents"])
        archive = artifact("stream.jsonl")
        write_private_new(archive, b"")
        journal = SessionJournal(archive, binding, clock_ns=clock.timestamp_ns)
        from apps.strategies_nautilus.portfolio_user_stream import ReadOnlyBinanceUserStream
        stream = ReadOnlyBinanceUserStream(http, api_secret=credentials.private_key_pem,
            journal=journal, clock=clock, loop=asyncio.get_running_loop())
        stage = "signed_subscription"
        await stream.start()
        await stream.ping()
        cleanup = "not_needed"
        if args.execute:
            stage = "full_metadata"
            metadata = await metadata_capture(clock)
            write_private_new(artifact("metadata.json"), metadata)
            capability_http = TestnetCapabilityHttpClient(clock, credentials.api_key, None,
                TESTNET_REST, ed25519_private_key=credentials.private_key_pem)
            stage = "fresh_buy_fee_filter_gate"
            capture, rules, price = await fresh_terms(capability_http, initial, SELECTION_SHA256,
                clock, journal, artifact("buy-capabilities.json"))
            now = clock.timestamp_ns()
            baseline_state = {"source": asdict(binding), "started_ns": now - 1,
                              "updated_ns": now - 1, "intents": {}}
            stage = "full_account_before_activation"
            initial_receipt = await collect_session(http, journal, baseline_state,
                                                    hashlib.sha256(initial).hexdigest())
            check_account(capture, initial_receipt.evidence["account"], binding)
            initial_receipt.assert_current(journal, hashlib.sha256(initial).hexdigest())
            if not 0 <= clock.timestamp_ns() - rules.ts_ns <= 5_000_000_000:
                raise StreamError("rules expired before fixed matching activation")
            owner, provider = matching_account(account=initial_receipt.evidence["account"],
                metadata_raw=metadata, binding=binding, clock=clock, http=http)
            initial_receipt.assert_current(journal, hashlib.sha256(initial).hexdigest())
            stage = "native_activation"
            start_matching(owner, provider, lease=lease, journal=journal, credentials=credentials,
                           loop=asyncio.get_running_loop())
            # Full native-vs-signed comparison is mandatory even at empty baseline.
            receipt, result = await review_native(http, journal, private_read(lease.checkpoint_path))
            if result["view"] != owner.ledger.state["view"]:
                raise StreamError("native bootstrap differs from signed account recovery")
            stage = "buy_admission"
            owner.bridge.arm(receipt, rules)
            order = owner.strategy.consume(fixture_signal(owner, "buy"), rules=rules, price=price)
            stage = "buy_lifecycle"
            await await_terminal(owner, order)
            await stream.ping()
            receipt, result = await review_native(http, journal, private_read(lease.checkpoint_path))
            if result["view"] != owner.ledger.state["view"]:
                raise StreamError("missing native events require recovery before reduction")
            write_private_new(artifact("buy-reconciled.json"), result["checkpoint"])
            owned = D(result["view"]["owned_btc"])
            if owned:
                stage = "owned_cleanup_gate"
                capture, rules, _ = await fresh_terms(capability_http, initial, SELECTION_SHA256,
                    clock, journal, artifact("sell-capabilities.json"))
                check_account(capture, receipt.evidence["account"], binding)
                # Prospective cleanup LIMIT at current best bid; never sweep old BTC.
                book = json.loads(next(r["body"] for r in capture["captures"]
                                       if r["path"] == "/api/v3/ticker/bookTicker"))
                price = D(book["bidPrice"])
                quantity = (owned / rules.quantity_step).to_integral_value(rounding=ROUND_FLOOR) * rules.quantity_step
                if quantity < rules.quantity_min or quantity * price < rules.notional_min:
                    cleanup = "owned_residual_below_minimum_retained"
                else:
                    receipt, result = await review_native(http, journal, private_read(lease.checkpoint_path))
                    if result["view"] != owner.ledger.state["view"]:
                        raise StreamError("native reduction state changed")
                    owner.bridge.arm(receipt, rules)
                    order = owner.strategy.consume(fixture_signal(owner, "flat"), rules=rules, price=price)
                    await await_terminal(owner, order)
                    cleanup = "one_owned_cleanup_attempt"
            await stream.ping()
            raw = private_read(lease.checkpoint_path)
        if cancel_recovery:
            stage = "signed_cancellation_recovery"
            receipt = await collect_session(http, journal, state, hashlib.sha256(raw).hexdigest())
            owner, result = await restore_cancel_runtime(raw=raw, receipt=receipt, journal=journal,
                lease=lease, clock=clock, http=http, credentials=credentials)
            cleanup = "terminal_session_no_action"
            if owner is not None:
                stage = "recovered_original_order_cancellation"
                order = next(o for o in owner.cache.orders() if not o.is_closed)
                await await_terminal(owner, order)
                await stream.ping()
                raw = private_read(lease.checkpoint_path)
                cleanup = (
                    "one_recovered_original_order_cancellation"
                    if f"cancel:{order.client_order_id}" in owner.ledger.state.get("dispatches", {})
                    else "original_order_completed_before_cancellation"
                )
        if not cancel_recovery or owner is not None:
            stage = "final_signed_reconciliation"
            receipt, result = await review_native(http, journal, raw)
        checkpoint = result.pop("checkpoint")
        write_private_new(artifact("recovered.json"), checkpoint)
        write_private_new(artifact("evidence.json"), canonical(receipt.evidence))
        receipt.assert_current(journal, hashlib.sha256(raw).hexdigest())
        result.update(schema_version="portfolio.testnet_bounded_matching_result.v1",
            code_commit=revision, code_dirty=False if args.execute or cancel_recovery else None,
            scope_activated=True, cleanup=cleanup, known_orders=len(receipt.evidence["orders"]),
            known_trades=len(receipt.evidence["trades"]),
            account_wide_open_orders=len(receipt.evidence["open_orders"]),
            production_requests=0, run_kind="matching" if args.execute else "cancel_only_recovery" if cancel_recovery else "GET_only_recovery",
            native_checkpoint_sha256=hashlib.sha256(raw).hexdigest(),
            archive=str(archive), session_id=lease.state["session_id"])
        # The numerical reconciler's matching_requests_made describes its GET-only scope.
        result["matching_dispatches_recorded"] = len(read_session(raw)["state"].get("dispatches", {}))
        write_private_new(artifact("report.json"), canonical(result))
        return {key: result[key] for key in ("run_kind", "full_account_assets",
            "full_account_reconciled", "known_orders", "known_trades", "account_wide_open_orders",
            "cleanup", "view")} | {"report": str(artifact("report.json"))}
    except BaseException as exc:
        if owner is not None and hasattr(owner, "bridge"):
            owner.bridge.fail("cancel_recovery_interrupted" if cancel_recovery else "matching_runner_aborted_requires_reconciliation")
        # Exception text is deliberately not archived: HTTP errors can contain signed URLs.
        write_private_new(artifact("failure.json"), canonical({"exception_type": type(exc).__name__,
            "stage": stage, "scope_activated": (lease.root / "activated.json").exists(),
            "code_commit": revision, "status": "halted_no_retry", "production_requests": 0}))
        raise
    finally:
        try:
            await stop_matching(owner)
        finally:
            try:
                if stream is not None:
                    await stream.disconnect()
            finally:
                if journal is not None:
                    journal.close()
                lease.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true", help="Consume the one fixed testnet matching session")
    mode.add_argument("--recover", action="store_true", help="GET-only original-ID reconciliation; never send orders")
    mode.add_argument("--recover-cancel", action="store_true", help="Reconcile fixed scope; cancel an active original order only if never attempted")
    parser.add_argument("--credentials", type=Path, default=Path.home() / ".config/trader/binance_testnet.env")
    try:
        result = asyncio.run(run(parser.parse_args()))
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": "halted_no_retry", "detail": "Inspect fixed private evidence; never delete activation or repeat BUY."}))
        return 1
    # Full balances and fill details remain in private artifacts.
    result.pop("view", None)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

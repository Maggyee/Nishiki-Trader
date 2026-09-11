"""Bounded actual-testnet LiveClock bootstrap/recovery probe. GET-only, no orders."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpClient, HttpMethod

from apps.strategies_nautilus.portfolio_session_bootstrap import (
    bootstrap_probe,
    reconcile_collected,
)
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_transport import (
    SessionJournal,
    SessionLease,
    SessionReadHttpClient,
    collect_session,
    private_read,
    write_private_new,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    load_testnet_ed25519_credentials,
)
from apps.strategies_nautilus.portfolio_testnet_observation import select_initial_observation
from apps.strategies_nautilus.portfolio_user_stream import ReadOnlyBinanceUserStream

SELECTION_SHA256 = "205cf2a16badecf973889f5de92ceede53d902d294d92eec565ff060f6c422cc"
PROJECT = Path(__file__).resolve().parents[2]


async def metadata_capture(clock):
    started = clock.timestamp_ns()
    async with asyncio.timeout(15):
        response = await HttpClient().request(
            HttpMethod.GET, url=TESTNET_REST + "/api/v3/exchangeInfo", headers={}, body=None
        )
    if response.status != 200 or len(response.body) > 16 * 1024 * 1024:
        raise StreamError("full testnet metadata read failed")
    return canonical(
        {
            "schema_version": "portfolio.testnet_exchange_info_observation.v1",
            "endpoint": TESTNET_REST + "/api/v3/exchangeInfo",
            "started_ns": started,
            "received_ns": clock.timestamp_ns(),
            "response_body": response.body.decode(),
            "response_sha256": hashlib.sha256(response.body).hexdigest(),
        }
    )


async def run(args):
    clock = LiveClock()
    credentials = load_testnet_ed25519_credentials(args.credentials)
    initial = private_read(args.selection, 8 * 1024 * 1024)
    http = SessionReadHttpClient(
        clock,
        credentials.api_key,
        None,
        TESTNET_REST,
        ed25519_private_key=credentials.private_key_pem,
    )
    binding = select_initial_observation(initial, args.selection_sha256, http)
    lease = SessionLease(binding, args.selection_sha256)
    journal, stream, owner = None, None, None
    prefix = "probe-" + uuid4().hex[:12]

    def artifact(name):
        return lease.root / f"{prefix}-{name}"

    try:
        if args.checkpoint:
            checkpoint_path = args.checkpoint.absolute()
            if checkpoint_path.parent != lease.root or not checkpoint_path.name.startswith(
                "probe-"
            ):
                raise StreamError("only a selected probe checkpoint in the fixed scope is accepted")
            raw = private_read(checkpoint_path)
            state = read_session(raw)["state"]
            if (
                state.get("runtime_profile") != "testnet_liveclock_readonly_probe_v1"
                or state["session_id"] != lease.state["session_id"]
            ):
                raise StreamError("probe cannot load matching or foreign session state")
            http.client_order_ids = frozenset(state["intents"])
        else:
            checkpoint_path = artifact("native.json")
            raw = initial
            now = clock.timestamp_ns()
            state = {
                "source": asdict(binding),
                "started_ns": now - 1,
                "updated_ns": now - 1,
                "intents": {},
            }
            metadata = await metadata_capture(clock)
            write_private_new(artifact("metadata.json"), metadata)
        archive = artifact("stream.jsonl")
        write_private_new(archive, b"")
        journal = SessionJournal(archive, binding, clock_ns=clock.timestamp_ns)
        stream = ReadOnlyBinanceUserStream(
            http,
            api_secret=credentials.private_key_pem,
            journal=journal,
            clock=clock,
            loop=asyncio.get_running_loop(),
        )
        async with asyncio.timeout(90):
            await stream.start()
            await stream.ping()
            if not args.checkpoint:
                initial_receipt = await collect_session(
                    http, journal, state, hashlib.sha256(initial).hexdigest()
                )
                initial_receipt.assert_current(journal, hashlib.sha256(initial).hexdigest())
                owner = bootstrap_probe(
                    account=initial_receipt.evidence["account"],
                    metadata_raw=metadata,
                    binding=binding,
                    path=checkpoint_path,
                    clock=clock,
                    http=http,
                    credentials=credentials,
                    loop=asyncio.get_running_loop(),
                    session_id=lease.state["session_id"],
                )
                journal.execution_handler = owner.receiver.receive
                journal.account_handler = owner.bridge.account_update
                initial_receipt.assert_current(journal, hashlib.sha256(initial).hexdigest())
                raw = private_read(checkpoint_path)
                state = read_session(raw)["state"]
            receipt = await collect_session(http, journal, state, hashlib.sha256(raw).hexdigest())
            if owner is not None:
                owner.bridge.assert_account_correlated()
            result = reconcile_collected(raw, receipt, journal, loop=asyncio.get_running_loop())
            recovered = artifact("recovered.json")
            write_private_new(recovered, result.pop("checkpoint"))
            write_private_new(artifact("evidence.json"), canonical(receipt.evidence))
            receipt.assert_current(journal, hashlib.sha256(raw).hexdigest())
            await stream.ping()
            receipt.assert_current(journal, hashlib.sha256(raw).hexdigest())
        result.update(
            schema_version="portfolio.testnet_session_transport_probe.v1",
            checkpoint=str(checkpoint_path),
            recovered_checkpoint=str(recovered),
            archive=str(archive),
            matching_scope_activated=(lease.root / "activated.json").exists(),
            code_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
            ).strip(),
            code_dirty=bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=PROJECT, text=True
                ).strip()
            ),
            known_orders_reconciled=len(receipt.evidence["orders"]),
            trades_reconciled=len(receipt.evidence["trades"]),
        )
        report_path = artifact("report.json")
        write_private_new(report_path, canonical(result))
        return {
            key: result[key]
            for key in (
                "full_account_assets",
                "full_account_reconciled",
                "native_reports_reconciled",
                "signed_source_bound",
                "runtime_ready",
                "matching_enabled",
                "matching_scope_activated",
                "output_sha256",
                "recovered_checkpoint",
            )
        } | {"report": str(report_path)}
    finally:
        try:
            try:
                if stream is not None:
                    await stream.disconnect()
            finally:
                if owner is not None:
                    try:
                        owner.engine.stop()
                        await asyncio.gather(
                            owner.engine.get_cmd_queue_task(), owner.engine.get_evt_queue_task()
                        )
                        owner.engine.dispose()
                    finally:
                        owner.ledger.close()
        finally:
            if journal is not None:
                journal.close()
            lease.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials", type=Path, default=Path.home() / ".config/trader/binance_testnet.env"
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=PROJECT / "data/spot-testnet-initial-account-20260911T014024Z.json",
    )
    parser.add_argument("--selection-sha256", default=SELECTION_SHA256)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Recover a selected prior read-only probe checkpoint; never resume orders",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (Exception, KeyboardInterrupt):
        print(
            json.dumps(
                {
                    "status": "session_transport_probe_failed",
                    "runtime_ready": False,
                    "matching_enabled": False,
                    "detail": "Inspect retained private evidence; no automatic retry or allowance reset.",
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

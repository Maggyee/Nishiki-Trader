"""Bounded, explicit Binance Spot testnet observation; never start an order engine."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from nautilus_trader.common.component import LiveClock

from apps.strategies_nautilus.portfolio_stream import StreamError
from apps.strategies_nautilus.portfolio_testnet_credentials import load_testnet_ed25519_credentials
from apps.strategies_nautilus.portfolio_testnet_observation import (
    TestnetObservationJournal,
    collect_testnet_observation,
    replay_testnet_observation,
    select_initial_observation,
)


async def observe_sessions(http, stream, journal, *, selection_sha256, interval_seconds=5):
    """Two explicit subscriptions, each with observations bracketing two ping intervals."""
    if not 0 < interval_seconds <= 5:
        raise StreamError("bounded observation interval required")
    observations, epochs = [], []
    old_fence = None
    async with asyncio.timeout(180):
        for _ in range(2):
            try:
                await stream.start()
                await stream.ping()
                current = journal.fence()
                if current.epoch in epochs:
                    raise StreamError("reconnect reused subscription epoch")
                if old_fence is not None:
                    try:
                        journal.assert_fence(old_fence)
                    except StreamError:
                        pass
                    else:
                        raise StreamError("reconnect accepted an old stream fence")
                epochs.append(current.epoch)
                observations.append(
                    await collect_testnet_observation(
                        http,
                        journal,
                        selection_sha256=selection_sha256,
                    )
                )
                for _ in range(2):
                    await asyncio.sleep(interval_seconds)
                    await stream.ping()
                observations.append(
                    await collect_testnet_observation(
                        http,
                        journal,
                        selection_sha256=selection_sha256,
                    )
                )
                old_fence = journal.fence()
            finally:
                await stream.disconnect()
            try:
                journal.fence()
            except StreamError:
                pass
            else:
                raise StreamError("disconnected stream remained usable")
    return observations, epochs


async def run(args):
    credentials = load_testnet_ed25519_credentials(args.credentials)
    clock = LiveClock()
    http = credentials.create_http_client(clock)
    with args.selection.open("rb") as selected:
        raw = selected.read(8 * 1024 * 1024 + 1)
    binding = select_initial_observation(raw, args.selection_sha256, http)
    # Reserve a fresh private archive; an existing run is never overwritten/appended.
    fd = os.open(args.archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    journal = TestnetObservationJournal(args.archive, binding, clock_ns=clock.timestamp_ns)
    try:
        http, stream = credentials.create_clients(
            journal=journal,
            clock=clock,
            loop=asyncio.get_running_loop(),
        )
        observations, epochs = await observe_sessions(
            http,
            stream,
            journal,
            selection_sha256=args.selection_sha256,
        )
    finally:
        journal.close()
    with args.archive.open("rb") as archive:
        raw = archive.read(64 * 1024 * 1024 + 1)
    digest = hashlib.sha256(raw).hexdigest()
    replayed = [
        replay_testnet_observation(
            raw,
            source=binding,
            expected_sha256=digest,
            collection_id=result["collection_id"],
            selection_sha256=args.selection_sha256,
        )
        for result in observations
    ]
    if replayed != observations:
        raise StreamError("testnet observation replay differs")
    rows = [json.loads(line) for line in raw.splitlines()]
    return {
        "schema_version": "portfolio.testnet_observation_run.v1",
        "archive": str(args.archive),
        "archive_sha256": digest,
        "selection_sha256": args.selection_sha256,
        "subscription_epochs": epochs,
        "explicit_reconnect_verified": True,
        "old_fences_rejected": True,
        "local_replay_verified": True,
        "health_receipts": sum(row["kind"] == "testnet_transport_alive" for row in rows),
        "account_events_observed": sum(row["kind"] == "testnet_event" for row in rows),
        "started_ns": rows[0]["received_ns"],
        "ended_ns": rows[-1]["received_ns"],
        "observations": observations,
        "global_stream_continuity_verified": False,
        "adapter_process_recovery_verified": False,
        "runtime_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (Exception, KeyboardInterrupt):
        # Never print exception text, which may contain private response material.
        print(
            json.dumps(
                {
                    "status": "observation_failed",
                    "runtime_ready": False,
                    "detail": "Check explicit inputs and retained partial archive; no automatic retry.",
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

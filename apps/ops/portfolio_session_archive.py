"""Offline ADR-017 archive review in a fresh standalone native process.

Requires explicit retained archive/checkpoint hashes and collection identity.
Loads no credentials, contacts no venue, and publishes only a private diagnostic
report; never a replacement checkpoint, live receipt, or session activation.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from apps.strategies_nautilus.portfolio_session_archive import (
    MAX_ARCHIVE_BYTES,
    replay_session_collection,
)
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_recovery import recover_session
from apps.strategies_nautilus.portfolio_session_transport import (
    HISTORY_NS,
    private_read,
    write_private_new,
)
from apps.strategies_nautilus.portfolio_stream import canonical


def review_archive(raw, checkpoint_raw, *, archive_sha256, checkpoint_sha256, collection_id, reviewed_ns, loop):
    """Call in a disposable process; native currency registration is process global."""
    archived = replay_session_collection(raw, checkpoint_raw, archive_sha256=archive_sha256,
        checkpoint_sha256=checkpoint_sha256, collection_id=collection_id)
    summary = archived.summary()
    if type(reviewed_ns) is not int or reviewed_ns < archived.completed_ns:
        raise ValueError("review cannot predate the selected historical collection")
    result = recover_session(checkpoint_raw, archived.evidence_raw,
        expected_sha256=checkpoint_sha256, evidence_sha256=summary["evidence_sha256"],
        # Validate/reconstruct at the ORIGINAL receipt time, never refresh evidence.
        now_ns=summary["observation_received_ns"], loop=loop)
    original = read_session(checkpoint_raw)["state"]
    recovered = read_session(result["checkpoint"])["state"]
    for key in ("session_id", "started_ns", "deadline_ns", "intents", "cancel_intents", "dispatches"):
        if recovered.get(key) != original.get(key):
            raise ValueError("historical reconstruction changed original session consumption")
    if not set(original["halt_reasons"]) <= set(recovered["halt_reasons"]):
        raise ValueError("historical reconstruction lost a halt")
    return {
        "schema_version": "portfolio.testnet_session_archive_review.v1",
        "status": "historical_session_replayed",
        **summary,
        "reviewed_ns": reviewed_ns,
        "observation_age_ns": reviewed_ns - summary["observation_received_ns"],
        "collector_history_window_expired": reviewed_ns - original["started_ns"] > HISTORY_NS,
        "full_account_assets": result["full_account_assets"],
        "full_account_reconciled": result["full_account_reconciled"],
        "native_reports_reconciled": result["native_reports_reconciled"],
        "historical_view": result["view"],
        "historical_halt_reasons": recovered["halt_reasons"],
        "historical_dispatches_recorded": len(recovered.get("dispatches", {})),
        "venue_requests_made": 0,
        "fixed_checkpoint_written": False,
        "next_step": "preserve_fixed_scope_and_original_evidence",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    loop = asyncio.new_event_loop()
    try:
        raw = private_read(args.archive, limit=MAX_ARCHIVE_BYTES)
        checkpoint_raw = private_read(args.checkpoint)
        report = review_archive(raw, checkpoint_raw, archive_sha256=args.archive_sha256,
            checkpoint_sha256=args.checkpoint_sha256, collection_id=args.collection_id,
            reviewed_ns=time.time_ns(), loop=loop)
        report_raw = canonical(report) + b"\n"
        write_private_new(args.output, report_raw)
    except Exception:
        # Private bodies, paths, parser values and native exceptions never go to stdout.
        print(json.dumps({"status": "historical_replay_failed", "runtime_ready": False,
                          "current_venue_state_verified": False, "new_orders_authorized": False}))
        return 1
    finally:
        loop.close()
    print(json.dumps({
        "status": report["status"],
        "report_sha256": hashlib.sha256(report_raw).hexdigest(),
        "evidence_sha256": report["evidence_sha256"],
        "full_account_assets": report["full_account_assets"],
        "historical_orders": len(report["historical_view"]["statuses"]),
        "historical_fills": len(report["historical_view"]["fills"]),
        "historical_owned_btc": report["historical_view"]["owned_btc"],
        "historical_dispatches_recorded": report["historical_dispatches_recorded"],
        "collector_history_window_expired": report["collector_history_window_expired"],
        "venue_requests_made": 0,
        "current_venue_state_verified": False,
        "new_orders_authorized": False,
        "runtime_ready": False,
    }, sort_keys=True))
    return 0  # Historical diagnostic completed; never an execution/restart permit.


if __name__ == "__main__":
    raise SystemExit(main())

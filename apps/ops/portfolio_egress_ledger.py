"""Replay pinned local egress attempt records offline; never dispatch or resume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.strategies_nautilus.portfolio_egress_ledger import (
    IPC_PROFILE,
    JOINT_PROFILE,
    LIMIT,
    PROFILE,
    replay,
)
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_tls_provenance import canonical, digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--joint-profile", action="store_true")
    profiles.add_argument("--ipc-profile", action="store_true")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--start-monotonic-ns", type=int)
    parser.add_argument("--through-monotonic-ns", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (args.start_monotonic_ns is None) != (args.through_monotonic_ns is None):
            raise ValueError("both_interval_edges_required")
        if (
            args.report.exists()
            or args.report.is_symlink()
            or args.report.resolve() == args.archive.resolve()
        ):
            raise ValueError("new_distinct_report_required")
        report = replay(
            private_read(args.archive, limit=LIMIT),
            expected_sha256=args.archive_sha256,
            binding_sha256=args.binding_sha256,
            profile=IPC_PROFILE
            if args.ipc_profile
            else JOINT_PROFILE
            if args.joint_profile
            else PROFILE,
            start_ns=args.start_monotonic_ns,
            through_ns=args.through_monotonic_ns,
        )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(json.dumps({"status": "egress_ledger_replay_failed", "network_admitted": False}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_sha256": digest(output),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # Local records cannot grant egress capacity or trading admission.


if __name__ == "__main__":
    raise SystemExit(main())

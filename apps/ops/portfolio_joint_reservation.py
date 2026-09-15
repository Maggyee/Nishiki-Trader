"""Replay an explicitly selected offline reservation rehearsal; never dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.strategies_nautilus.portfolio_joint_admission import sha
from apps.strategies_nautilus.portfolio_joint_reservation import MAX_ARCHIVE, replay
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or args.report.resolve() == args.archive.resolve()
        ):
            raise ValueError("new distinct report required")
        report = replay(
            private_read(args.archive, limit=MAX_ARCHIVE),
            expected_sha256=args.archive_sha256,
            policy_sha256=args.policy_sha256,
            scope_id=args.scope_id,
        )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "reservation_replay_failed",
                    "network_admitted": False,
                    "venue_requests_made": 0,
                }
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_sha256": sha(output),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # Even a completed local rehearsal cannot reserve gateway capacity.


if __name__ == "__main__":
    raise SystemExit(main())

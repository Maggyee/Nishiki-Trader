"""Review joint first-request blockers offline; never capture or activate a scope."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from apps.strategies_nautilus.portfolio_joint_admission import MAX_INPUT, review, sha
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--at-ns", type=int)
    parser.add_argument("--monotonic-ns", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if bool(args.candidate) != bool(args.candidate_sha256):
        parser.error("candidate and original SHA256 must be selected together")
    if (args.at_ns is None) != (args.monotonic_ns is None):
        parser.error("historical UTC and monotonic review times must be selected together")
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or (args.candidate and args.report.resolve() == args.candidate.resolve())
        ):
            raise ValueError("new distinct report required")
        report = review(
            private_read(args.candidate, limit=MAX_INPUT) if args.candidate else None,
            expected_sha256=args.candidate_sha256,
            at_ns=time.time_ns() if args.at_ns is None else args.at_ns,
            monotonic_ns=time.monotonic_ns() if args.monotonic_ns is None else args.monotonic_ns,
        )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "admission_review_failed",
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
                "blockers": report["blockers"],
                "report_sha256": sha(output),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # A written review is not a network admission permit.


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify selected source/gateway signatures offline and write a blocked review."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from apps.strategies_nautilus.portfolio_joint_admission import MAX_INPUT, sha
from apps.strategies_nautilus.portfolio_joint_attestation import MAX_PROOF, review
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "policy", "bundle"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--at-ns", type=int)
    parser.add_argument("--monotonic-ns", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.at_ns is None) != (args.monotonic_ns is None):
        parser.error("historical UTC and monotonic review times must be selected together")
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or any(
                args.report.resolve() == path.resolve()
                for path in (args.candidate, args.policy, args.bundle)
            )
        ):
            raise ValueError("new distinct report required")
        report = review(
            private_read(args.candidate, limit=MAX_INPUT),
            candidate_sha256=args.candidate_sha256,
            policy_raw=private_read(args.policy, limit=MAX_PROOF),
            policy_sha256=args.policy_sha256,
            bundle_raw=private_read(args.bundle, limit=MAX_PROOF),
            bundle_sha256=args.bundle_sha256,
            scope_id=args.scope_id,
            at_ns=time.time_ns() if args.at_ns is None else args.at_ns,
            monotonic_ns=time.monotonic_ns() if args.monotonic_ns is None else args.monotonic_ns,
        )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "attestation_review_failed",
                    "network_admitted": False,
                    "capacity_reserved": False,
                    "scope_consumed": False,
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
                "blockers": report["blockers"],
                "network_admitted": False,
                "capacity_reserved": False,
                "scope_consumed": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # Successful authorship review never grants network admission.


if __name__ == "__main__":
    raise SystemExit(main())

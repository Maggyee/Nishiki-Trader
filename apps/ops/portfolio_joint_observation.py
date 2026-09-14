"""Replay a selected synthetic joint archive; no capture mode or credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.strategies_nautilus.portfolio_joint_observation import JointEvidence, digest, replay_joint
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
from apps.strategies_nautilus.portfolio_market_depth import MAX_ARCHIVE
from apps.strategies_nautilus.portfolio_market_depth_archive import flags
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument(
        "--loopback-profile",
        action="store_true",
        help="Explicitly select the separate native loopback archive profile",
    )
    profiles.add_argument(
        "--tls-loopback-profile",
        action="store_true",
        help="Replay the separate TLS joint archive and original wire bytes",
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or args.report.resolve() == args.archive.resolve()
        ):
            raise ValueError("new distinct output required")
        report = replay_joint(
            private_read(args.archive, limit=MAX_ARCHIVE),
            expected_sha256=args.archive_sha256,
            evidence_type=TLSJointEvidence
            if args.tls_loopback_profile
            else RoutedJointEvidence
            if args.loopback_profile
            else JointEvidence,
        )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(json.dumps({"status": "joint_replay_failed", **flags()}))
        return 1
    print(
        json.dumps(
            {"status": report["status"], "report_sha256": digest(output), **flags()}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

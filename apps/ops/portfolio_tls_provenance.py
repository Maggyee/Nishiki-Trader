"""Replay selected local TLS provenance; no capture or credential options."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.strategies_nautilus.portfolio_session_transport import write_private_new
from apps.strategies_nautilus.portfolio_tls_provenance import canonical, digest, read_provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or args.report.resolve() == args.archive.resolve()
        ):
            raise ValueError("new distinct output required")
        report = read_provenance(args.archive, expected_sha256=args.archive_sha256)
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(json.dumps({"status": "tls_provenance_replay_failed", "network_admitted": False}))
        return 1
    print(
        json.dumps(
            {"status": report["status"], "report_sha256": digest(output), "network_admitted": False}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

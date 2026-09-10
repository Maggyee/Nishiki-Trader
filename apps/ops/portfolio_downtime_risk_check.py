"""Read-only local downtime risk review; never connects or grants restart readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.strategies_nautilus.portfolio_downtime_risk import DowntimeRiskError, review_downtime_risk
from apps.strategies_nautilus.portfolio_stream import SourceBinding
from apps.strategies_nautilus.portfolio_venue import _unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("history", type=Path)
    parser.add_argument("--source-binding", type=Path, required=True)
    parser.add_argument("--before-sha256", required=True)
    parser.add_argument("--after-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        source = SourceBinding(
            **json.loads(args.source_binding.read_bytes(), object_pairs_hook=_unique_object)
        )
        result = review_downtime_risk(
            args.before.read_bytes(),
            args.after.read_bytes(),
            args.history.read_bytes(),
            source=source,
            expected_before_sha256=args.before_sha256,
            expected_after_sha256=args.after_sha256,
        )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, AttributeError) as exc:
        reason = (
            str(exc) if isinstance(exc, DowntimeRiskError) else "invalid downtime review inputs"
        )
        print(json.dumps({"status": "blocked", "reason": reason, "runtime_ready": False}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if result["observed_stop_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

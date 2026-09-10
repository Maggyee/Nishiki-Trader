"""Read-only local account receipt replay; no credentials, network or restart permit."""

from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from apps.strategies_nautilus.portfolio_account import AccountAnchor
from apps.strategies_nautilus.portfolio_account_archive import replay_account_collection
from apps.strategies_nautilus.portfolio_stream import SourceBinding
from apps.strategies_nautilus.portfolio_venue import _unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--source-binding", type=Path, required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = SourceBinding(
            **json.loads(args.source_binding.read_bytes(), object_pairs_hook=_unique_object)
        )
        fields = json.loads(args.anchor.read_bytes(), object_pairs_hook=_unique_object)
        fields["quote"], fields["base"] = Decimal(fields["quote"]), Decimal(fields["base"])
        result = asyncio.run(
            replay_account_collection(
                args.archive.read_bytes(),
                source=source,
                expected_sha256=args.sha256,
                collection_id=args.collection_id,
                anchor=AccountAnchor(**fields),
            )
        )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "invalid account archive inputs",
                    "runtime_ready": False,
                }
            )
        )
        return 2
    print(json.dumps(result.summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

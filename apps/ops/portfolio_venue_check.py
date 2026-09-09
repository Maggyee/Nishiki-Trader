"""Read-only captured Binance rule/fee compatibility diagnostic; never submits."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from apps.strategies_nautilus.portfolio_venue import (
    CapturedResponse,
    PriceReference,
    VenueInputError,
    parse_binance_rules,
)


def check_bundle(bundle: dict, *, now_ns: int) -> dict:
    if bundle["schema_version"] != "portfolio.venue_inputs.v1":
        raise VenueInputError("unsupported venue bundle version")
    responses = [
        CapturedResponse(**bundle[name]) for name in ("exchange_info", "commission", "my_filters")
    ]
    if any(not isinstance(row["price"], str) for row in bundle["references"]):
        raise VenueInputError("reference price must be a decimal string")
    references = tuple(
        PriceReference(**{**row, "price": Decimal(row["price"])}) for row in bundle["references"]
    )
    evidence = parse_binance_rules(
        *responses,
        account_id=bundle["account_id"],
        now_ns=now_ns,
        max_age_ns=60_000_000_000,
        references=references,
    )
    incompatible = [
        side
        for side, currency in (
            ("BUY", evidence.rules.buy_fee_currency),
            ("SELL", evidence.rules.sell_fee_currency),
        )
        if currency != "USDT"
    ]
    return {
        "status": "unsupported_fee_currency" if incompatible else "parsed_offline_only",
        "runtime_ready": False,
        "account_reconciled": False,
        "unsupported_fee_sides": incompatible,
        "rules": asdict(evidence.rules),
        "response_sha256": dict(evidence.response_sha256),
        "inapplicable_filters": list(evidence.inapplicable_filters),
        "price_references": [asdict(ref) for ref in evidence.price_references],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle", type=Path, help="local captured response bundle; no network access"
    )
    parser.add_argument(
        "--now-ns", type=int, help="explicit evaluation time for offline reproduction"
    )
    args = parser.parse_args(argv)
    try:
        report = check_bundle(
            json.loads(args.bundle.read_text()),
            now_ns=args.now_ns if args.now_ns is not None else time.time_ns(),
        )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
        reason = str(exc) if isinstance(exc, VenueInputError) else "invalid venue input bundle"
        print(json.dumps({"status": "blocked", "reason": reason, "runtime_ready": False}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 2 if report["unsupported_fee_sides"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

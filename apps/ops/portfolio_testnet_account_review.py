"""Compare selected full-account observations without qualifying recovery or equity.

Offline only: verify both archives, preserve every asset, and inspect native
currency representation without registering guessed currencies or starting engines.
Detailed reports are private; CLI stdout contains counts and digests only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path

from nautilus_trader.model.objects import Currency, Money

from apps.strategies_nautilus.portfolio_stream import SourceBinding, StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_mapping import map_observed_balances
from apps.strategies_nautilus.portfolio_testnet_observation import (
    account_balances,
    replay_testnet_observation,
)
from apps.strategies_nautilus.portfolio_venue import _unique_object

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def _selected(raw, source, digest, collection_id, selection_sha256):
    summary = replay_testnet_observation(
        raw,
        source=source,
        expected_sha256=digest,
        collection_id=collection_id,
        selection_sha256=selection_sha256,
    )
    rows = [json.loads(line, object_pairs_hook=_unique_object) for line in raw.splitlines()]
    selected = [r for r in rows if r.get("collection_id") == collection_id]
    receipts = [r for r in selected if r["kind"] == "rest_response"]
    # Replay above validated exact account / openOrders / openOrders / account order.
    account = json.loads(receipts[-1]["raw"], object_pairs_hook=_unique_object)
    orders = json.loads(receipts[2]["raw"], object_pairs_hook=_unique_object)
    return {
        "summary": summary,
        "started_ns": selected[0]["started_ns"],
        "completed_ns": selected[-1]["received_ns"],
        "balances": account_balances(account, source.account_uid),
        "metadata": {key: value for key, value in account.items() if key != "balances"},
        "orders": sorted(orders, key=lambda row: (row["symbol"], row["orderId"])),
    }


def _amounts(pair):
    return {"free": str(pair[0]), "locked": str(pair[1])}


def native_representation(balances):
    """Inspect the current native registry; default precision fallback is forbidden."""
    rows = []
    for asset, (free, locked) in sorted(balances.items()):
        currency = Currency.from_str(asset, strict=True)
        if currency is None:
            rows.append({"asset": asset, "status": "missing_native_currency"})
            continue
        try:
            exact = all(
                Money(amount, currency).as_decimal() == amount
                for amount in (free, locked, free + locked)
            )
            status = "exact_observed_amounts" if exact else "native_amount_rounding"
        except (ValueError, OverflowError, ArithmeticError):
            status = "native_amount_unrepresentable"
        rows.append({"asset": asset, "native_precision": currency.precision, "status": status})
    return rows


def review_accounts(
    before_raw,
    after_raw,
    *,
    before_sha256,
    before_collection,
    after_sha256,
    after_collection,
    selection_sha256,
    exchange_info_raw=None,
    exchange_info_sha256=None,
):
    if not 0 < len(before_raw) <= MAX_ARCHIVE_BYTES:
        raise StreamError("bounded selected archive required")
    if hashlib.sha256(before_raw).hexdigest() != before_sha256:
        raise StreamError("selected prior archive changed")
    # Observed source only, never labeled independently verified. The selected
    # digest pins it; replay requires every row of both archives to match it.
    first = json.loads(before_raw.splitlines()[0], object_pairs_hook=_unique_object)
    source = SourceBinding(**first["binding"])
    before = _selected(before_raw, source, before_sha256, before_collection, selection_sha256)
    after = _selected(after_raw, source, after_sha256, after_collection, selection_sha256)
    if after["started_ns"] <= before["completed_ns"]:
        raise StreamError("non-overlapping forward observation interval required")
    old, new = before["balances"], after["balances"]
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    changed = [
        {"asset": asset, "before": _amounts(old[asset]), "after": _amounts(new[asset])}
        for asset in sorted(old.keys() & new.keys())
        if old[asset] != new[asset]
    ]
    mapping = native_representation(new)
    unknown = sum(r["status"] == "missing_native_currency" for r in mapping)
    inexact = sum(
        r["status"] in {"native_amount_rounding", "native_amount_unrepresentable"} for r in mapping
    )
    orders_equal = before["orders"] == after["orders"]
    fields_changed = sorted(
        key
        for key in before["metadata"].keys() | after["metadata"].keys()
        if key not in before["metadata"]
        or key not in after["metadata"]
        or before["metadata"][key] != after["metadata"][key]
    )
    drift = bool(added or removed or changed or fields_changed or not orders_equal)
    if (exchange_info_raw is None) != (exchange_info_sha256 is None):
        raise StreamError("exchange metadata and selected digest must be supplied together")
    metadata_mapping = None
    if exchange_info_raw is not None:
        metadata_mapping = map_observed_balances(
            exchange_info_raw,
            expected_sha256=exchange_info_sha256,
            balances=new,
            account_uid=source.account_uid,
            observed_ns=after["completed_ns"],
        )
    mapped = bool(metadata_mapping and metadata_mapping["detached_native_account_balances_equal"])
    return {
        "schema_version": "portfolio.testnet_account_review.v1",
        "status": "observed_drift" if drift else "observed_equal",
        "inputs": {
            "before_sha256": before_sha256,
            "before_collection": before_collection,
            "after_sha256": after_sha256,
            "after_collection": after_collection,
            "selection_sha256": selection_sha256,
        },
        "before_completed_ns": before["completed_ns"],
        "after_started_ns": after["started_ns"],
        "after_completed_ns": after["completed_ns"],
        "assets_recorded": len(new),
        "assets_added": added,
        "assets_removed": removed,
        "balances_changed": changed,
        "open_orders_equal": orders_equal,
        "account_fields_changed": fields_changed,
        "before_open_orders": len(before["orders"]),
        "after_open_orders": len(after["orders"]),
        "current_observed_balances": {a: _amounts(v) for a, v in sorted(new.items())},
        "nautilus_version": version("nautilus-trader"),
        "native_representation": mapping,
        "missing_native_currencies": unknown,
        "inexact_native_balances": inexact,
        "exchange_metadata_mapping": metadata_mapping,
        "source_consistent": True,
        "independent_uid_verified": False,
        "baseline_qualified": False,
        "reset_history_verified": False,
        "no_trading_history_verified": False,
        "api_key_restrictions_verified": False,
        "valuation_qualified": False,
        "native_mapping_qualified": False,
        "global_continuity_verified": False,
        "runtime_ready": False,
        "blocking_reasons": [
            "independent_identity_and_baseline_unqualified",
            "testnet_permissions_and_reset_history_unqualified",
            "business_events_and_between_observation_history_unqualified",
            "full_asset_valuation_and_native_recovery_unqualified",
        ]
        + (["observed_account_drift_requires_review"] if drift else [])
        + (["missing_native_currency_definitions"] if unknown and not mapped else [])
        + (["native_amount_precision_or_range_mismatch"] if inexact and not mapped else [])
        + (["exchange_metadata_mapping_incomplete"] if metadata_mapping and not mapped else []),
    }


def _read(path):
    with path.open("rb") as stream:
        return stream.read(MAX_ARCHIVE_BYTES + 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for side in ("before", "after"):
        parser.add_argument(f"--{side}-archive", type=Path, required=True)
        parser.add_argument(f"--{side}-sha256", required=True)
        parser.add_argument(f"--{side}-collection", required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exchange-info", type=Path)
    parser.add_argument("--exchange-info-sha256")
    args = parser.parse_args(argv)
    try:
        report = review_accounts(
            _read(args.before_archive),
            _read(args.after_archive),
            before_sha256=args.before_sha256,
            before_collection=args.before_collection,
            after_sha256=args.after_sha256,
            after_collection=args.after_collection,
            selection_sha256=args.selection_sha256,
            exchange_info_raw=_read(args.exchange_info) if args.exchange_info else None,
            exchange_info_sha256=args.exchange_info_sha256,
        )
        raw = canonical(report) + b"\n"
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        print(json.dumps({"status": "review_failed", "runtime_ready": False}))
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "assets_recorded": report["assets_recorded"],
                "changed_assets": len(report["balances_changed"]),
                "added_assets": len(report["assets_added"]),
                "removed_assets": len(report["assets_removed"]),
                "after_open_orders": report["after_open_orders"],
                "missing_native_currencies": report["missing_native_currencies"],
                "inexact_native_balances": report["inexact_native_balances"],
                "detached_native_account_balances_equal": bool(
                    report["exchange_metadata_mapping"]
                    and report["exchange_metadata_mapping"][
                        "detached_native_account_balances_equal"
                    ]
                ),
                "runtime_ready": False,
            },
            sort_keys=True,
        )
    )
    return 0  # completed diagnostic, never a readiness/promotion result


if __name__ == "__main__":
    raise SystemExit(main())

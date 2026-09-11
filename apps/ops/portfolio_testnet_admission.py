"""Offline testnet observation admission, indicative valuation and baseline review.

Consumes pinned account and market captures. Never loads credentials, starts an
engine or turns an observation anchor into a qualified daily-risk baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from apps.ops.portfolio_testnet_account_review import _read, _selected
from apps.strategies_nautilus.portfolio_risk_policy import POLICY_ID
from apps.strategies_nautilus.portfolio_stream import SourceBinding, StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_mapping import map_observed_balances
from apps.strategies_nautilus.portfolio_testnet_observation import account_balances
from apps.strategies_nautilus.portfolio_testnet_order_plan import lifecycle_test_plan
from apps.strategies_nautilus.portfolio_testnet_valuation import indicative_valuation
from apps.strategies_nautilus.portfolio_venue import _unique_object

ADMISSION_ID = "testnet-observation-admission-v1-20260911"
DAY_NS = 86_400_000_000_000
MAX_CAPTURE_SPAN_NS = 60_000_000_000
PATHS = ("/api/v3/exchangeInfo", "/api/v3/ticker/bookTicker")


def review_admission(
    archive_raw,
    market_raw,
    initial_raw,
    *,
    archive_sha256,
    collection_id,
    market_sha256,
    selection_sha256,
):
    if (
        not 0 < len(archive_raw) <= 64 * 1024 * 1024
        or hashlib.sha256(archive_raw).hexdigest() != archive_sha256
    ):
        raise StreamError("selected account archive changed")
    if (
        not 0 < len(initial_raw) <= 8 * 1024 * 1024
        or hashlib.sha256(initial_raw).hexdigest() != selection_sha256
    ):
        raise StreamError("selected initial account observation changed")
    initial = json.loads(initial_raw, object_pairs_hook=_unique_object)
    if (
        initial["schema_version"] != "portfolio.testnet_initial_account_observation.v1"
        or initial["endpoint"] != "https://testnet.binance.vision"
        or initial["path"] != "/api/v3/account"
        or hashlib.sha256(initial["response_body"].encode()).hexdigest()
        != initial["response_sha256"]
    ):
        raise StreamError("initial account source mismatch")
    body = json.loads(initial["response_body"], object_pairs_hook=_unique_object)
    account_balances(body, str(body["uid"]))
    source = SourceBinding(initial["endpoint"], str(body["uid"]), initial["key_sha256"])
    observed = _selected(archive_raw, source, archive_sha256, collection_id, selection_sha256)
    if (
        not 0 < len(market_raw) <= 32 * 1024 * 1024
        or hashlib.sha256(market_raw).hexdigest() != market_sha256
    ):
        raise StreamError("selected market capture changed")
    market = json.loads(market_raw, object_pairs_hook=_unique_object)
    if (
        market["schema_version"] != "portfolio.testnet_market_capture.v1"
        or market["account_archive_sha256"] != archive_sha256
        or market["account_collection_id"] != collection_id
        or not isinstance(market["captures"], list)
        or len(market["captures"]) != 2
    ):
        raise StreamError("market/account observation binding mismatch")
    captures, bodies = market["captures"], []
    previous = observed["completed_ns"]
    for path, capture in zip(PATHS, captures, strict=True):
        if (
            capture["endpoint"] != "https://testnet.binance.vision" + path
            or type(capture["started_ns"]) is not int
            or type(capture["received_ns"]) is not int
            or not previous <= capture["started_ns"] <= capture["received_ns"]
            or capture["received_ns"] - observed["started_ns"] > MAX_CAPTURE_SPAN_NS
            or capture["received_ns"] // DAY_NS != observed["started_ns"] // DAY_NS
            or hashlib.sha256(capture["response_body"].encode()).hexdigest()
            != capture["response_sha256"]
        ):
            raise StreamError("market capture endpoint/hash/time mismatch")
        bodies.append(json.loads(capture["response_body"], object_pairs_hook=_unique_object))
        previous = capture["received_ns"]
    metadata = canonical(
        {"schema_version": "portfolio.testnet_exchange_info_observation.v1", **captures[0]}
    )
    mapping = map_observed_balances(
        metadata,
        expected_sha256=hashlib.sha256(metadata).hexdigest(),
        balances=observed["balances"],
        account_uid=source.account_uid,
        observed_ns=observed["completed_ns"],
    )
    valuation = indicative_valuation(observed["balances"], *bodies)
    checks = {
        "selected_observation_replayed": True,
        "testnet_source_consistent": True,
        "account_market_capture_interval_bounded": True,
        "full_native_amount_mapping": mapping["detached_native_account_balances_equal"],
        "all_assets_have_indicative_marks": valuation["all_assets_priced"],
        "account_wide_open_orders_empty": not observed["orders"],
        "account_reports_can_trade": observed["metadata"]["canTrade"],
    }
    reasons = [key for key, passed in checks.items() if not passed]
    reasons += [
        "independent_identity_and_key_permissions_unqualified",
        "qualified_utc_day_open_and_cashflow_history_missing",
        "quote_event_freshness_and_full_valuation_unqualified",
        "account_market_atomic_revision_unqualified",
        "actual_adapter_recovery_and_business_events_unqualified",
        "scoped_order_test_runner_and_admission_not_qualified",
    ]
    if valuation["depth_exceeded_assets"]:
        reasons.append("observed_balances_exceed_top_book_capacity")
    anchor_inputs = {
        "policy_id": ADMISSION_ID,
        "archive_sha256": archive_sha256,
        "collection_id": collection_id,
        "selection_sha256": selection_sha256,
        "source_binding_sha256": hashlib.sha256(
            canonical(
                {
                    "endpoint": source.endpoint,
                    "uid": source.account_uid,
                    "key_sha256": source.key_sha256,
                }
            )
        ).hexdigest(),
    }
    anchor_id = hashlib.sha256(canonical(anchor_inputs)).hexdigest()
    return {
        "schema_version": "portfolio.testnet_admission_review.v1",
        "policy_id": ADMISSION_ID,
        "risk_policy_id": POLICY_ID,
        "inputs": anchor_inputs | {"market_sha256": market_sha256},
        "checks": checks,
        "observation_anchor": {
            "id": anchor_id,
            "kind": "prospective_observation_reference",
            "start_ns": observed["completed_ns"],
            "balances": {
                asset: {"free": str(free), "locked": str(locked)}
                for asset, (free, locked) in sorted(observed["balances"].items())
            },
            "initial_indicative_mark_usdt": valuation["full_indicative_mark_usdt"],
            "day_open_equity_usdt": None,
            "daily_loss_usdt": None,
            "effective_daily_limit_usdt": None,
            "baseline_qualified": False,
            "reset_history_verified": False,
        },
        "native_mapping": mapping,
        "valuation": valuation,
        "order_test_plan": lifecycle_test_plan(*bodies),
        "independent_uid_verified": False,
        "api_trading_enabled": None,
        "api_key_restrictions_verified": False,
        "source_globally_authenticated": False,
        "account_market_atomic_revision_verified": False,
        "testnet_observation_review_complete": True,
        "testnet_order_ready": False,
        "runtime_ready": False,
        "blocking_reasons": reasons,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--market-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = review_admission(
            _read(args.archive),
            _read(args.market),
            _read(args.initial),
            archive_sha256=args.archive_sha256,
            collection_id=args.collection,
            market_sha256=args.market_sha256,
            selection_sha256=args.selection_sha256,
        )
        raw = canonical(report) + b"\n"
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        print(json.dumps({"status": "admission_review_failed", "runtime_ready": False}))
        return 2
    value = report["valuation"]
    print(
        json.dumps(
            {
                "status": "observation_review_complete",
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "assets_recorded": value["assets_recorded"],
                "priced_assets": value["priced_assets"],
                "unpriced_assets": len(value["unpriced_assets"]),
                "depth_exceeded_assets": len(value["depth_exceeded_assets"]),
                "testnet_order_ready": False,
                "runtime_ready": False,
            },
            sort_keys=True,
        )
    )
    return 0  # successful evidence review, never an order permit


if __name__ == "__main__":
    raise SystemExit(main())

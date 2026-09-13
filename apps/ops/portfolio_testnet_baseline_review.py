"""Offline full-account, UTC baseline and cash-flow gap review (ADR-015/016).

Replays selected original account/market and session archives in a standalone
native process. Endpoint agreement is not complete cash-flow or reset history.
No credentials, network, session writer or executable risk baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from decimal import localcontext
from pathlib import Path

from apps.ops.portfolio_session_archive import review_archive
from apps.ops.portfolio_testnet_admission import DAY_NS, review_admission
from apps.strategies_nautilus.portfolio_risk_policy import (
    DAILY_CAP_USDT,
    DAILY_FRACTION,
    PEAK_LOSS_USDT,
    POLICY_ID,
)
from apps.strategies_nautilus.portfolio_session_ledger import read_session
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_venue import _decimal

INPUTS = {"initial": 8, "account_archive": 64, "market": 32, "session_archive": 64, "checkpoint": 32}


def _balance_bridge(anchor, baseline, final):
    """Exact asset-unit conservation, without assuming any missing asset is zero."""
    rows, differences, locks, missing = [], [], [], []
    with localcontext() as context:
        context.prec = 50
        for asset in sorted(anchor.keys() | baseline.keys() | final.keys()):
            before = anchor.get(asset)
            start = baseline.get(asset)
            end = final.get(asset)
            if before is None or start is None or end is None:
                missing.append(asset)
                rows.append({"asset": asset, "coverage_complete": False,
                    "reference_present": before is not None, "session_baseline_present": start is not None,
                    "session_end_present": end is not None, "unexplained_net_delta": None})
                continue
            if set(before) != {"free", "locked"} or not isinstance(start, list) or len(start) != 2:
                raise StreamError("complete free/locked balance pair required")
            ref_total = _decimal(before["free"]) + _decimal(before["locked"])
            start_total = _decimal(start[0]) + _decimal(start[1])
            end_total = _decimal(end)
            known_delta = end_total - start_total  # From fully reconciled native fills/fees.
            observed_delta = end_total - ref_total
            unexplained = observed_delta - known_delta
            if unexplained:
                differences.append(asset)
            if _decimal(before["locked"]) != _decimal(start[1]):
                locks.append(asset)
            rows.append({"asset": asset, "coverage_complete": True,
                "reference_total": str(ref_total), "session_baseline_total": str(start_total),
                "historical_end_total": str(end_total), "known_session_delta": str(known_delta),
                "observed_endpoint_delta": str(observed_delta), "unexplained_net_delta": str(unexplained)})
    return {"assets": rows, "assets_compared": len(rows), "asset_coverage_gaps": missing,
        "unexplained_net_delta_assets": differences, "reference_to_session_locked_changes": locks,
        "observed_endpoint_deltas_explained": not missing and not differences,
        "cash_flow_history_complete": False, "reset_history_verified": False,
        "external_net_cash_flow_usdt": None,
        "method": "historical_end_minus_reference_minus_native_session_delta",
        "limitation": "offsetting_external_flows_or_resets_between_observations_not_excluded"}


def _gaps(admission, session, state):
    anchor = admission["observation_anchor"]
    value = admission["valuation"]
    started = anchor["start_ns"]
    if not started < state["started_ns"] <= session["observation_received_ns"]:
        raise StreamError("reference must precede the complete selected session")
    source = state["source"]
    binding_sha = hashlib.sha256(canonical({"endpoint": source["endpoint"],
        "uid": source["account_uid"], "key_sha256": source["key_sha256"]})).hexdigest()
    if binding_sha != admission["inputs"]["source_binding_sha256"]:
        raise StreamError("reference and session must use the selected original source")
    bridge = _balance_bridge(anchor["balances"], state["baseline"], session["historical_view"]["expected_totals"])
    return {
        "schema_version": "portfolio.testnet_baseline_gap_review.v1",
        "status": "historical_review_complete_baseline_blocked",
        "risk_policy_id": POLICY_ID,
        "evidence_basis": "selected_historical_account_market_and_native_session_archives",
        "reviewed_ns": session["reviewed_ns"],
        "inputs": {"admission": admission["inputs"], "session": {k: session[k] for k in
            ("archive_sha256", "checkpoint_sha256", "collection_id", "evidence_sha256")}},
        "valuation": {k: value[k] for k in ("assets_recorded", "priced_assets", "unpriced_assets",
            "depth_exceeded_assets", "all_assets_priced", "full_indicative_mark_usdt",
            "individual_quote_age_verified", "valuation_qualified", "liquidation_value_verified")},
        "valuation_applies_to": "original_reference_capture_only_not_later_session_or_review_time",
        "reference_native_mapping_equal": admission["checks"]["full_native_amount_mapping"],
        "utc_evidence": {"reference_ns": started, "reference_utc_day_start_ns": started // DAY_NS * DAY_NS,
            "reference_offset_from_midnight_ns": started % DAY_NS,
            "session_started_ns": state["started_ns"],
            "session_observation_ns": session["observation_received_ns"],
            "reference_to_session_observation_ns": session["observation_received_ns"] - started,
            "crosses_utc_day": started // DAY_NS != session["observation_received_ns"] // DAY_NS,
            "qualified_midnight_baseline_present": False},
        "balance_bridge": bridge,
        "historical_session": {"fills": len(session["historical_view"]["fills"]),
            "open_orders": len(session["historical_view"]["open_order_ids"]),
            "owned_btc": session["historical_view"]["owned_btc"],
            "dispatches_recorded": session["historical_dispatches_recorded"],
            "halt_reasons": session["historical_halt_reasons"]},
        "risk_inputs": {"qualified_current_equity_usdt": None, "qualified_day_open_equity_usdt": None,
            "daily_loss_usdt": None, "effective_daily_limit_usdt": None,
            "qualified_peak_equity_usdt": None, "peak_loss_usdt": None,
            "policy_daily_cap_usdt": str(DAILY_CAP_USDT), "policy_daily_fraction": str(DAILY_FRACTION),
            "policy_fixed_peak_loss_ceiling_usdt": str(PEAK_LOSS_USDT)},
        "blocking_reasons": (["unpriced_nonzero_assets"] if value["unpriced_assets"] else [])
            + (["per_asset_top_book_capacity_exceeded"] if value["depth_exceeded_assets"] else [])
            + (["full_native_reference_mapping_unqualified"] if not admission["checks"]["full_native_amount_mapping"] else [])
            + (["reference_open_orders_present"] if not admission["checks"]["account_wide_open_orders_empty"] else [])
            + (["historical_session_open_orders_present"] if session["historical_view"]["open_order_ids"] else [])
            + (["asset_coverage_changed"] if bridge["asset_coverage_gaps"] else [])
            + (["unexplained_endpoint_balance_delta"] if bridge["unexplained_net_delta_assets"] else [])
            + (["reference_to_session_locks_changed"] if bridge["reference_to_session_locked_changes"] else [])
            + ["quote_event_freshness_and_account_market_atomicity_unqualified",
               "independent_utc_day_open_and_peak_history_missing",
               "complete_external_cash_flow_and_reset_history_missing",
               "independent_identity_and_key_restrictions_unqualified"],
        "baseline_qualified": False, "current_venue_state_verified": False,
        "source_authenticated": False, "new_orders_authorized": False, "runtime_ready": False,
        "venue_requests_made": 0, "fixed_checkpoint_written": False,
    }


def review_baseline(raws, hashes, *, account_collection, session_collection, reviewed_ns, loop):
    """Use a fresh process for native mapping/recovery; raw archives are revalidated."""
    if set(raws) != set(INPUTS) or set(hashes) != set(INPUTS):
        raise StreamError("all selected original inputs required")
    for name, limit in INPUTS.items():
        if not isinstance(raws[name], bytes) or not 0 < len(raws[name]) <= limit * 1024 * 1024:
            raise StreamError("bounded original inputs required")
    admission = review_admission(raws["account_archive"], raws["market"], raws["initial"],
        archive_sha256=hashes["account_archive"], collection_id=account_collection,
        market_sha256=hashes["market"], selection_sha256=hashes["initial"])
    session = review_archive(raws["session_archive"], raws["checkpoint"],
        archive_sha256=hashes["session_archive"], checkpoint_sha256=hashes["checkpoint"],
        collection_id=session_collection, reviewed_ns=reviewed_ns, loop=loop)
    return _gaps(admission, session, read_session(raws["checkpoint"])["state"])


def main(argv=None):
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    for name in INPUTS:
        option = name.replace("_", "-")
        parser.add_argument(f"--{option}", type=Path, required=True)
        parser.add_argument(f"--{option}-sha256", required=True)
    parser.add_argument("--account-collection", required=True)
    parser.add_argument("--session-collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    loop = asyncio.new_event_loop()
    try:
        raws = {name: private_read(getattr(args, name), limit=limit * 1024 * 1024) for name, limit in INPUTS.items()}
        hashes = {name: getattr(args, name + "_sha256") for name in INPUTS}
        report = review_baseline(raws, hashes, account_collection=args.account_collection,
            session_collection=args.session_collection, reviewed_ns=time.time_ns(), loop=loop)
        raw = canonical(report) + b"\n"
        write_private_new(args.output, raw)
    except Exception:
        print(json.dumps({"status": "baseline_gap_review_failed", "baseline_qualified": False, "runtime_ready": False}))
        return 1
    finally:
        loop.close()
    print(json.dumps({"status": report["status"], "report_sha256": hashlib.sha256(raw).hexdigest(),
        "assets_compared": report["balance_bridge"]["assets_compared"],
        "unpriced_assets": len(report["valuation"]["unpriced_assets"]),
        "unexplained_net_delta_assets": len(report["balance_bridge"]["unexplained_net_delta_assets"]),
        "asset_coverage_gaps": len(report["balance_bridge"]["asset_coverage_gaps"]),
        "baseline_qualified": False, "current_venue_state_verified": False, "runtime_ready": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

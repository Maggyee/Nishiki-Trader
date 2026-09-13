"""Historical route coverage and prospective observation budgets, never admission."""

from __future__ import annotations

from apps.strategies_nautilus.portfolio_market_depth_archive import flags
from apps.strategies_nautilus.portfolio_testnet_observation import REQUESTS as ACCOUNT_READS
from apps.strategies_nautilus.portfolio_testnet_valuation import PIVOTS

PILOT_ASSETS = PIVOTS[:3]
MAX_PILOT_STREAMS = 3
DEPTH_WEIGHTS = {100: 5, 500: 25, 1000: 50, 5000: 250}


def request_budget(symbols, *, levels=100):
    """Future sequential requests; signed selectors omit credentials/signatures."""
    if type(levels) is not int or levels not in DEPTH_WEIGHTS:
        raise ValueError("unsupported planned depth size")
    rows = [
        {
            "phase": "clock_initial",
            "method": "GET",
            "path": "/api/v3/time",
            "params": {},
            "weight": 1,
        }
    ]
    for phase in ("account_before", "account_after"):
        if phase == "account_after":
            rows.extend(
                [
                    {
                        "phase": "route_discovery",
                        "method": "GET",
                        "path": "/api/v3/exchangeInfo",
                        "params": {},
                        "weight": 20,
                    },
                    {
                        "phase": "route_discovery",
                        "method": "GET",
                        "path": "/api/v3/ticker/bookTicker",
                        "params": {},
                        "weight": 4,
                    },
                    *[
                        {
                            "phase": "market_bootstrap",
                            "method": "GET",
                            "path": "/api/v3/depth",
                            "params": {"symbol": s, "limit": str(levels)},
                            "weight": DEPTH_WEIGHTS[levels],
                        }
                        for s in sorted(symbols)
                    ],
                    {
                        "phase": "clock_linked",
                        "method": "GET",
                        "path": "/api/v3/time",
                        "params": {},
                        "weight": 1,
                    },
                ]
            )
        rows.extend(
            {
                "phase": phase,
                "method": "GET",
                "path": path,
                "params": dict(params),
                "weight": 20 if path.endswith("/account") else 80,
            }
            for path, params in ACCOUNT_READS
        )
    rows.append(
        {"phase": "clock_final", "method": "GET", "path": "/api/v3/time", "params": {}, "weight": 1}
    )
    ws = [
        {"operation": op, "weight": 2}
        for op in (
            "ws_api_connection",
            "userDataStream.subscribe.signature",
            "userDataStream.unsubscribe",
        )
    ]
    return {
        "rest_requests": rows,
        "rest_get_count": len(rows),
        "private_get_count": 2 * len(ACCOUNT_READS),
        "rest_weight": sum(r["weight"] for r in rows),
        "ws_api_operations": ws,
        "ws_api_weight": 6,
        "total_documented_weight": sum(r["weight"] for r in rows) + 6,
        "market_connections": 1,
        "market_streams": len(symbols),
        "account_ws_api_connections": 1,
        "http_retries": 0,
        "snapshot_retries": 0,
        "reconnects": 0,
        "current_shared_ip_budget_verified": False,
    }


def observation_plan(admission, depth):
    """Inputs come from original-byte replay in the separate ops entrypoint."""
    value = admission["valuation"]
    rows = value["assets"]
    all_symbols = sorted({leg["symbol"] for row in rows for leg in row["path"]})
    assets = {row["asset"]: row for row in rows}
    missing_targets = [a for a in PILOT_ASSETS if a not in assets or not assets[a]["path"]]
    pilot_symbols = sorted(
        {leg["symbol"] for a in PILOT_ASSETS if a in assets for leg in assets[a]["path"]}
    )
    bad_sides = sorted(
        {
            r["symbol"]
            for r in value["unavailable_books"]
            if r["reason"]
            in ("empty_bid", "empty_ask", "crossed_book", "not_spot_trading", "missing_book")
        }
    )
    coverage = []
    for row in rows:
        required = sorted({leg["symbol"] for leg in row["path"]})
        missing = sorted(set(required) - set(pilot_symbols))
        if row["mark_usdt"] is None:
            status = "unpriced_nonzero_asset"
        elif not required:
            status = "no_market_leg_required"
        elif missing:
            status = "outside_pilot_route_set"
        else:
            status = "pilot_route_symbols_present"
        coverage.append(
            {
                "asset": row["asset"],
                "required_symbols": required,
                "missing_pilot_symbols": missing,
                "status": status,
                "historical_top_book_capacity_exceeded": row["asset"]
                in value["depth_exceeded_assets"],
                "native_two_sided_quote_unavailable_symbols": sorted(
                    set(required) & set(bad_sides)
                ),
            }
        )
    budget = request_budget(pilot_symbols)
    limit = depth["summary"]["observed_weight_limit_1m"]
    scenarios = []
    for levels, weight in DEPTH_WEIGHTS.items():
        total = (
            request_budget([], levels=levels)["total_documented_weight"] + len(all_symbols) * weight
        )
        scenarios.append(
            {
                "levels_per_side": levels,
                "route_symbols": len(all_symbols),
                "depth_weight": len(all_symbols) * weight,
                "total_documented_weight": total,
                "within_one_recorded_minute_limit": total <= limit,
            }
        )
    return {
        "schema_version": "portfolio.testnet_observation_plan.v1",
        "status": "historical_planning_complete_not_collection_admission",
        "evidence_basis": "replayed_historical_account_market_and_independent_v2_depth",
        "reference_ns": admission["observation_anchor"]["start_ns"],
        "route_policy": value["method"],
        "assets_recorded": len(rows),
        "historical_priced_assets": value["priced_assets"],
        "unpriced_assets": value["unpriced_assets"],
        "historical_depth_exceeded_assets": value["depth_exceeded_assets"],
        "all_required_symbols": all_symbols,
        "asset_coverage": coverage,
        "pilot": {
            "target_assets": list(PILOT_ASSETS),
            "symbols": pilot_symbols,
            "selection_rule": "first_three_fixed_ADR016_pivots_with_their_existing_deterministic_routes",
            "missing_or_unpriced_targets": missing_targets,
            "max_streams": MAX_PILOT_STREAMS,
            "route_count_within_cap": len(pilot_symbols) <= MAX_PILOT_STREAMS,
            "native_quote_side_blockers": sorted(set(pilot_symbols) & set(bad_sides)),
            "all_assets_covered": not any(
                r["status"] in ("unpriced_nonzero_asset", "outside_pilot_route_set")
                for r in coverage
            ),
            "collector_implemented": False,
            "budget": budget,
        },
        "full_route_budget_scenarios": scenarios,
        "historical_weight_limit_1m": limit,
        "resource_envelope": {
            "max_duration_seconds": 120,
            "shutdown_seconds": 5,
            "market_bootstrap_seconds": 15,
            "per_request_seconds": 10,
            "observe_after_link_seconds": 20,
            "max_streams": 3,
            "max_frame_bytes": 1048576,
            "aggregate_pending_bytes": 16777216,
            "aggregate_pending_events": 4096,
            "combined_archive_bytes": 67108864,
            "max_event_age_ns": 5000000000,
            "bounds_measure": "serialized_bytes_not_process_RSS",
            "multi_symbol_throughput_verified": False,
            "overflow_action": "abort_without_dropping_or_rebasing",
        },
        "interval_semantics": {
            "account_before_after": "two_complete_existing_four_GET_observations_on_one_signed_epoch",
            "market_references": "one_independent_epoch_and_U_u_E_receipt_vector_per_symbol",
            "common_revision": None,
            "account_u_is_market_update_id": False,
            "equal_endpoints_prove_complete_flow_or_reset_history": False,
            "qualified_equity_usdt": None,
            "qualified_day_open_usdt": None,
        },
        "blocking_reasons": [
            "fresh_selected_account_metadata_and_books_required",
            "live_shared_ip_budget_and_connection_usage_unknown",
            "multi_symbol_journal_and_demultiplexer_not_implemented",
            "native_throughput_backpressure_and_fault_acceptance_required",
            "joint_account_market_interval_archive_not_implemented",
            "full_equity_UTC_flow_reset_and_atomicity_unqualified",
        ],
        "venue_requests_made": 0,
        "credentials_loaded": False,
        "new_probe_authorized": False,
        **flags(),
    }

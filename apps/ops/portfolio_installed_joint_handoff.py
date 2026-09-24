"""Offline original-byte handoff audit for the installed snapshot fixture.

This compares verified fixture selectors with the full joint collector's fixed
operation schedule. Matching selectors are not ordered joint observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

# The installed replayer's source loader obtains these protected project modules
# from sys.modules. Import them before running its read-only replay.
from apps.strategies_nautilus import portfolio_rate_evidence as _rates  # noqa: F401
from apps.strategies_nautilus import portfolio_tls_provenance as _provenance  # noqa: F401
from apps.strategies_nautilus.portfolio_observation_plan import request_budget

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "infra/egress-guard"
PROFILE = "portfolio.installed_joint_handoff_review.v1"
MAX_REPORT = 8 * 1024 * 1024
STEPS = ("metadata", "account_first", "orders_first", "orders_second", "account_second", "books")
SELECTORS = (
    "exchange_info",
    "account_read",
    "open_orders",
    "open_orders",
    "account_read",
    "book_ticker",
)
REST_PATHS = {
    "/api/v3/time": "time",
    "/api/v3/exchangeInfo": "exchange_info",
    "/api/v3/ticker/bookTicker": "book_ticker",
    "/api/v3/account": "account_read",
    "/api/v3/openOrders": "open_orders",
    "/api/v3/depth": "depth_100",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("handoff_duplicate_json_key")
            value[key] = item
        return value

    return json.loads(raw, object_pairs_hook=pairs)


def selected_sources(report):
    """Bind offline replay to exactly the checked-in installed fixture inventory."""
    path = GATEWAY / "installed_gateway.py"
    namespace = {"__name__": "installed_handoff_sources"}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    files = namespace["FILES"]
    manifest = report["gateway_manifest"]
    if (
        manifest["schema_version"] != namespace["PROFILE"]
        or set(manifest["files"]) != set(files)
        or report["source_sha256"] != manifest["files"]
    ):
        raise ValueError("handoff_protected_inventory")
    sources = {}
    for name in files:
        source = (
            ROOT / "apps/strategies_nautilus" / name
            if name.startswith("portfolio_")
            else GATEWAY / name
        ).read_bytes()
        if digest(source) != manifest["files"][name]:
            raise ValueError("handoff_source_changed")
        sources[name] = source
    return namespace, sources


def operation_gap(symbols):
    planned = request_budget(symbols)
    try:
        expected_rest = Counter(REST_PATHS[row["path"]] for row in planned["rest_requests"])
    except KeyError as exc:
        raise ValueError("handoff_joint_budget_changed") from exc
    installed_rest = Counter(SELECTORS) + Counter({"depth_100": len(symbols)})
    joint_ws = [row["operation"] for row in planned["ws_api_operations"]]
    if (
        sum(expected_rest.values()) != planned["rest_get_count"]
        or any(row["method"] != "GET" for row in planned["rest_requests"])
        or sorted(
            row["params"]["symbol"]
            for row in planned["rest_requests"]
            if row["path"] == "/api/v3/depth" and row["params"].get("limit") == "100"
        )
        != sorted(symbols)
        or sum(row["path"] == "/api/v3/depth" for row in planned["rest_requests"]) != len(symbols)
        or joint_ws
        != [
            "ws_api_connection",
            "userDataStream.subscribe.signature",
            "userDataStream.unsubscribe",
        ]
        or planned["market_connections"] != 1
        or installed_rest - expected_rest
    ):
        raise ValueError("handoff_joint_budget_changed")
    return planned, installed_rest, expected_rest, joint_ws


def review(raw, *, expected_sha256, scenario="snapshot_success"):
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= MAX_REPORT
        or digest(raw) != expected_sha256
        or scenario not in {"snapshot_success", "snapshot_two_hops"}
    ):
        raise ValueError("handoff_selected_complete_report_required")
    value = unique_json(raw)
    if (
        value.get("schema_version") != "portfolio.installed_gateway_acceptance.v1"
        or value.get("status") != "passed"
        or value.get("snapshot_ws_profile") is not True
        or value.get("venue_requests") != 0
        or value.get("network_admitted") is not False
        or value.get("trading_admitted") is not False
    ):
        raise ValueError("handoff_fixture_report_required")
    entry = next((s for s in value["scenarios"] if s.get("scenario") == scenario), None)
    if entry is None or entry["status"] != "passed":
        raise ValueError("handoff_selected_scenario_required")
    loader, sources = selected_sources({**entry, "source_sha256": value["source_sha256"]})

    def load(name):
        return loader["load"](sources[name])

    sequence, concurrent = load("gateway_read_sequence.py"), load("gateway_concurrent_ws.py")
    account, market, snapshot = (
        load("gateway_account_ws.py"),
        load("gateway_market_ws.py"),
        load("gateway_snapshot_ws.py"),
    )
    requests = load("gateway_native_requests.py")
    modules = sequence["load_sources"]({k: v.decode() for k, v in sources.items()})
    sequence_raw = entry["sequence_archive"].encode()
    bundles = entry["bundles"]
    sequence_report = sequence["replay"](
        sequence_raw,
        expected_sha256=digest(sequence_raw),
        bundles=bundles,
        modules=modules,
        orders=True,
        routes=True,
    )
    if (
        sequence_report != entry["sequence_replay"]
        or sequence_report["status"] != "complete"
        or sequence_report["prepared_steps"] != len(STEPS)
        or sequence_report["accepted_steps"] != len(STEPS)
    ):
        raise ValueError("handoff_sequence_not_complete")
    chosen = concurrent["selection"](sequence_raw, bundles, sequence, modules)
    chosen = account["selection"](chosen, bundles)
    chosen = market["selection"](chosen, bundles)
    if chosen != entry["ws_selection"]:
        raise ValueError("handoff_original_route_selection_changed")
    frames = loader["load"](sources["portfolio_ws_frames.py"])
    state_type = snapshot["state_type"](concurrent, account, requests, market)
    ws_raw = entry["ws_archive"].encode()
    ws_report = concurrent["replay"](
        ws_raw,
        expected_sha256=digest(ws_raw),
        selected=chosen,
        provenance=modules["provenance"],
        frames=frames,
        state_type=state_type,
    )
    native = ws_report["native_result"]
    symbols = chosen["symbols"]
    if (
        ws_report != entry["ws_replay"]
        or ws_report["status"] != "complete"
        or not ws_report["revocation_recorded"]
        or not ws_report["sockets_closed_recorded"]
        or ws_report["snapshot_attempts_consumed"] != len(symbols)
        or ws_report["snapshots_accepted"] != len(symbols)
        or ws_report["prepared_connections"] != 2
        or not ws_report["fixture_subscription_acknowledged"]
        or not ws_report["market_native_acknowledged"]
        or ws_report["market_events_recorded"] != 2 * len(symbols)
        or ws_report["account_subscription_authenticated"] is not False
        or ws_report["real_account_authenticated"] is not False
        or native["snapshot_linked"] is not True
        or native["account"]["partial_update"] is not True
        or native["stream_fence_verified"] is not False
        or native["quote_ticks_created"] is not False
        or native["qualified_for_execution"] is not False
    ):
        raise ValueError("handoff_native_snapshot_not_acknowledged")

    planned, installed_rest, expected_rest, joint_ws = operation_gap(symbols)
    return {
        "schema_version": PROFILE,
        "status": "blocked_incomplete_joint_collector",
        "selected_report_sha256": expected_sha256,
        "sequence_archive_sha256": digest(sequence_raw),
        "snapshot_ws_archive_sha256": digest(ws_raw),
        "symbols": symbols,
        "installed_selector_order": list(SELECTORS) + ["depth_100:" + symbol for symbol in symbols],
        "installed_rest_selector_counts": dict(sorted(installed_rest.items())),
        "joint_rest_selector_counts": dict(sorted(expected_rest.items())),
        "missing_rest_selector_counts": dict(sorted((expected_rest - installed_rest).items())),
        "installed_account_ws_operations": ["account_connect", "account_subscribe"],
        "missing_account_ws_operations": ["account_unsubscribe"],
        "fixture_subscription_acknowledged": True,
        "real_account_authenticated": False,
        "installed_market_connections": 1,
        "installed_rest_get_count": sum(installed_rest.values()),
        "joint_rest_get_count": planned["rest_get_count"],
        "ordered_joint_operations_accepted": 0,
        "joint_operation_count": planned["rest_get_count"]
        + len(joint_ws)
        + planned["market_connections"],
        "complete_account_intervals": 0,
        "snapshot_revision_linked": True,
        "quote_ticks_created": False,
        "real_source_authority_qualified": False,
        "fresh_provider_usage_qualified": False,
        "installed_gateway_joint_collector_integrated": False,
        "network_admitted": False,
        "trading_admitted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument(
        "--scenario", choices=("snapshot_success", "snapshot_two_hops"), default="snapshot_success"
    )
    args = parser.parse_args(argv)
    print(
        json.dumps(
            review(
                args.report.read_bytes(), expected_sha256=args.report_sha256, scenario=args.scenario
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

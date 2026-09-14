"""Offline first-dispatch capacity review; untrusted claims never grant admission.

Original REST/WS rate fields are parsed again, not accepted as normalized reports.
No socket, credential loader, activation writer or trusted gateway adapter exists
here. Coverage/usage bounds are candidate inputs whose authenticity is unresolved.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
from pathlib import Path

from apps.strategies_nautilus.portfolio_rate_evidence import (
    RateEvidenceError,
    _body,
    _integer,
    rest_rate_evidence,
    ws_rate_evidence,
)

SECOND = 1_000_000_000
MAX_INPUT = 16 * 1024 * 1024
CONTRACT_SHA256 = "91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48"
CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "docs/progress/portfolio-testnet-joint-capture-contract-2026-09-14.json"
)
SCHEMA = "portfolio.joint_admission_candidate.v1"
ENDPOINTS = {
    "rest": "https://testnet.binance.vision",
    "account": "wss://ws-api.testnet.binance.vision/ws-api/v3",
    "market": "wss://stream.testnet.binance.vision/stream",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise RateEvidenceError("candidate_fields_required_no_authentication_overrides")


def bounded_list(value, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise RateEvidenceError("candidate_list_bound")
    return value


def interval(value):
    if not isinstance(value, list) or len(value) != 2:
        raise RateEvidenceError("server_time_interval_required")
    low, high = (_integer(n, positive=True) for n in value)
    if high < low or high - low > SECOND:
        raise RateEvidenceError("server_time_uncertainty_invalid")
    return low, high


def binding(value, role):
    exact(value, "endpoint destination_ip egress_ip address_family")
    destination = ipaddress.ip_address(value["destination_ip"])
    egress = ipaddress.ip_address(value["egress_ip"])
    if (
        value["endpoint"] != ENDPOINTS[role]
        or type(value["address_family"]) is not int
        or value["address_family"] != destination.version
        or destination.version != egress.version
        or str(destination) != value["destination_ip"]
        or str(egress) != value["egress_ip"]
    ):
        raise RateEvidenceError("candidate_endpoint_or_address_family_changed")
    return value


def contract():
    raw = CONTRACT.read_bytes()
    if sha(raw) != CONTRACT_SHA256:
        raise RateEvidenceError("selected_capture_contract_changed")
    return _body(raw)


def _sample(row, role, at_ns, monotonic_ns):
    exact(
        row,
        "binding received_ns monotonic_ns server_time_ns raw_b64 body_sha256 "
        + ("headers" if role == "rest" else "request_id"),
    )
    binding(row["binding"], role)
    received = _integer(row["received_ns"], positive=True)
    mono = _integer(row["monotonic_ns"], positive=True)
    wall_age, mono_age = at_ns - received, monotonic_ns - mono
    if min(wall_age, mono_age) < 0 or abs(wall_age - mono_age) > 50_000_000:
        raise RateEvidenceError("candidate_clock_discontinuity")
    low, high = interval(row["server_time_ns"])
    raw = base64.b64decode(row["raw_b64"], validate=True)
    if sha(raw) != row["body_sha256"]:
        raise RateEvidenceError("selected_rate_body_changed")
    parsed = (
        rest_rate_evidence(raw, row["headers"])
        if role == "rest"
        else ws_rate_evidence(raw, request_id=row["request_id"])
    )
    return parsed, (low, high), (low + wall_age, high + wall_age), max(wall_age, mono_age)


def _ledger(value, at_low, at_high):
    exact(
        value,
        "bindings covered_from_ns covered_through_ns future_through_ns all_callers usage_bounds connection_attempts",
    )
    exact(value["bindings"], "rest account market")
    for role in ENDPOINTS:
        binding(value["bindings"][role], role)
    start = _integer(value["covered_from_ns"], positive=True)
    end = _integer(value["covered_through_ns"], positive=True)
    future = _integer(value["future_through_ns"], positive=True)
    if not start <= end <= future or end > at_high or type(value["all_callers"]) is not bool:
        raise RateEvidenceError("candidate_coverage_interval_invalid")
    complete = value["all_callers"] and end >= at_high
    bounds = {}
    for row in bounded_list(value["usage_bounds"], 128):
        exact(
            row, "role rate_limit_type interval_seconds used_upper_bound other_clients_upper_bound"
        )
        key = row["role"], row["rate_limit_type"], _integer(row["interval_seconds"], positive=True)
        if (
            key[0] not in ENDPOINTS
            or key[1] not in {"REQUEST_WEIGHT", "RAW_REQUESTS", "CONNECTIONS"}
            or key in bounds
        ):
            raise RateEvidenceError("candidate_duplicate_or_foreign_usage_bound")
        bounds[key] = (
            _integer(row["used_upper_bound"]),
            _integer(row["other_clients_upper_bound"]),
        )
    attempts, ids = {role: 0 for role in ("account", "market")}, set()
    for row in bounded_list(value["connection_attempts"], 4096):
        exact(row, "id role server_time_ns outcome")
        low, high = interval(row["server_time_ns"])
        if (
            not isinstance(row["id"], str)
            or not 0 < len(row["id"]) <= 128
            or row["id"] in ids
            or row["role"] not in attempts
            or row["outcome"] not in {"succeeded", "failed", "uncertain"}
            or low < start
            or high > end
            or high > at_high
        ):
            raise RateEvidenceError("candidate_attempt_identity_or_coverage")
        ids.add(row["id"])
        # An uncertain edge overlapping any possible preceding window is counted.
        if high >= at_low - 300 * SECOND:
            attempts[row["role"]] += 1
    return start, complete, future >= at_high + 125 * SECOND, bounds, attempts


def review(raw=None, *, expected_sha256=None, at_ns, monotonic_ns):
    """Review the full maximum scope before its first request, without dispatch.

    used_upper_bound claims cover the entire relevant fixed bucket through the
    review instant, including failed/uncertain requests and all other callers.
    Their evidence and enforcement are NOT authenticated by this calculation.
    """
    _integer(at_ns, positive=True)
    _integer(monotonic_ns, positive=True)
    draft = contract()
    budget = draft["maximum_three_symbol_budget"]
    blockers = [
        "authenticated_initial_source_adapter_unavailable",
        "authenticated_complete_egress_adapter_unavailable",
        "market_connection_charge_unresolved",
        "real_capture_profile_and_durable_activation_unimplemented",
    ]
    result = {
        "schema_version": "portfolio.joint_admission_review.v1",
        "status": "blocked_before_first_request",
        "contract_sha256": CONTRACT_SHA256,
        "candidate_sha256": None,
        "reviewed_at_ns": at_ns,
        "reviewed_monotonic_ns": monotonic_ns,
        "maximum_scope": {
            k: budget[k]
            for k in ("rest_get_count", "rest_weight", "ws_api_weight", "total_documented_weight")
        },
        "interval_reviews": [],
        "rate_sources": {},
        "connection_review": None,
        "blockers": blockers,
        "source_authenticated": False,
        "shared_egress_verified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
        "qualification": draft["qualification"],
        **{
            k: v
            for k, v in draft.items()
            if k.startswith("qualified_") or k == "common_account_market_revision"
        },
    }
    if raw is None:
        if expected_sha256 is not None:
            raise RateEvidenceError("candidate_bytes_required_with_hash")
        blockers.extend(["preexisting_rate_samples_missing", "complete_egress_candidate_missing"])
        return result
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_INPUT or sha(raw) != expected_sha256:
        raise RateEvidenceError("selected_admission_candidate_changed")
    candidate = _body(raw)
    exact(candidate, "schema_version contract_sha256 samples ledger")
    if candidate["schema_version"] != SCHEMA or candidate["contract_sha256"] != CONTRACT_SHA256:
        raise RateEvidenceError("candidate_profile_or_contract_changed")
    exact(candidate["samples"], "rest account")
    histories = {}
    for role, rows in candidate["samples"].items():
        bounded_list(rows, 16)
        if not rows:
            blockers.append(role + "_preexisting_rate_samples_missing")
            continue
        histories[role] = [_sample(row, role, at_ns, monotonic_ns) for row in rows]
        result["rate_sources"][role] = [
            {
                "body_sha256": parsed["body_sha256"],
                "header_pairs_sha256": parsed.get("header_pairs_sha256"),
                "request_id": parsed.get("request_id"),
                "received_server_time_ns": list(received),
                "review_server_time_ns": list(current),
                "age_ns": age,
            }
            for parsed, received, current, age in histories[role]
        ]
        for index, current in enumerate(histories[role]):
            if index == 0:
                continue
            previous = histories[role][index - 1]
            if (
                rows[index]["binding"] != rows[index - 1]["binding"]
                or rows[index]["received_ns"] <= rows[index - 1]["received_ns"]
                or rows[index]["monotonic_ns"] <= rows[index - 1]["monotonic_ns"]
                or current[1][0] < previous[1][0]
            ):
                raise RateEvidenceError("candidate_history_source_or_time_changed")
            old_rates = {
                (r["rate_limit_type"], r["interval_seconds"]): r for r in previous[0]["rates"]
            }
            new_rates = {
                (r["rate_limit_type"], r["interval_seconds"]): r for r in current[0]["rates"]
            }
            if old_rates.keys() != new_rates.keys():
                raise RateEvidenceError("candidate_advertised_intervals_changed")
            for key, row in new_rates.items():
                old = old_rates[key]
                width = key[1] * SECOND
                if (
                    row["limit"] != old["limit"]
                    or previous[1][0] // width != current[1][1] // width
                ):
                    raise RateEvidenceError("candidate_limit_or_bucket_changed_no_reset_inference")
                if old["count"] is not None and (
                    row["count"] is None or row["count"] < old["count"]
                ):
                    raise RateEvidenceError("candidate_counter_regressed")
    result["candidate_sha256"] = sha(raw)
    if not histories:
        blockers.append("complete_egress_review_requires_server_clock")
        return result
    at_low = min(h[-1][2][0] for h in histories.values())
    at_high = max(h[-1][2][1] for h in histories.values())
    if at_high - at_low > SECOND:
        raise RateEvidenceError("candidate_endpoint_clock_intervals_disagree")
    ledger = candidate["ledger"]
    if ledger is None:
        blockers.append("complete_egress_candidate_missing")
        return result
    start, complete, future, bounds, attempts = _ledger(ledger, at_low, at_high)
    if not complete:
        blockers.append("egress_coverage_gap_or_other_callers_missing")
    if not future:
        blockers.append("other_client_reservation_horizon_incomplete")
    # Union reservations are conservative arithmetic, not a provider scope claim.
    egress = {(v["egress_ip"], v["address_family"]) for v in ledger["bindings"].values()}
    if len(egress) != 1:
        blockers.append("cross_endpoint_egress_binding_missing")
    seen_bounds = set()
    for role, history in histories.items():
        parsed, received_server, current_server, age = history[-1]
        if ledger["bindings"][role] != candidate["samples"][role][-1]["binding"]:
            raise RateEvidenceError("candidate_ledger_destination_or_egress_drift")
        if age > 5 * SECOND:
            blockers.append(role + "_rate_sample_stale")
        for rate in parsed["rates"]:
            kind, seconds = rate["rate_limit_type"], rate["interval_seconds"]
            key = role, kind, seconds
            width = seconds * SECOND
            bucket = received_server[0] // width
            reasons = []
            if kind != "CONNECTIONS" and (
                received_server[1] // width != bucket
                or current_server[0] // width != bucket
                or current_server[1] // width != bucket
            ):
                reasons.append("clock_uncertainty_crosses_bucket")
            bound = bounds.get(key)
            if bound is not None:
                seen_bounds.add(key)
            if kind == "ORDERS":
                reasons.append("account_order_scope_not_covered_by_ip_ledger")
            elif bound is None:
                reasons.append("usage_and_other_client_upper_bound_missing")
            elif not complete or start > (
                at_low - width if kind == "CONNECTIONS" else bucket * width
            ):
                reasons.append("full_interval_egress_coverage_missing")
            used, other = bound if bound is not None else (None, None)
            if rate["count"] is not None and used is not None and used < rate["count"]:
                reasons.append("ledger_upper_bound_below_server_count")
            remaining = (
                budget["total_documented_weight"]
                if kind == "REQUEST_WEIGHT"
                else budget["rest_get_count"]
                if kind == "RAW_REQUESTS" and role == "rest"
                else 2
                if kind == "CONNECTIONS"
                else None
            )
            if remaining is None:
                reasons.append("applicable_operation_cost_or_scope_unresolved")
            headroom = (
                rate["limit"] - used - other - remaining
                if used is not None and remaining is not None
                else None
            )
            if headroom is not None and headroom < 0:
                reasons.append("remaining_scope_or_other_clients_exceed_limit")
            result["interval_reviews"].append(
                {
                    "role": role,
                    **rate,
                    "used_upper_bound": used,
                    "other_clients_upper_bound": other,
                    "remaining_scope_reservation": remaining,
                    "headroom_after_documented_reservation": headroom,
                    "reasons": reasons,
                }
            )
            blockers.extend(f"{role}:{kind}:{seconds}:{reason}" for reason in reasons)
    # The documented market connection limit has no current usage response.
    others = {}
    for role in attempts:
        key = role, "CONNECTIONS", 300
        bound = bounds.get(key)
        seen_bounds.add(key)
        others[role] = bound[1] if bound is not None else None
        if bound is None or bound[0] < attempts[role]:
            blockers.append(role + "_connection_upper_bound_missing_or_below_attempts")
    if set(bounds) - seen_bounds:
        raise RateEvidenceError("candidate_unadvertised_usage_bounds")
    rolling_complete = complete and start <= at_low - 300 * SECOND
    if not rolling_complete:
        blockers.append("complete_rolling_connection_history_missing")
    used_union = (
        sum(max(attempts[role], bounds[(role, "CONNECTIONS", 300)][0]) for role in attempts)
        if all((role, "CONNECTIONS", 300) in bounds for role in attempts)
        else None
    )
    other_union = sum(others.values()) if all(n is not None for n in others.values()) else None
    headroom = (
        300 - used_union - other_union - 2
        if used_union is not None and other_union is not None
        else None
    )
    if headroom is not None and headroom < 0:
        blockers.append("conservative_connection_union_exceeds_documented_limit")
    result["connection_review"] = {
        "attempts_by_endpoint": attempts,
        "used_upper_bound_union": used_union,
        "other_clients_upper_bound_union": other_union,
        "remaining_connections": 2,
        "documented_limit": 300,
        "limit_basis": "pinned_documentation_not_current_authenticated_sample",
        "headroom": headroom,
        "claimed_rolling_coverage_complete": rolling_complete,
        "provider_shared_counter_inferred": False,
    }
    result["interval_reviews"].sort(
        key=lambda r: (r["role"], r["rate_limit_type"], r["interval_seconds"])
    )
    result["blockers"] = sorted(set(blockers))
    return result

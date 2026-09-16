"""Review joint first-request blockers offline; never capture or activate a scope."""

from __future__ import annotations

import argparse
import ipaddress
import json
import time
from pathlib import Path

from apps.ops.portfolio_rest_bootstrap_review import review as replay_bootstrap
from apps.strategies_nautilus.portfolio_joint_admission import MAX_INPUT, contract, review, sha
from apps.strategies_nautilus.portfolio_rate_evidence import _body, _integer
from apps.strategies_nautilus.portfolio_session_transport import private_read, write_private_new
from apps.strategies_nautilus.portfolio_stream import canonical


def review_bootstrap(plan_raw, events_raw, response_raw, *, at_ns, monotonic_ns, boot_id):
    """Join historical bootstrap originals to the frozen gate, without inventing a ledger.

    A retained receipt is not an authenticated dispatch sample. In particular,
    completing a slow body download must not refresh the earlier header counter.
    """
    replay = replay_bootstrap(plan_raw, events_raw, response_raw)
    plan = _body(plan_raw)
    rows = [_body(line) for line in events_raw.splitlines()]
    result = review(at_ns=at_ns, monotonic_ns=monotonic_ns)
    result.update(
        schema_version="portfolio.joint_bootstrap_admission_review.v1",
        bootstrap_evidence=replay,
        bootstrap_scope_consumed=True,
        joint_scope_consumed=False,
        capacity_reserved=False,
        restart_allowed=False,
        trading_admitted=False,
    )
    if replay["status"] != "completed_original_rest_bootstrap_replayed":
        result["blockers"].append("bootstrap_incomplete_or_failed_no_dispatch_sample")
        return result
    events = {r["kind"]: r for r in rows if r["kind"] != "response_chunk"}
    ready = events["child_ready"]["identity"]
    collector = plan["collector"]
    uid, gid = (_integer(collector[k], positive=True) for k in ("uid", "gid"))
    for key in ("destination_ipv4", "private_ipv4", "public_ipv4"):
        if str(ipaddress.IPv4Address(plan[key])) != plan[key]:
            raise ValueError("bootstrap_address_binding")
    if (
        events["scope_consumed"]["source_commit"] != plan["source_commit"]
        or events["tcp_prepared"]["destination"] != plan["destination_ipv4"]
        or events["tcp_prepared"]["port"] != 443
        or collector["name"] != "trader-egress"
        or ready["uids"] != [uid] * 4
        or ready["gids"] != [gid] * 4
        or ready["groups"]
        or any(ready["capabilities"].values())
        or ready["no_new_privileges"] != 1
        or events["tls_verified"]["local"][0] != "169.254.254.2"
        or plan["maintenance_accepted"] is not True
        or plan["unknown_prior_usage_accepted"] is not True
    ):
        raise ValueError("bootstrap_transport_or_collector_binding")
    if (
        events["window_prepared"]["collector_ms"] != 12000
        or events["window_prepared"]["blackout_ms"] != 20000
    ):
        raise ValueError("bootstrap_window_contract")
    if not isinstance(plan["host_boot_id"], str) or not plan["host_boot_id"] or not boot_id:
        raise ValueError("bootstrap_boot_identity_required")
    header, body = response_raw.split(b"\r\n\r\n", 1)
    total = 0
    header_receipt = None
    for row in rows:
        if row["kind"] == "response_chunk":
            total += row["size"]
            if total >= len(header) + 4:
                header_receipt = row
                break
    complete = events["response_complete"]
    same_boot = boot_id == plan["host_boot_id"]
    wall_age = at_ns - header_receipt["utc_ns"]
    mono_age = monotonic_ns - header_receipt["monotonic_ns"] if same_boot else None
    local_clock_consistent = all(
        abs((r["utc_ns"] - rows[0]["utc_ns"]) - (r["monotonic_ns"] - rows[0]["monotonic_ns"]))
        <= 50_000_000
        for r in rows
    )
    review_clock_consistent = (
        same_boot
        and at_ns >= rows[-1]["utc_ns"]
        and monotonic_ns >= rows[-1]["monotonic_ns"]
        and abs(wall_age - mono_age) <= 50_000_000
        and local_clock_consistent
    )
    sample_max_age = contract()["budget_interpretation"]["sample_max_age_ns"]
    receipt_age = max(wall_age, mono_age) if review_clock_consistent else None
    header_to_complete = complete["monotonic_ns"] - header_receipt["monotonic_ns"]
    result["bootstrap_context"] = {
        "source_commit": plan["source_commit"],
        "installation_manifest_sha256": plan["installation_manifest_sha256"],
        "collector_identity_receipt_matches_plan": True,
        "tls_receipt_matches_selected_peer": True,
        "public_source_basis": "operator_mapping_claim_in_selected_plan_not_venue_echo",
        "operator_mapping_sha256": plan["operator_mapping_sha256"],
        "source_authority_qualified": False,
        "gateway_authority_qualified": False,
        "review_boot_matches_capture": same_boot,
        "local_receipt_clocks_consistent": local_clock_consistent,
        "review_clock_consistent": review_clock_consistent,
        "header_persisted_utc_ns": header_receipt["utc_ns"],
        "header_persisted_monotonic_ns": header_receipt["monotonic_ns"],
        "header_to_complete_ns": header_to_complete,
        "header_already_stale_at_body_completion": header_to_complete > sample_max_age,
        "header_receipt_age_ns": receipt_age,
        "provider_counter_age_verified": False,
        "sample_max_age_ns": sample_max_age,
        "reported_server_time_ms": _body(body).get("serverTime"),
        "server_time_interval_ns": None,
        "http_date_is_clock_anchor": False,
        "maintenance_active_to_cleanup_ns": events["cleanup"]["monotonic_ns"]
        - events["window_active"]["monotonic_ns"],
        "historical_guard_covers_current_dispatch": False,
        "coverage_before_window_verified": False,
        "coverage_after_cleanup_verified": False,
        "rolling_connection_history_verified": False,
        "future_other_caller_bound": None,
    }
    # This is historical evidence, deliberately not a v1 candidate with guessed
    # server time, zero RAW_REQUESTS/connections or a fabricated all-callers ledger.
    result["blockers"] = [b for b in result["blockers"] if b != "preexisting_rate_samples_missing"]
    result["blockers"].extend(
        [
            "fresh_qualified_rest_dispatch_sample_missing",
            "account_preexisting_rate_samples_missing",
            "qualified_server_clock_interval_missing",
            "bootstrap_guard_ended_no_current_or_future_coverage",
            "complete_rolling_connection_history_missing",
            "source_and_gateway_authority_qualification_missing",
        ]
    )
    if not review_clock_consistent:
        result["blockers"].append("bootstrap_review_clock_or_boot_not_comparable")
    if header_to_complete > sample_max_age:
        result["blockers"].append("bootstrap_counter_stale_before_body_completed")
    if receipt_age is not None and receipt_age > sample_max_age:
        result["blockers"].append("bootstrap_header_receipt_stale_at_review")
    for rate in replay["rates"]["rates"]:
        kind = rate["rate_limit_type"]
        remaining = (
            result["maximum_scope"]["total_documented_weight"]
            if kind == "REQUEST_WEIGHT"
            else result["maximum_scope"]["rest_get_count"]
            if kind == "RAW_REQUESTS"
            else None
        )
        reasons = ["historical_bootstrap_not_current_dispatch_sample"]
        if rate["count"] is None:
            reasons.append("usage_not_observed")
        reasons.append(
            "account_scope_not_qualified_by_public_bootstrap"
            if kind == "ORDERS"
            else "complete_usage_and_other_caller_upper_bounds_missing"
        )
        result["interval_reviews"].append(
            {
                "role": "rest",
                **rate,
                "used_upper_bound": None,
                "other_clients_upper_bound": None,
                "remaining_scope_reservation": remaining,
                "headroom_after_documented_reservation": None,
                "reasons": reasons,
            }
        )
        result["blockers"].extend(
            f"rest:{kind}:{rate['interval_seconds']}:{reason}" for reason in reasons
        )
    result["blockers"] = sorted(set(result["blockers"]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--candidate-sha256")
    for name in ("plan", "events", "response"):
        parser.add_argument("--bootstrap-" + name, type=Path)
        parser.add_argument("--bootstrap-" + name + "-sha256")
    parser.add_argument(
        "--boot-id", help="review boot ID; required with historical bootstrap times"
    )
    parser.add_argument("--at-ns", type=int)
    parser.add_argument("--monotonic-ns", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if bool(args.candidate) != bool(args.candidate_sha256):
        parser.error("candidate and original SHA256 must be selected together")
    if (args.at_ns is None) != (args.monotonic_ns is None):
        parser.error("historical UTC and monotonic review times must be selected together")
    selected = [
        getattr(args, "bootstrap_" + name + suffix)
        for name in ("plan", "events", "response")
        for suffix in ("", "_sha256")
    ]
    if any(selected) and (not all(selected) or args.candidate):
        parser.error("select all three bootstrap originals and hashes, separately from candidates")
    if any(selected) and args.at_ns is not None and not args.boot_id:
        parser.error("historical bootstrap review requires its explicit review boot ID")
    if args.boot_id and not any(selected):
        parser.error("boot ID applies only to bootstrap review")
    try:
        if (
            args.report.exists()
            or args.report.is_symlink()
            or (args.candidate and args.report.resolve() == args.candidate.resolve())
        ):
            raise ValueError("new distinct report required")
        clocks = {
            "at_ns": time.time_ns() if args.at_ns is None else args.at_ns,
            "monotonic_ns": time.monotonic_ns() if args.monotonic_ns is None else args.monotonic_ns,
        }
        if any(selected):
            originals = []
            for name in ("plan", "events", "response"):
                raw = private_read(getattr(args, "bootstrap_" + name), limit=MAX_INPUT)
                if sha(raw) != getattr(args, "bootstrap_" + name + "_sha256"):
                    raise ValueError("selected_bootstrap_original_changed")
                originals.append(raw)
            report = review_bootstrap(
                *originals,
                **clocks,
                boot_id=args.boot_id or Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            )
        else:
            report = review(
                private_read(args.candidate, limit=MAX_INPUT) if args.candidate else None,
                expected_sha256=args.candidate_sha256,
                **clocks,
            )
        output = canonical(report) + b"\n"
        write_private_new(args.report, output)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "admission_review_failed",
                    "network_admitted": False,
                    "venue_requests_made": 0,
                }
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "blockers": report["blockers"],
                "report_sha256": sha(output),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # A written review is not a network admission permit.


if __name__ == "__main__":
    raise SystemExit(main())

"""Conditional capacity arithmetic cannot authenticate source or permit networking."""

import base64
import copy
import json
import socket
import subprocess
import sys

import pytest

from apps.ops.portfolio_joint_admission import main
from apps.strategies_nautilus import portfolio_joint_admission as gate
from apps.strategies_nautilus.portfolio_rate_evidence import RateEvidenceError
from tests.strategies_nautilus.test_portfolio_rate_evidence import rate, raw

S = gate.SECOND
NOW = 3620 * S
MONO = 1000 * S


def binding(role):
    return {
        "endpoint": gate.ENDPOINTS[role],
        "destination_ip": "203.0.113.10",
        "egress_ip": "198.51.100.1",
        "address_family": 4,
    }


def sample(role, *, ago=1, weight=70):
    rates = (
        [rate(), rate("RAW_REQUESTS", number=5, limit=61000)]
        if role == "rest"
        else [rate(), rate("CONNECTIONS", number=5, limit=300)]
    )
    body = (
        raw({"rateLimits": rates})
        if role == "rest"
        else raw(
            {
                "id": "seed-1",
                "status": 200,
                "result": {"rateLimits": rates},
                "rateLimits": [rate(count=weight)],
            }
        )
    )
    return {
        "binding": binding(role),
        "received_ns": NOW - ago * S,
        "monotonic_ns": MONO - ago * S,
        "server_time_ns": [NOW - ago * S, NOW - ago * S + 10_000_000],
        "raw_b64": base64.b64encode(body).decode(),
        "body_sha256": gate.sha(body),
        **(
            {"headers": [["X-MBX-USED-WEIGHT-1M", str(weight)]]}
            if role == "rest"
            else {"request_id": "seed-1"}
        ),
    }


def bound(role, kind, seconds, used=80, other=10):
    return {
        "role": role,
        "rate_limit_type": kind,
        "interval_seconds": seconds,
        "used_upper_bound": used,
        "other_clients_upper_bound": other,
    }


def candidate():
    return {
        "schema_version": gate.SCHEMA,
        "contract_sha256": gate.CONTRACT_SHA256,
        "samples": {r: [sample(r)] for r in ("rest", "account")},
        "ledger": {
            "bindings": {r: binding(r) for r in gate.ENDPOINTS},
            "covered_from_ns": 3300 * S,
            "covered_through_ns": NOW + 10_000_000,
            "future_through_ns": NOW + 126 * S,
            "all_callers": True,
            "usage_bounds": [
                bound("rest", "REQUEST_WEIGHT", 60),
                bound("rest", "RAW_REQUESTS", 300),
                bound("account", "REQUEST_WEIGHT", 60),
                bound("account", "CONNECTIONS", 300, 2, 1),
                bound("market", "CONNECTIONS", 300, 1, 1),
            ],
            "connection_attempts": [
                {
                    "id": str(i),
                    "role": "market" if i == 2 else "account",
                    "server_time_ns": [NOW - (i + 1) * S, NOW - (i + 1) * S],
                    "outcome": outcome,
                }
                for i, outcome in enumerate(("succeeded", "failed", "uncertain"))
            ],
        },
    }


def review(value=None, **kwargs):
    data = raw(candidate() if value is None else value)
    return gate.review(data, expected_sha256=gate.sha(data), at_ns=NOW, monotonic_ns=MONO, **kwargs)


def row(report, role="rest", kind="REQUEST_WEIGHT", seconds=60):
    return next(
        r
        for r in report["interval_reviews"]
        if (r["role"], r["rate_limit_type"], r["interval_seconds"]) == (role, kind, seconds)
    )


def test_complete_candidate_reports_arithmetic_but_never_admits():
    value = candidate()
    before = copy.deepcopy(value)
    report = review(value)
    assert value == before
    assert row(report)["headroom_after_documented_reservation"] == 6000 - 80 - 10 - 468
    assert row(report, kind="RAW_REQUESTS", seconds=300)["remaining_scope_reservation"] == 17
    assert report["maximum_scope"] == {
        "rest_get_count": 17,
        "rest_weight": 462,
        "ws_api_weight": 6,
        "total_documented_weight": 468,
    }
    assert report["connection_review"]["attempts_by_endpoint"] == {"account": 2, "market": 1}
    assert report["connection_review"]["headroom"] == 300 - 3 - 2 - 2
    assert not report["connection_review"]["provider_shared_counter_inferred"]
    assert len(report["blockers"]) == 4
    assert not report["network_admitted"] and not report["source_authenticated"]
    assert not report["shared_egress_verified"] and not any(report["qualification"].values())
    assert all(
        v is None
        for k, v in report.items()
        if k.startswith("qualified_") or k == "common_account_market_revision"
    )


@pytest.mark.parametrize("headroom", [1, 0, -1])
def test_complete_remaining_budget_and_other_callers_are_reserved(headroom):
    value = candidate()
    value["ledger"]["usage_bounds"][0]["used_upper_bound"] = 6000 - 468 - 10 - headroom
    result = row(review(value))
    assert result["headroom_after_documented_reservation"] == headroom
    assert ("remaining_scope_or_other_clients_exceed_limit" in result["reasons"]) == (headroom < 0)


def test_rest_and_ws_counts_are_not_overwritten_with_each_other():
    value = candidate()
    value["samples"]["account"] = [sample("account", weight=5900)]
    value["ledger"]["usage_bounds"][2]["used_upper_bound"] = 5900
    report = review(value)
    assert row(report)["count"] == 70
    assert row(report, "account")["count"] == 5900
    assert not row(report)["reasons"]
    assert "remaining_scope_or_other_clients_exceed_limit" in row(report, "account")["reasons"]


@pytest.mark.parametrize(
    "role,kind", [("rest", "RAW_REQUESTS"), ("account", "CONNECTIONS"), ("market", "CONNECTIONS")]
)
def test_missing_usage_bound_never_becomes_zero(role, kind):
    value = candidate()
    value["ledger"]["usage_bounds"] = [
        r
        for r in value["ledger"]["usage_bounds"]
        if (r["role"], r["rate_limit_type"]) != (role, kind)
    ]
    report = review(value)
    if kind == "CONNECTIONS":
        assert report["connection_review"]["used_upper_bound_union"] is None
        assert report["connection_review"]["headroom"] is None
    else:
        result = row(report, kind=kind, seconds=300)
        assert result["count"] is None and result["used_upper_bound"] is None
        assert result["headroom_after_documented_reservation"] is None


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "uncertain"])
def test_all_attempt_outcomes_consume_connection_capacity(outcome):
    value = candidate()
    value["ledger"]["connection_attempts"][0]["outcome"] = outcome
    value["ledger"]["usage_bounds"][3]["used_upper_bound"] = 297
    report = review(value)
    assert report["connection_review"]["attempts_by_endpoint"]["account"] == 2
    assert report["connection_review"]["headroom"] == -2
    assert "conservative_connection_union_exceeds_documented_limit" in report["blockers"]


@pytest.mark.parametrize("offset,counted", [(-1, False), (0, True), (1, True)])
def test_uncertain_rolling_window_edge_is_conservative(offset, counted):
    value = candidate()
    edge = NOW - 300 * S
    value["ledger"]["connection_attempts"].append(
        {
            "id": "edge",
            "role": "market",
            "server_time_ns": [edge - S, edge + offset],
            "outcome": "uncertain",
        }
    )
    # Keep the entire uncertainty interval within the supported one-second cap.
    value["ledger"]["connection_attempts"][-1]["server_time_ns"][0] = edge - 100
    value["ledger"]["usage_bounds"][4]["used_upper_bound"] = 2
    assert review(value)["connection_review"]["attempts_by_endpoint"]["market"] == 1 + counted


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("all_callers", False, "egress_coverage_gap_or_other_callers_missing"),
        ("covered_from_ns", NOW - 299 * S, "complete_rolling_connection_history_missing"),
        ("covered_through_ns", NOW, "egress_coverage_gap_or_other_callers_missing"),
        ("future_through_ns", NOW + 124 * S, "other_client_reservation_horizon_incomplete"),
    ],
)
def test_coverage_and_other_client_reservation_gaps(field, value, reason):
    data = candidate()
    data["ledger"][field] = value
    assert reason in review(data)["blockers"]


@pytest.mark.parametrize("ago,stale", [(5, False), (6, True)])
def test_sample_age_boundary(ago, stale):
    value = candidate()
    value["samples"] = {r: [sample(r, ago=ago)] for r in ("rest", "account")}
    assert ("rest_rate_sample_stale" in review(value)["blockers"]) == stale


@pytest.mark.parametrize("kind", ["sample", "dispatch"])
def test_entire_server_uncertainty_must_fit_one_bucket(kind):
    value = candidate()
    for samples in value["samples"].values():
        samples[0]["server_time_ns"] = (
            [3659 * S - 1, 3659 * S + 1] if kind == "dispatch" else [3660 * S - 1, 3660 * S + 1]
        )
    value["ledger"]["covered_through_ns"] = (3660 if kind == "dispatch" else 3661) * S + 1
    value["ledger"]["future_through_ns"] = 4000 * S
    assert "clock_uncertainty_crosses_bucket" in row(review(value))["reasons"]


@pytest.mark.parametrize("change", ["regression", "bucket", "limit", "intervals", "source", "time"])
def test_sample_history_does_not_infer_resets_or_rewrite_source(change):
    value = candidate()
    older = sample("rest", ago=2, weight=71 if change == "regression" else 60)
    if change == "bucket":
        older["server_time_ns"] = [3559 * S, 3559 * S]
    if change == "source":
        older["binding"]["egress_ip"] = "198.51.100.2"
    if change == "time":
        older["received_ns"] = NOW
    if change in {"limit", "intervals"}:
        body = {"rateLimits": [rate(limit=6001 if change == "limit" else 6000)]}
        if change == "limit":
            body["rateLimits"].append(rate("RAW_REQUESTS", number=5, limit=61000))
        data = raw(body)
        older.update(raw_b64=base64.b64encode(data).decode(), body_sha256=gate.sha(data))
    value["samples"]["rest"].insert(0, older)
    with pytest.raises(RateEvidenceError):
        review(value)


def test_monotonic_same_bucket_history_is_retained():
    value = candidate()
    value["samples"]["rest"].insert(0, sample("rest", ago=2, weight=60))
    assert row(review(value))["count"] == 70


@pytest.mark.parametrize(
    "change",
    [
        "destination",
        "family",
        "endpoint",
        "duplicate_attempt",
        "unknown_outcome",
        "duplicate_bound",
        "negative",
        "boolean",
        "false_auth",
        "body_hash",
        "duplicate_header",
        "clock",
        "future",
    ],
)
def test_malformed_or_self_authenticated_candidates_fail(change):
    value = candidate()
    ledger = value["ledger"]
    sample_row = value["samples"]["rest"][0]
    if change == "destination":
        ledger["bindings"]["rest"]["destination_ip"] = "203.0.113.11"
    if change == "family":
        sample_row["binding"]["address_family"] = 6
    if change == "endpoint":
        sample_row["binding"]["endpoint"] = "https://api.binance.com"
    if change == "duplicate_attempt":
        ledger["connection_attempts"].append(copy.deepcopy(ledger["connection_attempts"][0]))
    if change == "unknown_outcome":
        ledger["connection_attempts"][0]["outcome"] = "ignored"
    if change == "duplicate_bound":
        ledger["usage_bounds"].append(copy.deepcopy(ledger["usage_bounds"][0]))
    if change == "negative":
        ledger["usage_bounds"][0]["used_upper_bound"] = -1
    if change == "boolean":
        ledger["usage_bounds"][0]["other_clients_upper_bound"] = False
    if change == "false_auth":
        value["source_authenticated"] = True
    if change == "body_hash":
        sample_row["body_sha256"] = "0" * 64
    if change == "duplicate_header":
        sample_row["headers"].append(["x-mbx-used-weight-1m", "70"])
    if change == "clock":
        sample_row["monotonic_ns"] -= S
    if change == "future":
        sample_row["received_ns"], sample_row["monotonic_ns"] = NOW + S, MONO + S
    with pytest.raises((RateEvidenceError, ValueError)):
        review(value)


def test_declared_day_interval_cannot_be_silently_omitted():
    value = candidate()
    selected = value["samples"]["rest"][0]
    data = raw(
        {
            "rateLimits": [
                rate(),
                rate("RAW_REQUESTS", number=5, limit=61000),
                rate(interval="DAY", limit=100000),
            ]
        }
    )
    selected.update(raw_b64=base64.b64encode(data).decode(), body_sha256=gate.sha(data))
    selected["headers"].append(["X-MBX-USED-WEIGHT-1D", "90"])
    report = review(value)
    assert "usage_and_other_client_upper_bound_missing" in row(report, seconds=86400)["reasons"]


def test_account_order_scope_cannot_be_covered_by_ip_bounds():
    value = candidate()
    selected = value["samples"]["account"][0]
    data = raw(
        {
            "id": "seed-1",
            "status": 200,
            "result": {},
            "rateLimits": [
                rate(count=70),
                rate("ORDERS", interval="SECOND", number=10, limit=50, count=1),
            ],
        }
    )
    selected.update(raw_b64=base64.b64encode(data).decode(), body_sha256=gate.sha(data))
    assert (
        "account_order_scope_not_covered_by_ip_ledger"
        in row(review(value), "account", "ORDERS", 10)["reasons"]
    )


def test_missing_input_cli_is_private_and_makes_no_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network used by offline admission review")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    target = tmp_path / "blocked.json"
    assert main(["--report", str(target), "--at-ns", str(NOW), "--monotonic-ns", str(MONO)]) == 2
    report = json.loads(target.read_bytes())
    assert "preexisting_rate_samples_missing" in report["blockers"]
    assert "complete_egress_candidate_missing" in report["blockers"]
    assert target.stat().st_mode & 0o777 == 0o600
    original = target.read_bytes()
    assert main(["--report", str(target)]) == 1
    assert target.read_bytes() == original


def test_two_fresh_cli_reviews_are_identical_and_still_blocked(tmp_path):
    source = tmp_path / "candidate.json"
    data = raw(candidate())
    source.write_bytes(data)
    source.chmod(0o600)
    outputs = []
    for index in range(2):
        target = tmp_path / f"review{index}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_admission",
                "--candidate",
                str(source),
                "--candidate-sha256",
                gate.sha(data),
                "--at-ns",
                str(NOW),
                "--monotonic-ns",
                str(MONO),
                "--report",
                str(target),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 2, proc.stdout + proc.stderr
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]
    assert not json.loads(outputs[0])["network_admitted"]
    assert source.read_bytes() == data


@pytest.mark.parametrize(
    "data", [b"{}", b"{", b'{"schema_version":1,"schema_version":2}', b'{"samples":NaN}']
)
def test_bad_selected_json_refused(data):
    with pytest.raises(RateEvidenceError):
        gate.review(data, expected_sha256=gate.sha(data), at_ns=NOW, monotonic_ns=MONO)


def test_wrong_selected_hash_refused():
    with pytest.raises(RateEvidenceError, match="selected_admission_candidate_changed"):
        gate.review(raw(candidate()), expected_sha256="0" * 64, at_ns=NOW, monotonic_ns=MONO)


def test_ledger_cannot_claim_observed_future_coverage():
    value = candidate()
    value["ledger"]["covered_through_ns"] = NOW + S
    with pytest.raises(RateEvidenceError, match="coverage_interval_invalid"):
        review(value)


def test_complete_candidate_cli_cannot_connect_or_create_activation(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network used for a self-reported capacity candidate")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    source, target = tmp_path / "candidate.json", tmp_path / "report.json"
    data = raw(candidate())
    source.write_bytes(data)
    source.chmod(0o600)
    assert (
        main(
            [
                "--candidate",
                str(source),
                "--candidate-sha256",
                gate.sha(data),
                "--at-ns",
                str(NOW),
                "--monotonic-ns",
                str(MONO),
                "--report",
                str(target),
            ]
        )
        == 2
    )
    assert set(tmp_path.iterdir()) == {source, target}
    assert not json.loads(target.read_bytes())["network_admitted"]


def test_original_source_hashes_and_history_remain_in_report():
    value = candidate()
    value["samples"]["rest"].insert(0, sample("rest", ago=2, weight=60))
    report = review(value)
    assert [r["body_sha256"] for r in report["rate_sources"]["rest"]] == [
        s["body_sha256"] for s in value["samples"]["rest"]
    ]
    assert all(r["header_pairs_sha256"] for r in report["rate_sources"]["rest"])
    assert report["rate_sources"]["account"][0]["request_id"] == "seed-1"


def test_ledger_bound_below_server_count_is_not_repaired_by_choosing_a_counter():
    value = candidate()
    value["ledger"]["usage_bounds"][0]["used_upper_bound"] = 69
    result = row(review(value))
    assert result["used_upper_bound"] == 69 and result["count"] == 70
    assert "ledger_upper_bound_below_server_count" in result["reasons"]

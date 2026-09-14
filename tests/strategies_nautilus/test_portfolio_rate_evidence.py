"""Original-field rate interpretation cannot become network admission."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from apps.strategies_nautilus.portfolio_rate_evidence import (
    RateEvidenceError,
    rest_rate_evidence,
    ws_rate_evidence,
)


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode()


def rate(kind="REQUEST_WEIGHT", interval="MINUTE", number=1, limit=6000, **extra):
    return {
        "rateLimitType": kind,
        "interval": interval,
        "intervalNum": number,
        "limit": limit,
        **extra,
    }


def reply():
    return {
        "id": "selected-1",
        "status": 200,
        "result": {"rateLimits": [rate(), rate("CONNECTIONS", number=5, limit=300)]},
        "rateLimits": [rate(count=70)],
    }


def test_rest_preserves_multiple_intervals_and_unknown_nonweight_usage():
    body = {
        "rateLimits": [
            rate(),
            rate(interval="DAY", limit=100000),
            rate("RAW_REQUESTS"),
            rate("ORDERS"),
        ]
    }
    headers = [
        ["X-MBX-USED-WEIGHT-1M", "70"],
        ["x-mbx-used-weight-1d", "400"],
        ["Content-Type", "application/json"],
    ]
    before = copy.deepcopy(headers)
    report = rest_rate_evidence(raw(body), headers)
    assert [
        (r["interval"], r["count"])
        for r in report["rates"]
        if r["rate_limit_type"] == "REQUEST_WEIGHT"
    ] == [("DAY", 400), ("MINUTE", 70)]
    assert all(
        r["count"] is None for r in report["rates"] if r["rate_limit_type"] != "REQUEST_WEIGHT"
    )
    assert headers == before
    assert report == rest_rate_evidence(raw(body), headers)
    assert report["network_admitted"] is False


def test_connection_definition_is_not_a_zero_usage_counter():
    report = ws_rate_evidence(raw(reply()), request_id="selected-1")
    connection, weight = report["rates"]
    assert connection["limit"] == 300
    assert connection["count"] is None
    assert connection["count_basis"] == "not_observed"
    assert weight["count"] == 70
    assert report["egress_ip"] is None
    for key in (
        "source_authenticated",
        "freshness_verified",
        "cross_endpoint_ledger_verified",
        "connection_attempt_coverage_verified",
        "network_admitted",
    ):
        assert report[key] is False


def test_an_explicit_connection_counter_still_does_not_cover_other_endpoints():
    body = reply()
    body["rateLimits"].append(rate("CONNECTIONS", number=5, limit=300, count=12))
    report = ws_rate_evidence(raw(body), request_id="selected-1")
    assert report["rates"][0]["count"] == 12
    assert report["cross_endpoint_ledger_verified"] is False
    assert report["connection_attempt_coverage_verified"] is False


def test_account_orders_are_not_an_ip_counter():
    body = reply()
    body["result"] = {}
    body["rateLimits"].append(rate("ORDERS", interval="SECOND", number=10, limit=50, count=4))
    report = ws_rate_evidence(raw(body), request_id="selected-1")
    assert report["rates"][0]["scope"] == "account"
    assert report["rates"][1]["scope"] == "ip"


@pytest.mark.parametrize("count", [6000, 6001])
def test_exhaustion_is_retained_as_evidence(count):
    report = rest_rate_evidence(
        raw({"rateLimits": [rate()]}), [["X-MBX-USED-WEIGHT-1M", str(count)]]
    )
    assert report["exhausted_intervals"] == [
        {"rate_limit_type": "REQUEST_WEIGHT", "interval": "MINUTE", "interval_num": 1}
    ]
    assert not report["network_admitted"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        [],
        [["X-MBX-USED-WEIGHT-1M", "70"], ["x-mbx-used-weight-1m", "70"]],
        [["X-MBX-USED-WEIGHT-1M", "70, 71"]],
        [["X-MBX-USED-WEIGHT-1M", "-1"]],
        [["X-MBX-USED-WEIGHT-1M", " 70"]],
        [["X-MBX-USED-WEIGHT-1M", "７０"]],
        [["X-MBX-USED-WEIGHT-1M", 70]],
        [["X-MBX-USED-WEIGHT-1M"]],
        [["X-MBX-USED-WEIGHT-1M", "70"], ["X-MBX-USED-WEIGHT-1H", "80"]],
        [["X-MBX-USED-WEIGHT-1M", "70"], ["other", "a" * 65536]],
    ],
)
def test_rest_ambiguous_missing_or_unbounded_headers_fail(headers):
    with pytest.raises(RateEvidenceError):
        rest_rate_evidence(raw({"rateLimits": [rate()]}), headers)


@pytest.mark.parametrize(
    "field,value",
    [
        ("limit", True),
        ("limit", 0),
        ("limit", "6000"),
        ("intervalNum", False),
        ("intervalNum", -1),
        ("intervalNum", 1.0),
        ("count", True),
        ("count", -1),
        ("count", "70"),
        ("rateLimitType", "NEW_KIND"),
        ("interval", "WEEK"),
        ("interval", []),
    ],
)
def test_rate_field_corruption_is_refused(field, value):
    body = reply()
    body["rateLimits"][0][field] = value
    with pytest.raises(RateEvidenceError):
        ws_rate_evidence(raw(body), request_id="selected-1")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.pop("rateLimits"),
        lambda b: b["rateLimits"][0].pop("count"),
        lambda b: b["rateLimits"].append(b["rateLimits"][0].copy()),
        lambda b: b["result"]["rateLimits"].append(rate()),
        lambda b: b["result"]["rateLimits"][0].update(limit=6001),
        lambda b: b["result"].update(rateLimits=[rate("CONNECTIONS", number=5, limit=300)]),
        lambda b: b.update(id="foreign"),
        lambda b: b.update(status=429),
        lambda b: b.update(status=True),
        lambda b: b.update(error={}),
        lambda b: b.update(result=[]),
    ],
)
def test_ws_correlation_and_limit_status_separation(mutation):
    body = reply()
    mutation(body)
    with pytest.raises(RateEvidenceError):
        ws_rate_evidence(raw(body), request_id="selected-1")


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"[]",
        b"{",
        b'{"rateLimits":[],"rateLimits":[]}',
        b'{"rateLimits":NaN}',
        b"\xff",
        b" " * (16 * 1024 * 1024 + 1),
    ],
)
def test_original_json_refusals(data):
    with pytest.raises(RateEvidenceError):
        rest_rate_evidence(data, [])


def test_different_endpoint_reports_do_not_infer_a_shared_ledger():
    rest = rest_rate_evidence(raw({"rateLimits": [rate()]}), [["x-mbx-used-weight-1m", "70"]])
    ws = ws_rate_evidence(raw(reply()), request_id="selected-1")
    assert rest["rates"][0]["count"] == ws["rates"][1]["count"]
    assert rest["endpoint_family"] != ws["endpoint_family"]
    assert not rest["cross_endpoint_ledger_verified"]
    assert not ws["cross_endpoint_ledger_verified"]


def contract():
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/progress/portfolio-testnet-joint-capture-contract-2026-09-14.json"
    data = path.read_bytes()
    assert (
        hashlib.sha256(data).hexdigest()
        == "91fab40cfd52b51cfac887f2dc45ee9594ce55d33b082f44d4aee31d2738ed48"
    )
    return root, json.loads(data)


def test_draft_budget_adds_early_metadata_without_reusing_route_metadata():
    from apps.strategies_nautilus.portfolio_observation_plan import request_budget

    _, draft = contract()
    budget = draft["maximum_three_symbol_budget"]
    old = request_budget(["BNBUSDT", "BTCUSDT", "ETHUSDT"])
    requests = budget["rest_requests"].copy()
    early = requests.pop(1)
    assert early == {
        "phase": "rate_limit_discovery",
        "method": "GET",
        "path": "/api/v3/exchangeInfo",
        "params": {},
        "weight": 20,
    }
    assert requests == old["rest_requests"]
    assert budget["rest_get_count"] == len(budget["rest_requests"]) == 17
    assert budget["rest_weight"] == sum(r["weight"] for r in budget["rest_requests"]) == 462
    assert budget["ws_api_operations"] == old["ws_api_operations"]
    assert budget["ws_api_weight"] == sum(r["weight"] for r in budget["ws_api_operations"]) == 6
    assert (
        budget["total_documented_weight"] == budget["rest_weight"] + budget["ws_api_weight"] == 468
    )
    assert old["total_documented_weight"] == 448


def test_draft_preserves_provider_selection_and_all_source_hashes():
    root, draft = contract()
    original = (
        root / "docs/progress/portfolio-testnet-provider-coverage-2026-09-13.json"
    ).read_bytes()
    assert hashlib.sha256(original).hexdigest() == draft["provider_contract_sha256"]
    assert draft["sources"] == json.loads(original)["sources"]
    assert draft["provider_revision"] == json.loads(original)["revision"]


def test_draft_has_no_capture_activation_or_qualification():
    _, draft = contract()
    assert draft["status"] == "draft_offline_contract_not_network_run_authorization"
    assert not draft["network_entrypoint_implemented"]
    assert not draft["new_probe_authorized"]
    assert not any(draft["qualification"].values())
    assert (
        draft["resource_envelope"]["observe_after_link_seconds"] * 1_000_000_000
        < draft["budget_interpretation"]["sample_max_age_ns"]
    )
    assert draft["budget_interpretation"]["first_request_is_not_exempt"]
    assert not draft["budget_interpretation"]["unbudgeted_seed_probe_permitted"]

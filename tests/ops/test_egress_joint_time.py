"""The second fixed clock request binds to both linked depth originals."""

import copy
import time

import pytest

from tests.ops.test_egress_installed_gateway import load

SYMBOLS = ["BNBUSDT", "BTCUSDT"]
ROUTE = "a" * 64
START = 1_790_000_000_000_000_000


def linked_results():
    rows = [{} for _ in range(13)]
    rows[9] = {"market_events": [{"receipt": {"utc_ns": START, "monotonic_ns": START}}]}
    for index in (10, 11):
        rows[index] = {
            "native_result": {
                "body_receipt": {
                    "utc_ns": START + (index - 9) * 1_000_000,
                    "monotonic_ns": START + (index - 9) * 1_000_000,
                }
            },
            "snapshot_linkage": {"snapshot_tls_sha256": str(index) * 64},
        }
    rows[12] = {
        "native_result": {
            "header_receipt": {
                "utc_ns": START + 3_000_000,
                "monotonic_ns": START + 3_000_000,
            },
            "server_time_ms": START // 1_000_000 + 3,
            "tls_sha256": "c" * 64,
        }
    }
    return rows


def test_linked_time_requires_both_snapshot_originals_and_ordered_clocks():
    sequence = load("gateway_read_sequence")
    assert (*sequence.JOINT_LINKED_STEPS, "clock_linked") == sequence.JOINT_TIME_STEPS
    assert sequence.JOINT_TIME_SCOPE != sequence.JOINT_LINKED_SCOPE
    assert sequence.joint_time_link(linked_results()) == {
        "server_time_ms": START // 1_000_000 + 3,
        "clock_tls_sha256": "c" * 64,
        "snapshot_tls_sha256": ["10" * 64, "11" * 64],
        "provider_clock_qualified": False,
    }


@pytest.mark.parametrize("damage", ["missing", "before_second", "stale", "clock_jump", "next_day"])
def test_linked_time_rejects_broken_snapshot_interval(damage):
    sequence = load("gateway_read_sequence")
    rows = copy.deepcopy(linked_results())
    stamp = rows[12]["native_result"]["header_receipt"]
    if damage == "missing":
        del rows[11]["snapshot_linkage"]
    elif damage == "before_second":
        stamp["utc_ns"] = START + 1_000_000
        stamp["monotonic_ns"] = START + 1_000_000
    elif damage == "stale":
        stamp["utc_ns"] += 61_000_000_000
        stamp["monotonic_ns"] += 61_000_000_000
    elif damage == "clock_jump":
        stamp["utc_ns"] += 60_000_000
    else:
        stamp["utc_ns"] = ((START // 86_400_000_000_000) + 1) * 86_400_000_000_000
        stamp["monotonic_ns"] += stamp["utc_ns"] - (START + 3_000_000)
    with pytest.raises(ValueError, match="joint_linked_time_"):
        sequence.joint_time_link(rows)


def test_native_clock_selector_fixes_index_12_and_original_route():
    base = load("gateway_native_requests")
    selector = load("gateway_joint_native_requests")
    clock = load("gateway_native_time")
    account = load("gateway_native_account")
    requests = {"view": selector.view, "base": vars(base)}
    view = clock.view(
        vars(account), index=12, symbols=SYMBOLS, route_sha256=ROUTE, requests=requests
    )
    selected = selector.view(vars(base), SYMBOLS, ROUTE)
    challenge = {
        "index": 12,
        "nonce": "a" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "route_sha256": ROUTE,
    }
    request = {
        "profile": selected["PROFILE"],
        "challenge_sha256": base.digest(base.canonical(challenge)),
        "request": selected["selected_request"](challenge),
    }
    selection = {
        "profile": view["SELECTION_PROFILE"],
        "binding_sha256": "b" * 64,
        "challenge": challenge,
        "request": request,
        "received": [challenge["utc_ns"], challenge["monotonic_ns"]],
    }
    contract = view["AccountContract"](selected, selection)
    assert contract.request == (
        b"GET /api/v3/time HTTP/1.1\r\n"
        b"Host: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
    )
    selection["challenge"] = {**challenge, "route_sha256": "c" * 64}
    with pytest.raises(ValueError, match="joint_request_route_challenge"):
        view["AccountContract"](selected, selection)
    selection["challenge"] = {**challenge, "index": 0}
    with pytest.raises(ValueError):
        view["AccountContract"](selected, selection)


def test_joint_time_fixture_peer_is_valid_python():
    harness = load("installed_gateway_selftest")
    compile(harness.JOINT_WS_PEER, "<joint-time-peer>", "exec")
    assert harness.JOINT_TIME_SCENARIOS == ("joint_time_success", "joint_time_bad_clock")
    entry = load("installed_gateway")
    assert entry.PROFILE == "portfolio.installed_gateway_fixture.v24"
    assert len(entry.FILES) == 26

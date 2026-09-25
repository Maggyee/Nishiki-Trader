"""The final account unsubscribe is fixed to the same disposable route."""

import copy
import json

import pytest

from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from apps.strategies_nautilus import portfolio_ws_frames as frames
from tests.ops import test_egress_joint_account_ws as ws_test
from tests.ops.test_egress_installed_gateway import load


@pytest.fixture(name="joint_prefix")
def existing_joint_prefix():
    return ws_test.originals.__wrapped__()


def test_complete_parent_and_native_unsubscribe_selector():
    sequence = load("gateway_read_sequence")
    base = load("gateway_native_requests")
    joint = load("gateway_joint_native_requests")
    symbols, route_hash = ["BNBUSDT", "BTCUSDT"], "a" * 64
    assert (*sequence.JOINT_FINAL_STEPS, "account_unsubscribe") == sequence.JOINT_COMPLETE_STEPS
    assert sequence.JOINT_COMPLETE_SCOPE != sequence.JOINT_FINAL_SCOPE
    requests = joint.view(vars(base), symbols, route_hash)
    challenge = {
        "index": 18,
        "nonce": "b" * 32,
        "utc_ns": 1_790_000_000_000_000_000,
        "monotonic_ns": 1_790_000_000_000_000_000,
        "route_sha256": route_hash,
    }
    assert requests["selected_request"](challenge) == {
        "kind": "ws",
        "id": "fixture-18",
        "method": "userDataStream.unsubscribe",
        "params": {"subscriptionId": 0},
    }
    with pytest.raises(ValueError, match="joint_request_route_challenge"):
        requests["selected_request"]({**challenge, "route_sha256": "c" * 64})


def test_unsubscribe_ack_requires_exact_id_status_and_empty_result():
    account = load("gateway_account_ws")
    assert (
        account.unsubscribe_response(
            b'{"id":"fixture-18","status":200,"result":{}}', request_id="fixture-18"
        )["result"]
        == {}
    )
    for raw in (
        b'{"id":"foreign","status":200,"result":{}}',
        b'{"id":"fixture-18","status":400,"result":{}}',
        b'{"id":"fixture-18","status":200,"result":{"subscriptionId":0}}',
    ):
        with pytest.raises(ValueError, match="account_ws_unsubscribe_response"):
            account.unsubscribe_response(raw, request_id="fixture-18")


def test_original_unsubscribe_requires_new_native_signer_and_exact_ack(joint_prefix):
    module, modules, selected, earlier, _, _, (now, mono) = joint_prefix
    account = load("gateway_account_ws")
    joint = load("gateway_joint_native_requests")
    route = {"symbols": ["BNBUSDT", "BTCUSDT"]}
    modules["joint_route_selection"] = lambda *_: route
    modules["joint_requests"] = vars(joint)
    previous = list(earlier) + [{} for _ in range(14)]
    previous.append(
        {"receipt": json.dumps({"utc_ns": now + 90_000_000, "monotonic_ns": mono + 90_000_000})}
    )
    context = {"profile": "joint-complete", "index": 18, "prefix_sha256": "a" * 64}
    binding = json.loads(earlier[2]["binding"])
    binding["read_sequence"] = context
    signer = copy.deepcopy(json.loads(earlier[2]["ws"].splitlines()[0])["payload"]["signer"])
    signer["process"].update(pid=990, start_ticks=1000)
    signer["process"]["namespaces"]["net"] = "unsubscribe-net"
    challenge = {
        "index": 18,
        "nonce": "b" * 32,
        "utc_ns": now + 100_000_000,
        "monotonic_ns": mono + 100_000_000,
        "route_sha256": module.digest(module.canonical(route)),
    }
    selected_request = joint.view(modules["requests"], route["symbols"], challenge["route_sha256"])
    envelope = json.loads(selected_request["native_request"](challenge))
    wire = frames.client_frame(account.wire_request(envelope))
    answer = b'{"id":"fixture-18","status":200,"result":{}}'
    events = [
        (
            "intent",
            {
                "final_clock_bundle_sha256": module.digest(module.canonical(previous[17])),
                "subscription_bundle_sha256": module.digest(module.canonical(previous[2])),
                "route_selection_sha256": module.digest(module.canonical(route)),
                "signer": signer,
            },
        ),
        (
            "signature_prepared",
            {
                "challenge": challenge,
                "request": envelope,
                "received": [now + 100_500_000, mono + 100_500_000],
                **provenance.raw_fields(wire),
            },
        ),
        ("grant_prepared", {"mark": module.MARK, "ttl_ms": 5000}),
        ("activated", {}),
        ("write_prepared", {}),
        ("response_chunk", provenance.raw_fields(bytes([0x81, len(answer)]) + answer)),
        ("unsubscribe_accepted", {}),
        ("revoked", {}),
        ("accepted", {}),
    ]

    def review(current):
        return module.review_step(
            {
                "binding": module.canonical(binding).decode(),
                "ws": ws_test.rows(module, current, now + 101_000_000, mono + 101_000_000),
            },
            18,
            context,
            selected,
            modules,
            previous,
        )

    assert review(events)["unsubscribe_acknowledged"]
    invalid = copy.deepcopy(events)
    invalid[0][1]["signer"] = json.loads(earlier[2]["ws"].splitlines()[0])["payload"]["signer"]
    with pytest.raises(ValueError, match="joint_ws_native_signer_identity"):
        review(invalid)
    bad_ack = copy.deepcopy(events)
    bad_answer = b'{"id":"foreign","status":200,"result":{}}'
    bad_ack[5] = (
        "response_chunk",
        provenance.raw_fields(bytes([0x81, len(bad_answer)]) + bad_answer),
    )
    bad_ack = bad_ack[:6] + [("revoked", {})]
    assert not review(bad_ack)["complete"]


def test_complete_fixture_peer_and_manifest():
    harness = load("installed_gateway_selftest")
    compile(harness.JOINT_WS_PEER, "<joint-complete-peer>", "exec")
    assert harness.JOINT_COMPLETE_SCENARIOS == ("joint_complete_success", "joint_complete_bad_ack")
    assert load("installed_gateway").PROFILE == "portfolio.installed_gateway_fixture.v27"

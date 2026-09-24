"""Native unsubscribe selector and original acknowledgement boundaries."""

import base64
import copy
import json

import pytest

from tests.ops.test_egress_installed_gateway import load


def receipt():
    account = load("gateway_account_ws")
    requests = load("gateway_native_requests")
    challenge = {
        "index": 19,
        "nonce": "a" * 32,
        "utc_ns": 1_800_000_000_300_000_000,
        "monotonic_ns": 1_000_000_000,
    }
    request = json.loads(requests.native_request(challenge))
    assert request["request"] == {
        "kind": "ws",
        "id": "fixture-19",
        "method": "userDataStream.unsubscribe",
        "params": {"subscriptionId": 0},
    }
    requests.validate_request(
        requests.canonical(request),
        challenge,
        received=(challenge["utc_ns"], challenge["monotonic_ns"]),
    )
    value = {
        "profile": account.UNSUB_RECEIPT,
        "request_sha256": "a" * 64,
        "response_b64": base64.b64encode(
            b'{"id":"fixture-2","status":200,"result":{"subscriptionId":0}}'
        ).decode(),
        "event_b64": base64.b64encode(
            account.canonical(
                {
                    "subscriptionId": 0,
                    "event": {
                        "e": "outboundAccountPosition",
                        "E": 1_800_000_000_200,
                        "u": 1_800_000_000_199,
                        "B": [{"a": "BTC", "f": "0.01000000", "l": "0.00100000"}],
                    },
                }
            )
        ).decode(),
        "response_receipt": {
            "utc_ns": challenge["utc_ns"] - 200_000_000,
            "monotonic_ns": challenge["monotonic_ns"] - 200_000_000,
        },
        "event_receipt": {
            "utc_ns": challenge["utc_ns"] - 100_000_000,
            "monotonic_ns": challenge["monotonic_ns"] - 100_000_000,
        },
        "unsubscribe_request_sha256": requests.digest(requests.canonical(request)),
        "unsubscribe_b64": base64.b64encode(
            b'{"id":"fixture-19","status":200,"result":{}}'
        ).decode(),
        "unsubscribe_receipt": {
            "utc_ns": challenge["utc_ns"] + 100_000_000,
            "monotonic_ns": challenge["monotonic_ns"] + 100_000_000,
        },
    }
    return account, value


def test_original_unsubscribe_receipt_matches_native_partial_account():
    account, value = receipt()
    raw = account.canonical(value)
    expected = account.expected_result(raw, unsubscribe=True)
    assert account.validate_native(raw, unsubscribe=True) == expected
    assert expected["unsubscribe_acknowledged"]
    assert expected["unsubscribe_request_sha256"] == value["unsubscribe_request_sha256"]
    assert expected["partial_update"] and not expected["full_account_snapshot"]
    assert not expected["stream_fence_verified"] and not expected["qualified_for_execution"]
    with pytest.raises(ValueError, match="account_ws_receipt_schema"):
        account.expected_result(raw)


@pytest.mark.parametrize(
    "damage", ["id", "status", "result", "duplicate", "event_order", "clock_drift", "missing"]
)
def test_unsubscribe_response_and_clock_tampering_refused(damage):
    account, original = receipt()
    value = copy.deepcopy(original)
    if damage in {"id", "status", "result", "duplicate"}:
        response = base64.b64decode(value["unsubscribe_b64"])
        if damage == "id":
            response = response.replace(b"fixture-19", b"foreign")
        elif damage == "status":
            response = response.replace(b"200", b"400")
        elif damage == "result":
            response = response.replace(b"{}", b'{"subscriptionId":0}')
        else:
            response = response.replace(b'"status":200', b'"status":200,"status":200')
        value["unsubscribe_b64"] = base64.b64encode(response).decode()
    elif damage == "event_order":
        value["unsubscribe_receipt"]["utc_ns"] = value["event_receipt"]["utc_ns"] - 1
    elif damage == "clock_drift":
        value["unsubscribe_receipt"]["monotonic_ns"] += 60_000_000
    else:
        del value["unsubscribe_request_sha256"]
    with pytest.raises(ValueError, match="account_ws_"):
        account.expected_result(account.canonical(value), unsubscribe=True)

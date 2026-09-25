"""The second four signed reads remain route-bound and reconcile both endpoints."""

import copy

import pytest

from tests.ops.test_egress_installed_gateway import load

START = 1_790_000_000_000_000_000


def results():
    rows = [{} for _ in range(17)]
    balances = [{"currency": "USDT", "precision": 8, "total": "5", "locked": "0", "free": "5"}]
    for index in (3, 13, 16):
        rows[index] = {"native_result": {"account_uid": 41001, "balances": copy.deepcopy(balances)}}
    for index in (4, 14, 15):
        rows[index] = {"native_result": {"account_uid": 41001, "orders": []}}
    rows[9] = {"market_events": [{"receipt": {"utc_ns": START, "monotonic_ns": START}}]}
    rows[16]["native_result"]["body_receipt"] = {
        "utc_ns": START + 15_000_000,
        "monotonic_ns": START + 15_000_000,
    }
    return rows


def test_second_pass_reconciles_incrementally_without_claiming_real_coverage():
    sequence = load("gateway_read_sequence")
    assert (
        *sequence.JOINT_TIME_STEPS,
        "account_after_first",
        "orders_after_first",
        "orders_after_second",
        "account_after_second",
    ) == sequence.JOINT_AFTER_STEPS
    assert sequence.JOINT_AFTER_SCOPE != sequence.JOINT_TIME_SCOPE
    for length in range(14, 18):
        sequence.reconcile_joint_after(results()[:length])


@pytest.mark.parametrize(
    ("index", "mutation", "error"),
    [
        (
            13,
            lambda rows: rows[13]["native_result"].update(account_uid=41002),
            "joint_after_account_changed",
        ),
        (
            14,
            lambda rows: rows[14]["native_result"].update(account_uid=41002),
            "joint_after_account_uid_changed",
        ),
        (
            14,
            lambda rows: rows[14]["native_result"]["orders"].append({"orderId": 1}),
            "joint_after_orders_changed",
        ),
        (
            15,
            lambda rows: rows[15]["native_result"]["orders"].append({"orderId": 1}),
            "sequence_open_orders_changed",
        ),
        (
            16,
            lambda rows: rows[16]["native_result"]["balances"][0].update(free="6"),
            "joint_after_balances_changed",
        ),
        (
            16,
            lambda rows: rows[16]["native_result"]["body_receipt"].update(
                utc_ns=START + 61_000_000_000, monotonic_ns=START + 61_000_000_000
            ),
            "joint_after_original_interval",
        ),
    ],
)
def test_second_pass_refuses_drift_at_the_first_observable_step(index, mutation, error):
    sequence = load("gateway_read_sequence")
    rows = results()[: index + 1]
    mutation(rows)
    with pytest.raises(ValueError, match=error):
        sequence.reconcile_joint_after(rows)


def test_second_pass_native_selectors_require_original_route_and_fixed_indices():
    base = load("gateway_native_requests")
    joint = load("gateway_joint_native_requests")
    account = load("gateway_native_account")
    orders = load("gateway_native_orders")
    symbols, sha = ["BNBUSDT", "BTCUSDT"], "a" * 64
    requests = joint.view(vars(base), symbols, sha)
    for index, path in (
        (13, "/api/v3/account"),
        (14, "/api/v3/openOrders"),
        (15, "/api/v3/openOrders"),
        (16, "/api/v3/account"),
    ):
        view = (
            account.view_for_index(index, symbols=symbols, route_sha256=sha, requests=requests)
            if index in {13, 16}
            else orders.view(
                vars(account), index=index, symbols=symbols, route_sha256=sha, requests=requests
            )
        )
        assert index == view["AccountContract"].CHALLENGE_INDEX
        assert {"route_sha256": sha} == view["AccountContract"].CHALLENGE_FIELDS
        assert view["requests"] is requests
        challenge = {
            "index": index,
            "nonce": "b" * 32,
            "utc_ns": START,
            "monotonic_ns": START,
            "route_sha256": sha,
        }
        assert requests["selected_request"](challenge)["path"] == path
        with pytest.raises(ValueError, match="joint_request_route_challenge"):
            requests["selected_request"]({**challenge, "route_sha256": "c" * 64})


def test_second_pass_peer_and_manifest_are_consistent():
    harness = load("installed_gateway_selftest")
    compile(harness.JOINT_WS_PEER, "<joint-after-peer>", "exec")
    assert harness.JOINT_AFTER_SCENARIOS == (
        "joint_after_success",
        "joint_after_orders_changed",
        "joint_after_balance_drift",
    )
    assert load("installed_gateway").PROFILE == "portfolio.installed_gateway_fixture.v26"

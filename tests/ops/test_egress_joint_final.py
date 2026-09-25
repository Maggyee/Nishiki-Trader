"""The final clock uses a new parent and remains a bounded fixture receipt."""

import copy
import os

import pytest

from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_joint_after import START, results


def test_final_clock_is_route_bound_and_not_a_provider_clock():
    sequence = load("gateway_read_sequence")
    clock = load("gateway_native_time")
    account = load("gateway_native_account")
    base = load("gateway_native_requests")
    joint = load("gateway_joint_native_requests")
    symbols, route_hash = ["BNBUSDT", "BTCUSDT"], "a" * 64
    requests = {"view": joint.view, "base": vars(base)}
    assert (*sequence.JOINT_AFTER_STEPS, "clock_final") == sequence.JOINT_FINAL_STEPS
    assert sequence.JOINT_FINAL_SCOPE != sequence.JOINT_AFTER_SCOPE
    view = clock.view(
        vars(account), index=17, symbols=symbols, route_sha256=route_hash, requests=requests
    )
    assert view["AccountContract"].CHALLENGE_INDEX == 17
    assert {"route_sha256": route_hash} == view["AccountContract"].CHALLENGE_FIELDS
    challenge = {
        "index": 17,
        "nonce": "b" * 32,
        "utc_ns": 1_790_000_000_000_000_000,
        "monotonic_ns": 1_790_000_000_000_000_000,
        "route_sha256": route_hash,
    }
    selected = joint.view(vars(base), symbols, route_hash)
    assert selected["selected_request"](challenge) == {
        "kind": "rest",
        "method": "GET",
        "path": "/api/v3/time",
        "params": {},
        "headers": {},
    }
    with pytest.raises(ValueError, match="joint_request_route_challenge"):
        selected["selected_request"]({**challenge, "route_sha256": "c" * 64})


def test_final_scope_releases_only_step_readme_fd(tmp_path):
    sequence = load("gateway_read_sequence")
    state = object.__new__(sequence.Sequence)
    state.joint_final = True
    state.storage = tmp_path
    readme = tmp_path / "README.md"
    readme.write_bytes(b"disposable step\n")
    fd = os.open(readme, os.O_RDONLY)
    try:
        state.held = {readme: (fd, sequence.Sequence.identity(os.fstat(fd)), readme.read_bytes())}
        state.fds = [fd]
        state.verify = lambda: None
        state.release_step_readme()
        assert state.fds == []
        assert state.held[readme][0] is None
        assert state.held[readme][2] == b"disposable step\n"
        with pytest.raises(OSError):
            os.fstat(fd)
    finally:
        if state.fds:
            os.close(fd)


def test_final_clock_links_to_last_account_original_on_same_day():
    sequence = load("gateway_read_sequence")
    rows = results()
    rows[16]["native_result"]["tls_sha256"] = "a" * 64
    rows.append(
        {
            "native_result": {
                "header_receipt": {
                    "utc_ns": START + 20_000_000,
                    "monotonic_ns": START + 20_000_000,
                },
                "tls_sha256": "b" * 64,
            }
        }
    )
    assert sequence.joint_final_link(rows) == {
        "account_tls_sha256": "a" * 64,
        "clock_tls_sha256": "b" * 64,
        "provider_clock_qualified": False,
    }
    for change in (-10_000_000, 61_000_000_000):
        modified = copy.deepcopy(rows)
        for key in ("utc_ns", "monotonic_ns"):
            modified[17]["native_result"]["header_receipt"][key] += change
        with pytest.raises(ValueError, match="joint_final_clock_original_interval"):
            sequence.joint_final_link(modified)


def test_final_fixture_peer_compiles_and_has_two_scenarios():
    harness = load("installed_gateway_selftest")
    compile(harness.JOINT_WS_PEER, "<joint-final-peer>", "exec")
    assert harness.JOINT_FINAL_SCENARIOS == ("joint_final_success", "joint_final_bad_clock")
    assert load("installed_gateway").PROFILE == "portfolio.installed_gateway_fixture.v26"

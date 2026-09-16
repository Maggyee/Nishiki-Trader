"""Offline bootstrap replay rejects rehashed semantic and original-byte corruption."""

import base64
import copy
import json

import pytest

from apps.ops.portfolio_rest_bootstrap_review import digest, pinned, review


def encode(rows):
    previous = None
    raw = b""
    for index, source in enumerate(rows):
        row = {
            **source,
            "seq": index,
            "previous_sha256": previous,
            "utc_ns": 100 + index,
            "monotonic_ns": 100 + index,
        }
        line = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        previous = digest(line)
        raw += line
    return raw


@pytest.fixture
def capture():
    plan = json.dumps(
        {
            "schema_version": "portfolio.egress_bootstrap_execution.v1",
            "scope": "portfolio.testnet_rest_bootstrap.v1",
            "destination_ipv4": "192.0.2.1",
        }
    ).encode()
    body = b'{"rateLimits":[{"rateLimitType":"REQUEST_WEIGHT","interval":"MINUTE","intervalNum":1,"limit":6000}]}'
    pairs = [["Content-Length", str(len(body))], ["X-MBX-USED-WEIGHT-1M", "20"]]
    response = (
        "HTTP/1.1 200 OK\r\n" + "".join(f"{k}: {v}\r\n" for k, v in pairs) + "\r\n"
    ).encode() + body
    rows = [
        {"kind": k}
        for k in [
            "scope_consumed",
            "topology_prepared",
            "child_ready",
            "window_prepared",
            "window_active",
            "tcp_prepared",
            "tls_verified",
            "get_prepared",
            "response_chunk",
            "response_complete",
            "child_transport_closed",
            "completed",
            "cleanup",
        ]
    ]
    rows[0]["plan_sha256"] = digest(plan)
    rows[6].update(
        peer=["192.0.2.1", 443],
        hostname="testnet.binance.vision",
        check_hostname=True,
        verify_mode=2,
        version="TLSv1.3",
        certificate_der_b64=base64.b64encode(b"fixture-certificate").decode(),
    )
    rows[7].update(
        method="GET",
        authority="testnet.binance.vision",
        path="/api/v3/exchangeInfo",
        documented_weight=20,
    )
    rows[8].update(size=len(response), sha256=digest(response))
    rows[9].update(status=200, headers=pairs, body_length=len(body), body_sha256=digest(body))
    rows[11].update(gets=1, network_admitted=False)
    rows[12]["errors"] = []
    return plan, rows, response


def test_complete_capture_is_evidence_only(capture):
    plan, rows, response = capture
    result = review(plan, encode(rows), response)
    assert result["status"] == "completed_original_rest_bootstrap_replayed"
    assert result["get_preparations"] == 1
    assert not any(
        result[k]
        for k in [
            "network_admitted",
            "trading_admitted",
            "restart_allowed",
            "pre_request_capacity_verified",
        ]
    )


@pytest.mark.parametrize(
    "mutation",
    ["peer", "tls", "body", "method", "weight", "count", "admission", "chunk_order", "duplicate"],
)
def test_rehashed_semantic_corruption_rejected(capture, mutation):
    plan, rows, response = copy.deepcopy(capture)
    if mutation == "peer":
        rows[6]["peer"][0] = "192.0.2.2"
    elif mutation == "tls":
        rows[6]["check_hostname"] = False
    elif mutation == "body":
        rows[9]["body_sha256"] = "0" * 64
    elif mutation == "method":
        rows[7]["method"] = "POST"
    elif mutation == "weight":
        rows[7]["documented_weight"] = 1
    elif mutation == "count":
        rows[11]["gets"] = True
    elif mutation == "admission":
        rows[11]["network_admitted"] = True
    elif mutation == "chunk_order":
        rows.insert(7, rows.pop(8))
    elif mutation == "duplicate":
        rows.insert(8, rows[7].copy())
    with pytest.raises(ValueError):
        review(plan, encode(rows), response)


def test_rehashed_length_mismatch_rejected(capture):
    plan, rows, response = capture
    old = rows[9]["headers"][0][1]
    response = response.replace(f"Content-Length: {old}".encode(), b"Content-Length: 1")
    rows[9]["headers"][0][1] = "1"
    rows[8].update(size=len(response), sha256=digest(response))
    with pytest.raises(ValueError):
        review(plan, encode(rows), response)


def test_partial_capture_cannot_resume(capture):
    plan, rows, response = capture
    rows = rows[:9] + [{"kind": "failed"}, {"kind": "cleanup", "errors": []}]
    result = review(plan, encode(rows), response)
    assert result["status"] == "incomplete_or_failed_consumed_no_retry"
    assert result["http_status"] == 200
    assert result["rates"] is None
    assert result["restart_allowed"] is False


def test_unreceipted_bytes_rejected(capture):
    plan, rows, response = capture
    with pytest.raises(ValueError):
        review(plan, encode(rows), response + b"trailing")


def test_pinned_reader_refuses_changed_bytes_and_symlink(tmp_path):
    path = tmp_path / "response"
    path.write_bytes(b"original")
    assert pinned(path, digest(b"original")) == b"original"
    with pytest.raises(ValueError):
        pinned(path, digest(b"changed"))
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        pinned(link, digest(b"original"))

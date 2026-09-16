"""Offline review of pinned original one-shot bootstrap receipts and HTTP bytes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import stat
from pathlib import Path

from apps.strategies_nautilus.portfolio_rate_evidence import rest_rate_evidence
from apps.strategies_nautilus.portfolio_tls_provenance import _validate_response, response_headers

LIMIT = 16 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    import os

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError("regular_bounded_artifact_required")
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT or digest(raw) != expected:
        raise ValueError("artifact_pin_mismatch")
    return raw


def review(plan_raw, events_raw, response_raw):
    if max(len(plan_raw), len(events_raw), len(response_raw)) > LIMIT:
        raise ValueError("review_limit")
    plan = json.loads(plan_raw)
    if (
        plan["schema_version"] != "portfolio.egress_bootstrap_execution.v1"
        or plan["scope"] != "portfolio.testnet_rest_bootstrap.v1"
    ):
        raise ValueError("bootstrap_plan_schema")
    rows = []
    previous = None
    for line in events_raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            type(row["seq"]) is not int
            or row["seq"] != len(rows)
            or row["previous_sha256"] != previous
            or line
            != (
                json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
            ).encode()
        ):
            raise ValueError("receipt_chain")
        if any(
            type(row[key]) is not int or row[key] <= 0 for key in ("utc_ns", "monotonic_ns")
        ) or (rows and row["monotonic_ns"] < rows[-1]["monotonic_ns"]):
            raise ValueError("receipt_clock")
        previous = digest(line)
        rows.append(row)
    kinds = [row["kind"] for row in rows]
    if not rows or kinds[0] != "scope_consumed" or rows[0]["plan_sha256"] != digest(plan_raw):
        raise ValueError("scope_binding")
    for kind in (
        "tcp_prepared",
        "tls_verified",
        "get_prepared",
        "response_complete",
        "completed",
        "cleanup",
    ):
        if kinds.count(kind) > 1:
            raise ValueError("repeated_operation")
    offset = 0
    for row in rows:
        if row["kind"] == "response_chunk":
            if type(row["size"]) is not int or not 0 < row["size"] <= 4096:
                raise ValueError("chunk_size")
            data = response_raw[offset : offset + row["size"]]
            if len(data) != row["size"] or digest(data) != row["sha256"]:
                raise ValueError("chunk_original_changed")
            offset += row["size"]
    if offset != len(response_raw):
        raise ValueError("unreceipted_response_bytes")
    result = {
        "schema_version": "portfolio.rest_bootstrap_replay.v1",
        "scope_consumed": True,
        "restart_allowed": False,
        "network_admitted": False,
        "trading_admitted": False,
        "pre_request_capacity_verified": False,
        "joint_capture_admitted": False,
        "plan_sha256": digest(plan_raw),
        "events_sha256": digest(events_raw),
        "response_sha256": digest(response_raw),
        "tcp_preparations": kinds.count("tcp_prepared"),
        "get_preparations": kinds.count("get_prepared"),
        "terminal_kind": kinds[-1],
        "status": "incomplete_or_failed_consumed_no_retry",
        "rates": None,
        "http_status": None,
    }
    if b"\r\n\r\n" in response_raw:
        header, body = response_raw.split(b"\r\n\r\n", 1)
        status, pairs = response_headers(header + b"\r\n\r\n")
        result["http_status"] = status
    expected = [
        "scope_consumed",
        "topology_prepared",
        "child_ready",
        "window_prepared",
        "window_active",
        "tcp_prepared",
        "tls_verified",
        "get_prepared",
        "response_complete",
        "child_transport_closed",
        "completed",
        "cleanup",
    ]
    semantic = [row for row in rows if row["kind"] != "response_chunk"]
    if [row["kind"] for row in semantic] != expected or semantic[-1]["errors"]:
        return result
    received = semantic[-4]
    tls = semantic[6]
    if any(
        not kinds.index("get_prepared") < index < kinds.index("response_complete")
        for index, kind in enumerate(kinds)
        if kind == "response_chunk"
    ):
        raise ValueError("chunk_order")
    if (
        result["http_status"] != 200
        or received["status"] != 200
        or received["headers"] != pairs
        or received["body_length"] != len(body)
        or received["body_sha256"] != digest(body)
        or len(body) > 8 * 1024 * 1024
        or _validate_response("rest", result["http_status"], pairs, None) != len(body)
    ):
        raise ValueError("complete_response_mismatch")
    if (
        tls["peer"] != [plan["destination_ipv4"], 443]
        or tls["hostname"] != "testnet.binance.vision"
        or tls["check_hostname"] is not True
        or tls["verify_mode"] != 2
        or tls["version"] not in ("TLSv1.2", "TLSv1.3")
    ):
        raise ValueError("tls_receipt_binding")
    if (
        semantic[7]["method"] != "GET"
        or semantic[7]["authority"] != "testnet.binance.vision"
        or semantic[7]["path"] != "/api/v3/exchangeInfo"
        or semantic[7]["documented_weight"] != 20
        or semantic[-2]["gets"] != 1
        or type(semantic[-2]["gets"]) is not int
        or semantic[-2]["network_admitted"] is not False
    ):
        raise ValueError("get_receipt_binding")
    certificate = base64.b64decode(tls["certificate_der_b64"], validate=True)
    if not 0 < len(certificate) <= 8192:
        raise ValueError("certificate_size")
    result.update(
        status="completed_original_rest_bootstrap_replayed",
        rates=rest_rate_evidence(body, pairs),
        certificate_sha256=digest(certificate),
        body_sha256=digest(body),
        body_bytes=len(body),
        tls_version=tls["version"],
        cleanup_verified_in_receipts=True,
        window_to_cleanup_seconds=(semantic[-1]["monotonic_ns"] - semantic[4]["monotonic_ns"])
        / 1e9,
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "events", "response"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            review(
                *(
                    pinned(getattr(args, name), getattr(args, name + "_sha256"))
                    for name in ("plan", "events", "response")
                )
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

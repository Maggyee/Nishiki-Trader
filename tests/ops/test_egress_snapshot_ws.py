"""Original HTTP snapshot anchors and per-symbol revision linkage."""

import base64
import copy
import json
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_market_ws import market_archive, rehash

pytest_plugins = ("tests.ops.test_egress_concurrent_ws",)


def http(code, revision=101):
    body = code.canonical(
        {
            "lastUpdateId": revision,
            "bids": [["100.00000000", "1.00000000"]],
            "asks": [["101.00000000", "2.00000000"]],
        }
    )
    return (
        b"HTTP/1.1 200 OK\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\nX-MBX-USED-WEIGHT-1M: 25\r\nConnection: close\r\n\r\n"
        + body
    )


def anchored_archive(fixture, originals, tmp_path):
    previous = market_archive(fixture, originals, tmp_path)
    code = load("gateway_snapshot_ws")
    market = previous.code.__dict__
    state_type = code.state_type(
        fixture.code.__dict__,
        previous.account.__dict__,
        load("gateway_native_requests").__dict__,
        market,
    )
    state = state_type(fixture.selected, fixture.provenance, fixture.frames)
    rows = []

    def emit(row):
        row = copy.deepcopy(row)
        row["profile"] = code.PROFILE
        state.feed(row["kind"], row["payload"], row["utc_ns"], row["monotonic_ns"])
        rows.append(row)

    for row in previous.rows:
        if row["kind"] == "grant_prepared":
            for symbol in fixture.selected["symbols"]:
                emit(
                    {
                        **row,
                        "kind": "snapshot_connection_prepared",
                        "payload": {
                            "symbol": symbol,
                            "endpoint": f"https://rest.fixture.invalid:23456/api/v3/depth?symbol={symbol}&limit=100",
                            "peer": list(fixture.code.PEER),
                        },
                    }
                )
        if row["kind"] == "close_prepared" and not any(
            r["kind"] == "snapshot_accepted" for r in rows
        ):
            for symbol in fixture.selected["symbols"]:
                tls = {
                    "symbol": symbol,
                    "peer": list(fixture.code.PEER),
                    "server_hostname": "rest.fixture.invalid",
                    "peer_certificate_sha256": "a" * 64,
                    "tls_version": "TLSv1.3",
                    "cipher": ["TLS_AES_256_GCM_SHA384", "TLSv1.3", 256],
                    "check_hostname": True,
                    "verify_mode": "CERT_REQUIRED",
                    "tls_minimum_version": "TLSv1.2",
                }
                req = code.request(symbol)
                data = http(previous.code)
                for kind, payload in (
                    ("snapshot_tls_connected", tls),
                    (
                        "snapshot_request_prepared",
                        {"symbol": symbol, **fixture.provenance.raw_fields(req)},
                    ),
                    (
                        "snapshot_chunk",
                        {"symbol": symbol, **fixture.provenance.raw_fields(data[:45])},
                    ),
                    (
                        "snapshot_chunk",
                        {"symbol": symbol, **fixture.provenance.raw_fields(data[45:])},
                    ),
                    ("snapshot_accepted", {"symbol": symbol}),
                ):
                    emit({**row, "kind": kind, "payload": payload})
        if row["kind"] in {"native_receipt_prepared", "native_acknowledged"}:
            row["payload"] = {
                "payload_sha256": previous.code.digest(state.payload()),
                "native_result": state.native_result(),
            }
        emit(row)
    return SimpleNamespace(
        code=code,
        market=previous.code,
        account=previous.account,
        rows=rows,
        raw=rehash(fixture, rows),
        payload=state.payload(),
        state_type=state_type,
    )


def replay(fixture, archive, raw=None):
    raw = archive.raw if raw is None else raw
    return fixture.code.replay(
        raw,
        expected_sha256=fixture.code.digest(raw),
        selected=fixture.selected,
        provenance=fixture.provenance,
        frames=fixture.frames,
        state_type=archive.state_type,
    )


def test_snapshot_linked_to_original_native_deltas_without_quote_claim(
    fixture, originals, tmp_path
):
    archive = anchored_archive(fixture, originals, tmp_path)
    result = archive.code.validate_native(
        archive.payload,
        lambda raw: archive.market.validate_native(raw, archive.account.validate_native),
        archive.market.__dict__,
    )
    report = replay(fixture, archive)
    assert report["status"] == "complete"
    assert report["native_result"] == result
    assert result["snapshot_linked"] and not result["order_book_synchronized"]
    assert not result["quote_ticks_created"] and not result["qualified_for_execution"]
    assert report["snapshot_attempts_consumed"] == 2
    assert report["snapshots_accepted"] == 2
    assert all(
        a["snapshot_last_update_id"] == 101
        and a["linked_last_update_id"] == 103
        and a["obsolete_events"] == 1
        and len(a["linked_event_sha256"]) == 1
        for a in result["anchors"]
    )


@pytest.mark.parametrize("revision", [99, 100, 103, 104, 2**64, True])
def test_snapshot_revision_requires_buffered_coverage(fixture, originals, tmp_path, revision):
    archive = anchored_archive(fixture, originals, tmp_path)
    value = json.loads(archive.payload)
    item = value["snapshots"][0]["chunks"]
    raw = b"".join(base64.b64decode(chunk["raw_b64"]) for chunk in item)
    body = json.loads(raw.split(b"\r\n\r\n")[1])
    body["lastUpdateId"] = revision
    new_body = archive.market.canonical(body)
    new_raw = http(archive.market, revision)
    assert new_body == new_raw.split(b"\r\n\r\n")[1]
    item[:] = [
        {
            "raw_b64": base64.b64encode(new_raw).decode(),
            "raw_sha256": archive.market.digest(new_raw),
            "receipt": item[0]["receipt"],
        }
    ]
    if revision == 100:
        result = archive.code.expected_result(
            archive.market.canonical(value),
            lambda raw: archive.market.expected_result(raw, archive.account.expected_result),
            archive.market.__dict__,
        )
        assert all(a["linked_last_update_id"] == 103 for a in result["anchors"])
    else:
        with pytest.raises(ValueError):
            archive.code.expected_result(
                archive.market.canonical(value),
                lambda raw: archive.market.expected_result(raw, archive.account.expected_result),
                archive.market.__dict__,
            )


@pytest.mark.parametrize(
    "damage",
    ["duplicate_header", "duplicate_key", "length", "crossed", "unsorted", "rounding"],
)
def test_snapshot_original_rejects_invalid_http_and_depth(fixture, damage):
    code = load("gateway_snapshot_ws")
    raw = http(fixture.code)
    if damage == "duplicate_header":
        raw = raw.replace(b"Connection: close\r\n", b"Connection: close\r\nContent-Length: 1\r\n")
    elif damage == "duplicate_key":
        raw = raw.replace(b'"lastUpdateId":101', b'"lastUpdateId":101,"lastUpdateId":101')
    elif damage == "length":
        raw = raw.replace(b"Content-Length: ", b"Content-Length: 9")
    else:
        body = json.loads(raw.split(b"\r\n\r\n")[1])
        if damage == "crossed":
            body["bids"][0][0] = "102.00000000"
        elif damage == "unsorted":
            body["bids"].append(["103.00000000", "1.00000000"])
        else:
            body["asks"][0][1] = "0.000000001"
        updated = fixture.code.canonical(body)
        raw = (
            raw[: raw.index(b"\r\n\r\n")].replace(
                str(len(raw.split(b"\r\n\r\n")[1])).encode(), str(len(updated)).encode(), 1
            )
            + b"\r\n\r\n"
            + updated
        )
    with pytest.raises(ValueError):
        code.response(raw, load("gateway_market_ws").__dict__)


@pytest.mark.parametrize(
    "damage", ["request", "chunk", "missing", "early_close", "missing_ack", "wrong_native_anchor"]
)
def test_rehashed_snapshot_journal_cannot_forge_completion(fixture, originals, tmp_path, damage):
    archive = anchored_archive(fixture, originals, tmp_path)
    rows = copy.deepcopy(archive.rows)
    target = next(row for row in rows if row["kind"] == "snapshot_request_prepared")
    if damage == "request":
        raw = base64.b64decode(target["payload"]["raw_b64"]).replace(b"limit=100", b"limit=500")
        target["payload"].update(
            raw_b64=base64.b64encode(raw).decode(), raw_sha256=archive.market.digest(raw)
        )
    elif damage == "chunk":
        target = next(row for row in rows if row["kind"] == "snapshot_chunk")
        target["payload"]["raw_sha256"] = "0" * 64
    elif damage == "missing":
        rows.remove(next(row for row in rows if row["kind"] == "snapshot_accepted"))
    elif damage == "early_close":
        target = next(row for row in rows if row["kind"] == "close_prepared")
        rows.remove(target)
        rows.insert(next(i for i, r in enumerate(rows) if r["kind"] == "snapshot_accepted"), target)
    elif damage == "wrong_native_anchor":
        target = next(row for row in rows if row["kind"] == "native_acknowledged")
        target["payload"]["native_result"]["anchors"][0]["linked_last_update_id"] += 1
    else:
        rows.remove(next(row for row in rows if row["kind"] == "native_acknowledged"))
    with pytest.raises(ValueError):
        replay(fixture, archive, rehash(fixture, rows))


def test_every_prefix_consumes_attempt_without_resumption(fixture, originals, tmp_path):
    archive = anchored_archive(fixture, originals, tmp_path)
    lines = archive.raw.splitlines(keepends=True)
    for end in range(1, len(lines)):
        report = replay(fixture, archive, b"".join(lines[:end]))
        assert report["status"] == "incomplete_no_resume" and not report["restart_allowed"]

"""Signed subscription originals, partial balances, revocation and native receipt gates."""

import base64
import copy
import json
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_concurrent_ws import fixture, make_archive, originals, rehash
from tests.ops.test_egress_installed_gateway import load

# Reuse original route fixtures; this is a distinct explicit transport profile.
__all__ = ["fixture", "originals"]


def server_frame(raw):
    return (
        b"\x81"
        + (bytes([len(raw)]) if len(raw) < 126 else b"\x7e" + len(raw).to_bytes(2, "big"))
        + raw
    )


def signed_archive(fixture, tmp_path):
    code, base = load("gateway_account_ws"), fixture.code
    requests = load("gateway_native_requests")
    state_type = code.state_type(base.__dict__, requests.__dict__)
    old = list(map(json.loads, make_archive(fixture, tmp_path).splitlines()))
    now, mono = old[0]["utc_ns"], old[0]["monotonic_ns"]
    challenge = {"index": 2, "nonce": "a" * 32, "utc_ns": now, "monotonic_ns": mono}
    envelope = json.loads(requests.native_request(challenge))
    wire = fixture.frames["client_frame"](code.wire_request(envelope))
    subscription = {
        "challenge": challenge,
        "request": envelope,
        "received": [now, mono],
        **fixture.provenance.raw_fields(wire),
    }
    response = b'{"id":"fixture-2","status":200,"result":{"subscriptionId":0}}'
    event = code.canonical(
        {
            "subscriptionId": 0,
            "event": {
                "e": "outboundAccountPosition",
                "E": 1700000000000,
                "u": 1699999999999,
                "B": [{"a": "BTC", "f": "0.01000000", "l": "0.00100000"}],
            },
        }
    )

    def row(kind, payload):
        return {
            "kind": kind,
            "payload": payload,
            "utc_ns": now,
            "monotonic_ns": mono,
            "profile": code.PROFILE,
        }

    process = {
        "pid": 99,
        "start_ticks": 100,
        "namespaces": {"net": "net:[2]"},
        "native_runtime_sha256": "c" * 64,
    }
    fixture.selected = code.selection(
        fixture.selected,
        [
            {
                "binding": code.canonical(
                    {"collector": {"process": process}, "net": "net:[1]"}
                ).decode()
            }
        ],
    )
    old[0]["payload"] = fixture.selected
    selected = state_type(fixture.selected, fixture.provenance, fixture.frames)
    rows = []

    def emit(r):
        r = copy.deepcopy(r)
        r["profile"] = code.PROFILE
        selected.feed(r["kind"], r["payload"], r["utc_ns"], r["monotonic_ns"])
        rows.append(r)

    inserted = False
    for r in old:
        if r["kind"] == "close_prepared" and not inserted:
            emit(row("subscription_prepared", subscription))
            for kind, raw in (("subscription_accepted", response), ("account_event", event)):
                emit(
                    row(
                        "response_chunk",
                        {"role": "account", **fixture.provenance.raw_fields(server_frame(raw))},
                    )
                )
                emit(
                    row(
                        kind,
                        {
                            **fixture.provenance.raw_fields(raw),
                            "receipt": {"utc_ns": now, "monotonic_ns": mono},
                        },
                    )
                )
            inserted = True
        if r["kind"] == "completed":
            payload = selected.payload()
            fields = {
                "payload_sha256": code.digest(payload),
                "native_result": code.expected_result(payload),
            }
            emit(row("native_receipt_prepared", fields))
            emit(row("native_acknowledged", fields))
        emit(r)
        if r["kind"] == "started":
            emit(row("signer_prepared", {"launcher_source_sha256": "a" * 64, "process": process}))
    return SimpleNamespace(
        code=code,
        state_type=state_type,
        rows=rows,
        raw=rehash(fixture, rows),
        payload=selected.payload(),
    )


def review(fixture, artifact, raw=None):
    raw = artifact.raw if raw is None else raw
    return fixture.code.replay(
        raw,
        expected_sha256=fixture.code.digest(raw),
        selected=fixture.selected,
        provenance=fixture.provenance,
        frames=fixture.frames,
        state_type=artifact.state_type,
    )


def test_signed_originals_map_only_changed_assets_and_preserve_event_clocks(fixture, tmp_path):
    archive = signed_archive(fixture, tmp_path)
    report = review(fixture, archive)
    assert report["status"] == "complete" and report["native_events_delivered"]
    assert report["fixture_subscription_acknowledged"]
    result = archive.code.validate_native(archive.payload)
    assert result == report["native_result"]
    assert len(result["balances"]) == 1
    assert result["balances"][0]["total"] == "0.01100000"
    assert result["partial_update"] and result["account_uid"] is None
    assert not result["full_account_snapshot"] and not result["stream_fence_verified"]
    assert not result["qualified_for_execution"] and not report["network_admitted"]


def test_every_signed_prefix_stays_incomplete_and_nonresumable(fixture, tmp_path):
    archive = signed_archive(fixture, tmp_path)
    lines = archive.raw.splitlines(keepends=True)
    for end in range(1, len(lines)):
        report = review(fixture, archive, b"".join(lines[:end]))
        assert report["status"] == "incomplete_no_resume"
        assert not report["restart_allowed"]


@pytest.mark.parametrize(
    "damage",
    [
        "method",
        "signature",
        "wire",
        "expired",
        "receipt_clock",
        "duplicate_subscription",
        "missing_response",
        "response_id",
        "wrong_subscription",
        "extra_event",
        "no_revoke",
        "early_delivery",
        "missing_ack",
        "duplicate_ack",
        "wrong_native_balance",
        "late_ack",
        "text_on_market",
        "signer_runtime",
        "signer_namespace",
        "signer_pid",
    ],
)
def test_rehashed_signed_archive_tampering_refused(fixture, tmp_path, damage):
    archive = signed_archive(fixture, tmp_path)
    rows = copy.deepcopy(archive.rows)

    def row(kind):
        return next(r for r in rows if r["kind"] == kind)

    selected = row("subscription_prepared")["payload"]
    if damage.startswith("signer_"):
        process = row("signer_prepared")["payload"]["process"]
        if damage == "signer_runtime":
            process["native_runtime_sha256"] = "b" * 64
        elif damage == "signer_namespace":
            process["namespaces"]["net"] = fixture.selected["root_network_namespace"]
        else:
            process["pid"] = False
    elif damage == "method":
        selected["request"]["request"]["method"] = "order.place"
    elif damage == "signature":
        selected["request"]["request"]["params"]["signature"] = base64.b64encode(bytes(64)).decode()
    elif damage == "wire":
        selected.update(fixture.provenance.raw_fields(fixture.frames["client_frame"](b"{}")))
    elif damage == "expired":
        selected["challenge"]["utc_ns"] -= 6_000_000_000
        selected["challenge"]["monotonic_ns"] -= 6_000_000_000
    elif damage == "receipt_clock":
        row("account_event")["payload"]["receipt"]["utc_ns"] += 1
    elif damage in {"duplicate_subscription", "duplicate_ack"}:
        target = row(
            "subscription_prepared" if damage == "duplicate_subscription" else "native_acknowledged"
        )
        rows.insert(rows.index(target) + 1, copy.deepcopy(target))
    elif damage in {"missing_response", "no_revoke", "missing_ack"}:
        rows.remove(
            row(
                {
                    "missing_response": "subscription_accepted",
                    "no_revoke": "revoked",
                    "missing_ack": "native_acknowledged",
                }[damage]
            )
        )
    elif damage in {"response_id", "wrong_subscription", "extra_event", "text_on_market"}:
        target = row("subscription_accepted" if damage == "response_id" else "account_event")
        raw = fixture.code.original(target["payload"])
        if damage == "response_id":
            raw = raw.replace(b"fixture-2", b"fixture-1")
        elif damage == "wrong_subscription":
            raw = raw.replace(b'"subscriptionId":0', b'"subscriptionId":1')
        index = rows.index(target) - 1
        chunk = rows[index]
        assert chunk["kind"] == "response_chunk"
        if damage == "extra_event":
            raw = server_frame(raw) * 2
        elif damage == "text_on_market":
            chunk["payload"]["role"] = "market"
            raw = server_frame(raw)
        else:
            target["payload"].update(fixture.provenance.raw_fields(raw))
            raw = server_frame(raw)
        chunk["payload"].update(fixture.provenance.raw_fields(raw))
    elif damage == "early_delivery":
        target = row("native_receipt_prepared")
        rows.remove(target)
        rows.insert(rows.index(row("revoked")), target)
    elif damage == "wrong_native_balance":
        row("native_acknowledged")["payload"]["native_result"]["balances"][0]["free"] = "100"
    elif damage == "late_ack":
        for r in rows[rows.index(row("native_acknowledged")) :]:
            r["utc_ns"] += 5_000_000_000
            r["monotonic_ns"] += 5_000_000_000
    with pytest.raises((ValueError, KeyError)):
        review(fixture, archive, rehash(fixture, rows))


@pytest.mark.parametrize(
    "damage",
    [
        "rounding",
        "negative",
        "duplicate_asset",
        "foreign_asset",
        "bool_time",
        "bool_subscription",
        "bad_update_time",
        "full_snapshot",
        "duplicate_key",
    ],
)
def test_partial_event_rejects_ambiguity_and_rounding(fixture, tmp_path, damage):
    archive = signed_archive(fixture, tmp_path)
    value = json.loads(archive.payload)
    event = json.loads(base64.b64decode(value["event_b64"]))
    row = event["event"]
    if damage == "rounding":
        row["B"][0]["f"] = "0.000000001"
    elif damage == "negative":
        row["B"][0]["l"] = "-1"
    elif damage == "duplicate_asset":
        row["B"] *= 2
    elif damage == "foreign_asset":
        row["B"][0]["a"] = "FOREIGN"
    elif damage == "bool_time":
        row["E"] = True
    elif damage == "bool_subscription":
        event["subscriptionId"] = False
    elif damage == "bad_update_time":
        row["u"] = row["E"] + 1
    elif damage == "full_snapshot":
        row["balances"] = row.pop("B")
    raw = archive.code.canonical(event)
    if damage == "duplicate_key":
        raw = raw.replace(b'"subscriptionId":0', b'"subscriptionId":0,"subscriptionId":0')
    value["event_b64"] = base64.b64encode(raw).decode()
    with pytest.raises(ValueError):
        archive.code.validate_native(archive.code.canonical(value))


def test_verification_cost_cannot_extend_original_signing_window(monkeypatch):
    code = load("gateway_account_ws")
    session = object.__new__(code.Session)
    challenge = {"utc_ns": 1, "monotonic_ns": 1}
    session.subscription = {"request": {}, "challenge": challenge}
    ticks = [1]

    def verify(*args, **kwargs):
        ticks[0] += 5_000_000_000

    session.collector = SimpleNamespace(verify=lambda: None)
    session.requests = {"validate_request": verify}
    monkeypatch.setattr(
        code,
        "time",
        SimpleNamespace(
            time_ns=lambda: ticks[0],
            monotonic_ns=lambda: ticks[0],
            monotonic=lambda: ticks[0] / 1e9,
        ),
    )
    with pytest.raises(ValueError, match="expired_before_wire"):
        session.before_wire(10)


def test_root_cannot_import_native(monkeypatch):
    code = load("gateway_account_ws")
    monkeypatch.setattr(code.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root"):
        code.validate_native(b"{}")

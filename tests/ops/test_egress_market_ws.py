"""Unanchored depth segments, exact native deltas and bound joint receipts."""

import base64
import copy
import json
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_account_ws import server_frame, signed_archive
from tests.ops.test_egress_concurrent_ws import fixture, originals, rehash
from tests.ops.test_egress_installed_gateway import load

__all__ = ["fixture", "originals"]


def update(code, symbol, index, receipt):
    raw = code.canonical(
        {
            "stream": symbol.lower() + "@depth@100ms",
            "data": {
                "e": "depthUpdate",
                "E": 1700000000000 + index,
                "s": symbol,
                "U": 100 + index * 2,
                "u": 101 + index * 2,
                "b": [["100.00000000", "1.00000000" if index == 0 else "0.00000000"]],
                "a": [["101.00000000", "2.00000000"]],
            },
        }
    )
    return {
        "raw_b64": base64.b64encode(raw).decode(),
        "raw_sha256": code.digest(raw),
        "receipt": receipt,
    }


def market_archive(fixture, originals, tmp_path):
    previous = signed_archive(fixture, tmp_path)
    code = load("gateway_market_ws")
    fixture.selected = code.selection(fixture.selected, originals.bundles)
    state_type = code.state_type(
        fixture.code.__dict__, previous.code.__dict__, load("gateway_native_requests").__dict__
    )
    state = state_type(fixture.selected, fixture.provenance, fixture.frames)
    rows = []
    inserted = False

    def emit(row):
        row = copy.deepcopy(row)
        row["profile"] = code.PROFILE
        state.feed(row["kind"], row["payload"], row["utc_ns"], row["monotonic_ns"])
        rows.append(row)

    for row in previous.rows:
        if row["kind"] == "started":
            row["payload"] = fixture.selected
        if row["kind"] == "close_prepared" and not inserted:
            for index in range(2):
                for symbol in fixture.selected["symbols"]:
                    event = update(
                        code, symbol, index, {k: row[k] for k in ("utc_ns", "monotonic_ns")}
                    )
                    raw = base64.b64decode(event["raw_b64"])
                    emit(
                        {
                            **row,
                            "kind": "response_chunk",
                            "payload": {
                                "role": "market",
                                **fixture.provenance.raw_fields(server_frame(raw)),
                            },
                        }
                    )
                    emit({**row, "kind": "market_event", "payload": event})
            inserted = True
        if row["kind"] in {"native_receipt_prepared", "native_acknowledged"}:
            row["payload"] = {
                "payload_sha256": code.digest(state.payload()),
                "native_result": state.native_result(),
            }
        emit(row)
    return SimpleNamespace(
        code=code,
        account=previous.code,
        state_type=state_type,
        raw=rehash(fixture, rows),
        rows=rows,
        payload=state.payload(),
    )


def review(fixture, archive, raw=None):
    raw = archive.raw if raw is None else raw
    return fixture.code.replay(
        raw,
        expected_sha256=fixture.code.digest(raw),
        selected=fixture.selected,
        provenance=fixture.provenance,
        frames=fixture.frames,
        state_type=archive.state_type,
    )


def test_actual_native_delta_batches_preserve_deletions_and_original_times(
    fixture, originals, tmp_path
):
    archive = market_archive(fixture, originals, tmp_path)
    report = review(fixture, archive)
    actual = archive.code.validate_native(archive.payload, archive.account.validate_native)
    assert actual == report["native_result"]
    assert report["status"] == "complete" and report["market_native_acknowledged"]
    assert report["market_events_recorded"] == 4
    assert actual["unanchored_depth_segment"]
    assert not any(
        actual[k]
        for k in (
            "snapshot_linked",
            "order_book_synchronized",
            "quote_ticks_created",
            "tick_size_validated",
            "qualified_for_execution",
        )
    )
    assert actual["account"]["partial_update"]
    for index, event in enumerate(actual["market"]):
        deltas = event["deltas"]
        assert [d["flags"] for d in deltas] == [0, 128]
        assert [d["order"]["side"] for d in deltas] == ["BUY", "SELL"]
        assert deltas[0]["action"] == ("UPDATE" if index < 2 else "DELETE")
        for delta in deltas:
            assert delta["sequence"] == event["last_update_id"]
            assert delta["ts_init"] == event["receipt"]["utc_ns"]
            assert delta["ts_event"] == (1700000000000 + (index // 2)) * 1_000_000


def test_each_joint_archive_prefix_remains_incomplete(fixture, originals, tmp_path):
    archive = market_archive(fixture, originals, tmp_path)
    lines = archive.raw.splitlines(keepends=True)
    for end in range(1, len(lines)):
        report = review(fixture, archive, b"".join(lines[:end]))
        assert report["status"] == "incomplete_no_resume" and not report["restart_allowed"]


@pytest.mark.parametrize(
    "damage",
    [
        "symbol",
        "stream",
        "range",
        "gap",
        "duplicate_update",
        "precision",
        "negative_size",
        "zero_price",
        "duplicate_level",
        "bool_id",
        "overflow_id",
        "overflow_time",
        "backward_event_time",
        "empty",
        "too_many_levels",
        "duplicate_key",
        "missing_symbol",
        "too_many_events",
        "receipt_clock",
        "metadata_precision",
    ],
)
def test_market_payload_refuses_ambiguous_unselected_or_broken_segments(
    fixture, originals, tmp_path, damage
):
    archive = market_archive(fixture, originals, tmp_path)
    payload = json.loads(archive.payload)
    item = payload["events"][2]
    value = json.loads(base64.b64decode(item["raw_b64"]))
    event = value["data"]
    if damage == "symbol":
        event["s"] = "FOREIGN"
    elif damage == "stream":
        value["stream"] = "foreign@depth@100ms"
    elif damage == "range":
        event["U"] = 104
    elif damage == "gap":
        event.update(U=104, u=105)
    elif damage == "duplicate_update":
        event.update(U=100, u=101)
    elif damage == "precision":
        event["a"][0][1] = "0.000000001"
    elif damage == "negative_size":
        event["a"][0][1] = "-1"
    elif damage == "zero_price":
        event["a"][0][0] = "0"
    elif damage == "duplicate_level":
        event["a"] *= 2
    elif damage == "bool_id":
        event["U"] = True
    elif damage == "overflow_id":
        event["u"] = 2**64
    elif damage == "overflow_time":
        event["E"] = 2**64
    elif damage == "backward_event_time":
        event["E"] = 1
    elif damage == "empty":
        event.update(a=[], b=[])
    elif damage == "too_many_levels":
        event["a"] *= 5
    elif damage == "missing_symbol":
        payload["events"] = payload["events"][:-1]
    elif damage == "too_many_events":
        payload["events"].append(copy.deepcopy(payload["events"][0]))
    elif damage == "receipt_clock":
        item["receipt"]["utc_ns"] -= 1
    elif damage == "metadata_precision":
        payload["definitions"][0]["price_precision"] = 9
    raw = archive.code.canonical(value)
    if damage == "duplicate_key":
        raw = raw.replace(b'"U":102', b'"U":102,"U":102')
    item.update(raw_b64=base64.b64encode(raw).decode(), raw_sha256=archive.code.digest(raw))
    with pytest.raises(ValueError):
        archive.code.expected_result(
            archive.code.canonical(payload), archive.account.expected_result
        )


def test_overlap_segment_advances_without_claiming_snapshot_bootstrap(fixture, originals, tmp_path):
    archive = market_archive(fixture, originals, tmp_path)
    payload = json.loads(archive.payload)
    for item in payload["events"][2:]:
        value = json.loads(base64.b64decode(item["raw_b64"]))
        value["data"]["U"] = 101
        raw = archive.code.canonical(value)
        item.update(raw_b64=base64.b64encode(raw).decode(), raw_sha256=archive.code.digest(raw))
    result = archive.code.validate_native(
        archive.code.canonical(payload), archive.account.validate_native
    )
    assert all(v["first_update_id"] == 101 for v in result["market"][2:])
    assert not result["snapshot_linked"]


@pytest.mark.parametrize(
    "damage",
    [
        "receipt",
        "event_original",
        "early_close",
        "missing_ack",
        "market_tail",
        "wrong_native",
        "missing_revoke",
    ],
)
def test_rehashed_joint_journal_cannot_forge_market_receipts(fixture, originals, tmp_path, damage):
    archive = market_archive(fixture, originals, tmp_path)
    rows = copy.deepcopy(archive.rows)

    def row(kind):
        return next(r for r in rows if r["kind"] == kind)

    if damage == "receipt":
        row("market_event")["payload"]["receipt"]["utc_ns"] += 1
    elif damage == "event_original":
        r = row("market_event")["payload"]
        raw = base64.b64decode(r["raw_b64"]).replace(b"100.00000000", b"200.00000000")
        r.update(raw_b64=base64.b64encode(raw).decode(), raw_sha256=archive.code.digest(raw))
    elif damage == "early_close":
        r = row("close_prepared")
        rows.remove(r)
        rows.insert(rows.index(row("market_event")), r)
    elif damage == "missing_ack":
        rows.remove(row("native_acknowledged"))
    elif damage == "missing_revoke":
        rows.remove(row("revoked"))
    elif damage == "market_tail":
        target = next(
            r
            for r in rows
            if r["kind"] == "response_chunk"
            and r["payload"]["role"] == "market"
            and fixture.code.original(r["payload"]) == b"\x88\x02\x03\xe8"
        )
        target["payload"].update(
            fixture.provenance.raw_fields(server_frame(b"{}") + b"\x88\x02\x03\xe8")
        )
    else:
        row("native_acknowledged")["payload"]["native_result"]["market"][0]["deltas"][0][
            "sequence"
        ] += 1
    with pytest.raises(ValueError):
        review(fixture, archive, rehash(fixture, rows))


def test_root_native_mapping_refused(monkeypatch):
    code = load("gateway_market_ws")
    monkeypatch.setattr(code.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root"):
        code.validate_native(b"{}", lambda _: None)


def test_original_metadata_precision_required(fixture, originals):
    code = load("gateway_market_ws")
    selected = dict(fixture.selected, symbols=["FOREIGN"])
    with pytest.raises(ValueError, match="original_metadata"):
        code.selection(selected, originals.bundles)

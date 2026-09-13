"""Detached depth semantics and durable native replay acceptance."""

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from apps.strategies_nautilus import portfolio_market_depth as core
from apps.strategies_nautilus import portfolio_market_depth_archive as archive
from apps.strategies_nautilus.portfolio_stream import canonical

BASE = 1_800_000_000_000_000_000


def metadata():
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
                "baseAssetPrecision": 8,
                "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"}],
            }
        ],
        "rateLimits": [
            {
                "rateLimitType": "REQUEST_WEIGHT",
                "interval": "MINUTE",
                "intervalNum": 1,
                "limit": 6000,
            }
        ],
    }


def delta(first=99, last=102, **fields):
    return {
        "e": "depthUpdate",
        "s": "BTCUSDT",
        "E": BASE // 1_000_000,
        "U": first,
        "u": last,
        "b": [["99", "3"]],
        "a": [],
        **fields,
    }


def snapshot(**fields):
    return {
        "lastUpdateId": 100,
        "bids": [["99", "1"], ["98", "2"]],
        "asks": [["101", "4"], ["102", "5"]],
        **fields,
    }


def event(book, data=None, now=BASE, size=200):
    book.event(data or delta(), received_ns=now, now_ns=now, raw_size=size)


def linked():
    book = core.DepthBook(metadata())
    event(book)
    book.snapshot(snapshot(), now_ns=BASE)
    return book


def test_native_replacement_delete_and_original_event_time():
    book = linked()
    quote = book.quotes[0]
    assert quote["bid_price"] == "99.00" and quote["bid_size"] == "3.00000000"
    assert quote["ts_event"] == BASE and quote["ts_init"] == BASE
    event(book, delta(103, 105, b=[["99", "0"]], E=BASE // 1_000_000 + 1), now=BASE + 2_000_000)
    assert book.quotes[-1]["bid_price"] == "98.00"
    assert book.quotes[-1]["ts_event"] == BASE + 1_000_000
    assert book.quotes[-1]["ts_init"] == BASE + 2_000_000
    assert book.summary()["native_quote_count"] == 2
    assert book.summary()["last_quote_age_at_receipt_ns"] == 1_000_000


def test_obsolete_duplicate_does_not_refresh():
    book = linked()
    event(book, now=BASE + core.SECOND)
    assert len(book.quotes) == 1 and book.obsolete == 1
    with pytest.raises(core.DepthError, match="quiet_depth_expired"):
        book.check_age(BASE + core.MAX_AGE + 1)
    assert not book.summary()["locally_linked"]


@pytest.mark.parametrize(
    "data,code",
    [
        (delta(104, 105), "depth_sequence_gap"),
        (delta(b=[["99", "7"]]), "conflicting_depth_range"),
        (delta(103, 104, E=BASE // 1_000_000 - 1), "stale_or_regressing"),
        (delta(103, 104, E=BASE // 1_000_000 + 1), "future_or_stale"),
        (delta(103, 104, E=BASE // 1_000_000 - 5001), "future_or_stale"),
        (delta(103, 104, E=BASE), "future_or_stale"),
        (delta(103, 104, s="ETHUSDT"), "unexpected_depth_frame"),
        (delta(103, 104, e="serverShutdown"), "unexpected_depth_frame"),
        (delta(True, 104), "invalid_integer"),
        (delta(104, 103), "invalid_depth_range"),
        (delta(103, 104, b=[["99", "NaN"]]), "invalid_decimal"),
        (delta(103, 104, b=[["99", "-1"]]), "invalid_decimal"),
        (delta(103, 104, b=[["0", "1"]]), "invalid_decimal"),
        (delta(103, 104, b=[["99.001", "1"]]), "native_depth_rounding"),
        (delta(103, 104, b=[["99", "1"], ["99", "2"]]), "duplicate_depth_price"),
        (delta(103, 104, b=[["101", "1"]]), "crossed_depth_book"),
        (delta(103, 104, a=[["101", "0"], ["102", "0"]]), "empty_depth_side"),
    ],
)
def test_invalid_event_poison_without_new_quote(data, code):
    book = linked()
    with pytest.raises(core.DepthError, match=code):
        event(book, data)
    assert len(book.quotes) == 1 and not book.summary()["locally_linked"]
    with pytest.raises(core.DepthError):
        event(book, delta(103, 104))


@pytest.mark.parametrize(
    "first,last,last_id,code",
    [
        (99, 102, 98, "snapshot_behind"),
        (99, 100, 100, "bootstrap_boundary"),
    ],
)
def test_bootstrap_refusals(first, last, last_id, code):
    book = core.DepthBook(metadata())
    event(book, delta(first, last))
    with pytest.raises(core.DepthError, match=code):
        book.snapshot(snapshot(lastUpdateId=last_id), now_ns=BASE)
        event(book, delta(101, 103))
    assert not book.quotes


def test_buffer_overlap_gap_and_finite_snapshot_frontier():
    book = core.DepthBook(metadata())
    event(book, delta(99, 100))
    event(book, delta(100, 102))
    book.snapshot(snapshot(), now_ns=BASE)
    assert book.obsolete == 1 and len(book.quotes) == 1
    book = core.DepthBook(metadata())
    bids = [[str(p), "1"] for p in range(100, 0, -1)]
    event(book, delta(b=[]))
    book.snapshot(snapshot(bids=bids), now_ns=BASE)
    with pytest.raises(core.DepthError, match="snapshot_coverage_exhausted"):
        event(book, delta(103, 104, b=[[p, "0"] for p, _ in bids] + [["0.50", "2"]]))
    assert len(book.quotes) == 1


@pytest.mark.parametrize("limit,value", [("MAX_BUFFER", 199), ("MAX_EVENTS", 0)])
def test_buffer_bounds(monkeypatch, limit, value):
    monkeypatch.setattr(core, limit, value)
    with pytest.raises(core.DepthError, match="depth_buffer_exceeded"):
        event(core.DepthBook(metadata()))


class ReceiptClock:
    def __init__(self):
        self.now = BASE

    def __call__(self):
        self.now += 10_000_000
        return self.now, self.now - BASE + core.SECOND


def body_fields(body):
    raw = body if isinstance(body, bytes) else canonical(body)
    return {
        "raw_b64": base64.b64encode(raw).decode(),
        "body_sha256": hashlib.sha256(raw).hexdigest(),
    }


def response(journal, body):
    path, params, _ = archive.REQUESTS[journal.state.requests]
    sent, mono = journal.clock()
    if path.endswith("/time") and body is None:
        body = {"serverTime": sent // 1_000_000 + 5}
    journal.append(
        "rest_response",
        path=path,
        params=params,
        sent_ns=sent,
        sent_monotonic_ns=mono,
        status=200,
        headers={"x-mbx-used-weight-1m": "28"},
        **body_fields(body),
    )


def open_journal(tmp_path):
    journal = archive.DepthJournal(tmp_path / "depth.jsonl", epoch="fixture", clock=ReceiptClock())
    response(journal, None)
    response(journal, metadata())
    journal.append("connected")
    return journal


def complete_archive(tmp_path):
    journal = open_journal(tmp_path)
    journal.append("depth_frame", **body_fields(delta()))
    response(journal, snapshot())
    response(journal, None)
    journal.append("depth_frame", **body_fields(delta(103, 104, b=[["99", "2"]])))
    response(journal, None)
    journal.append("transport_closed")
    journal.append("completed", result=journal.state.summary())
    journal.close()
    return (tmp_path / "depth.jsonl").read_bytes()


def replay(raw):
    return archive.replay_depth(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


def rechain(rows):
    previous = "0" * 64
    result = b""
    for seq, row in enumerate(rows):
        row.pop("sha256", None)
        row.update(seq=seq, previous=previous)
        previous = hashlib.sha256(canonical(row)).hexdigest()
        result += canonical(row | {"sha256": previous}) + b"\n"
    return result


def test_closed_archive_two_fresh_processes(tmp_path):
    raw = complete_archive(tmp_path)
    result = replay(raw)
    assert result["summary"]["native_quote_count"] == 2
    assert result["historical_replay_only"]
    assert all(result[key] is False for key in archive.flags())
    reports = []
    for n in range(2):
        path = tmp_path / f"replay{n}.json"
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(s in k.upper() for s in ("BINANCE", "API_KEY", "SECRET"))
        }
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_market_depth",
                "--replay",
                "--archive",
                str(tmp_path / "depth.jsonl"),
                "--archive-sha256",
                hashlib.sha256(raw).hexdigest(),
                "--report",
                str(path),
            ],
            capture_output=True,
            env=env,
            timeout=20,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        reports.append(path.read_bytes())
    assert reports[0] == reports[1] and json.loads(reports[0]) == result
    assert (tmp_path / "depth.jsonl").read_bytes() == raw


@pytest.mark.parametrize(
    "damage",
    [
        "truncate",
        "unsealed",
        "tail",
        "bytes",
        "source",
        "epoch",
        "unit",
        "gap",
        "clock",
        "time_sample",
        "weight",
        "selector",
        "summary",
        "raw_hash",
        "status",
        "bootstrap_deadline",
    ],
)
def test_replay_rejects_integrity_and_semantic_damage(tmp_path, damage):
    raw = complete_archive(tmp_path)
    rows = [json.loads(line) for line in raw.splitlines()]
    if damage == "truncate":
        raw = raw[:-1]
    elif damage == "unsealed":
        raw = rechain(rows[:-1])
    elif damage == "tail":
        raw = rechain(rows + [copy.deepcopy(rows[-1])])
    elif damage == "bytes":
        raw = raw.replace(b"BTCUSDT", b"ETHUSDT", 1)
    else:
        if damage == "source":
            rows[3]["source"]["rest"] = "https://api.binance.com"
        elif damage == "epoch":
            rows[4]["epoch"] = "other"
        elif damage == "unit":
            rows[4].update(body_fields(delta(E=BASE)))
        elif damage == "gap":
            rows[7].update(body_fields(delta(105, 106)))
        elif damage == "clock":
            rows[4]["received_ns"] += 51_000_000
        elif damage == "time_sample":
            rows[1].update(body_fields({"serverTime": BASE // 1_000_000 + 1000}))
        elif damage == "weight":
            rows[2]["headers"]["x-mbx-used-weight-1m"] = "6000"
        elif damage == "selector":
            rows[1]["path"] = "/api/v3/account"
        elif damage == "summary":
            rows[-1]["result"]["native_quote_count"] = 10
        elif damage == "raw_hash":
            rows[4]["body_sha256"] = "0" * 64
        elif damage == "status":
            rows[1]["status"] = 200.0
        elif damage == "bootstrap_deadline":
            for row in rows[4:]:
                row["received_ns"] += 16 * core.SECOND
                row["monotonic_ns"] += 16 * core.SECOND
        raw = rechain(rows)
    with pytest.raises(core.DepthError, match="depth_archive_replay_failed"):
        replay(raw)


def test_raw_invalid_utf8_precedes_parsing_and_cannot_seal(tmp_path):
    journal = open_journal(tmp_path)
    with pytest.raises(core.DepthError, match="invalid_depth_json"):
        journal.append("depth_frame", **body_fields(b"\xff\x00"))
    journal.close()
    rows = [json.loads(line) for line in (tmp_path / "depth.jsonl").read_bytes().splitlines()]
    assert base64.b64decode(rows[-1]["raw_b64"]) == b"\xff\x00"
    assert not journal.state.book.quotes and journal.state.summary()["segment_failed"]
    with pytest.raises(core.DepthError):
        replay((tmp_path / "depth.jsonl").read_bytes())


@pytest.mark.parametrize("failure", ["disk", "size"])
def test_persistence_failure_blocks_native_conversion(tmp_path, monkeypatch, failure):
    journal = open_journal(tmp_path)
    journal.append("depth_frame", **body_fields(delta()))
    response(journal, snapshot())
    if failure == "disk":

        def broken(_):
            raise OSError("fixture disk failed")

        monkeypatch.setattr(archive.os, "fsync", broken)
    else:
        monkeypatch.setattr(archive, "MAX_ARCHIVE", journal.size)
    with pytest.raises(core.DepthError, match="depth_archive_"):
        journal.append("depth_frame", **body_fields(delta(103, 104)))
    assert journal.failed and len(journal.state.book.quotes) == 1
    with pytest.raises(core.DepthError, match="requires_review"):
        journal.append("completed", result=journal.state.summary())
    journal.close()


@pytest.mark.parametrize(
    "change", ["rtt", "offset_lower", "offset_upper", "drift", "missing_weight"]
)
def test_clock_intervals_and_missing_ip_budget(tmp_path, change):
    journal = archive.DepthJournal(tmp_path / "depth.jsonl", epoch="fixture", clock=ReceiptClock())
    sent, mono = journal.clock()
    received = sent + (501_000_000 if change == "rtt" else 10_000_000)
    server = sent // 1_000_000 + 5
    if change == "offset_lower":
        server -= 300
    if change == "offset_upper":
        server += 300
    fields = dict(
        path="/api/v3/time",
        params={},
        sent_ns=sent,
        sent_monotonic_ns=mono,
        received_ns=received,
        monotonic_ns=mono + received - sent,
        status=200,
        headers={} if change == "missing_weight" else {"x-mbx-used-weight-1m": "1"},
        **body_fields({"serverTime": server}),
    )
    if change == "drift":
        fields["received_ns"] += 51_000_000
    with pytest.raises(core.DepthError):
        journal.append("rest_response", **fields)
    assert journal.state.summary()["segment_failed"]
    journal.close()


def test_frozen_contract_hash_and_limits():
    from pathlib import Path

    contract = Path(
        "docs/progress/portfolio-testnet-provider-coverage-2026-09-13.json"
    ).read_bytes()
    assert hashlib.sha256(contract).hexdigest() == archive.CONTRACT_SHA256
    assert len(archive.REQUESTS) == 5 and sum(row[2] for row in archive.REQUESTS) == 28
    assert (core.MAX_FRAME, core.MAX_BUFFER, core.MAX_EVENTS, core.MAX_ARCHIVE) == (
        1048576,
        16777216,
        4096,
        67108864,
    )

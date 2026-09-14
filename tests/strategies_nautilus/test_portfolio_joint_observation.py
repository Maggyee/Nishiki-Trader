"""Interleaving, aggregate pressure and detached multi-symbol native acceptance."""

import base64
import copy
import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_market_depth import SECOND, DepthError
from apps.strategies_nautilus.portfolio_market_depth_archive import flags
from apps.strategies_nautilus.portfolio_stream import canonical
from tests.strategies_nautilus.test_portfolio_market_depth import (
    BASE,
    delta,
    metadata,
    rechain,
    snapshot,
)

SYMBOLS = ["BNBUSDT", "BTCUSDT", "ETHUSDT"]


def manifest():
    return {
        "synthetic": True,
        "design_sha256": joint.DESIGN_SHA256,
        "source": {"endpoint": joint.REST, "account_uid": "1", "key_sha256": "0" * 64},
        "account_epoch": "synthetic-account",
        "market_epoch": "synthetic-market",
        "subscription_id": 7,
        "symbols": SYMBOLS,
        "initial_account": {
            "uid": 1,
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": a, "free": "1", "locked": "0"}
                for a in ["BNB", "BTC", "ETH", "USDT", "UNPRICED"]
            ],
        },
    }


def all_metadata():
    body = metadata()
    row = body["symbols"][0]
    row["quoteAssetPrecision"] = 8
    body["symbols"] = [dict(row, symbol=s, baseAsset=s[:-4]) for s in SYMBOLS]
    # Unselected/unpriced assets remain in the full CASH snapshot.
    body["symbols"].append(dict(row, symbol="UNPRICEDUSDT", baseAsset="UNPRICED", status="BREAK"))
    return body


class Clock:
    def __init__(self, start=BASE):
        self.now, self.mono = start, SECOND

    def __call__(self):
        return self.now, self.mono

    def advance(self, ns):
        self.now += ns
        self.mono += ns


class Fixture:
    def __init__(self, tmp_path, *, limits=None, start=BASE):
        self.path = tmp_path / "joint.jsonl"
        self.clock = Clock(start)
        self.journal = joint.JointJournal(
            self.path, manifest=manifest(), clock=self.clock, limits=limits
        )

    def append(self, kind, **fields):
        self.journal.append(kind, **fields)

    def read(self, body=None, **changes):
        state = self.journal.state
        request = state.budget["rest_requests"][state.request_index]
        if body is None:
            path = request["path"]
            if path.endswith("/time"):
                body = {"serverTime": self.clock.now // 1_000_000}
            elif path.endswith("/account"):
                body = manifest()["initial_account"]
            elif path.endswith("/openOrders"):
                body = []
            elif path.endswith("/exchangeInfo"):
                body = all_metadata()
            elif path.endswith("/depth"):
                body = snapshot()
            else:
                body = []
        fields = {
            **request,
            "status": 200,
            "sent_ns": self.clock.now,
            "sent_monotonic_ns": self.clock.mono,
            "epoch": "synthetic-account",
            "used_weight_1m": 448,
            **joint.raw_fields(canonical(body)),
            **changes,
        }
        self.append("rest_response", **fields)

    def ws(self):
        state = self.journal.state
        self.append(
            "ws_operation",
            operation=state.budget["ws_api_operations"][state.ws_index]["operation"],
            status=200,
            subscription_id=7,
            epoch="synthetic-account",
        )

    def connect(self):
        self.read()
        self.ws()
        self.ws()
        for _ in range(6):
            self.read()
        self.append(
            "market_connected",
            epoch="synthetic-market",
            url="wss://stream.testnet.binance.vision/stream?streams="
            + "/".join(s.lower() + "@depth@100ms" for s in SYMBOLS),
        )

    def frame_fields(self, symbol, first=99, last=102, **changes):
        data = delta(first, last, s=symbol, E=self.clock.now // 1_000_000, **changes)
        return {
            "epoch": "synthetic-market",
            **joint.raw_fields(
                canonical({"stream": symbol.lower() + "@depth@100ms", "data": data})
            ),
        }

    def frame(self, symbol, first=99, last=102, **changes):
        self.append("market_frame", **self.frame_fields(symbol, first, last, **changes))

    def account(self, event=None):
        self.append(
            "account_frame",
            epoch="synthetic-account",
            **joint.raw_fields(
                canonical(
                    {
                        "subscriptionId": 7,
                        "event": event
                        or {
                            "e": "outboundAccountPosition",
                            "E": self.clock.now // 1_000_000,
                            "u": self.clock.now // 1_000_000,
                            "B": [{"a": "BTC", "f": "1", "l": "0"}],
                        },
                    }
                )
            ),
        )

    def link(self):
        self.connect()
        # All three share pending capacity; account callbacks interleave while
        # some symbols await their sole snapshot and others already emit quotes.
        for s in SYMBOLS:
            self.journal.enqueue("market_frame", **self.frame_fields(s))
        self.journal.drain()
        self.account()
        for i, s in enumerate(SYMBOLS):
            self.read()
            self.account()
            self.frame(s, 103, 104, b=[["99", str(i + 4)]])
        self.read()  # linked clock sample

    def finish(self):
        for i in range(4):
            self.frame(SYMBOLS[i % 3], 105 if i < 3 else 107, 106 if i < 3 else 108)
            self.read()
        self.read()
        self.ws()
        for which in ("market", "account"):
            self.append("closed", transport=which, epoch="synthetic-" + which)
        self.journal.complete()
        self.journal.close()
        return self.path.read_bytes()


def replay(raw):
    return joint.replay_joint(raw, expected_sha256=joint.digest(raw))


def test_interleaved_native_accounts_and_two_fresh_process_replays(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.link()
    raw = fixture.finish()
    result = replay(raw)
    summary = result["summary"]
    assert summary["rest_get_responses"] == 16
    assert summary["ws_api_operations"] == 3 and summary["documented_weight"] == 448
    assert summary["common_revision"] is None
    assert all(result[k] is False for k in flags())
    assert summary["qualified_equity_usdt"] is None
    assert all(
        n["exact_assets"] == 5 and n["detached_native_account_balances_equal"]
        for n in result["native_accounts"]
    )
    assert len(summary["account_events"]) == 4
    assert summary["account_intervals"][0]["balances"]["UNPRICED"] == ["1", "0"]
    for i, symbol in enumerate(SYMBOLS):
        quotes = result["native_quotes"][symbol]
        assert {q["instrument_id"] for q in quotes} == {symbol + ".BINANCE"}
        # Independent expectation from absolute quantity replacements.
        assert quotes[0]["bid_size"] == "3.00000000"
        assert quotes[1]["bid_size"] == f"{i + 4}.00000000"
        assert summary["market_intervals"][symbol]["reference"]["snapshot"]["L"] == 100
    outputs = []
    for i in range(2):
        out = tmp_path / f"replay{i}.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "apps.ops.portfolio_joint_observation",
                "--archive",
                str(fixture.path),
                "--archive-sha256",
                joint.digest(raw),
                "--report",
                str(out),
            ],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        outputs.append(out.read_bytes())
        assert out.stat().st_mode & 0o777 == 0o600
    assert outputs[0] == outputs[1] and json.loads(outputs[0]) == result
    assert fixture.path.read_bytes() == raw


@pytest.mark.parametrize(
    "mode",
    ["queued_events", "queued_bytes", "bootstrap_events", "bootstrap_bytes", "mixed_account"],
)
def test_shared_pending_overflow_is_durable_and_poisoned(tmp_path, mode):
    f = Fixture(tmp_path)
    f.connect()
    j = f.journal
    size = len(canonical(j._row("market_frame", f.frame_fields(SYMBOLS[0]))))
    if mode.endswith("bytes"):
        j.limits = replace(j.limits, pending_bytes=size * 2 + 100)
    else:
        j.limits = replace(j.limits, pending_events=2)
    j.enqueue("market_frame", **f.frame_fields(SYMBOLS[0]))
    j.enqueue("market_frame", **f.frame_fields(SYMBOLS[1]))
    if mode.startswith("bootstrap") or mode == "mixed_account":
        j.drain()
        assert j.state.retained_events == 2
    with pytest.raises(DepthError, match="shared_pending"):
        if mode == "mixed_account":
            f.account()
        else:
            j.enqueue("market_frame", **f.frame_fields(SYMBOLS[2]))
    assert j.failed and not any(b.quotes for b in j.state.books.values())
    assert json.loads(f.path.read_bytes().splitlines()[-1])["kind"] == "aborted"
    with pytest.raises(DepthError):
        j.drain()
    j.close()
    with pytest.raises(DepthError):
        replay(f.path.read_bytes())


@pytest.mark.parametrize("which", SYMBOLS)
def test_one_symbol_gap_aborts_whole_segment(tmp_path, which):
    f = Fixture(tmp_path)
    f.link()
    counts = {s: len(b.quotes) for s, b in f.journal.state.books.items()}
    with pytest.raises(DepthError, match="sequence_gap"):
        f.frame(which, 106, 108)
    with pytest.raises(DepthError):
        f.frame(SYMBOLS[0], 105, 106)
    assert counts == {s: len(b.quotes) for s, b in f.journal.state.books.items()}
    f.journal.close()


def test_healthy_symbols_cannot_refresh_quiet_symbol(tmp_path):
    f = Fixture(tmp_path)
    f.link()
    f.clock.advance(4 * SECOND)
    f.frame("BTCUSDT", 105, 106)
    f.frame("BNBUSDT", 105, 106)
    f.clock.advance(SECOND + 1)
    with pytest.raises(DepthError, match="quiet_depth_expired"):
        f.frame("BTCUSDT", 107, 108)
    f.journal.close()


@pytest.mark.parametrize(
    "kind",
    [
        "balanceUpdate",
        "externalLockUpdate",
        "executionReport",
        "eventStreamTerminated",
        "unknownFunding",
    ],
)
def test_account_ambiguous_events_persist_before_refusal(tmp_path, kind):
    f = Fixture(tmp_path)
    f.link()
    event = {"e": kind, "E": f.clock.now // 1_000_000, "a": "BTC", "d": "1"}
    with pytest.raises(DepthError, match="requires_review"):
        f.account(event)
    rows = [json.loads(r) for r in f.path.read_bytes().splitlines()]
    assert (
        json.loads(
            base64.b64decode(
                next(r for r in reversed(rows) if r["kind"] == "account_frame")["raw_b64"]
            )
        )["event"]
        == event
    )
    assert rows[-1]["kind"] == "aborted"
    f.journal.close()


@pytest.mark.parametrize(
    "change",
    [
        "missing_zero_asset",
        "new_asset",
        "free_delta",
        "lock_delta",
        "uid",
        "open_order",
        "interrupted",
    ],
)
def test_full_account_changes_and_interleaved_event_refused(tmp_path, change):
    f = Fixture(tmp_path)
    f.link()
    body = copy.deepcopy(manifest()["initial_account"])
    if change == "missing_zero_asset":
        # Exact asset set matters even when an omitted asset is zero.
        f.journal.state.manifest["initial_account"]["balances"][-1]["free"] = "0"
        body["balances"].pop()
    elif change == "new_asset":
        body["balances"].append({"asset": "FOREIGN", "free": "0", "locked": "0"})
    elif change == "free_delta":
        body["balances"][0]["free"] = "2"
    elif change == "lock_delta":
        body["balances"][0]["free"], body["balances"][0]["locked"] = "0", "1"
    elif change == "uid":
        body["uid"] = 2
    f.read(body)
    if change == "interrupted":
        with pytest.raises(DepthError, match="collection_interrupted"):
            f.account()
    else:
        orders = [{"symbol": "BTCUSDT", "orderId": 5}] if change == "open_order" else []
        f.read(orders)
        f.read(orders)
        with pytest.raises(DepthError):
            f.read(body)
    f.journal.close()


@pytest.mark.parametrize(
    "damage", ["outer_symbol", "inner_symbol", "epoch", "raw_hash", "invalid_json", "frame_limit"]
)
def test_raw_frame_dispatch_refusals(tmp_path, damage):
    f = Fixture(tmp_path)
    f.link()
    fields = f.frame_fields("BTCUSDT", 105, 106)
    body = json.loads(base64.b64decode(fields["raw_b64"]))
    if damage == "outer_symbol":
        body["stream"] = "ethusdt@depth@100ms"
    elif damage == "inner_symbol":
        body["data"]["s"] = "FOREIGN"
    fields.update(joint.raw_fields(canonical(body)))
    if damage == "epoch":
        fields["epoch"] = "foreign"
    elif damage == "raw_hash":
        fields["body_sha256"] = "f" * 64
    elif damage == "invalid_json":
        fields.update(joint.raw_fields(b"\xff"))
    elif damage == "frame_limit":
        f.journal.limits = replace(f.journal.limits, frame_bytes=1)
    with pytest.raises(DepthError):
        f.append("market_frame", **fields)
    rows = [json.loads(line) for line in f.path.read_bytes().splitlines()]
    persisted = next(r for r in reversed(rows) if r["kind"] == "market_frame")
    assert persisted["raw_b64"] == fields["raw_b64"] and rows[-1]["kind"] == "aborted"
    f.journal.close()


@pytest.mark.parametrize("failure", ["archive_cap", "fsync"])
def test_disk_failure_never_converts_or_seals(tmp_path, monkeypatch, failure):
    f = Fixture(tmp_path)
    f.link()
    before = len(f.journal.state.books["BTCUSDT"].quotes)
    if failure == "archive_cap":
        f.journal.limits = replace(
            f.journal.limits, archive_bytes=f.journal.size + joint.INCIDENT_RESERVE + 1
        )
    else:
        monkeypatch.setattr(os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(DepthError):
        f.frame("BTCUSDT", 105, 106)
    assert len(f.journal.state.books["BTCUSDT"].quotes) == before
    with pytest.raises(DepthError):
        f.journal.complete()
    f.journal.close()
    with pytest.raises(DepthError):
        replay(f.path.read_bytes())


def test_midnight_is_explicit_and_unqualified(tmp_path):
    f = Fixture(tmp_path, start=(BASE // joint.DAY + 1) * joint.DAY - SECOND)
    f.link()
    f.clock.advance(2 * SECOND)
    result = replay(f.finish())
    assert result["summary"]["crossed_utc_boundary"]
    assert result["summary"]["qualified_day_open_usdt"] is None


@pytest.mark.parametrize(
    "damage",
    ["unsealed", "truncated", "seal", "source", "epoch", "extra_get", "clock", "account_hash"],
)
def test_rechained_semantic_corruption_and_incomplete_archive_refused(tmp_path, damage):
    f = Fixture(tmp_path)
    f.link()
    raw = f.finish()
    rows = [json.loads(line) for line in raw.splitlines()]
    if damage == "unsealed":
        rows.pop()
    elif damage == "seal":
        next(r for r in rows if r["kind"] == "completed")["result"]["baseline_qualified"] = True
    elif damage == "source":
        rows[0]["manifest"]["source"]["endpoint"] = "https://api.binance.com"
    elif damage == "epoch":
        next(r for r in rows if r["kind"] == "account_frame")["epoch"] = "foreign"
    elif damage == "extra_get":
        rows[-1] = dict(next(r for r in rows if r["kind"] == "rest_response"))
    elif damage == "clock":
        rows[5]["received_ns"] += SECOND
    elif damage == "account_hash":
        next(r for r in rows if r.get("path") == "/api/v3/account")["body_sha256"] = "f" * 64
    changed = rechain(rows)
    if damage == "truncated":
        changed = changed[:-1]
    with pytest.raises(DepthError):
        replay(changed)


@pytest.mark.parametrize(
    "kind", ["weight", "status", "request_timeout", "clock_sample", "bootstrap", "control"]
)
def test_budgets_and_deadlines_fail_without_retry(tmp_path, kind):
    f = Fixture(tmp_path)
    if kind == "clock_sample":
        with pytest.raises(DepthError, match="clock_sample"):
            f.read({"serverTime": f.clock.now // 1_000_000 - 1000})
    else:
        f.connect()
        if kind == "bootstrap":
            f.clock.advance(15 * SECOND + 1)
            with pytest.raises(DepthError, match="bootstrap_deadline"):
                f.append("tick")
        elif kind == "control":
            for _ in range(5):
                f.append(
                    "market_pong", epoch="synthetic-market", payload_b64="eA==", echo_b64="eA=="
                )
            with pytest.raises(DepthError, match="control_rate"):
                f.append(
                    "market_pong", epoch="synthetic-market", payload_b64="eA==", echo_b64="eA=="
                )
        else:
            f.frame("BNBUSDT")
            changes = {"used_weight_1m": 5999} if kind == "weight" else {"status": 429}
            if kind == "request_timeout":
                f.clock.advance(11 * SECOND)
                # Unlinked depth may still be buffered; request deadline wins before snapshot.
                changes = {
                    "sent_ns": f.clock.now - 11 * SECOND,
                    "sent_monotonic_ns": f.clock.mono - 11 * SECOND,
                }
            with pytest.raises(DepthError):
                f.read(**changes)
    assert f.journal.failed
    f.journal.close()


def test_processing_delay_rejects_previously_fresh_buffer(tmp_path):
    f = Fixture(tmp_path)
    f.connect()
    f.journal.enqueue("market_frame", **f.frame_fields("BTCUSDT"))
    f.clock.advance(5 * SECOND + 1)
    with pytest.raises(DepthError, match="future_or_stale_depth_event"):
        f.journal.drain()
    assert not f.journal.state.books["BTCUSDT"].pending
    rows = [json.loads(line) for line in f.path.read_bytes().splitlines()]
    assert rows[-2]["kind"] == "dispatch" and rows[-1]["kind"] == "aborted"
    assert rows[-2]["received_ns"] > rows[-3]["received_ns"] + 5 * SECOND
    f.journal.close()


def test_callback_mutation_cannot_change_persisted_interpretation(tmp_path):
    f = Fixture(tmp_path)
    f.connect()
    fields = f.frame_fields("BTCUSDT")
    f.journal.enqueue("market_frame", **fields)
    fields["epoch"] = "changed-after-enqueue"
    f.journal.drain()
    assert f.journal.state.books["BTCUSDT"].pending
    f.journal.close()


def test_dispatch_order_and_late_processing_rejected_on_replay(tmp_path):
    f = Fixture(tmp_path)
    f.link()
    raw = f.finish()
    for damage in ("wrong_receipt", "delayed", "duplicate_dispatch"):
        rows = [json.loads(line) for line in raw.splitlines()]
        index = next(i for i, r in enumerate(rows) if r["kind"] == "market_frame")
        dispatched = next(
            r for r in rows if r["kind"] == "dispatch" and r["receipt_seq"] == rows[index]["seq"]
        )
        if damage == "wrong_receipt":
            dispatched["receipt_seq"] += 1
        elif damage == "delayed":
            dispatched["received_ns"] += 6 * SECOND
            dispatched["monotonic_ns"] += 6 * SECOND
        else:
            rows.insert(rows.index(dispatched) + 1, dict(dispatched))
        with pytest.raises(DepthError):
            replay(rechain(rows))


def test_one_sided_snapshot_fails_closed(tmp_path):
    f = Fixture(tmp_path)
    f.connect()
    f.frame("BNBUSDT")
    with pytest.raises(DepthError, match="invalid_snapshot_book"):
        f.read(snapshot(asks=[]))
    f.journal.close()


def test_cli_blocks_network_and_refuses_overwrite(tmp_path, monkeypatch):
    import socket

    from apps.ops.portfolio_joint_observation import main

    f = Fixture(tmp_path)
    f.link()
    raw = f.finish()
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("network forbidden"))
    report = tmp_path / "cli.json"
    args = [
        "--archive",
        str(f.path),
        "--archive-sha256",
        joint.digest(raw),
        "--report",
        str(report),
    ]
    assert main(args) == 0
    original = report.read_bytes()
    assert main(args) == 1
    assert report.read_bytes() == original and f.path.read_bytes() == raw


def test_missing_native_metadata_cannot_drop_an_account_asset(tmp_path):
    f = Fixture(tmp_path)
    f.link()
    rows = [json.loads(line) for line in f.finish().splitlines()]
    row = next(r for r in rows if r.get("path", "").endswith("/exchangeInfo"))
    body = json.loads(base64.b64decode(row["raw_b64"]))
    body["symbols"].pop()  # UNPRICED remains in both full account snapshots.
    row.update(joint.raw_fields(canonical(body)))
    # The metadata hash is used during native mapping, not smuggled into a seal.
    with pytest.raises(DepthError, match="native_account_mapping"):
        replay(rechain(rows))

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from nautilus_trader.adapters.binance.http.client import BinanceHttpClient
from nautilus_trader.common.component import TestClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_account import AccountAnchor
from apps.strategies_nautilus.portfolio_account_collector import BinanceReadOnlyAccountCollector
from apps.strategies_nautilus.portfolio_stream import StreamError, UserStreamJournal, bind_source
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


@pytest.fixture
def journal(tmp_path):
    now = [BASE_NS + 2 * SECOND]
    client = SimpleNamespace(base_url="https://api.binance.com", api_key="fixture-read-key")
    binding = bind_source(client, "123")
    stream = UserStreamJournal(tmp_path / "stream.jsonl", binding, clock_ns=lambda: now[0])
    yield stream, now, client
    stream.close()


def event(**updates):
    return json.dumps(
        {
            "subscriptionId": 7,
            "event": {
                "e": "executionReport",
                "E": BASE_NS // 1_000_000,
                "s": "BTCUSDT",
                "i": 123,
                "I": 456,
                **updates,
            },
        }
    ).encode()


def test_ack_required_and_every_new_epoch_invalidates_old_fence(journal):
    s, _, _ = journal
    with pytest.raises(StreamError):
        s.fence()
    s.subscribed(7, s.binding)
    before = s.fence()
    s.disconnect()
    s.subscribed(7, s.binding)  # exchange may reuse subscription ID
    assert s.fence().epoch != before.epoch
    with pytest.raises(StreamError, match="changed"):
        s.assert_fence(before)


def test_duplicate_execution_reports_are_archived_without_assuming_sequence_gaps(journal):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    fence = s.fence()
    assert not s.observe(event())
    assert s.observe(event())
    assert not s.observe(event(I=9000))  # Binance execution IDs need not be contiguous
    assert not s.observe(event(I=8000))  # receipt order is not exchange global sequence
    with pytest.raises(StreamError):
        s.assert_fence(fence)


@pytest.mark.parametrize(
    "raw",
    [
        b"broken",
        b'{"subscriptionId":7,"subscriptionId":8}',
        event(e="eventStreamTerminated"),
        event(e="listenKeyExpired"),
        event(e="balanceUpdate"),
        event(e="externalLockUpdate"),
        event(e="unknown"),
        event(E=0),
        event(E=(BASE_NS + 10 * SECOND) // 1_000_000),
        event(s="ETHUSDT"),
        event(i=True),
        event(I=-1),
        b"x" * 65_537,
        json.dumps({"subscriptionId": 8, "event": {}}).encode(),
    ],
)
def test_anomalies_invalidate_the_session(journal, raw):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    with pytest.raises(StreamError):
        s.observe(raw)
    with pytest.raises(StreamError):
        s.fence()


def test_conflicting_duplicate_is_not_silently_ignored(journal):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    s.observe(event())
    with pytest.raises(StreamError, match="conflicting"):
        s.observe(event(z="0.002"))


def test_partial_balance_update_is_archived_and_invalidates_rest_fence(journal):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    before = s.fence()
    s.observe(
        event(
            e="outboundAccountPosition",
            u=BASE_NS // 1_000_000,
            B=[{"a": "BTC", "f": "0.001", "l": "0"}],
        )
    )
    with pytest.raises(StreamError):
        s.assert_fence(before)


def test_pong_is_not_account_activity_and_cannot_repair_a_transport_gap(journal):
    s, now, _ = journal
    s.subscribed(7, s.binding)
    before = s.fence()
    now[0] += SECOND
    s.transport_alive()
    s.assert_fence(before)
    now[0] += 61 * SECOND
    with pytest.raises(StreamError):
        s.transport_alive()
    now[0] -= 60 * SECOND
    with pytest.raises(StreamError):
        s.fence()


def test_archive_restart_revalidates_hashes_and_never_reuses_subscription(tmp_path):
    path = tmp_path / "stream.jsonl"
    binding = bind_source(
        SimpleNamespace(base_url="https://api.binance.com", api_key="fixture-key"), "123"
    )
    s = UserStreamJournal(path, binding, clock_ns=lambda: BASE_NS)
    s.subscribed(7, binding)
    s.observe(event())
    s.close()
    raw = path.read_bytes()
    restarted = UserStreamJournal(path, binding, clock_ns=lambda: BASE_NS)
    with pytest.raises(StreamError):
        restarted.fence()
    restarted.close()
    path.write_bytes(raw[:-1])
    with pytest.raises(StreamError, match="incomplete"):
        UserStreamJournal(path, binding, clock_ns=lambda: BASE_NS)
    path.write_bytes(raw.replace(b"executionReport", b"executionReporX"))
    with pytest.raises(StreamError, match="integrity"):
        UserStreamJournal(path, binding, clock_ns=lambda: BASE_NS)


def test_archive_has_one_writer_and_bound_account(journal, tmp_path):
    s, _, _ = journal
    with pytest.raises(BlockingIOError):
        UserStreamJournal(tmp_path / "stream.jsonl", s.binding, clock_ns=lambda: BASE_NS)
    s.close()
    with pytest.raises(StreamError, match="source mismatch"):
        UserStreamJournal(
            tmp_path / "stream.jsonl",
            replace(s.binding, account_uid="other"),
            clock_ns=lambda: BASE_NS,
        )


def test_write_failure_cannot_rearm_the_same_journal(journal, monkeypatch):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    import apps.strategies_nautilus.portfolio_stream as module

    monkeypatch.setattr(module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(StreamError):
        s.observe(event())
    with pytest.raises(StreamError):
        s.subscribed(7, s.binding)


@pytest.mark.parametrize("change", ["none", "event", "disconnect", "account", "key", "key_during"])
def test_real_native_signer_and_rest_collection_bound_to_stream(journal, monkeypatch, change):
    s, now, _ = journal
    clock = TestClock()
    clock.set_time(now[0])
    client = BinanceHttpClient(
        clock, "fixture-read-key", "fixture-secret", "https://api.binance.com"
    )
    # The installed native sign_request runs unchanged; only network transport is replaced.
    s.subscribed(7, s.binding)
    calls = []

    async def wire(method, path, *, payload, ratelimiter_keys=None):
        assert method == HttpMethod.GET
        signed = {k: v for k, v in payload.items() if k != "signature"}
        expected = hmac.new(
            b"fixture-secret", urlencode(signed).encode(), hashlib.sha256
        ).hexdigest()
        assert hmac.compare_digest(payload["signature"], expected)
        assert client.headers["X-MBX-APIKEY"] == "fixture-read-key"
        calls.append(path)
        if path.endswith("allOrders"):
            if change == "event":
                s.observe(event())
            elif change == "disconnect":
                s.disconnect()
                s.subscribed(7, s.binding)
        if path.endswith("apiRestrictions"):
            body = {"enableReading": True, "enableSpotAndMarginTrading": False}
        elif path.endswith("account"):
            body = {
                "uid": 123,
                "accountType": "SPOT",
                "canTrade": True,
                "permissions": ["SPOT"],
                "balances": [],
            }
        else:
            body = []
        if change == "key_during" and len(calls) == 7:
            client._key = "rotated-fixture-key"
        return json.dumps(body).encode()

    monkeypatch.setattr(client, "send_request", wire)
    if change == "key":
        s.binding = replace(s.binding, key_sha256="wrong")
    anchor = AccountAnchor(
        "other" if change == "account" else "123", "BINANCE-001", BASE_NS, D("500")
    )
    collector = BinanceReadOnlyAccountCollector(client, clock_ns=lambda: now[0], stream=s)
    if change != "none":
        with pytest.raises(ValueError):
            asyncio.run(collector.collect(anchor))
        if change in {"key", "account"}:
            assert not calls
    else:
        result = asyncio.run(collector.collect(anchor))
        s.assert_fence(result.stream_fence)
        assert not result.atomic_revision_verified
        assert len(calls) == 7
        s.observe(event())
        with pytest.raises(StreamError):
            s.assert_fence(result.stream_fence)


@pytest.mark.parametrize(
    "balances",
    [
        [{"a": "BTC", "f": "NaN", "l": "0"}],
        [{"a": "BTC", "f": "1", "l": "-1"}],
        [{"a": "BTC", "f": "0"}],
        [{"a": "BTC", "f": "0", "l": "0"}] * 2,
    ],
)
def test_malformed_partial_balances_disconnect(journal, balances):
    s, _, _ = journal
    s.subscribed(7, s.binding)
    with pytest.raises(StreamError):
        s.observe(event(e="outboundAccountPosition", u=BASE_NS // 1_000_000, B=balances))
    with pytest.raises(StreamError):
        s.fence()

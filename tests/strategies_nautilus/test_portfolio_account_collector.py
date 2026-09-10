from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from decimal import Decimal as D

import pytest
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_account import AccountAnchor
from apps.strategies_nautilus.portfolio_account_archive import (
    AccountArchiveError,
    replay_account_collection,
)
from apps.strategies_nautilus.portfolio_account_collector import BinanceReadOnlyAccountCollector
from apps.strategies_nautilus.portfolio_stream import StreamError, UserStreamJournal, bind_source
from apps.strategies_nautilus.portfolio_venue import VenueInputError
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS, SECOND


class SignedClientFixture:
    base_url = "https://api.binance.com"
    api_key = "fixture-read-key"

    def __init__(self):
        self.calls = []
        account = {
            "uid": 123,
            "accountType": "SPOT",
            "canTrade": True,
            "permissions": ["SPOT"],
            "balances": [],
        }
        self.responses = {
            "/sapi/v1/account/apiRestrictions": [
                {"enableReading": True, "enableSpotAndMarginTrading": False}
            ],
            "/api/v3/account": [account, copy.deepcopy(account)],
            "/api/v3/openOrders": [[], []],
            "/api/v3/allOrders": [[]],
            "/api/v3/myTrades": [[]],
        }

    async def sign_request(self, method, path, *, payload):
        assert method == HttpMethod.GET
        assert payload["recvWindow"] == "5000"
        assert int(payload["timestamp"]) == (BASE_NS + 2 * SECOND) // 1_000_000
        self.calls.append((method, path, payload.copy()))
        return json.dumps(self.responses[path].pop(0)).encode()


def collect(client, *, max_pages=32, start_ns=BASE_NS):
    source = BinanceReadOnlyAccountCollector(
        client, clock_ns=lambda: BASE_NS + 2 * SECOND, max_pages=max_pages
    )
    return asyncio.run(source.collect(AccountAnchor("123", "BINANCE-001", start_ns, D("500"))))


def test_signed_gets_only_read_only_key_and_explicit_non_atomic_result():
    client = SignedClientFixture()
    result = collect(client)
    assert len(client.calls) == 7
    assert all(method == HttpMethod.GET for method, _, _ in client.calls)
    assert all(
        "symbol" not in params for _, path, params in client.calls if path.endswith("openOrders")
    )
    assert len(result.wire_sha256) == 7
    assert not result.api_trading_enabled
    assert not result.atomic_revision_verified
    assert result.evidence.account.account_id == "123"
    assert result.evidence.start_ns == BASE_NS


@pytest.mark.parametrize(
    "path,key,cursor",
    [("/api/v3/allOrders", "orderId", "orderId"), ("/api/v3/myTrades", "id", "fromId")],
)
def test_full_pages_require_followup_and_keep_native_wire_hashes(path, key, cursor):
    client = SignedClientFixture()
    client.responses[path] = [[{key: i} for i in range(1000)], [{key: 1000}]]
    result = collect(client)
    calls = [p for _, pth, p in client.calls if pth == path]
    assert calls[0]["startTime"] == str(BASE_NS // 1_000_000)
    assert calls[1][cursor] == "1000"
    assert "startTime" not in calls[1]
    assert len(result.wire_sha256) == 8


def test_full_last_page_never_claims_complete_history():
    client = SignedClientFixture()
    client.responses["/api/v3/allOrders"] = [[{"orderId": i} for i in range(1000)]]
    with pytest.raises(VenueInputError, match="pagination incomplete"):
        collect(client, max_pages=1)


@pytest.mark.parametrize(
    "rows",
    [[{"orderId": 2}, {"orderId": 1}], [{"orderId": 1}, {"orderId": 1}], [{"orderId": True}]],
)
def test_ambiguous_history_page_fails_closed(rows):
    client = SignedClientFixture()
    client.responses["/api/v3/allOrders"] = [rows]
    with pytest.raises(VenueInputError, match="history page"):
        collect(client)


@pytest.mark.parametrize(
    "path,change",
    [
        ("/api/v3/account", {"uid": 999}),
        ("/api/v3/account", {"canTrade": False}),
        ("/api/v3/openOrders", [{"clientOrderId": "new-external-order"}]),
    ],
)
def test_account_changes_during_reads_require_new_collection(path, change):
    client = SignedClientFixture()
    if path.endswith("account"):
        client.responses[path][1].update(change)
    else:
        client.responses[path][1] = change
    with pytest.raises(VenueInputError, match="changed during collection"):
        collect(client)


def test_wrong_signed_account_or_read_permission_fails_before_history():
    client = SignedClientFixture()
    client.responses["/api/v3/account"][0]["uid"] = 999
    with pytest.raises(VenueInputError, match="UID mismatch"):
        collect(client)
    assert not any(path.endswith("allOrders") for _, path, _ in client.calls)
    client = SignedClientFixture()
    client.responses["/sapi/v1/account/apiRestrictions"][0]["enableReading"] = False
    with pytest.raises(VenueInputError, match="reading permission"):
        collect(client)


def test_collector_refuses_unqualified_long_history_and_arbitrary_signed_hosts():
    client = SignedClientFixture()
    with pytest.raises(VenueInputError, match="history archive"):
        collect(client, start_ns=BASE_NS - 86_400 * SECOND)
    assert not client.calls
    client.base_url = "https://untrusted.example"
    with pytest.raises(VenueInputError, match="endpoint"):
        collect(client)


def test_transport_errors_do_not_echo_private_payloads():
    client = SignedClientFixture()

    async def failure(*args, **kwargs):
        raise RuntimeError("secret signed URL should not escape")

    client.sign_request = failure
    with pytest.raises(VenueInputError, match="^signed account read failed$"):
        collect(client)


@pytest.fixture
def collection_journal(tmp_path):
    path = tmp_path / "collection.jsonl"
    binding = bind_source(SignedClientFixture(), "123")
    journal = UserStreamJournal(path, binding, clock_ns=lambda: BASE_NS + 2 * SECOND)
    journal.subscribed(7, binding)
    yield path, journal, AccountAnchor("123", "BINANCE-001", BASE_NS, D("500"))
    journal.close()


def stream_collector(client, journal):
    return BinanceReadOnlyAccountCollector(client, clock_ns=journal.clock_ns, stream=journal)


def test_shared_journal_rejects_overlapping_collectors_before_network(collection_journal):
    path, journal, anchor = collection_journal

    async def scenario():
        first, second = SignedClientFixture(), SignedClientFixture()
        entered, release = asyncio.Event(), asyncio.Event()
        original = first.sign_request

        async def paused(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        first.sign_request = paused
        task = asyncio.create_task(stream_collector(first, journal).collect(anchor))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            with pytest.raises(StreamError, match="collection already active"):
                await stream_collector(second, journal).collect(anchor)
            assert not second.calls
            release.set()
            result = await task
            raw = path.read_bytes()
            archived = await replay_account_collection(
                raw,
                source=journal.binding,
                expected_sha256=hashlib.sha256(raw).hexdigest(),
                collection_id=result.collection_id,
                anchor=anchor,
            )
            assert archived.collected.evidence == result.evidence
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["cancel", "timeout", "response", "disconnect"])
def test_interrupted_collection_is_aborted_and_next_collection_replays(
    collection_journal,
    monkeypatch,
    failure,
):
    path, journal, anchor = collection_journal
    import apps.strategies_nautilus.portfolio_account_collector as module

    async def scenario():
        client = SignedClientFixture()
        entered = asyncio.Event()
        original = client.sign_request

        async def failing(method, endpoint, *, payload):
            if endpoint.endswith("allOrders"):
                entered.set()
                if failure in {"cancel", "timeout"}:
                    await asyncio.Event().wait()
                if failure == "disconnect":
                    journal.disconnect()
                else:
                    raise ValueError("private server details")
            return await original(method, endpoint, payload=payload)

        client.sign_request = failing
        if failure == "timeout":
            monkeypatch.setattr(module, "COLLECTION_TIMEOUT_SECONDS", 0.05)
        task = asyncio.create_task(stream_collector(client, journal).collect(anchor))
        await asyncio.wait_for(entered.wait(), 1)
        if failure == "cancel":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ValueError):
            await task
        failed_rows = list(map(json.loads, path.read_bytes().splitlines()))
        failed_id = next(
            row["collection_id"] for row in failed_rows if row["kind"] == "rest_started"
        )
        assert failed_rows[-1]["kind"] == "rest_aborted"
        assert failed_rows[-1]["collection_id"] == failed_id
        assert not any(row["kind"] == "rest_collection" for row in failed_rows)
        assert "private server details" not in path.read_text()
        if failure == "disconnect":
            journal.subscribed(8, journal.binding)
        result = await stream_collector(SignedClientFixture(), journal).collect(anchor)
        raw = path.read_bytes()
        arguments = dict(
            source=journal.binding, expected_sha256=hashlib.sha256(raw).hexdigest(), anchor=anchor
        )
        with pytest.raises(AccountArchiveError):
            await replay_account_collection(raw, collection_id=failed_id, **arguments)
        replayed = await replay_account_collection(
            raw, collection_id=result.collection_id, **arguments
        )
        assert replayed.collected.evidence == result.evidence
        assert result.collection_id != failed_id

    asyncio.run(scenario())


def test_total_timeout_also_bounds_collector_without_a_journal(monkeypatch):
    import apps.strategies_nautilus.portfolio_account_collector as module

    client = SignedClientFixture()

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    client.sign_request = stalled
    monkeypatch.setattr(module, "COLLECTION_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(VenueInputError, match="total time limit"):
        collect(client)


@pytest.mark.parametrize("received", [BASE_NS + SECOND, BASE_NS + 63 * SECOND, 1.5, True])
def test_clock_regression_expiry_and_invalid_time_stop_after_first_response(received):
    now = [BASE_NS + 2 * SECOND]
    client = SignedClientFixture()
    original = client.sign_request

    async def changed_clock(*args, **kwargs):
        raw = await original(*args, **kwargs)
        now[0] = received
        return raw

    client.sign_request = changed_clock
    collector = BinanceReadOnlyAccountCollector(client, clock_ns=lambda: now[0])
    with pytest.raises(VenueInputError):
        asyncio.run(collector.collect(AccountAnchor("123", "BINANCE-001", BASE_NS, D("500"))))
    assert len(client.calls) == 1


def test_source_rotation_stops_before_another_signed_request(collection_journal):
    path, journal, anchor = collection_journal
    client = SignedClientFixture()
    original = client.sign_request

    async def rotate(*args, **kwargs):
        raw = await original(*args, **kwargs)
        client.api_key = "rotated-fixture-key"
        return raw

    client.sign_request = rotate
    with pytest.raises(VenueInputError, match="source changed"):
        asyncio.run(stream_collector(client, journal).collect(anchor))
    assert len(client.calls) == 1
    assert json.loads(path.read_bytes().splitlines()[-1])["kind"] == "rest_aborted"


def test_abort_persistence_failure_blocks_the_journal(collection_journal, monkeypatch):
    path, journal, anchor = collection_journal
    client = SignedClientFixture()

    async def failed_request(*args, **kwargs):
        monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
        raise ValueError("private transport failure")

    client.sign_request = failed_request
    with pytest.raises(StreamError, match="persistence failed"):
        asyncio.run(stream_collector(client, journal).collect(anchor))
    second = SignedClientFixture()
    with pytest.raises(StreamError):
        asyncio.run(stream_collector(second, journal).collect(anchor))
    assert not second.calls
    assert not journal.connected
    assert not any(
        row["kind"] == "rest_collection" for row in map(json.loads, path.read_bytes().splitlines())
    )

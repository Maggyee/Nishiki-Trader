from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_session_bootstrap import (
    ReadOnlyRuntimeBridge,
    ReadOnlyRuntimeLedger,
    reconcile_collected,
)
from apps.strategies_nautilus.portfolio_session_ledger import SessionLedger, read_session
from apps.strategies_nautilus.portfolio_session_transport import (
    SessionJournal,
    SessionLease,
    SessionReadHttpClient,
    collect_session,
    private_read,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.runners.portfolio_session_acceptance import (
    BASE,
    BINDING,
    SECOND,
    SID,
    fixture_context,
    install_submitted,
    native_order,
    recovery_evidence,
    rules,
    signal,
)

PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    + base64.b64encode(bytes.fromhex("302e020100300506032b657004220420") + bytes(32)).decode()
    + "\n-----END PRIVATE KEY-----\n"
)


@pytest.fixture
def case(tmp_path):
    loop = asyncio.new_event_loop()
    owner = fixture_context(loop)
    ledger = SessionLedger(tmp_path / "native.json").create(owner, session_id=SID, source=BINDING)
    owner.clock.set_time(BASE + SECOND)
    sig = signal(owner.clock.timestamp_ns())
    order = native_order(owner, sig)
    ledger.prepare(owner, signal=sig, order=order, rules=rules(owner.clock.timestamp_ns()))
    install_submitted(owner, order)
    ledger.observe(owner)
    owner.clock.set_time(BASE + 8 * SECOND)
    http = SessionReadHttpClient(
        owner.clock,
        "offline-session-key",
        None,
        TESTNET_REST,
        ed25519_private_key=PEM,
        client_order_ids=[str(order.client_order_id)],
    )
    archive = tmp_path / "stream.jsonl"
    journal = SessionJournal(archive, BINDING, clock_ns=owner.clock.timestamp_ns)
    journal.subscribed(7, BINDING)
    evidence = json.loads(recovery_evidence(scenario="fill"))
    response = {
        "/api/v3/account": evidence["account"],
        "/api/v3/openOrders": [],
        "/api/v3/order": evidence["orders"][0],
        "/api/v3/myTrades": evidence["trades"],
    }
    calls = []
    ctx = SimpleNamespace(
        owner=owner,
        ledger=ledger,
        loop=loop,
        http=http,
        journal=journal,
        response=response,
        calls=calls,
        archive=archive,
        hook=None,
    )

    async def request(method, *, url, headers, **kwargs):
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        assert "signature" in params and "offline-session-key" in headers.values()
        calls.append(parsed.path)
        if ctx.hook:
            ctx.hook(parsed.path, params)
        return SimpleNamespace(status=200, body=canonical(response[parsed.path]))

    http._client = SimpleNamespace(request=request)
    try:
        yield ctx
    finally:
        ledger.close()
        journal.close()
        owner.engine.dispose()
        loop.close()


def collect(case):
    return case.loop.run_until_complete(
        collect_session(case.http, case.journal, case.ledger.state, case.ledger.sha256)
    )


def test_signed_original_order_collection_and_native_recovery(case):
    receipt = collect(case)
    assert case.calls == [
        "/api/v3/account",
        "/api/v3/openOrders",
        "/api/v3/order",
        "/api/v3/myTrades",
        "/api/v3/openOrders",
        "/api/v3/account",
    ]
    result = reconcile_collected(
        case.ledger.path.read_bytes(), receipt, case.journal, loop=case.loop
    )
    assert result["signed_source_bound"] and result["full_account_reconciled"]
    assert not result["runtime_ready"] and not result["matching_enabled"]
    assert len(read_session(result["checkpoint"])["state"]["view"]["fills"]) == 1
    assert (
        "signature" not in case.archive.read_text()
        and "PRIVATE KEY" not in case.archive.read_text()
    )
    assert (
        json.loads(case.archive.read_text().splitlines()[-1])["kind"]
        == "session_collection_completed"
    )


@pytest.mark.parametrize(
    "change", ["source", "checkpoint", "time", "disconnect", "evidence", "reconnect"]
)
def test_completed_receipt_cannot_outlive_bound_state(case, change):
    receipt = collect(case)
    selected = case.ledger.sha256
    if change == "source":
        case.journal.binding = replace(BINDING, account_uid="999")
    elif change == "checkpoint":
        selected = "b" * 64
    elif change == "time":
        case.owner.clock.set_time(BASE + 14 * SECOND)
    elif change == "disconnect":
        case.journal.disconnect()
    elif change == "reconnect":
        case.journal.disconnect()
        case.journal.subscribed(8, BINDING)
    else:
        receipt.evidence["account"]["balances"][0]["free"] = "0"
    with pytest.raises(StreamError):
        receipt.assert_current(case.journal, selected)


@pytest.mark.parametrize(
    "change", ["missing", "foreign", "full_page", "wrong_order", "wrong_trade"]
)
def test_incomplete_or_foreign_reports_never_seal(case, change):
    if change == "missing":
        case.response["/api/v3/myTrades"] = []
    elif change == "foreign":
        case.response["/api/v3/openOrders"] = [case.response["/api/v3/order"] | {"orderId": 999}]
    elif change == "full_page":
        case.response["/api/v3/myTrades"] *= 1000
    elif change == "wrong_order":
        case.response["/api/v3/order"]["clientOrderId"] = "foreign"
    else:
        case.response["/api/v3/myTrades"][0]["orderId"] = 999
    if change == "missing":
        receipt = collect(case)
        with pytest.raises(ValueError):
            reconcile_collected(
                case.ledger.path.read_bytes(), receipt, case.journal, loop=case.loop
            )
    else:
        with pytest.raises((StreamError, ValueError)):
            collect(case)
        assert "session_collection_completed" not in case.archive.read_text()
    assert case.journal._active_collection is None


def test_stream_event_during_get_invalidates_collection_before_native_use(case):
    def hook(path, params):
        if path == "/api/v3/order":
            case.journal.disconnect("fixture connection lost")

    case.hook = hook
    with pytest.raises(StreamError):
        collect(case)
    assert len(case.calls) == 3
    assert "session_collection_completed" not in case.archive.read_text()
    assert case.journal._active_collection is None


def test_get_timeout_has_no_automatic_retry(case):
    def hook(path, params):
        raise TimeoutError("fixture timeout")

    case.hook = hook
    with pytest.raises(StreamError):
        collect(case)
    assert len(case.calls) == 1


def test_changed_complete_balances_refuse_native_recovery(case):
    case.response["/api/v3/account"]["balances"][0]["free"] = "999"
    receipt = collect(case)
    with pytest.raises(ValueError):
        reconcile_collected(case.ledger.path.read_bytes(), receipt, case.journal, loop=case.loop)


@pytest.mark.parametrize(
    "method,path,selectors",
    [
        (HttpMethod.POST, "/api/v3/order", {"symbol": "BTCUSDT"}),
        (HttpMethod.DELETE, "/api/v3/order", {"symbol": "BTCUSDT"}),
        (HttpMethod.GET, "/api/v3/order", {"symbol": "BTCUSDT", "origClientOrderId": "foreign"}),
        (
            HttpMethod.GET,
            "/api/v3/myTrades",
            {"symbol": "BTCUSDT", "orderId": "999", "limit": "1000"},
        ),
        (HttpMethod.GET, "/sapi/v1/account/apiRestrictions", {}),
        (HttpMethod.GET, "/api/v3/openOrders", {"symbol": "BTCUSDT"}),
    ],
)
def test_http_exact_get_whitelist(case, method, path, selectors):
    with pytest.raises(StreamError):
        case.loop.run_until_complete(
            case.http.sign_request(
                method, path, selectors | {"timestamp": "1", "recvWindow": "5000"}
            )
        )
    assert case.calls == []


def envelope(case, *, kind="outboundAccountPosition", subscription_id=7):
    return canonical(
        {
            "subscriptionId": subscription_id,
            "event": {
                "e": kind,
                "E": case.owner.clock.timestamp_ms(),
                "u": case.owner.clock.timestamp_ms(),
                "B": [{"a": "ETH", "f": "5", "l": "0"}],
            },
        }
    )


def test_source_bound_account_callback_runs_only_after_durable_raw_archive(case):
    observed = []

    def handler(event):
        assert any(
            json.loads(row)["kind"] == "testnet_event"
            for row in case.archive.read_text().splitlines()
        )
        observed.append(event)

    case.journal.account_handler = handler
    case.journal.observe(envelope(case))
    assert len(observed) == 1
    with pytest.raises(StreamError):
        case.journal.observe(envelope(case, subscription_id=99))
    assert len(observed) == 1


def test_callback_error_disconnects_after_retaining_original_envelope(case):
    def fail(event):
        raise ValueError("native callback failed")

    case.journal.account_handler = fail
    with pytest.raises(StreamError):
        case.journal.observe(envelope(case))
    assert not case.journal.connected and "testnet_event" in case.archive.read_text()


def test_receipt_archive_disk_failure_prevents_callback(case, monkeypatch):
    observed = []
    case.journal.account_handler = observed.append

    def fail(fd):
        raise OSError("fixture disk failure")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(StreamError):
        case.journal.observe(envelope(case))
    assert observed == [] and case.journal._failed


def test_new_profile_does_not_accept_observation_seals(case):
    with pytest.raises(StreamError):
        case.journal.begin_collection(
            case.journal.fence(),
            {"profile": "portfolio.testnet_observation.v1", "selection_sha256": "a" * 64},
            BASE,
        )
    with pytest.raises(StreamError):
        case.journal.record_collection(case.journal.fence(), [])


def test_fixed_scope_lock_identity_and_activation_survive_restart(tmp_path):
    root = tmp_path / "scope"
    lease = SessionLease(BINDING, "a" * 64, root=root)
    selected = lease.state
    with pytest.raises(BlockingIOError):
        SessionLease(BINDING, "a" * 64, root=root)
    lease.activate()
    with pytest.raises(FileExistsError):
        lease.activate()
    lease.close()
    restored = SessionLease(BINDING, "a" * 64, root=root)
    assert restored.state == selected
    with pytest.raises(StreamError, match="lacks native"):
        restored.assert_active()
    with pytest.raises(FileExistsError):
        restored.activate()
    restored.close()
    assert (root / "README.md").exists()
    with pytest.raises(StreamError):
        SessionLease(replace(BINDING, account_uid="999"), "a" * 64, root=root)


def test_probe_does_not_activate_matching_session(tmp_path):
    lease = SessionLease(BINDING, "a" * 64, root=tmp_path / "scope")
    try:
        assert not (lease.root / "activated.json").exists()
        assert not lease.checkpoint_path.exists()
    finally:
        lease.close()


def test_deleted_manifest_cannot_reset_known_activation(tmp_path):
    lease = SessionLease(BINDING, "a" * 64, root=tmp_path / "scope")
    lease.activate()
    lease.close()
    (lease.root / "scope.json").unlink()
    with pytest.raises(StreamError, match="missing scope"):
        SessionLease(BINDING, "a" * 64, root=lease.root)


def test_liveclock_probe_snapshot_uses_one_cursor_and_forbids_orders(case, tmp_path):
    # Reconstruct an empty native fixture with real wall-clock creation time.
    owner = fixture_context(case.loop)
    clock = LiveClock()
    from nautilus_trader.cache.cache import Cache
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.events import AccountState

    from apps.strategies_nautilus.portfolio_session_account import SessionCashAccount

    original = owner.cache.accounts()[0].events[0]
    now = clock.timestamp_ns()
    cache = Cache()
    cache.add_instrument(owner.cache.instruments()[0])
    cache.add_account(
        SessionCashAccount(
            AccountState(
                account_id=original.account_id,
                account_type=original.account_type,
                base_currency=None,
                balances=original.balances,
                margins=[],
                reported=False,
                info={},
                event_id=UUID4(),
                ts_event=now,
                ts_init=now,
            ),
            cache=cache,
        )
    )
    live_owner = SimpleNamespace(clock=clock, cache=cache)
    ledger = ReadOnlyRuntimeLedger(tmp_path / "probe.json").create(
        live_owner, session_id=SID, source=BINDING
    )
    try:
        ledger.observe(live_owner)
        wrapped = read_session(ledger.path.read_bytes())
        assert wrapped["state"]["updated_ns"] == wrapped["native"]["ts_ns"]
        bridge = ReadOnlyRuntimeBridge(live_owner, ledger)
        with pytest.raises(ValueError):
            bridge.require_healthy()
        for method in (ledger.prepare, ledger.prepare_cancel, ledger.record_dispatch):
            with pytest.raises(ValueError, match="cannot"):
                method()
        bridge.account_update(
            {
                "E": clock.timestamp_ms(),
                "u": clock.timestamp_ms(),
                "B": [{"a": "BTC", "f": "2", "l": "0"}],
            }
        )
        bridge.assert_account_correlated()
        bridge.account_update(
            {
                "E": clock.timestamp_ms(),
                "u": clock.timestamp_ms(),
                "B": [{"a": "BTC", "f": "3", "l": "0"}],
            }
        )
        with pytest.raises(StreamError):
            bridge.assert_account_correlated()
        assert ledger.state["halt_reasons"]
    finally:
        ledger.close()
        owner.engine.dispose()


def test_private_read_rejects_symlinks_and_public_files(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"{}")
    path.chmod(0o644)
    with pytest.raises(StreamError):
        private_read(path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        private_read(link)


def test_disconnect_during_native_reconciliation_invalidates_result(case, monkeypatch):
    receipt = collect(case)
    from apps.strategies_nautilus import portfolio_session_bootstrap as module

    original = module.recover_session

    def disconnect(*args, **kwargs):
        result = original(*args, **kwargs)
        case.journal.disconnect("fixture disconnected during native reconciliation")
        return result

    monkeypatch.setattr(module, "recover_session", disconnect)
    with pytest.raises(StreamError):
        reconcile_collected(case.ledger.path.read_bytes(), receipt, case.journal, loop=case.loop)


def test_production_host_is_denied_even_with_valid_account_selectors(case):
    case.http._base_url = "https://api.binance.com"
    with pytest.raises(StreamError):
        collect(case)
    assert case.calls == []


def test_activation_fsync_failure_never_reopens_allowance(tmp_path, monkeypatch):
    lease = SessionLease(BINDING, "a" * 64, root=tmp_path / "scope")

    def fail(fd):
        raise OSError("fixture fsync failed")

    monkeypatch.setattr(os, "fsync", fail)
    try:
        with pytest.raises(OSError):
            lease.activate()
        with pytest.raises(FileExistsError):
            lease.activate()
    finally:
        lease.close()


def test_liveclock_full_native_bootstrap_without_execution_client(tmp_path):
    from apps.strategies_nautilus.portfolio_session_bootstrap import bootstrap_probe
    from tests.ops.test_portfolio_testnet_admission import symbol

    async def scenario():
        clock = LiveClock()
        http = SessionReadHttpClient(
            clock, "offline-session-key", None, TESTNET_REST, ed25519_private_key=PEM
        )
        symbols = [symbol("BTC"), symbol("ETH")]
        for s in symbols:
            s.update(
                quotePrecision=8,
                icebergAllowed=True,
                ocoAllowed=True,
                quoteOrderQtyMarketAllowed=True,
                allowTrailingStop=True,
                isMarginTradingAllowed=False,
                permissions=["SPOT"],
            )
        body = canonical({"symbols": symbols})
        metadata = canonical(
            {
                "schema_version": "portfolio.testnet_exchange_info_observation.v1",
                "endpoint": TESTNET_REST + "/api/v3/exchangeInfo",
                "started_ns": clock.timestamp_ns(),
                "received_ns": clock.timestamp_ns(),
                "response_body": body.decode(),
                "response_sha256": hashlib.sha256(body).hexdigest(),
            }
        )
        account = {
            "uid": 123,
            "accountType": "SPOT",
            "canTrade": True,
            "balances": [
                {"asset": a, "free": q, "locked": "0"}
                for a, q in (("BTC", "2"), ("USDT", "100"), ("ETH", "5"))
            ],
        }
        owner = bootstrap_probe(
            account=account,
            metadata_raw=metadata,
            binding=BINDING,
            path=tmp_path / "probe.json",
            clock=clock,
            http=http,
            credentials=SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM),
            loop=asyncio.get_running_loop(),
            session_id=SID,
        )
        try:
            assert len(owner.cache.accounts()[0].balances()) == 3
            assert owner.cache.instruments()[0].size_precision == 8
            with pytest.raises(StreamError):
                owner.engine.register_client(owner.receiver)
            with pytest.raises(StreamError):
                owner.engine.execute(None)
            owner.bridge.account_update(
                {
                    "E": clock.timestamp_ms(),
                    "u": clock.timestamp_ms(),
                    "B": [{"a": "ETH", "f": "5", "l": "0"}],
                }
            )
            owner.bridge.assert_account_correlated()
            with pytest.raises(StreamError):
                owner.bridge.account_update(
                    {
                        "E": clock.timestamp_ms(),
                        "u": clock.timestamp_ms(),
                        "B": [{"a": "ETH", "f": "6", "l": "0"}],
                    }
                )
            assert "unexplained_unrelated_asset_delta" in owner.ledger.state["halt_reasons"]
        finally:
            owner.engine.stop()
            await asyncio.gather(
                owner.engine.get_cmd_queue_task(), owner.engine.get_evt_queue_task()
            )
            owner.engine.dispose()
            owner.ledger.close()

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_session_ledger import (
    SessionLedgerError,
    balances,
    read_session,
)
from apps.strategies_nautilus.portfolio_session_runtime import (
    RUNTIME_PROFILE,
    await_terminal,
    fixture_signal,
    matching_account,
    start_matching,
    stop_matching,
)
from apps.strategies_nautilus.portfolio_session_transport import (
    CollectedSession,
    SessionJournal,
    SessionLease,
    SessionReadHttpClient,
)
from apps.strategies_nautilus.portfolio_stream import StreamError, canonical
from apps.strategies_nautilus.portfolio_testnet_credentials import TESTNET_REST
from apps.strategies_nautilus.runners.portfolio_session_acceptance import BINDING, rules
from apps.strategies_nautilus.runners.portfolio_session_bridge_acceptance import (
    drain,
    execution_report,
)
from tests.ops.test_portfolio_testnet_admission import symbol
from tests.strategies_nautilus.test_portfolio_session_transport import PEM


def create_owner(root):
    clock = LiveClock()
    credentials = SimpleNamespace(api_key="offline-session-key", private_key_pem=PEM)
    http = SessionReadHttpClient(clock, credentials.api_key, None, TESTNET_REST,
                                ed25519_private_key=PEM)
    symbols = [symbol("BTC"), symbol("ETH")]
    for row in symbols:
        row.update(quotePrecision=8, icebergAllowed=True, ocoAllowed=True,
                   quoteOrderQtyMarketAllowed=True, allowTrailingStop=True,
                   isMarginTradingAllowed=False, permissions=["SPOT"])
    body = canonical({"symbols": symbols})
    metadata = canonical({"schema_version": "portfolio.testnet_exchange_info_observation.v1",
        "endpoint": TESTNET_REST + "/api/v3/exchangeInfo", "started_ns": clock.timestamp_ns(),
        "received_ns": clock.timestamp_ns(), "response_body": body.decode(),
        "response_sha256": hashlib.sha256(body).hexdigest()})
    account = {"uid": 123, "accountType": "SPOT", "canTrade": True, "balances": [
        {"asset": a, "free": q, "locked": "0"} for a, q in (("BTC", "2"), ("USDT", "100"), ("ETH", "5"))]}
    owner, provider = matching_account(account=account, metadata_raw=metadata,
                                      binding=BINDING, clock=clock, http=http)
    lease = SessionLease(BINDING, "a" * 64, root=root)
    journal = SessionJournal(root / "stream.jsonl", BINDING, clock_ns=clock.timestamp_ns)
    journal.subscribed(7, BINDING)
    owner.lease, owner.journal = lease, journal
    start_matching(owner, provider, lease=lease, journal=journal, credentials=credentials,
                   loop=asyncio.get_running_loop())
    owner.calls = []
    owner.on_request = None

    async def request(method, *, url, **kwargs):
        parsed = urlsplit(url)
        assert parsed.scheme + "://" + parsed.netloc == TESTNET_REST
        assert parsed.path == "/api/v3/order"
        params = parse_qs(parsed.query)
        assert params["signature"][0]
        state = read_session(owner.ledger.path.read_bytes())["state"]
        kind = "submit" if method == HttpMethod.POST else "cancel"
        oid = params["newClientOrderId" if kind == "submit" else "origClientOrderId"][0]
        assert state["dispatches"][f"{kind}:{oid}"]
        assert state["view"]["statuses"][oid] == ("SUBMITTED" if kind == "submit" else "PENDING_CANCEL")
        assert state["runtime_profile"] == RUNTIME_PROFILE
        owner.calls.append((method, params))
        if owner.on_request:
            await owner.on_request(method)
        return SimpleNamespace(status=200, body=canonical({"symbol": "BTCUSDT",
            "orderId": 101 if oid.endswith("-b") else 102, "clientOrderId": oid,
            "transactTime": clock.timestamp_ms()}))
    owner.http._client = SimpleNamespace(request=request)
    arm(owner)
    return owner


def arm(owner):
    evidence = {"source": asdict(BINDING), "received_ns": owner.clock.timestamp_ns()}
    receipt = CollectedSession(owner.ledger.sha256, evidence, owner.journal.fence(), "fixture",
                               hashlib.sha256(canonical(evidence)).hexdigest())
    owner.rules = rules(owner.clock.timestamp_ns())
    owner.bridge.arm(receipt, owner.rules)


@pytest.fixture
def case(tmp_path):
    loop = asyncio.new_event_loop()
    async def build():
        return create_owner(tmp_path / "scope")
    owner = loop.run_until_complete(build())
    owner.loop = loop
    try:
        yield owner
    finally:
        loop.run_until_complete(stop_matching(owner))
        owner.journal.close()
        owner.lease.close()
        loop.close()


def submit(owner, side="buy"):
    return owner.strategy.consume(fixture_signal(owner, side), rules=owner.rules, price="70000.00")


def flush(owner):
    owner.loop.run_until_complete(drain(owner))


def emit(owner, order, **kwargs):
    owner.journal.observe(canonical({"subscriptionId": 7,
        "event": json.loads(execution_report(owner, order, **kwargs))}))


def test_real_clock_queue_and_signed_one_attempt_dispatch(case):
    order = submit(case)
    assert not case.calls
    flush(case)
    assert len(case.calls) == 1 and order.status.name == "SUBMITTED"
    assert case.risk.command_count == 1
    assert not case.bridge.failed
    with pytest.raises((SessionLedgerError, StreamError)):
        submit(case)
    assert len(case.calls) == 1
    archive = (case.lease.root / "stream.jsonl").read_text()
    assert "matching_attempt" in archive and "matching_response" in archive
    assert "signature" not in archive and PEM not in archive


def test_real_clock_full_buy_owned_cleanup_and_account_event_ordering(case):
    buy = submit(case)
    flush(case)
    emit(case, buy)
    flush(case)
    # Account callback arrives ahead of queued native fill; it must wait, never patch.
    case.bridge.account_update({"E": case.clock.timestamp_ms(), "u": case.clock.timestamp_ms(),
        "B": [{"a": "BTC", "f": "2.0001", "l": "0"}, {"a": "USDT", "f": "93", "l": "0"}]})
    assert case.bridge.account_updates
    emit(case, buy, kind="TRADE", quantity="0.00010000", total="0.00010000", tid=201)
    flush(case)
    case.bridge.assert_account_correlated()
    assert D(case.ledger.state["view"]["owned_btc"]) == D("0.0001")
    arm(case)
    sell = submit(case, "flat")
    flush(case)
    emit(case, sell)
    emit(case, sell, kind="TRADE", quantity="0.00010000", total="0.00010000", tid=202)
    flush(case)
    assert not case.bridge.failed
    assert D(case.ledger.state["view"]["owned_btc"]) == 0
    assert D(case.ledger.state["view"]["expected_totals"]["BTC"]) == 2
    assert len(case.calls) == 2


def test_ack_timer_cancels_once_after_two_seconds_and_settles_late_fill(case):
    async def on_request(method):
        order = case.cache.orders()[0]
        if method == HttpMethod.POST:
            emit(case, order)
        else:
            emit(case, order, kind="TRADE", quantity="0.00008000", total="0.00008000", tid=201)
            emit(case, order, kind="CANCELED", total="0.00008000")
    case.on_request = on_request
    order = submit(case)
    result = case.loop.run_until_complete(await_terminal(case, order))
    assert result == "CANCELED" and len(case.calls) == 2
    events = order.events
    ack = next(e.ts_init for e in events if type(e).__name__ == "OrderAccepted")
    cancel = next(e.ts_init for e in events if type(e).__name__ == "OrderPendingCancel")
    assert 2_000_000_000 <= cancel - ack < 3_000_000_000
    assert D(case.ledger.state["view"]["owned_btc"]) == D("0.00008")


@pytest.mark.parametrize("stage", ["prepare", "submitted", "dispatch", "journal"])
def test_durable_failure_blocks_real_transport(case, monkeypatch, stage):
    old = os.fsync
    def fsync(fd):
        orders = case.cache.orders()
        status = orders[0].status.name if orders else "PREPARE"
        dispatches = case.ledger.state.get("dispatches", {})
        if (stage == "prepare" or stage == "submitted" and status == "SUBMITTED"
            or stage == "dispatch" and dispatches):
            raise OSError("fixture failed fsync")
        return old(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    if stage == "journal":
        old_append = case.journal._append
        def append(kind, **kwargs):
            if kind == "matching_attempt":
                raise OSError("fixture archive unavailable")
            return old_append(kind, **kwargs)
        monkeypatch.setattr(case.journal, "_append", append)
    if stage == "prepare":
        with pytest.raises(OSError):
            submit(case)
    else:
        submit(case)
        flush(case)
    assert not case.calls


def test_transport_timeout_preserves_submitted_and_late_fill(case):
    async def failure(method):
        raise TimeoutError("fixture signed URL must not escape")
    case.on_request = failure
    order = submit(case)
    flush(case)
    assert len(case.calls) == 1 and order.status.name == "SUBMITTED"
    assert case.bridge.failed and case.ledger.state["dispatches"]
    # Native accounting continues after send uncertainty; next admission stays halted.
    case.client._handle_user_ws_message(execution_report(case, order))
    case.client._handle_user_ws_message(execution_report(case, order,
        kind="TRADE", quantity="0.00010000", total="0.00010000", tid=201))
    flush(case)
    assert D(case.ledger.state["view"]["owned_btc"]) == D("0.0001")
    with pytest.raises(SessionLedgerError):
        arm(case)


@pytest.mark.parametrize("failure", ["disconnect", "rules", "receipt", "lease"])
def test_queue_delay_source_or_scope_loss_blocks_sending(case, failure):
    submit(case)
    if failure == "disconnect":
        case.journal.disconnect("fixture lost")
    elif failure == "lease":
        case.lease.close()
    elif failure == "rules":
        case.bridge.admission = (case.bridge.admission[0], rules(1))
    else:
        case.bridge.admission[0].evidence["received_ns"] = 1
    flush(case)
    assert not case.calls and case.bridge.failed


@pytest.mark.parametrize("method,path,params", [
    (HttpMethod.POST, "/api/v3/order", {}),
    (HttpMethod.DELETE, "/api/v3/openOrders", {}),
    (HttpMethod.GET, "/api/v3/account", {}),
    (HttpMethod.POST, "https://api.binance.com/api/v3/order", {}),
])
def test_forbidden_transport_routes(case, method, path, params):
    with pytest.raises(StreamError):
        case.loop.run_until_complete(case.http.sign_request(method, path, params))
    with pytest.raises(StreamError):
        case.loop.run_until_complete(case.http.send_request(method, path, params))
    assert not case.calls


def test_native_risk_denial_consumes_buy_without_network(case):
    case.risk.set_max_notional_per_order(case.cache.instruments()[0].id, D("6"))
    order = submit(case)
    flush(case)
    assert order.status.name == "DENIED" and not case.calls
    assert case.ledger.state["view"]["buy_allowance_consumed"]


def test_unexplained_balance_cannot_be_used_for_admission(case):
    original = balances(case.cache.accounts()[0])
    case.bridge.account_update({"E": case.clock.timestamp_ms(), "u": case.clock.timestamp_ms(),
                               "B": [{"a": "BTC", "f": "3", "l": "0"}]})
    with pytest.raises(StreamError):
        submit(case)
    assert balances(case.cache.accounts()[0]) == original and not case.calls


def test_activation_survives_process_owner_close_and_forbids_new_buy(case):
    submit(case)
    flush(case)
    case.lease.close()
    lease = SessionLease(BINDING, "a" * 64, root=case.lease.root)
    try:
        lease.assert_active()
        with pytest.raises(StreamError):
            lease.activate()
    finally:
        lease.close()


def test_native_liveclock_order_creation_has_bounded_age(case):
    now = case.clock.timestamp_ns()
    assert case.ledger._order_time_valid(SimpleNamespace(ts_init=now - 100), now)
    assert not case.ledger._order_time_valid(SimpleNamespace(ts_init=now + 1), now)
    assert not case.ledger._order_time_valid(SimpleNamespace(ts_init=now - 1_000_000_001), now)


@pytest.mark.parametrize("change", [{"symbol": "ETHUSDT"}, {"quantity": "0.1"},
    {"type": "MARKET"}, {"price": "100000"}, {"newClientOrderId": "foreign"},
    {"recvWindow": "60000"}, {"extra": "value"}])
def test_parameter_mutation_never_reaches_native_network(case, change):
    order = submit(case)
    flush(case)
    params = {k: values[0] for k, values in case.calls[0][1].items() if k != "signature"}
    params.update(change)
    with pytest.raises((StreamError, SessionLedgerError)):
        case.loop.run_until_complete(case.http.sign_request(HttpMethod.POST, "/api/v3/order", params))
    assert len(case.calls) == 1 and order.status.name == "SUBMITTED"


def test_native_ed25519_signature_matches_exact_unsigned_order_bytes(case, tmp_path):
    import base64
    import subprocess
    from urllib.parse import urlencode

    submit(case)
    flush(case)
    params = {k: values[0] for k, values in case.calls[0][1].items()}
    signature = params.pop("signature")
    key, public, message, sig = [tmp_path / name for name in ("key.pem", "public.pem", "message", "sig")]
    key.write_text(PEM)  # Public test seed; never a real credential.
    message.write_bytes(urlencode(params).encode())
    sig.write_bytes(base64.b64decode(signature))
    subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(public)],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public),
                    "-rawin", "-in", str(message), "-sigfile", str(sig)],
                   check=True, capture_output=True)


def test_unknown_native_callback_halts_matching(case):
    buy = submit(case)
    flush(case)
    raw = json.loads(execution_report(case, buy))
    raw["c"] = "foreign-order"
    with pytest.raises(StreamError):
        case.journal.observe(canonical({"subscriptionId": 7, "event": raw}))
    assert case.bridge.failed and not case.journal.connected
    assert len(case.calls) == 1

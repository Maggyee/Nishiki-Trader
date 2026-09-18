"""Signed fixture account requests must bind wire bytes and exact native balances."""

import base64
import json
import os
import ssl
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger
from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_tls_receipt import _rechain
from tests.ops.test_egress_tls_receipt import channels as channels

PIN, TRUST = "a" * 64, b"selected fixture trust"


def body(precision=False):
    return {
        "uid": 41001,
        "accountType": "SPOT",
        "balances": [
            {
                "asset": "BTC",
                "free": "0.000000001" if precision else "0.01000000",
                "locked": "0.00100000",
            },
            {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
            {"asset": "BNB", "free": "1.00000000", "locked": "0.10000000"},
            {"asset": "USDT", "free": "500.00000000", "locked": "12.50000000"},
        ],
    }


def selection(module, *, index=3):
    requests = load("gateway_native_requests")
    challenge = {
        "index": index,
        "nonce": "a" * 32,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
    }
    request = json.loads(requests.native_request(challenge))
    value = {
        "profile": module.SELECTION_PROFILE,
        "binding_sha256": PIN,
        "challenge": challenge,
        "request": request,
        "received": [time.time_ns(), time.monotonic_ns()],
    }
    return vars(requests), value


@pytest.fixture
def account_case(tmp_path, channels, monkeypatch):
    account, tls, receiver, gateway = [
        load(n)
        for n in ("gateway_native_account", "gateway_tls", "gateway_tls_receipt", "ledger_gateway")
    ]
    module = account.ledger_view(ledger)
    tmp_path.chmod(0o700)
    attempt = ledger.AttemptLedger(
        tmp_path,
        binding=SimpleNamespace(verify=lambda: {"binding_sha256": PIN}),
        binding_sha256=PIN,
        profile=ledger.ACCOUNT_PROFILE,
    )
    lifecycle = gateway.GatewayLifecycle(attempt, module)
    requests, selected = selection(account)
    contract = account.AccountContract(requests, selected)
    transport = account.transport_view(vars(tls), contract)
    state = SimpleNamespace(
        account=account,
        contract=contract,
        attempt=attempt,
        lifecycle=lifecycle,
        transport=transport,
        module=module,
        receiver=receiver,
        errors=[],
        sent=[],
        connected=[],
        headers=[],
    )
    collector = SimpleNamespace(channel=channels[0], verify=lambda: None)
    channels[1].connection.settimeout(5)

    class Socket:
        chunks = []

        def setsockopt(self, *args):
            assert args[-1] == tls.MARK

        def settimeout(self, value):
            assert 0 < value <= 4

        def connect(self, peer):
            assert peer == tls.PEER and attempt.state.pending == 0
            state.connected.append(peer)

        def sendall(self, raw):
            assert raw == contract.request
            # Independently verify the actual encoded query and signature.
            query = raw.split(b" ")[1].split(b"?", 1)[1].decode()
            params = parse_qsl(query, strict_parsing=True)
            assert [k for k, v in params] == ["timestamp", "recvWindow", "signature"]
            requests["verify_signature"](urlencode(params[:-1]), params[-1][1])
            state.sent.append(raw)

        def recv(self, size):
            return self.chunks.pop(0) if self.chunks else b""

        def getpeername(self):
            return tls.PEER

        def getpeercert(self, **kwargs):
            return b"fixture cert"

        def version(self):
            return "TLSv1.3"

        def cipher(self):
            return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        def close(self):
            pass

    connection = Socket()
    context = SimpleNamespace(
        check_hostname=True, verify_mode=ssl.CERT_REQUIRED, wrap_socket=lambda *a, **k: connection
    )
    monkeypatch.setattr(
        provenance,
        "_selection",
        lambda *a: (SimpleNamespace(hostname="rest.fixture.invalid"), context),
    )
    monkeypatch.setattr(tls.socket, "socket", lambda *a, **k: connection)
    state.socket, state.context = connection, context

    def review_tls(raw=None):
        raw = (attempt.path / "tls.jsonl").read_bytes() if raw is None else raw
        return transport["replay"](
            raw,
            expected_sha256=provenance.digest(raw),
            attempts=attempt.expected,
            lifecycle=lifecycle.expected,
            binding_sha256=PIN,
            trust_sha256=provenance.digest(TRUST),
            ledger_module=module,
            gateway_module=vars(gateway),
            provenance=provenance,
            rates=account.rates_view(),
        )

    def completed(raw):
        controller._revoke()
        payload = receiver.payload_from_tls(raw, review_tls(raw))
        return receiver.deliver(
            collector,
            attempt,
            lifecycle,
            payload,
            provenance,
            native_result=account.expected_result(payload),
        )

    controller = gateway.FixtureLedgerGateway(
        attempt,
        lifecycle=lifecycle,
        authorize=lambda: {"ok": True, "request_sha256": contract.request_pin},
        grant=lambda: None,
        revoke=lambda: None,
        send=lambda: transport["capture"](
            attempt, lifecycle, TRUST, provenance, account.rates_view(), on_complete=completed
        ),
    )

    def child():
        try:
            receiver.receive_payload(
                channels[1], provenance, account.rates_view(), native=account.validate_native
            )
        except BaseException as exc:
            state.errors.append(exc)
            channels[1].close()

    def run(value=None):
        raw = provenance.canonical(body() if value is None else value)
        connection.chunks = [
            b"HTTP/1.1 200 OK\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\nX-MBX-USED-WEIGHT-1M: 20\r\n\r\n",
            raw,
        ]
        state.thread = threading.Thread(target=child)
        state.thread.start()
        return controller.dispatch()

    def review(raw=None, **changes):
        raw = (attempt.path / "receipt.jsonl").read_bytes() if raw is None else raw
        kwargs = dict(
            expected_sha256=provenance.digest(raw),
            tls_raw=(attempt.path / "tls.jsonl").read_bytes(),
            attempts=attempt.expected,
            lifecycle=lifecycle.expected,
            binding_sha256=PIN,
            trust_sha256=provenance.digest(TRUST),
            ledger_module=module,
            gateway_module=vars(gateway),
            transport=transport,
            provenance=provenance,
            rates=account.rates_view(),
            native=vars(account),
        )
        kwargs.update(changes)
        return receiver.replay(raw, **kwargs)

    state.run, state.review, state.review_tls, state.controller = (
        run,
        review,
        review_tls,
        controller,
    )
    yield state
    channels[0].close()
    if hasattr(state, "thread"):
        state.thread.join(6)
        assert not state.thread.is_alive()
    controller.close()


def test_signed_wire_and_exact_native_balances(account_case):
    case = account_case
    case.run()
    case.thread.join(1)
    result = case.review()
    assert result["native_account_acknowledged"] and result["attempt_outcome_recorded"]
    assert not case.errors and len(case.sent) == 1 and case.controller.revoked
    assert len(result["native_result"]["balances"]) == 4
    assert (
        next(r for r in result["native_result"]["balances"] if r["currency"] == "ETH")["total"]
        == "0.00000000"
    )
    assert result["header_receipt"] == result["native_result"]["header_receipt"]
    rates = case.review_tls()["rate_evidence"]
    assert (
        rates["used_weight_1m"] == 20
        and rates["limit"] is None
        and rates["connection_charge"] is None
    )
    assert not result["network_admitted"] and not result["native_collector_integrated"]


def test_native_rounding_refuses_ack_preserves_tls_and_pending(account_case):
    case = account_case
    with pytest.raises(RuntimeError):
        case.run(body(True))
    case.thread.join(1)
    assert str(case.errors[0]) == "native_account_rounding_refused"
    assert case.review_tls()["status"] == "complete"
    report = case.review()
    assert not report["native_account_acknowledged"] and not report["attempt_outcome_recorded"]
    assert case.attempt.state.pending == 0 and case.controller.revoked


@pytest.mark.parametrize("stage", ["connect", "send"])
def test_expired_signed_request_never_sent(account_case, monkeypatch, stage):
    case = account_case
    original = case.contract.validate_at

    def expire(*args, **kwargs):
        monkeypatch.setattr(
            case.contract,
            "validate_at",
            lambda utc, mono: original(utc + 6_000_000_000, mono + 6_000_000_000),
        )
        return case.socket

    if stage == "connect":
        expire()
    else:
        case.context.wrap_socket = expire
    with pytest.raises(ValueError, match="stale_or_clock_change"):
        case.run()
    assert not case.sent and len(case.connected) == (stage == "send")
    assert case.attempt.state.pending == 0 and case.controller.revoked


@pytest.mark.parametrize(
    "damage", ["request", "signature", "scope", "index", "received", "profile"]
)
def test_selected_account_contract_refuses_mutation(damage):
    account = load("gateway_native_account")
    requests, value = selection(account)
    if damage == "request":
        value["request"]["request"]["path"] = "/api/v3/order"
    elif damage == "signature":
        value["request"]["request"]["params"]["signature"] = "A" * 88
    elif damage == "scope":
        value["binding_sha256"] = "invalid"
    elif damage == "index":
        value["challenge"]["index"] = 6
    elif damage == "received":
        value["received"][1] += 6_000_000_000
    else:
        value["profile"] = "old"
    with pytest.raises(ValueError):
        account.AccountContract(requests, value)


@pytest.mark.parametrize(
    "damage", ["balance", "clock", "parser", "profile", "attempt", "selection"]
)
def test_account_replay_requires_original_request_and_receipt(account_case, damage):
    case = account_case
    case.run()
    raw = (case.attempt.path / "receipt.jsonl").read_bytes()
    rows = list(map(json.loads, raw.splitlines()))
    kwargs = {}
    if damage == "balance":
        rows[1]["native_result"]["balances"][0]["free"] = "999"
    elif damage == "clock":
        rows[1]["native_result"]["header_receipt"]["utc_ns"] += 1
    elif damage == "parser":
        kwargs["native"] = None
    elif damage == "profile":
        rows[0]["profile"] = "portfolio.installed_native_receipt.v1"
    elif damage == "attempt":
        attempts = list(map(json.loads, case.attempt.expected.splitlines()))
        for row in attempts:
            if row["kind"] in {"prepared", "outcome"}:
                row["payload"]["request_sha256"] = "0" * 64
        kwargs["attempts"] = _rechain(attempts)
    else:
        case.contract.selection["received"][0] += 1
    with pytest.raises(ValueError):
        case.review(_rechain(rows), **kwargs)


@pytest.mark.parametrize(
    "damage", ["uid", "duplicate", "missing", "unknown", "negative", "float", "nonfinite"]
)
def test_account_mapping_refuses_incomplete_or_ambiguous_balances(damage):
    account = load("gateway_native_account")
    value = body()
    if damage == "uid":
        value["uid"] = 41002
    elif damage == "duplicate":
        value["balances"][1] = value["balances"][0]
    elif damage == "missing":
        value["balances"].pop()
    elif damage == "unknown":
        value["balances"][0]["asset"] = "OTHER"
    else:
        value["balances"][0]["free"] = {"negative": "-1", "float": 1.0, "nonfinite": "NaN"}[damage]
    payload = provenance.canonical(
        {
            "response_b64": base64.b64encode(
                b"HTTP/1.1 200 OK\r\n\r\n" + provenance.canonical(value)
            ).decode()
        }
    )
    with pytest.raises(ValueError):
        account.expected_result(payload)


def test_account_native_import_refuses_root(monkeypatch):
    account = load("gateway_native_account")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root_refused"):
        account.prepare_native()


def test_signature_verification_time_cannot_extend_send_window(account_case, monkeypatch):
    case = account_case
    original = case.contract.validate_at
    utc, mono = time.time_ns, time.monotonic_ns

    def delayed(utc_ns, mono_ns):
        original(utc_ns, mono_ns)
        monkeypatch.setattr(
            case.account,
            "time",
            SimpleNamespace(
                time_ns=lambda: utc() + 6_000_000_000, monotonic_ns=lambda: mono() + 6_000_000_000
            ),
        )

    monkeypatch.setattr(case.contract, "validate_at", delayed)
    with pytest.raises(ValueError, match="expired_before_wire"):
        case.run()
    assert not case.connected and not case.sent and case.attempt.state.pending == 0


def test_tls_account_profile_requires_explicit_selected_contract(account_case):
    case = account_case
    case.run()
    raw = (case.attempt.path / "tls.jsonl").read_bytes()
    with pytest.raises(ValueError, match="gateway_tls_selection"):
        load("gateway_tls").replay(
            raw,
            expected_sha256=provenance.digest(raw),
            attempts=case.attempt.expected,
            lifecycle=case.lifecycle.expected,
            binding_sha256=PIN,
            trust_sha256=provenance.digest(TRUST),
            ledger_module=case.module,
            gateway_module=vars(load("ledger_gateway")),
            provenance=provenance,
            rates=case.account.rates_view(),
        )


@pytest.mark.parametrize("damage", ["wrong_operation", "second_attempt", "outcome_pin"])
def test_account_ledger_fixed_single_attempt(account_case, damage):
    case = account_case
    if damage == "wrong_operation":
        with pytest.raises(ValueError, match="single_signed_account_attempt_required"):
            case.attempt.prepare(
                caller="collector",
                operation="open_orders",
                request_sha256=case.contract.request_pin,
            )
    elif damage == "outcome_pin":
        case.attempt.prepare(
            caller="collector", operation="account_read", request_sha256=case.contract.request_pin
        )
        with pytest.raises(ValueError, match="outcome_request_changed"):
            case.attempt.outcome(index=0, result="succeeded", request_sha256="0" * 64)
    else:
        case.run()
        with pytest.raises(ValueError, match="single_signed_account_attempt_required"):
            case.attempt.prepare(
                caller="collector",
                operation="account_read",
                request_sha256=case.contract.request_pin,
            )

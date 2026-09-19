"""Same-run originals, predecessor receipts and conservative sequence outcomes."""

import copy
import json
import os
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.ops.test_egress_installed_gateway import DIRECTORY, load
from tests.ops.test_egress_native_receipt import metadata
from tests.ops.test_egress_signed_account import body
from tests.ops.test_egress_tls_receipt import _rechain


def capture_sequence(tmp_path_factory, *, orders=False, routes=False):
    orders = orders or routes
    root = tmp_path_factory.mktemp("read-sequence")
    entry = load("installed_gateway")
    code = load("gateway_read_sequence")
    sources = {
        name: (
            (
                DIRECTORY.parents[1] / "apps/strategies_nautilus"
                if name.startswith("portfolio_")
                else DIRECTORY
            )
            / name
        ).read_text()
        for name in entry.FILES
    }
    original_modules = {
        k: v for k, v in sys.modules.items() if k == "apps" or k.startswith("apps.")
    }
    modules = code.load_sources(sources)
    trust = root / "trust.pem"
    trust.write_bytes(b"fixture trust")
    held, descriptors = {}, []

    def open_file(path, mode):
        path = trust if path == "/etc/trader/egress-gateway-fixture-ca.pem" else Path(path)
        fd = os.open(path, os.O_RDONLY)
        descriptors.append(fd)
        held[path] = path.read_bytes()
        return fd

    def open_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(fd)
        return fd

    def verify():
        for path, raw in held.items():
            if path.read_bytes() != raw:
                raise ValueError("held_original_changed")

    authority = SimpleNamespace(
        verify=verify, open_file=open_file, open_directory=open_directory, manifest_sha256="a" * 64
    )
    sequence = code.Sequence(
        {"STORAGE": str(root)},
        authority,
        SimpleNamespace(manifest_sha256="b" * 64),
        modules,
        orders=orders,
        routes=routes,
    )
    real_socket = socket.socket
    errors, payloads = [], []
    try:

        def capture_step(index):
            sequence.prepare(index)
            binding = {
                "read_sequence": sequence.verify(),
                "base_manifest_sha256": "a" * 64,
                "gateway_manifest_sha256": "b" * 64,
                "tls_trust_sha256": code.digest(trust.read_bytes()),
                "rules": {},
                "route": [],
                "net": "fixture",
                "collector": {
                    "process": {
                        "native_runtime_sha256": "c" * 64,
                        "installation_manifest_sha256": "a" * 64,
                    }
                },
            }
            sequence.bind(binding)
            pin = code.digest(code.canonical(binding))
            native = (
                modules["books"]
                if routes and index == 5
                else modules["orders"]
                if orders and index in {2, 3}
                else modules["account"]
                if index
                else modules["metadata"]
            )
            ledger = native["ledger_view"](modules["ledger"]) if index else modules["ledger"]
            rates = modules["account"]["rates_view"]() if index else modules["rates"]
            attempt = ledger.AttemptLedger(
                sequence.storage,
                binding=SimpleNamespace(verify=lambda: {"binding_sha256": pin}),
                binding_sha256=pin,
                profile=ledger.PROFILE,
            )
            lifecycle = modules["gateway"]["GatewayLifecycle"](attempt, ledger)
            transport = modules["tls"]
            request = transport["REQUEST"]
            request_pin = None
            if index:
                challenge = {
                    "index": 8 if routes and index == 5 else 4 if orders and index in {2, 3} else 3,
                    "nonce": os.urandom(16).hex(),
                    "utc_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                }
                selected = {
                    "profile": native["SELECTION_PROFILE"],
                    "binding_sha256": pin,
                    "challenge": challenge,
                    "request": json.loads(modules["requests"]["native_request"](challenge)),
                    "received": [time.time_ns(), time.monotonic_ns()],
                }
                contract = native["AccountContract"](modules["requests"], selected)
                (attempt.path / contract.SELECTION_FILE).write_bytes(contract.raw)
                (attempt.path / contract.SELECTION_FILE).chmod(0o600)
                transport = modules["account"]["transport_view"](transport, contract)
                request, request_pin = contract.request, contract.request_pin
            value = (
                body()
                if index
                else {
                    "symbols": metadata(),
                    "rateLimits": [
                        {
                            "rateLimitType": "REQUEST_WEIGHT",
                            "interval": "MINUTE",
                            "intervalNum": 1,
                            "limit": 6000,
                        },
                        {
                            "rateLimitType": "RAW_REQUESTS",
                            "interval": "MINUTE",
                            "intervalNum": 5,
                            "limit": 61000,
                        },
                        {
                            "rateLimitType": "CONNECTIONS",
                            "interval": "MINUTE",
                            "intervalNum": 5,
                            "limit": 300,
                        },
                    ],
                }
            )
            if orders and index in {2, 3}:
                value = copy.deepcopy(load("installed_gateway_selftest").FIXTURE_ORDERS)
            if routes and index == 0:
                for row in value["symbols"]:
                    row.update(status="TRADING", isSpotTradingAllowed=True)
            if routes and index == 5:
                value = copy.deepcopy(load("installed_gateway_selftest").FIXTURE_BOOKS)
            raw = code.canonical(value)
            chunks = [
                b"HTTP/1.1 200 OK\r\nContent-Length: "
                + str(len(raw)).encode()
                + b"\r\nX-MBX-USED-WEIGHT-1M: 20\r\n\r\n",
                raw,
            ]
            sent = []
            connection = SimpleNamespace(
                setsockopt=lambda *a: None,
                settimeout=lambda t: None,
                connect=lambda peer: None,
                sendall=sent.append,
                recv=lambda size: chunks.pop(0),
                close=lambda: None,
                getpeername=lambda: modules["tls"]["PEER"],
                getpeercert=lambda **kw: b"cert",
                version=lambda: "TLSv1.3",
                cipher=lambda: ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256),
            )
            context = SimpleNamespace(
                check_hostname=True,
                verify_mode=ssl.CERT_REQUIRED,
                wrap_socket=lambda *a, **k: connection,
            )
            left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            channel = load("collector_launcher").ControlChannel
            peer = (os.getpid(), os.getuid(), os.getgid())
            channels = [channel(c, peer, timeout=5) for c in (left, right)]
            collector = SimpleNamespace(channel=channels[0], verify=lambda: sequence.verify())
            receipt = modules["receipt"]
            provenance = modules["provenance"]

            def consume():
                try:
                    payloads.append(
                        receipt["receive_payload"](
                            channels[1], provenance, rates, native=native["validate_native"]
                        )
                    )
                except BaseException as exc:
                    errors.append(exc)

            def completed(tls):
                gateway._revoke()
                report = transport["replay"](
                    tls,
                    expected_sha256=code.digest(tls),
                    attempts=attempt.expected,
                    lifecycle=lifecycle.expected,
                    binding_sha256=pin,
                    trust_sha256=code.digest(trust.read_bytes()),
                    ledger_module=ledger,
                    gateway_module=modules["gateway"],
                    provenance=provenance,
                    rates=rates,
                )
                payload = receipt["payload_from_tls"](tls, report)
                return receipt["deliver"](
                    collector,
                    attempt,
                    lifecycle,
                    payload,
                    provenance,
                    native_result=native["expected_result"](payload),
                )

            gateway = modules["gateway"]["FixtureLedgerGateway"](
                attempt,
                lifecycle=lifecycle,
                authorize=lambda: {
                    "ok": True,
                    **({"request_sha256": request_pin} if index else {}),
                },
                grant=lambda: None,
                revoke=lambda: None,
                send=lambda: transport["capture"](
                    attempt, lifecycle, trust.read_bytes(), provenance, rates, on_complete=completed
                ),
            )
            thread = threading.Thread(target=consume)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(
                    provenance,
                    "_selection",
                    lambda *a: (SimpleNamespace(hostname="rest.fixture.invalid"), context),
                )
                patch.setattr(socket, "socket", lambda *a, **k: connection)
                thread.start()
                try:
                    gateway.dispatch()
                finally:
                    thread.join(6)
                    gateway.close()
                    for c in channels:
                        c.close()
            assert not thread.is_alive() and not errors and sent == [request]
            bundle = sequence.read_bundle()
            sequence.append(
                "accepted", {"index": index, "bundle_sha256": code.digest(code.canonical(bundle))}
            )

        for index in range(len(sequence.steps)):
            capture_step(index)
        sequence.append("completed", {})
        yield SimpleNamespace(
            orders=orders,
            routes=routes,
            code=code,
            modules=modules,
            raw=sequence.expected,
            bundles=sequence.bundles,
            sequence=sequence,
            payloads=payloads,
            root=root,
            authority=authority,
        )
    finally:
        socket.socket = real_socket
        sequence.close()
        for name in list(sys.modules):
            if name == "apps" or name.startswith("apps."):
                del sys.modules[name]
        sys.modules.update(original_modules)
        for fd in descriptors:
            os.close(fd)


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    yield from capture_sequence(tmp_path_factory)


def review(case, raw=None, bundles=None):
    raw = case.raw if raw is None else raw
    return case.code.replay(
        raw,
        expected_sha256=case.code.digest(raw),
        bundles=case.bundles if bundles is None else bundles,
        modules=case.modules,
        orders=case.orders,
        routes=case.routes,
    )


def test_three_native_receipts_bind_one_complete_sequence(captured):
    result = review(captured)
    assert result["status"] == "complete" and result["accepted_steps"] == 3
    assert result["repeated_balances_equal"] and result["metadata_precision_matched"]
    assert len(captured.payloads) == 3
    assert not result["atomic_account_snapshot"] and not result["stream_fence_verified"]
    assert not result["network_admitted"] and not result["qualified_for_execution"]


@pytest.mark.parametrize("end", range(1, 8))
def test_every_original_prefix_stays_incomplete_without_final_record(captured, end):
    lines = captured.raw.splitlines(keepends=True)[:end]
    count = sum(json.loads(line)["kind"] == "prepared" for line in lines)
    result = review(captured, b"".join(lines), captured.bundles[:count])
    assert result["status"] == "incomplete_no_resume" and not result["restart_allowed"]
    assert not result["same_run_receipts_verified"]


@pytest.mark.parametrize(
    "damage", ["swap", "missing", "extra", "binding", "selection", "receipt", "request", "balance"]
)
def test_spliced_or_changed_child_originals_cannot_complete(captured, damage):
    bundles = copy.deepcopy(captured.bundles)
    if damage == "swap":
        bundles[1], bundles[2] = bundles[2], bundles[1]
    elif damage == "missing":
        bundles.pop()
    elif damage == "extra":
        bundles.append(bundles[-1])
    elif damage == "binding":
        binding = json.loads(bundles[1]["binding"])
        binding["read_sequence"]["prefix_sha256"] = "e" * 64
        bundles[1]["binding"] = captured.code.canonical(binding).decode()
    elif damage == "selection":
        bundles[1]["selection"] = bundles[2]["selection"]
    elif damage == "receipt":
        del bundles[1]["receipt"]
    elif damage == "request":
        bundles[1]["tls"] = bundles[2]["tls"]
    else:
        rows = list(map(json.loads, bundles[1]["receipt"].splitlines()))
        rows[-1]["native_result"]["balances"][0]["free"] = "100"
        bundles[1]["receipt"] = _rechain(rows).decode()
    with pytest.raises(ValueError):
        review(captured, bundles=bundles)


@pytest.mark.parametrize(
    "damage",
    [
        "skip",
        "duplicate",
        "early_complete",
        "clock",
        "early_accept",
        "profile",
        "digest",
        "after_complete",
    ],
)
def test_rehashed_parent_cannot_skip_original_order_or_clocks(captured, damage):
    rows = list(map(json.loads, captured.raw.splitlines()))
    if damage == "skip":
        rows.pop(2)
    elif damage == "duplicate":
        rows.insert(3, copy.deepcopy(rows[2]))
    elif damage == "early_complete":
        rows[2]["kind"], rows[2]["payload"] = "completed", {}
    elif damage == "clock":
        rows[3]["utc_ns"] += 60_000_000
    elif damage == "early_accept":
        for key in ("utc_ns", "monotonic_ns"):
            rows[2][key] = rows[1][key]
    elif damage == "profile":
        rows[0]["profile"] = "other"
    elif damage == "digest":
        rows[2]["payload"]["bundle_sha256"] = "f" * 64
    else:
        rows.append(copy.deepcopy(rows[-1]))
    with pytest.raises(ValueError):
        review(captured, _rechain(rows))


def test_reconciliation_uses_decimal_equality_and_checks_locked(captured):
    results = copy.deepcopy(review(captured)["steps"])
    results[2]["native_result"]["balances"][0]["free"] = "1.0"
    assert captured.code.reconcile(results)["repeated_balances_equal"]
    results[2]["native_result"]["balances"][0]["locked"] = "0.2"
    with pytest.raises(ValueError, match="balances_changed"):
        captured.code.reconcile(results)


def test_metadata_precision_must_match_account_mapping_before_next_read(captured):
    results = copy.deepcopy(review(captured)["steps"][:1])
    results[0]["native_result"]["currencies"][0]["precision"] = 7
    with pytest.raises(ValueError, match="metadata_precision_mismatch"):
        captured.code.reconcile(results)


def test_fresh_sequence_refuses_existing_scope_before_any_step(captured):
    with pytest.raises(FileExistsError):
        captured.code.Sequence(
            {"STORAGE": str(captured.root)},
            captured.authority,
            SimpleNamespace(manifest_sha256="b" * 64),
            captured.modules,
        )
    assert captured.sequence.expected == captured.raw


@pytest.fixture
def fresh(captured, tmp_path):
    sequence = captured.code.Sequence(
        {"STORAGE": str(tmp_path)},
        captured.authority,
        SimpleNamespace(manifest_sha256="b" * 64),
        captured.modules,
    )
    try:
        yield sequence
    finally:
        sequence.close()


def test_held_file_deduplicates_descriptors_and_drift_never_revives(fresh):
    path = fresh.path / "README.md"
    fd = fresh.hold(path)
    count = len(fresh.fds)
    assert all(fresh.hold(path) == fd for _ in range(20))
    assert len(fresh.fds) == count
    original = path.read_bytes()
    path.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="held_original_changed"):
        fresh.verify()
    path.write_bytes(original)
    with pytest.raises(ValueError, match="authority_ended"):
        fresh.verify()


@pytest.mark.parametrize("damage", ["mode", "replace", "journal"])
def test_held_sequence_path_or_journal_drift_blocks_next_step(fresh, damage):
    if damage == "mode":
        fresh.path.chmod(0o755)
    elif damage == "replace":
        fresh.path.rename(fresh.path.with_name("moved-sequence"))
        fresh.path.mkdir(mode=0o700)
    else:
        (fresh.path / "sequence.jsonl").write_bytes(b"changed")
    with pytest.raises(ValueError):
        fresh.prepare(0)
    assert not (fresh.path / "metadata").exists()


def test_parent_preparation_fsync_failure_cannot_create_or_retry_child(
    fresh, captured, monkeypatch
):
    original = os.fsync

    def fail(fd):
        if fd == fresh.journal.fd:
            raise OSError("fixture fsync failure")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failure"):
        fresh.prepare(0)
    assert not (fresh.path / "metadata").exists()
    raw = (fresh.path / "sequence.jsonl").read_bytes()
    result = captured.code.replay(
        raw, expected_sha256=captured.code.digest(raw), bundles=[], modules=captured.modules
    )
    assert result["prepared_steps"] == 0 and result["accepted_steps"] == 0
    with pytest.raises(ValueError, match="persistence_failed"):
        fresh.prepare(0)

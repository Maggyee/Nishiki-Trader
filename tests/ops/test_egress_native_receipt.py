"""Nautilus receives original gateway response bytes solely in the nonroot consumer."""

import json
import os
import threading
from contextlib import suppress
from types import SimpleNamespace

import pytest

from apps.strategies_nautilus import portfolio_egress_ledger as ledger
from apps.strategies_nautilus import portfolio_rate_evidence as rates
from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from tests.ops.test_egress_gateway_tls import PIN, TRUST
from tests.ops.test_egress_gateway_tls import case as case
from tests.ops.test_egress_installed_gateway import load
from tests.ops.test_egress_tls_receipt import _rechain
from tests.ops.test_egress_tls_receipt import channels as channels


def metadata(precision=8):
    return [
        {
            "symbol": asset + "USDT",
            "baseAsset": asset,
            "baseAssetPrecision": precision,
            "quoteAsset": "USDT",
            "quoteAssetPrecision": 8,
        }
        for asset in ("BTC", "ETH", "BNB")
    ]


@pytest.fixture
def native_case(case, channels):
    receipt, native = load("gateway_tls_receipt"), load("gateway_native_receipt")
    state = SimpleNamespace(receipt=receipt, native=native, errors=[], consumed=[], results=[])
    collector = SimpleNamespace(channel=channels[0], verify=lambda: None)

    def client():
        try:
            state.consumed.append(
                receipt.receive_payload(
                    channels[1], provenance, rates, native=native.validate_native
                )
            )
        except BaseException as exc:
            state.errors.append(exc)
            channels[1].close()

    def completed(raw):
        case.gateway._revoke()
        payload = receipt.payload_from_tls(raw, case.review(raw))
        return receipt.deliver(
            collector,
            case.ledger,
            case.lifecycle,
            payload,
            provenance,
            native_result=native.expected_result(payload),
        )

    case.gateway.send = lambda: case.module.capture(
        case.ledger, case.lifecycle, TRUST, provenance, rates, on_complete=completed
    )

    def run(precision=8):
        body = json.loads(case.body)
        body["symbols"] = metadata(precision)
        raw = provenance.canonical(body)
        header = case.header.replace(str(len(case.body)).encode(), str(len(raw)).encode())
        case.socket.chunks = [header, raw]
        state.thread = threading.Thread(target=client)
        state.thread.start()
        return case.gateway.dispatch()

    def review(raw=None, **overrides):
        raw = (case.ledger.path / "receipt.jsonl").read_bytes() if raw is None else raw
        kwargs = dict(
            expected_sha256=provenance.digest(raw),
            tls_raw=case.path.read_bytes(),
            attempts=case.ledger.expected,
            lifecycle=case.lifecycle.expected,
            binding_sha256=PIN,
            trust_sha256=provenance.digest(TRUST),
            ledger_module=ledger,
            gateway_module=vars(load("ledger_gateway")),
            transport=vars(case.module),
            provenance=provenance,
            rates=rates,
            native=vars(native),
        )
        kwargs.update(overrides)
        return receipt.replay(raw, **kwargs)

    state.run, state.review = run, review
    yield state
    channels[0].close()
    if hasattr(state, "thread"):
        state.thread.join(timeout=6)
        assert not state.thread.is_alive()


def test_gateway_bytes_construct_native_currencies_before_ack(case, native_case):
    native_case.run()
    native_case.thread.join(timeout=1)
    result = native_case.review()
    assert not native_case.errors and len(native_case.consumed) == 1
    assert result["native_metadata_acknowledged"] and result["attempt_outcome_recorded"]
    assert result["native_result"] == native_case.native.validate_native(native_case.consumed[0])
    assert result["native_result"]["currencies"] == [
        {"code": c, "precision": 8} for c in ("BNB", "BTC", "ETH", "USDT")
    ]
    assert result["header_receipt"] == result["native_result"]["header_receipt"]
    assert not result["native_collector_integrated"] and not result["network_admitted"]
    assert case.gateway.revoked and case.ledger.state.pending is None


def test_native_precision_rejection_preserves_complete_tls_and_pending_delivery(case, native_case):
    with pytest.raises(RuntimeError):
        native_case.run(17)
    native_case.thread.join(timeout=1)
    assert isinstance(native_case.errors[0], ValueError) and not native_case.consumed
    assert case.review()["status"] == "complete" and case.gateway.revoked
    result = native_case.review()
    assert not result["native_metadata_acknowledged"] and not result["attempt_outcome_recorded"]
    assert case.ledger.state.pending == 0


@pytest.mark.parametrize("damage", ["currency", "version", "clock", "downgrade", "parser"])
def test_native_result_cannot_be_rehashed_or_downgraded(case, native_case, damage):
    native_case.run()
    rows = [
        json.loads(line) for line in (case.ledger.path / "receipt.jsonl").read_bytes().splitlines()
    ]
    if damage == "currency":
        rows[1]["native_result"]["currencies"][0]["precision"] = 7
    elif damage == "version":
        rows[1]["native_result"]["native_version"] = "other"
    elif damage == "clock":
        rows[1]["native_result"]["header_receipt"]["monotonic_ns"] += 1
    elif damage == "downgrade":
        for row in rows:
            row["profile"] = native_case.receipt.PROFILE
            del row["native_result"]
    with pytest.raises(ValueError):
        native_case.review(_rechain(rows), **({"native": None} if damage == "parser" else {}))


def test_native_import_refuses_root_before_loading_package(monkeypatch):
    module = load("gateway_native_receipt")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="native_import_as_root_refused"):
        module.prepare_native()


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "lib/../outside",
        "lib//double",
        "lib/./dot",
        "bin/other",
        "manifest.json",
    ],
)
def test_runtime_inventory_refuses_path_escape(name):
    assert not load("gateway_native_runtime").valid_name(name)


def test_runtime_close_releases_held_descriptors(tmp_path):
    module = load("gateway_native_runtime")
    runtime = object.__new__(module.NativeRuntime)
    path = tmp_path / "runtime"
    path.write_bytes(b"fixture")
    fd = os.open(path, os.O_RDONLY)
    runtime.fds = [(str(path), fd, runtime.identity(os.fstat(fd)))]
    runtime.close()
    runtime.close()
    with pytest.raises(OSError):
        os.fstat(fd)


@pytest.mark.parametrize("damage", ["size", "mode", "replace"])
def test_runtime_observed_drift_invalidates_snapshot(tmp_path, monkeypatch, damage):
    module = load("gateway_native_runtime")
    runtime = object.__new__(module.NativeRuntime)
    path = tmp_path / "runtime"
    path.write_bytes(b"fixture")
    fd = os.open(path, os.O_RDONLY)
    runtime.fds = [(str(path), fd, runtime.identity(os.fstat(fd)))]
    runtime.mount = "fixture_mount"
    monkeypatch.setattr(runtime, "mount_identity", lambda: "fixture_mount")
    runtime.verify()
    if damage == "size":
        path.write_bytes(b"changed size")
    elif damage == "mode":
        path.chmod(0o444)
    else:
        path.rename(path.with_suffix(".old"))
        path.write_bytes(b"fixture")
    try:
        with pytest.raises(ValueError, match="native_runtime_changed"):
            runtime.verify()
    finally:
        with suppress(OSError):
            runtime.close()


@pytest.mark.parametrize(
    "damage", ["traversal", "symlink", "duplicate", "size", "inventory", "selection"]
)
def test_runtime_staging_rejects_untrusted_archive_members(tmp_path, monkeypatch, damage):
    import io
    import tarfile

    module = load("gateway_native_runtime")
    monkeypatch.setattr(module, "ROOT", str(tmp_path / "runtime"))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        member = tarfile.TarInfo("../escape" if damage == "traversal" else "bin/python3.12")
        if damage == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        elif damage == "size":
            member.size = module.LIMIT + 1
        else:
            member.size = 1
        archive.addfile(member, io.BytesIO(b"x") if member.size == 1 else None)
        if damage == "duplicate":
            archive.addfile(member, io.BytesIO(b"x"))
        if damage in {"inventory", "selection"}:
            manifest = provenance.canonical(
                {"profile": module.PROFILE, "native_version": module.VERSION, "files": {}}
            )
            member = tarfile.TarInfo("manifest.json")
            member.size = len(manifest)
            archive.addfile(member, io.BytesIO(manifest))
    raw = output.getvalue()
    with pytest.raises(ValueError):
        module.stage(
            raw, "0" * 64 if damage == "selection" else provenance.digest(raw), lambda *args: None
        )
    assert not (tmp_path / "escape").exists()

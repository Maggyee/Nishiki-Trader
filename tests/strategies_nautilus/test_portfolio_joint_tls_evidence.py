"""A local source profile never accepts real authorities or weaker TLS settings."""

import asyncio
import ssl
from urllib.parse import urlsplit

import pytest

from apps.strategies_nautilus import portfolio_joint_observation as joint
from apps.strategies_nautilus.portfolio_joint_tls_evidence import PROFILE, TLSJointEvidence, Wire
from apps.strategies_nautilus.portfolio_joint_tls_transport import TLSBackend
from apps.strategies_nautilus.portfolio_joint_transport import run_loopback
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from tests.strategies_nautilus.test_portfolio_joint_observation import Clock
from tests.strategies_nautilus.test_portfolio_joint_routes import route_manifest
from tests.strategies_nautilus.test_portfolio_tls_provenance import certificates as certificates


def selection(clock, trust):
    result = route_manifest(clock)
    return {
        **result,
        "tls_profile": PROFILE,
        "tls_trust_sha256": joint.digest(trust),
        "tls_endpoints": {
            role: f"{'https' if role == 'http' else 'wss'}://{role}.fixture.invalid:{urlsplit(url).port}"
            for role, url in result["wire_endpoints"].items()
        },
    }


@pytest.mark.parametrize(
    "value",
    [
        "https://testnet.binance.vision",
        "https://api.binance.com",
        "https://127.0.0.1:19001",
        "http://http.fixture.invalid:19001",
    ],
)
def test_real_or_unbound_authority_rejected_before_network(tmp_path, value):
    clock = Clock()
    manifest = selection(clock, b"fixture")
    manifest["tls_endpoints"]["http"] = value
    with pytest.raises(DepthError, match="fixture_endpoints"):
        joint.JointJournal(
            tmp_path / "refused.jsonl",
            manifest=manifest,
            clock=clock,
            evidence_type=TLSJointEvidence,
        )


def test_missing_selected_trust_and_old_runner_have_no_fallback(tmp_path, certificates):
    clock = Clock()
    trust = certificates["selected"][1]
    journal = joint.JointJournal(
        tmp_path / "tls.jsonl",
        manifest=selection(clock, trust),
        clock=clock,
        evidence_type=TLSJointEvidence,
    )
    try:
        with pytest.raises(DepthError, match="selected_trust"):
            TLSBackend(journal, b"foreign")
        with pytest.raises(DepthError, match="explicit_bounded_loopback"):
            asyncio.run(run_loopback(journal, None))
    finally:
        journal.close()


@pytest.mark.parametrize("change", ["hostname", "chain", "minimum"])
def test_changed_verifier_rejected_before_connect(tmp_path, certificates, monkeypatch, change):
    async def forbidden(*args, **kwargs):
        pytest.fail("TLS connection opened before verifier checks")

    monkeypatch.setattr(asyncio, "open_connection", forbidden)
    clock = Clock()
    trust = certificates["selected"][1]
    journal = joint.JointJournal(
        tmp_path / "tls.jsonl",
        manifest=selection(clock, trust),
        clock=clock,
        evidence_type=TLSJointEvidence,
    )
    try:
        backend = TLSBackend(journal, trust)
        if change in {"hostname", "chain"}:
            backend.context.check_hostname = False
        if change == "chain":
            backend.context.verify_mode = ssl.CERT_NONE
        if change == "minimum":
            backend.context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        with pytest.raises(DepthError, match="verifier_changed"):
            asyncio.run(backend._open("http", "/api/v3/time"))
    finally:
        journal.close()


@pytest.mark.parametrize(
    "changes", ["payload", "role", "sequence", "utc_age", "processing_age", "before_prepare"]
)
def test_original_message_binding_and_dispatch_age(changes):
    state = TLSJointEvidence()
    wire = Wire({"role": "account"})
    state.wires[1] = wire
    state.role_connections = {"account": 1, "market": 1}
    wire.events.append((1, b"message", 10, 10_000_000_000, 10_000_000_000))
    row = {"seq": 11}
    role, opcode, payload, now, mono = "account", 1, b"message", 10_000_000_001, 10_000_000_001
    if changes == "payload":
        payload = b"substituted"
    if changes == "role":
        opcode = 9
    if changes == "sequence":
        row["seq"] = 9
    if changes == "utc_age":
        now += 5_000_000_000
    if changes == "processing_age":
        mono += 5_000_000_000
    if changes == "before_prepare":
        state.prepared = {"seq": 11}
    with pytest.raises(DepthError):
        state._event(role, opcode, payload, row, now, mono)

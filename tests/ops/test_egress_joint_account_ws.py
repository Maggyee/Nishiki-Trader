"""Detached staged account-channel originals and signed-subscription refusals."""

import base64
import copy
import hashlib
import json
import time

import pytest

from apps.strategies_nautilus import portfolio_tls_provenance as provenance
from apps.strategies_nautilus import portfolio_ws_frames as frames
from tests.ops.test_egress_installed_gateway import load


def rows(module, events, now, mono):
    raw, previous = bytearray(), None
    for index, (kind, payload) in enumerate(events):
        row = {
            "seq": index,
            "previous_sha256": previous,
            "kind": kind,
            "profile": module.PROFILE,
            "utc_ns": now + index * 1_000_000,
            "monotonic_ns": mono + index * 1_000_000,
            "payload": payload,
        }
        line = module.canonical(row) + b"\n"
        raw.extend(line)
        previous = module.digest(line)
    return raw.decode()


@pytest.fixture
def originals():
    module = load("gateway_joint_account_ws")
    requests = load("gateway_native_requests")
    account = load("gateway_account_ws")
    ws = load("gateway_concurrent_ws")
    modules = {
        "provenance": provenance,
        "frames": vars(frames),
        "requests": vars(requests),
        "account_ws": vars(account),
        "ws": vars(ws),
    }
    process = {
        "pid": 123,
        "start_ticks": 456,
        "native_runtime_sha256": "d" * 64,
        "installation_manifest_sha256": "a" * 64,
        "namespaces": {"net": "native-net", "mnt": "same-mount"},
    }
    anchor = {
        "read_sequence": {"profile": "clock", "index": 0, "prefix_sha256": "a" * 64},
        "base_manifest_sha256": "a" * 64,
        "gateway_manifest_sha256": "b" * 64,
        "tls_trust_sha256": "c" * 64,
        "rules": {},
        "route": [],
        "net": "root-net",
        "collector": {"process": process, "launcher_source_sha256": "f" * 64},
    }
    selected = {
        key: anchor[key]
        for key in ("base_manifest_sha256", "gateway_manifest_sha256", "tls_trust_sha256")
    }
    first = {"binding": module.canonical(anchor).decode()}
    nonce = base64.b64encode(b"a" * 16).decode()
    response = (
        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        + b"Sec-WebSocket-Accept: "
        + base64.b64encode(
            hashlib.sha1(nonce.encode() + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
        )
        + b"\r\n\r\n"
    )
    now, mono = time.time_ns(), time.monotonic_ns()
    connect_context = {"profile": "joint", "index": 1, "prefix_sha256": "e" * 64}
    binding = {
        **anchor,
        "read_sequence": connect_context,
        "clock_anchor_sha256": module.digest(first["binding"].encode()),
    }
    connect_events = [
        (
            "intent",
            {
                "endpoint": ws.endpoint("account", {})[0],
                "peer": list(module.PEER),
                "nonce": nonce,
                "clock_bundle_sha256": module.digest(module.canonical(first)),
            },
        ),
        ("grant_prepared", {"mark": module.MARK, "ttl_ms": 5000}),
        ("activated", {}),
        (
            "tls_connected",
            {
                "peer": list(module.PEER),
                "server_hostname": "account.fixture.invalid",
                "peer_certificate_sha256": "f" * 64,
                "tls_version": "TLSv1.3",
                "cipher": ["TLS_AES_256_GCM_SHA384", "TLSv1.3", 256],
                "check_hostname": True,
                "verify_mode": "CERT_REQUIRED",
            },
        ),
        ("request_prepared", provenance.raw_fields(ws.request("account", {}, nonce))),
        ("response_chunk", provenance.raw_fields(response)),
        ("upgrade_accepted", {}),
        ("revoked", {}),
        ("accepted", {}),
    ]
    connect = {
        "binding": module.canonical(binding).decode(),
        "ws": rows(module, connect_events, now, mono),
    }
    subscribe_context = {"profile": "joint", "index": 2, "prefix_sha256": "f" * 64}
    binding["read_sequence"] = subscribe_context
    challenge = {
        "index": 2,
        "nonce": "a" * 32,
        "utc_ns": now + 20_000_000,
        "monotonic_ns": mono + 20_000_000,
    }
    envelope = json.loads(requests.native_request(challenge))
    wire = frames.client_frame(account.wire_request(envelope))
    signer = {
        "launcher_source_sha256": "f" * 64,
        "process": {
            **process,
            "pid": 789,
            "start_ticks": 999,
            "namespaces": {"net": "signer-net", "mnt": "same-mount"},
        },
    }
    answer = b'{"id":"fixture-2","status":200,"result":{"subscriptionId":0}}'
    subscribe_events = [
        (
            "intent",
            {
                "connection_bundle_sha256": module.digest(module.canonical(connect)),
                "signer": signer,
            },
        ),
        (
            "signature_prepared",
            {
                "challenge": challenge,
                "request": envelope,
                "received": [now + 20_500_000, mono + 20_500_000],
                **provenance.raw_fields(wire),
            },
        ),
        ("grant_prepared", {"mark": module.MARK, "ttl_ms": 5000}),
        ("activated", {}),
        ("write_prepared", {}),
        ("response_chunk", provenance.raw_fields(bytes([0x81, len(answer)]) + answer)),
        ("subscription_accepted", {}),
        ("revoked", {}),
        ("accepted", {}),
    ]
    subscription = {
        "binding": module.canonical(binding).decode(),
        "ws": rows(module, subscribe_events, now + 21_000_000, mono + 21_000_000),
    }
    return (
        module,
        modules,
        selected,
        (first, connect, subscription),
        (connect_context, subscribe_context),
        (connect_events, subscribe_events),
        (now, mono),
    )


def test_original_upgrade_and_native_signed_subscription(originals):
    module, modules, selected, bundles, contexts, _, _ = originals
    connected = module.review_step(bundles[1], 1, contexts[0], selected, modules, bundles[:1])
    signed = module.review_step(bundles[2], 2, contexts[1], selected, modules, bundles[:2])
    assert connected["complete"] and connected["account_connection_upgraded"]
    assert signed["complete"] and signed["subscription_acknowledged"]
    assert signed["native_signer_verified"] and not signed["account_interval_complete"]


@pytest.mark.parametrize("index,cutoff", [(1, 2), (1, 3), (1, 5), (2, 3), (2, 4), (2, 5)])
def test_revoked_prefix_never_accepts_a_step(originals, index, cutoff):
    module, modules, selected, bundles, contexts, events, clocks = originals
    partial = list(events[index - 1][:cutoff]) + [("revoked", {})]
    starting = (clocks[0] + 21_000_000, clocks[1] + 21_000_000) if index == 2 else clocks
    bundle = {**bundles[index], "ws": rows(module, partial, *starting)}
    result = module.review_step(
        bundle, index, contexts[index - 1], selected, modules, bundles[:index]
    )
    assert result["complete"] is False
    assert result["native_result"] is None


@pytest.mark.parametrize(
    "damage",
    [
        "parent",
        "upgrade",
        "signer",
        "signer_source",
        "signer_net",
        "signature",
        "ack",
        "revoke",
        "extra_frame",
    ],
)
def test_fully_rehashed_original_tampering_refused(originals, damage):
    module, modules, selected, original, contexts, events, clocks = originals
    bundles = copy.deepcopy(original)
    connect_events, subscribe_events = copy.deepcopy(events)
    if damage == "parent":
        connect_events[0][1]["clock_bundle_sha256"] = "0" * 64
    elif damage == "upgrade":
        connect_events[5] = (
            "response_chunk",
            provenance.raw_fields(b"HTTP/1.1 403 Forbidden\r\n\r\n"),
        )
    elif damage == "signer":
        subscribe_events[0][1]["signer"]["process"]["native_runtime_sha256"] = "0" * 64
    elif damage == "signer_source":
        subscribe_events[0][1]["signer"]["launcher_source_sha256"] = "invalid"
    elif damage == "signer_net":
        subscribe_events[0][1]["signer"]["process"]["namespaces"]["net"] = "root-net"
    elif damage == "signature":
        subscribe_events[1][1]["request"]["request"]["params"]["signature"] = "A" * 88
    elif damage == "ack":
        subscribe_events[5] = ("response_chunk", provenance.raw_fields(b'\x81\x15{"id":"foreign"}'))
    elif damage == "revoke":
        subscribe_events.pop(7)
    else:
        subscribe_events[5] = (
            "response_chunk",
            provenance.raw_fields(bytes([0x81, 0x02]) + b"{}" + bytes([0x81, 0x02]) + b"{}"),
        )
    bundles[1]["ws"] = rows(module, connect_events, *clocks)
    bundles[2]["ws"] = rows(
        module, subscribe_events, clocks[0] + 21_000_000, clocks[1] + 21_000_000
    )
    with pytest.raises((ValueError, KeyError)):
        if damage in {"parent", "upgrade"}:
            module.review_step(bundles[1], 1, contexts[0], selected, modules, bundles[:1])
        else:
            module.review_step(bundles[2], 2, contexts[1], selected, modules, bundles[:2])


@pytest.mark.parametrize(
    "damage", [None, "route", "bundles", "request", "sni", "upgrade", "revoke"]
)
def test_market_upgrade_requires_original_route_request_and_revocation(originals, damage):
    module, modules, selected, initial, _, _, clocks = originals
    previous = list(initial) + [{"binding": initial[0]["binding"]} for _ in range(6)]
    route = {"symbols": ["BNBUSDT", "BTCUSDT"]}
    modules["joint_route_selection"] = lambda bundles, selected, modules: route
    ws = modules["ws"]
    nonce = base64.b64encode(b"m" * 16).decode()
    context = {"profile": "joint", "index": 9, "prefix_sha256": "e" * 64}
    binding = {
        **json.loads(initial[0]["binding"]),
        "read_sequence": context,
        "clock_anchor_sha256": module.digest(initial[0]["binding"].encode()),
    }
    accept = base64.b64encode(
        hashlib.sha1(nonce.encode() + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
    )
    response = (
        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
    )
    events = [
        (
            "intent",
            {
                "endpoint": ws["endpoint"]("market", route)[0],
                "peer": list(module.PEER),
                "nonce": nonce,
                "route_selection_sha256": module.digest(module.canonical(route)),
                "route_bundles_sha256": module.digest(module.canonical(previous)),
            },
        ),
        ("grant_prepared", {"mark": module.MARK, "ttl_ms": 5000}),
        ("activated", {}),
        (
            "tls_connected",
            {
                "peer": list(module.PEER),
                "server_hostname": "market.fixture.invalid",
                "peer_certificate_sha256": "f" * 64,
                "tls_version": "TLSv1.3",
                "cipher": ["TLS_AES_256_GCM_SHA384", "TLSv1.3", 256],
                "check_hostname": True,
                "verify_mode": "CERT_REQUIRED",
            },
        ),
        ("request_prepared", provenance.raw_fields(ws["request"]("market", route, nonce))),
        ("response_chunk", provenance.raw_fields(response)),
        ("upgrade_accepted", {}),
        ("revoked", {}),
        ("accepted", {}),
    ]
    if damage == "route":
        route["symbols"] = ["BTCUSDT"]
    elif damage == "bundles":
        previous[8]["binding"] = "changed"
    elif damage == "request":
        events[4] = ("request_prepared", provenance.raw_fields(b"GET /foreign HTTP/1.1\r\n\r\n"))
    elif damage == "sni":
        events[3][1]["server_hostname"] = "account.fixture.invalid"
    elif damage == "upgrade":
        events[5] = ("response_chunk", provenance.raw_fields(response.replace(accept, b"invalid")))
    elif damage == "revoke":
        events.pop(7)
    bundle = {
        "binding": module.canonical(binding).decode(),
        "ws": rows(module, events, clocks[0] + 35_000_000, clocks[1] + 35_000_000),
    }
    if damage:
        with pytest.raises(ValueError):
            module.review_step(bundle, 9, context, selected, modules, previous)
    else:
        result = module.review_step(bundle, 9, context, selected, modules, previous)
        assert result["complete"] and result["market_connection_upgraded"]
        assert result["account_interval_complete"] is False

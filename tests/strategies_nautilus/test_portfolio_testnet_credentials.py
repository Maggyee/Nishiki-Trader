from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from nautilus_trader.common.component import TestClock
from nautilus_trader.core.nautilus_pyo3 import HttpMethod

from apps.strategies_nautilus.portfolio_stream import UserStreamJournal, bind_source
from apps.strategies_nautilus.portfolio_testnet_credentials import (
    TESTNET_REST,
    TestnetCredentialError,
    load_testnet_ed25519_credentials,
)
from apps.strategies_nautilus.portfolio_user_stream import SUBSCRIBE
from apps.strategies_nautilus.runners.portfolio_simulation_acceptance import BASE_NS


@pytest.fixture
def configured(tmp_path):
    generated = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519"],
        capture_output=True,
        timeout=5,
    )
    assert generated.returncode == 0
    private_path = tmp_path / "private key.pem"
    private_path.write_bytes(generated.stdout)
    private_path.chmod(0o600)
    public_path = tmp_path / "public.pem"
    generated_public = subprocess.run(
        ["openssl", "pkey", "-pubout"],
        input=generated.stdout,
        capture_output=True,
        timeout=5,
    )
    assert generated_public.returncode == 0
    public_path.write_bytes(generated_public.stdout)
    config = tmp_path / "testnet.env"
    config.write_text(
        "# Synthetic credentials, never sent to Binance\n"
        "export BINANCE_TESTNET_API_KEY='" + "A" * 64 + "'\n"
        f"BINANCE_TESTNET_PRIVATE_KEY_PATH='{private_path}'\n"
    )
    config.chmod(0o600)
    return config, private_path, public_path


def verify_signature(tmp_path, public_path, message, signature):
    message_path, signature_path = tmp_path / "message", tmp_path / "signature"
    message_path.write_bytes(message.encode())
    signature_path.write_bytes(base64.b64decode(signature, validate=True))
    verified = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_path),
            "-rawin",
            "-in",
            str(message_path),
            "-sigfile",
            str(signature_path),
        ],
        capture_output=True,
        timeout=5,
    )
    assert verified.returncode == 0


def test_native_http_and_ws_signatures_verify_with_openssl(configured, tmp_path, monkeypatch):
    config, private_path, public_path = configured
    before = config.read_bytes(), private_path.read_bytes()
    credentials = load_testnet_ed25519_credentials(config)
    assert "A" * 64 not in repr(credentials)
    assert "PRIVATE KEY" not in repr(credentials)
    clock = TestClock()
    clock.set_time(BASE_NS)
    http = credentials.create_http_client(clock)
    assert http.base_url == TESTNET_REST
    assert http._secret is None
    journal = UserStreamJournal(
        tmp_path / "journal.jsonl", bind_source(http, "123"), clock_ns=clock.timestamp_ns
    )
    loop = asyncio.new_event_loop()
    http, stream = credentials.create_clients(journal=journal, clock=clock, loop=loop)
    methods = []

    async def http_wire(method, path, *, payload, **kwargs):
        assert method == HttpMethod.GET and path == "/api/v3/account"
        verify_signature(
            tmp_path,
            public_path,
            urlencode({k: v for k, v in payload.items() if k != "signature"}),
            payload["signature"],
        )
        methods.append("GET account")
        return b'{"uid":123}'

    class Socket:
        def is_active(self):
            return True

        def is_reconnecting(self):
            return False

        def is_disconnecting(self):
            return False

        async def disconnect(self):
            pass

        async def send_text(self, raw):
            request = json.loads(raw)
            assert request["method"] == SUBSCRIBE
            params = request["params"]
            message = "&".join(
                f"{key}={params[key]}" for key in sorted(params) if key != "signature"
            )
            verify_signature(tmp_path, public_path, message, params["signature"])
            methods.append(SUBSCRIBE)
            stream._handle_message(
                json.dumps(
                    {"id": request["id"], "status": 200, "result": {"subscriptionId": 7}}
                ).encode()
            )

    async def connect(**kwargs):
        assert stream._base_url == "wss://ws-api.testnet.binance.vision/ws-api/v3"
        return Socket()

    monkeypatch.setattr(http, "send_request", http_wire)
    monkeypatch.setattr(
        "apps.strategies_nautilus.portfolio_user_stream.WebSocketClient",
        SimpleNamespace(connect=connect),
    )
    try:
        loop.run_until_complete(
            http.sign_request(
                HttpMethod.GET, "/api/v3/account", payload={"timestamp": str(BASE_NS // 1_000_000)}
            )
        )
        loop.run_until_complete(stream.start())
        assert journal.connected
        assert methods == ["GET account", SUBSCRIBE]
        assert "A" * 64 not in (tmp_path / "journal.jsonl").read_text()
        # Missing Ed25519 state fails instead of falling back to HMAC.
        http._ed25519_private_key = None
        with pytest.raises(TestnetCredentialError):
            loop.run_until_complete(http.sign_request(HttpMethod.GET, "/api/v3/account"))
    finally:
        loop.run_until_complete(stream.disconnect())
        journal.close()
        loop.close()
    assert (config.read_bytes(), private_path.read_bytes()) == before


@pytest.mark.parametrize(
    "change", ["missing_path", "duplicate", "hmac_secret", "endpoint", "shell", "relative"]
)
def test_ambiguous_configs_and_shell_expansion_are_rejected(configured, change):
    config, private_path, _ = configured
    raw = config.read_text()
    if change == "missing_path":
        raw = raw.split("BINANCE_TESTNET_PRIVATE_KEY_PATH")[0]
    elif change == "duplicate":
        raw += "BINANCE_TESTNET_API_KEY='" + "B" * 64 + "'\n"
    elif change == "hmac_secret":
        raw += "BINANCE_TESTNET_API_SECRET='private-placeholder'\n"
    elif change == "endpoint":
        raw += "ENDPOINT=https://api.binance.com\n"
    elif change == "relative":
        raw = raw.replace(str(private_path), "private.pem")
    else:
        marker = config.parent / "must-not-exist"
        raw = raw.replace(str(private_path), f"$(touch {marker})")
    config.write_text(raw)
    with pytest.raises(
        TestnetCredentialError, match="^testnet Ed25519 credential configuration invalid$"
    ):
        load_testnet_ed25519_credentials(config)
    assert not (config.parent / "must-not-exist").exists()


@pytest.mark.parametrize("which", ["config", "key"])
@pytest.mark.parametrize("change", ["public_mode", "symlink", "oversize", "absent"])
def test_private_regular_bounded_files_required(configured, which, change):
    config, private_path, _ = configured
    target = config if which == "config" else private_path
    if change == "public_mode":
        target.chmod(0o644)
    elif change == "symlink":
        other = Path(str(target) + ".original")
        target.rename(other)
        target.symlink_to(other)
    elif change == "oversize":
        target.write_bytes(b"x" * 65_537)
    else:
        target.unlink()
    with pytest.raises(TestnetCredentialError):
        load_testnet_ed25519_credentials(config)


@pytest.mark.parametrize("change", ["public", "malformed", "truncated", "wrong_oid"])
def test_only_exact_ed25519_pkcs8_private_container_is_accepted(configured, change):
    config, private_path, public_path = configured
    pem = private_path.read_bytes()
    if change == "public":
        pem = public_path.read_bytes()
    elif change == "malformed":
        pem = b"invalid private data"
    else:
        der = base64.b64decode(b"".join(pem.splitlines()[1:-1]))
        der = der[:-1] if change == "truncated" else der[:8] + b"\x00" + der[9:]
        pem = (
            b"-----BEGIN PRIVATE KEY-----\n"
            + base64.b64encode(der)
            + b"\n-----END PRIVATE KEY-----\n"
        )
    private_path.write_bytes(pem)
    with pytest.raises(TestnetCredentialError):
        load_testnet_ed25519_credentials(config)

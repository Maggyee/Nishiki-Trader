"""Explicit Ed25519 files for the read-only Spot testnet transport; no discovery."""

from __future__ import annotations

import base64
import os
import shlex
import stat
from dataclasses import dataclass, field
from pathlib import Path

from nautilus_trader.core.nautilus_pyo3 import ed25519_signature

from apps.strategies_nautilus.portfolio_account_collector import BinanceAccountReadOnlyHttpClient
from apps.strategies_nautilus.portfolio_user_stream import ReadOnlyBinanceUserStream

TESTNET_REST = "https://testnet.binance.vision"
KEY_VARIABLE = "BINANCE_TESTNET_API_KEY"
PATH_VARIABLE = "BINANCE_TESTNET_PRIVATE_KEY_PATH"


class TestnetCredentialError(ValueError):
    __test__ = False


class Ed25519TestnetReadOnlyHttpClient(BinanceAccountReadOnlyHttpClient):
    """Native Ed25519 signing without the upstream requirement for an HMAC secret."""

    def _get_sign(self, data):
        if self._ed25519_private_key is None:
            raise TestnetCredentialError("Ed25519 signing key unavailable")
        return ed25519_signature(self._ed25519_private_key, data)


def _private_file(path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise TestnetCredentialError("explicit absolute credential path required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or not 0 < info.st_size <= 65_536
        ):
            raise TestnetCredentialError("private regular credential file required")
        raw = source.read(65_537)
        if len(raw) > 65_536:
            raise TestnetCredentialError("credential file exceeds size bound")
        return raw


@dataclass(frozen=True)
class Ed25519TestnetCredentials:
    api_key: str = field(repr=False)
    private_key_pem: str = field(repr=False)

    def create_http_client(self, clock):
        # HTTP does not auto-detect PEM in api_secret: use its explicit Ed25519 slot.
        return Ed25519TestnetReadOnlyHttpClient(
            clock,
            self.api_key,
            None,
            TESTNET_REST,
            ed25519_private_key=self.private_key_pem,
        )

    def create_clients(self, *, journal, clock, loop):
        http = self.create_http_client(clock)
        # Native WS detects Ed25519 PKCS#8 PEM in its api_secret parameter.
        stream = ReadOnlyBinanceUserStream(
            http,
            api_secret=self.private_key_pem,
            journal=journal,
            clock=clock,
            loop=loop,
        )
        return http, stream


def load_testnet_ed25519_credentials(config_path: Path):
    """Read one selected env file and its private key; never evaluate shell code.

    Exactly API_KEY and PRIVATE_KEY_PATH are accepted. No HMAC secret, endpoint
    override, environment expansion, key-generation or account request is performed.
    """
    try:
        fields = {}
        for line in _private_file(config_path).decode().splitlines():
            parts = shlex.split(line, comments=True, posix=True)
            if parts[:1] == ["export"]:
                parts = parts[1:]
            if not parts:
                continue
            if len(parts) != 1 or "=" not in parts[0]:
                raise TestnetCredentialError("literal credential assignments required")
            name, value = parts[0].split("=", 1)
            if name not in {KEY_VARIABLE, PATH_VARIABLE} or name in fields or not value:
                raise TestnetCredentialError("ambiguous credential configuration")
            fields[name] = value
        if set(fields) != {KEY_VARIABLE, PATH_VARIABLE}:
            raise TestnetCredentialError("API key and private-key path required")
        api_key = fields[KEY_VARIABLE]
        if not api_key.isascii() or not api_key.isalnum() or not 32 <= len(api_key) <= 256:
            raise TestnetCredentialError("invalid testnet API key format")
        pem = _private_file(Path(fields[PATH_VARIABLE]))
        lines = [line.strip() for line in pem.decode("ascii").splitlines() if line.strip()]
        if (
            len(lines) < 3
            or lines[0] != "-----BEGIN PRIVATE KEY-----"
            or lines[-1] != "-----END PRIVATE KEY-----"
        ):
            raise TestnetCredentialError("unencrypted PKCS#8 private key required")
        der = base64.b64decode("".join(lines[1:-1]), validate=True)
        # Exact RFC 8410 seed-only PKCS#8 produced by openssl genpkey ED25519:
        # version 0, OID 1.3.101.112, nested OCTET STRING containing a 32-byte seed.
        # Refuse other containers instead of blindly accepting their last 32 bytes.
        if len(der) != 48 or der[:16] != bytes.fromhex("302e020100300506032b657004220420"):
            raise TestnetCredentialError("unsupported Ed25519 PKCS#8 container")
        normalized = (
            "-----BEGIN PRIVATE KEY-----\n"
            + base64.b64encode(der).decode()
            + "\n-----END PRIVATE KEY-----\n"
        )
        return Ed25519TestnetCredentials(api_key, normalized)
    except (OSError, ValueError, TypeError):
        raise TestnetCredentialError("testnet Ed25519 credential configuration invalid") from None

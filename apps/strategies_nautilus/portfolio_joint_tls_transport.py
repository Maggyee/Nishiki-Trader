"""Project-owned TLS transport for the separate local joint acceptance profile."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import ssl
from contextlib import suppress
from urllib.parse import urlencode, urlsplit

from apps.strategies_nautilus.portfolio_joint_observation import digest, raw_fields
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from apps.strategies_nautilus.portfolio_tls_provenance import MAX_HEADER, _one
from apps.strategies_nautilus.portfolio_ws_frames import client_frame


class TLSBackend:
    def __init__(self, journal, trust_pem, *, accounting=None):
        if (
            type(journal.state) is not TLSJointEvidence
            or not isinstance(trust_pem, bytes)
            or not 0 < len(trust_pem) <= MAX_HEADER
            or digest(trust_pem) != journal.state.manifest["tls_trust_sha256"]
        ):
            raise DepthError("joint_tls_selected_trust_required")
        self.journal = journal
        self.accounting = accounting
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=trust_pem.decode("ascii"))
        self.on_failure = None

    async def _open(self, role, target):
        if (
            not self.context.check_hostname
            or self.context.verify_mode != ssl.CERT_REQUIRED
            or self.context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            raise DepthError("joint_tls_verifier_changed")
        manifest = self.journal.state.manifest
        endpoint = manifest["tls_endpoints"][role]
        parsed = urlsplit(endpoint)
        connection = self.journal.state.prepared["operation_id"]
        nonce = base64.b64encode(os.urandom(16)).decode() if role != "http" else None
        if self.accounting is not None:
            self.accounting.before_wire("connect")
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            parsed.port,
            ssl=self.context,
            server_hostname=parsed.hostname,
            ssl_handshake_timeout=10,
            ssl_shutdown_timeout=1,
            limit=MAX_HEADER,
        )
        try:
            tls = writer.get_extra_info("ssl_object")
            self.journal.append(
                "tls_opened",
                connection_id=connection,
                role=role,
                endpoint=endpoint,
                target=target,
                websocket_nonce=nonce,
                peer=list(writer.get_extra_info("peername")),
                server_hostname=tls.server_hostname,
                peer_certificate_sha256=digest(tls.getpeercert(binary_form=True)),
                trust_sha256=manifest["tls_trust_sha256"],
                check_hostname=self.context.check_hostname,
                verify_mode="CERT_REQUIRED"
                if self.context.verify_mode == ssl.CERT_REQUIRED
                else "invalid",
                tls_version=tls.version(),
                cipher=list(tls.cipher()),
            )
        except BaseException:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            raise
        return connection, reader, writer, parsed.netloc, nonce

    async def chunk(self, connection, reader):
        raw = await reader.read(4096)
        received_ns, monotonic_ns = self.journal.clock()
        if not raw:
            raise DepthError("joint_tls_unexpected_eof")
        self.journal.append(
            "tls_chunk",
            connection_id=connection,
            received_ns=received_ns,
            monotonic_ns=monotonic_ns,
            **raw_fields(raw),
        )

    async def get(self, op, params, headers):
        connection, reader, writer, authority, _ = await self._open("http", op["path"])
        try:
            target = op["path"] + ("?" + urlencode(params) if params else "")
            request = f"GET {target} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n"
            request += "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
            # Outbound private selectors/signatures never enter the byte journal.
            if self.accounting is not None:
                self.accounting.before_wire("request")
            writer.write(request.encode("ascii"))
            await writer.drain()
            wire = self.journal.state.wires[connection]
            while wire.headers is None or len(wire.buffer) < wire.body_length:
                await self.chunk(connection, reader)
            usage = _one(wire.headers["pairs"], "x-mbx-used-weight-1m")
            result = wire.headers["status"], usage, bytes(wire.buffer)
        finally:
            writer.close()
            await writer.wait_closed()
        self.journal.append("tls_closed", connection_id=connection)
        return result

    async def connect(self, role, handler, ping_handler):
        target = (
            "/ws-api/v3"
            if role == "account"
            else "/stream?streams="
            + "/".join(s.lower() + "@depth@100ms" for s in self.journal.state.manifest["symbols"])
        )
        connection, reader, writer, authority, nonce = await self._open(role, target)
        try:
            request = f"GET {target} HTTP/1.1\r\nHost: {authority}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            if self.accounting is not None:
                self.accounting.before_wire("request")
            writer.write(request.encode("ascii"))
            await writer.drain()
            while self.journal.state.wires[connection].headers is None:
                await self.chunk(connection, reader)
            return TLSWebSocket(self, connection, reader, writer, handler, ping_handler)
        except BaseException:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            raise


class TLSWebSocket:
    def __init__(self, backend, connection, reader, writer, handler, ping_handler):
        self.backend, self.connection = backend, connection
        self.reader, self.writer = reader, writer
        self.handler, self.ping_handler = handler, ping_handler
        self.active = True
        self.closing = False
        self.peer_closed = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task = asyncio.create_task(self._read())

    @property
    def journal(self):
        return self.backend.journal

    @property
    def wire(self):
        return self.journal.state.wires[self.connection]

    def is_active(self):
        return self.active and not self.writer.is_closing()

    def is_reconnecting(self):
        return False

    def is_disconnecting(self):
        return self.closing

    async def _read(self):
        try:
            while True:
                while self.wire.events:
                    opcode, payload, *_ = self.wire.events[0]
                    if opcode == 1:
                        self.handler(payload)
                    elif opcode == 9:
                        self.ping_handler(payload)
                    else:
                        self.journal.append(
                            "tls_peer_control",
                            connection_id=self.connection,
                            opcode=opcode,
                            **raw_fields(payload),
                        )
                        if opcode == 8:
                            self.peer_closed.set()
                            return
                    if self.journal.failed:
                        raise DepthError("joint_tls_callback_failed")
                await self.backend.chunk(self.connection, self.reader)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.backend.on_failure("joint_tls_stream_failed")
        finally:
            self.active = False

    async def send_text(self, raw):
        prepared = self.journal.state.prepared
        body = json.loads(raw)
        if (
            self.wire.opened["role"] != "account"
            or prepared is None
            or body["method"]
            not in {"userDataStream.subscribe.signature", "userDataStream.unsubscribe"}
            or body["method"] != prepared["operation"].get("operation")
            or body["id"] != prepared["request_id"]
        ):
            raise DepthError("joint_tls_unprepared_account_method")
        async with self.lock:
            if self.backend.accounting is not None:
                self.backend.accounting.before_wire("request")
            self.writer.write(client_frame(raw))
            await self.writer.drain()

    async def send_pong(self, payload):
        async with self.lock:
            self.journal.append(
                "tls_pong_prepared", connection_id=self.connection, **raw_fields(payload)
            )
            if self.backend.accounting is not None:
                self.backend.accounting.control()
            self.writer.write(client_frame(payload, 10))
            await self.writer.drain()

    async def disconnect(self):
        if self.closing:
            raise DepthError("joint_tls_close_already_attempted")
        self.closing = True
        try:
            if not self.journal.failed:
                async with self.lock:
                    self.journal.append("tls_close_prepared", connection_id=self.connection)
                    if self.backend.accounting is not None:
                        self.backend.accounting.control()
                    self.writer.write(client_frame(b"\x03\xe8", 8))
                    await self.writer.drain()
                await self.peer_closed.wait()
            self.writer.close()
            await self.writer.wait_closed()
            if not self.journal.failed:
                self.journal.append("tls_closed", connection_id=self.connection)
        finally:
            self.active = False
            self.writer.close()
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task


async def run_tls_loopback(journal, signer, *, trust_pem, observe_seconds=0.1):
    from apps.strategies_nautilus.portfolio_joint_transport import _run_loopback

    backend = TLSBackend(journal, trust_pem)
    return await _run_loopback(journal, signer, observe_seconds=observe_seconds, transport=backend)

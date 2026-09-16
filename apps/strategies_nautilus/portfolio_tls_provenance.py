"""One-shot TLS/HTTP Upgrade evidence against explicit local fixture peers.

This is a transport acceptance primitive, not a joint collector. Only reserved
fixture authorities routed to literal 127.0.0.1 are callable. No credential,
subscription, frame-processing, retry, redirect or real-exchange mode exists.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import ssl
import stat
import time
from contextlib import suppress
from urllib.parse import urlsplit

PROFILE = "portfolio.loopback_tls_provenance.v1"
MAX_HEADER = 65536
MAX_BODY = 16 * 1024 * 1024
MAX_ARCHIVE = 24 * 1024 * 1024
PATHS = {
    "rest": "/api/v3/exchangeInfo",
    "account": "/ws-api/v3",
    "market": "/stream?streams=btcusdt@depth@100ms",
}


class ProvenanceError(ValueError):
    """A source, persistence or transport boundary failed."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def raw_fields(raw):
    return {"raw_b64": base64.b64encode(raw).decode(), "raw_sha256": digest(raw)}


def _selection(endpoint, role, trust_pem, trust_sha256):
    """Validate all local-only inputs before any socket or archive is opened."""
    try:
        parsed = urlsplit(endpoint)
        scheme = "https" if role == "rest" else "wss"
        host = f"{role}.fixture.invalid"
        if (
            role not in PATHS
            or parsed.scheme != scheme
            or parsed.hostname != host
            or not parsed.port
            or endpoint != f"{scheme}://{host}:{parsed.port}{PATHS[role]}"
            or not isinstance(trust_pem, bytes)
            or not 0 < len(trust_pem) <= MAX_HEADER
            or digest(trust_pem) != trust_sha256
        ):
            raise ValueError
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=trust_pem.decode("ascii"))
    except (ValueError, TypeError, ssl.SSLError, UnicodeError):
        raise ProvenanceError("explicit_loopback_source_and_pinned_trust_required") from None
    return parsed, context


class _Journal:
    def __init__(self, path, *, limit=MAX_ARCHIVE, reserve=0):
        self.limit, self.reserve = limit, reserve
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.size = self.seq = 0
        self.previous = None
        self.failed = False
        try:
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except BaseException:
            os.close(self.fd)
            raise

    def append(self, kind, **fields):
        if self.failed:
            raise ProvenanceError("provenance_persistence_already_failed")
        row = {
            "seq": self.seq,
            "previous_sha256": self.previous,
            "kind": kind,
            "utc_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        }
        raw = canonical(row) + b"\n"
        ceiling = self.limit if kind == "aborted" else self.limit - self.reserve
        if self.size + len(raw) > ceiling:
            raise ProvenanceError("provenance_archive_limit")
        try:
            view = memoryview(raw)
            while view:
                written = os.write(self.fd, view)
                if written <= 0:
                    raise OSError("short provenance write")
                view = view[written:]
            os.fsync(self.fd)
        except BaseException:
            self.failed = True
            # Remove an unacknowledged final row, including a failed completion
            # fsync. If the filesystem also refuses truncation, the archive remains
            # ambiguous and must not be selected as evidence by the caller.
            with suppress(OSError):
                os.ftruncate(self.fd, self.size)
            raise
        self.seq += 1
        self.size += len(raw)
        self.previous = digest(raw)


def response_headers(raw):
    """Retain duplicate, case-sensitive original pairs; reject ambiguous syntax."""
    if not 0 < len(raw) <= MAX_HEADER or not raw.endswith(b"\r\n\r\n"):
        raise ProvenanceError("invalid_provenance_headers")
    lines = raw[:-4].split(b"\r\n")
    if not re.fullmatch(rb"HTTP/1\.1 [0-9]{3}(?: [\x20-\x7e]*)?", lines[0]):
        raise ProvenanceError("invalid_provenance_status_line")
    pairs = []
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if (
            not separator
            or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
            or any(b < 32 and b != 9 or b == 127 for b in value)
        ):
            raise ProvenanceError("invalid_provenance_header_field")
        pairs.append([name.decode("ascii"), value.strip(b" \t").decode("latin1")])
    return int(lines[0].split(b" ")[1]), pairs


def _one(pairs, name):
    values = [value for key, value in pairs if key.lower() == name]
    if len(values) != 1:
        raise ProvenanceError("missing_or_duplicate_provenance_header")
    return values[0]


def _validate_response(role, status, pairs, nonce):
    if any(k.lower() in {"transfer-encoding", "content-encoding"} for k, _ in pairs):
        raise ProvenanceError("unsupported_provenance_response_framing")
    if role == "rest":
        if status != 200:
            raise ProvenanceError("provenance_http_status_refused")
        length = _one(pairs, "content-length")
        if not length.isascii() or not length.isdecimal() or len(length) > 8:
            raise ProvenanceError("invalid_provenance_body_length")
        if not 0 < int(length) <= MAX_BODY:
            raise ProvenanceError("provenance_body_limit")
        return int(length)
    accept = base64.b64encode(
        hashlib.sha1(nonce.encode() + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
    ).decode()
    if (
        status != 101
        or _one(pairs, "upgrade").lower() != "websocket"
        or "upgrade" not in {v.strip().lower() for v in _one(pairs, "connection").split(",")}
        or _one(pairs, "sec-websocket-accept") != accept
        or any(
            k.lower() in {"content-length", "sec-websocket-extensions", "sec-websocket-protocol"}
            for k, _ in pairs
        )
    ):
        raise ProvenanceError("provenance_upgrade_refused")
    return 0


async def capture_loopback_tls(
    path,
    *,
    endpoint,
    role,
    trust_pem,
    trust_sha256,
    timeout=10,
    max_body=MAX_BODY,
    max_archive=MAX_ARCHIVE,
    incident_reserve=0,
    close_timeout=5,
):
    """Capture one TLS connection and one GET/Upgrade; then close within five seconds.

    The caller selects a new private archive and an ephemeral fixture trust root.
    A consumed archive cannot be reused after any failure. WS evidence stops at
    Upgrade: no frame or signed subscription is sent or claimed as captured.
    """
    parsed, context = _selection(endpoint, role, trust_pem, trust_sha256)
    if type(timeout) not in (int, float) or not 0 < timeout <= 10:
        raise ProvenanceError("bounded_provenance_timeout_required")
    if (
        type(max_body) is not int
        or not 0 < max_body <= MAX_BODY
        or type(max_archive) is not int
        or not 4096 <= max_archive <= MAX_ARCHIVE
        or type(incident_reserve) is not int
        or not 0 <= incident_reserve <= 4096
        or incident_reserve >= max_archive
        or type(close_timeout) not in (int, float)
        or not 0 < close_timeout <= 5
    ):
        raise ProvenanceError("bounded_provenance_limits_required")
    journal = _Journal(path, limit=max_archive, reserve=incident_reserve)
    writer = None
    failure = None
    nonce = base64.b64encode(os.urandom(16)).decode() if role != "rest" else None
    try:
        journal.append(
            "prepared",
            profile=PROFILE,
            endpoint=endpoint,
            role=role,
            peer_ip="127.0.0.1",
            trust_sha256=trust_sha256,
            websocket_nonce=nonce,
        )
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                parsed.port,
                ssl=context,
                server_hostname=parsed.hostname,
                ssl_handshake_timeout=timeout,
                ssl_shutdown_timeout=1,
                limit=MAX_HEADER,
            )
            peer = writer.get_extra_info("peername")
            tls = writer.get_extra_info("ssl_object")
            if peer != ("127.0.0.1", parsed.port) or tls is None:
                raise ProvenanceError("provenance_peer_changed")
            certificate = tls.getpeercert(binary_form=True)
            if (
                not certificate
                or not context.check_hostname
                or context.verify_mode != ssl.CERT_REQUIRED
            ):
                raise ProvenanceError("provenance_tls_verification_missing")
            journal.append(
                "tls_connected",
                peer=list(peer),
                server_hostname=tls.server_hostname,
                peer_certificate_sha256=digest(certificate),
                tls_version=tls.version(),
                cipher=list(tls.cipher()),
                verify_mode="CERT_REQUIRED",
                check_hostname=True,
                trust_sha256=trust_sha256,
                tls_minimum_version="TLSv1.2",
            )
            headers = (
                f"GET {PATHS[role]} HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
                + (
                    "Connection: close\r\n"
                    if role == "rest"
                    else f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n"
                )
                + "\r\n"
            )
            journal.append("request_prepared", method="GET", target=PATHS[role])
            writer.write(headers.encode("ascii"))
            await writer.drain()
            # Persist each returned decrypted chunk before interpreting even HTTP
            # framing. Partial headers/bodies and malformed replies survive abort.
            response = bytearray()

            async def receive():
                chunk = await reader.read(4096)
                if not chunk:
                    raise ProvenanceError("provenance_response_truncated")
                journal.append("response_chunk", **raw_fields(chunk))
                response.extend(chunk)

            while b"\r\n\r\n" not in response:
                if len(response) >= MAX_HEADER:
                    raise ProvenanceError("provenance_header_limit")
                await receive()
            header_length = response.index(b"\r\n\r\n") + 4
            raw = bytes(response[:header_length])
            journal.append("response_headers", raw_sha256=digest(raw), length=header_length)
            status, pairs = response_headers(raw)
            length = _validate_response(role, status, pairs, nonce)
            if length > max_body:
                raise ProvenanceError("selected_provenance_body_limit")
            if length:
                while len(response) < header_length + length:
                    await receive()
                if len(response) != header_length + length:
                    raise ProvenanceError("provenance_unexpected_http_trailing_bytes")
                raw = bytes(response[header_length:])
                journal.append("response_body", raw_sha256=digest(raw), length=length)
            journal.append(
                "response_accepted",
                status=status,
                header_pairs=pairs,
                unprocessed_upgrade_tail_bytes=len(response) - header_length if not length else 0,
            )
    except BaseException as exc:
        failure = exc
    finally:
        if writer is not None:
            try:
                async with asyncio.timeout(close_timeout):
                    writer.close()
                    await writer.wait_closed()
                journal.append("transport_closed")
            except BaseException as exc:
                failure = failure or exc
        try:
            if failure is None:
                journal.append("completed", exchange_requests=0, network_admitted=False)
            else:
                # Use controlled categories, never exception text containing URLs/headers.
                with suppress(OSError, ProvenanceError):
                    journal.append("aborted", reason=type(failure).__name__)
        finally:
            os.close(journal.fd)
    if failure is not None:
        raise failure


def read_provenance(path, *, expected_sha256):
    """Historical original-byte verification, never a fresh TLS or egress attestation."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > MAX_ARCHIVE
        ):
            raise ProvenanceError("private_provenance_archive_required")
        raw = source.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE or digest(raw) != expected_sha256:
        raise ProvenanceError("provenance_original_hash_changed")
    try:
        return _replay(raw, expected_sha256)
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        if isinstance(exc, ProvenanceError):
            raise
        raise ProvenanceError("invalid_provenance_archive") from None


def _replay(raw, expected_sha256):
    previous, rows = None, []
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            line != canonical(row) + b"\n"
            or type(row["seq"]) is not int
            or row["seq"] != len(rows)
            or row["previous_sha256"] != previous
            or type(row["utc_ns"]) is not int
            or row["utc_ns"] <= 0
            or type(row["monotonic_ns"]) is not int
            or row["monotonic_ns"] <= 0
        ):
            raise ProvenanceError("provenance_receipt_chain_changed")
        if rows and (
            row["utc_ns"] < rows[-1]["utc_ns"] or row["monotonic_ns"] < rows[-1]["monotonic_ns"]
        ):
            raise ProvenanceError("provenance_receipt_clock_regressed")
        rows.append(row)
        previous = digest(line)
    if not rows or rows[0]["kind"] != "prepared" or rows[0]["profile"] != PROFILE:
        raise ProvenanceError("provenance_profile_required")
    selection, tls = rows[:2]
    role = selection["role"]
    expected = ["prepared", "tls_connected", "request_prepared", "response_headers"]
    expected += ["response_body"] if role == "rest" else []
    expected += ["response_accepted", "transport_closed", "completed"]
    semantic = [r for r in rows if r["kind"] != "response_chunk"]
    if [r["kind"] for r in semantic] != expected:
        raise ProvenanceError("incomplete_provenance_capture")
    parsed = urlsplit(selection["endpoint"])
    scheme = "https" if role == "rest" else "wss"
    if (
        role not in PATHS
        or not parsed.port
        or selection["endpoint"] != f"{scheme}://{role}.fixture.invalid:{parsed.port}{PATHS[role]}"
        or selection["peer_ip"] != "127.0.0.1"
        or tls["server_hostname"] != parsed.hostname
        or tls["peer"] != ["127.0.0.1", parsed.port]
        or tls["check_hostname"] is not True
        or tls["verify_mode"] != "CERT_REQUIRED"
        or tls["tls_minimum_version"] != "TLSv1.2"
        or tls["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
        or tls["trust_sha256"] != selection["trust_sha256"]
        or not re.fullmatch("[0-9a-f]{64}", tls["trust_sha256"])
        or not re.fullmatch("[0-9a-f]{64}", tls["peer_certificate_sha256"])
    ):
        raise ProvenanceError("provenance_source_binding_changed")
    if semantic[2]["method"] != "GET" or semantic[2]["target"] != PATHS[role]:
        raise ProvenanceError("provenance_request_selection_changed")
    chunks = []
    received_size = 0
    for row in rows:
        if row["kind"] == "response_chunk":
            data = base64.b64decode(row["raw_b64"], validate=True)
            if (
                not 0 < len(data) <= 4096
                or digest(data) != row["raw_sha256"]
                or not semantic[2]["seq"] < row["seq"] < semantic[-3]["seq"]
            ):
                raise ProvenanceError("provenance_response_hash_changed")
            chunks.append(data)
            received_size += len(data)
        elif row["kind"] == "response_headers":
            if type(row["length"]) is not int or not 0 < row["length"] <= min(
                MAX_HEADER, received_size
            ):
                raise ProvenanceError("provenance_headers_precede_original_bytes")
        elif row["kind"] == "response_body":
            if (
                type(row["length"]) is not int
                or not 0 < row["length"] <= MAX_BODY
                or received_size != semantic[3]["length"] + row["length"]
            ):
                raise ProvenanceError("provenance_body_precedes_original_bytes")
    response = b"".join(chunks)
    header = semantic[3]
    raw_headers = response[: header["length"]]
    if digest(raw_headers) != header["raw_sha256"]:
        raise ProvenanceError("provenance_response_hash_changed")
    status, pairs = response_headers(raw_headers)
    length = _validate_response(role, status, pairs, rows[0]["websocket_nonce"])
    accepted = semantic[-3]
    body = response[len(raw_headers) :]
    if (
        accepted["status"] != status
        or accepted["header_pairs"] != pairs
        or (
            length
            and (
                len(body) != length
                or semantic[4]["length"] != length
                or semantic[4]["raw_sha256"] != digest(body)
            )
        )
        or accepted["unprocessed_upgrade_tail_bytes"] != (len(body) if not length else 0)
        or semantic[-1]["exchange_requests"] != 0
        or semantic[-1]["network_admitted"] is not False
        or (not length and len(body) > 4095)
    ):
        raise ProvenanceError("provenance_response_replay_changed")
    return {
        "profile": PROFILE,
        "status": "historical_loopback_provenance_replayed",
        "archive_sha256": expected_sha256,
        "selection": rows[0],
        "tls": rows[1],
        "response_status": status,
        "header_pairs": pairs,
        "original_body_sha256": digest(body) if length else None,
        "unprocessed_upgrade_tail_bytes": accepted["unprocessed_upgrade_tail_bytes"],
        "network_admitted": False,
        "actual_exchange_source_verified": False,
        "shared_egress_verified": False,
    }

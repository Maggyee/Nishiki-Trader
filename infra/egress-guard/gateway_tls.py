"""One fixed local HTTPS operation owned by the installed fixture gateway."""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import ssl
import stat
import time
from contextlib import suppress

PROFILE = "portfolio.installed_gateway_tls.v1"
PEER = ("198.51.100.2", 23456)
ENDPOINT = "https://rest.fixture.invalid:23456/api/v3/exchangeInfo"
REQUEST = b"GET /api/v3/exchangeInfo HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
MARK = 0x7472
LIMIT = 2 * 1024 * 1024
BODY_LIMIT = 65536


def capture(ledger, lifecycle, trust, provenance, rates, *, on_headers=None, on_complete=None):
    """No caller-selected destination/request, retry, socket handoff or credentials."""
    parsed, context = provenance._selection(ENDPOINT, "rest", trust, provenance.digest(trust))
    ledger.checkpoint()
    if ledger.state.pending != 0 or len(ledger.state.attempts) != 1:
        raise ValueError("pending_fixed_attempt_required")
    path = ledger.path / "tls.jsonl"
    journal = provenance._Journal(path, limit=LIMIT, reserve=4096)
    reader = connection = None
    expected = b""
    deadline = time.monotonic() + 4
    try:
        reader = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        identity = os.fstat(reader)

        def append(kind, **fields):
            nonlocal expected
            ledger._storage()
            info = path.stat(follow_symlinks=False)
            if (
                (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.pread(reader, LIMIT + 1, 0) != expected
            ):
                raise ValueError("gateway_tls_archive_changed")
            row = {
                "seq": journal.seq,
                "previous_sha256": journal.previous,
                "kind": kind,
                "utc_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
                **fields,
            }
            journal.append(
                kind,
                **{k: v for k, v in row.items() if k not in {"seq", "previous_sha256", "kind"}},
            )
            expected += provenance.canonical(row) + b"\n"
            if os.pread(reader, LIMIT + 1, 0) != expected:
                raise ValueError("gateway_tls_persisted_bytes_changed")

        def timeout():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("fixed_tls_deadline")
            return remaining

        try:
            append(
                "connection_prepared",
                profile=PROFILE,
                binding_sha256=ledger.state.binding_sha256,
                attempt_prefix_sha256=provenance.digest(ledger.expected),
                lifecycle_prefix_sha256=provenance.digest(lifecycle.expected),
                endpoint=ENDPOINT,
                peer=list(PEER),
                trust_sha256=provenance.digest(trust),
            )
            ledger.checkpoint()
            connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)
            connection.settimeout(timeout())
            connection.connect(PEER)
            connection.settimeout(timeout())
            connection = context.wrap_socket(connection, server_hostname=parsed.hostname)
            if (
                connection.getpeername() != PEER
                or not context.check_hostname
                or context.verify_mode != ssl.CERT_REQUIRED
            ):
                raise ValueError("fixed_tls_peer_or_verification")
            certificate = connection.getpeercert(binary_form=True)
            if not certificate:
                raise ValueError("fixed_tls_certificate_missing")
            append(
                "tls_connected",
                peer=list(connection.getpeername()),
                server_hostname=parsed.hostname,
                peer_certificate_sha256=provenance.digest(certificate),
                tls_version=connection.version(),
                cipher=list(connection.cipher()),
                check_hostname=True,
                verify_mode="CERT_REQUIRED",
                tls_minimum_version="TLSv1.2",
            )
            append("request_prepared", **provenance.raw_fields(REQUEST))
            ledger.checkpoint()
            connection.settimeout(timeout())
            connection.sendall(REQUEST)
            response = bytearray()
            header_end = length = None
            while True:
                connection.settimeout(timeout())
                chunk = connection.recv(4096)
                received_utc, received_mono = time.time_ns(), time.monotonic_ns()
                if not chunk:
                    raise ValueError("fixed_tls_response_truncated")
                append(
                    "response_chunk",
                    utc_ns=received_utc,
                    monotonic_ns=received_mono,
                    **provenance.raw_fields(chunk),
                )
                response.extend(chunk)
                if header_end is None:
                    if b"\r\n\r\n" not in response:
                        if len(response) >= provenance.MAX_HEADER:
                            raise ValueError("fixed_tls_header_limit")
                        continue
                    # Trusted harness notification follows the successful chunk fsync.
                    if on_headers is not None:
                        on_headers()
                    header_end = response.index(b"\r\n\r\n") + 4
                    if header_end > provenance.MAX_HEADER:
                        raise ValueError("fixed_tls_header_limit")
                    status, pairs = provenance.response_headers(bytes(response[:header_end]))
                    length = provenance._validate_response("rest", status, pairs, None)
                    if not 0 < length <= BODY_LIMIT:
                        raise ValueError("fixed_tls_body_limit")
                if len(response) < header_end + length:
                    continue
                if len(response) != header_end + length:
                    raise ValueError("fixed_tls_trailing_bytes")
                body = bytes(response[header_end:])
                rates.rest_rate_evidence(body, pairs)
                ledger.checkpoint()
                append(
                    "response_accepted",
                    header_sha256=provenance.digest(bytes(response[:header_end])),
                    body_sha256=provenance.digest(body),
                )
                break
            connection.close()
            connection = None
            append("transport_closed")
            append("completed")
        except BaseException as exc:
            if connection is not None:
                connection.close()
                connection = None
            with suppress(Exception):
                append("aborted", reason=type(exc).__name__)
            raise
    finally:
        if connection is not None:
            connection.close()
        if reader is not None:
            os.close(reader)
        os.close(journal.fd)
    if on_complete is not None:
        return on_complete(expected)
    return True


def replay(
    raw,
    *,
    expected_sha256,
    attempts,
    lifecycle,
    binding_sha256,
    trust_sha256,
    ledger_module,
    gateway_module,
    provenance,
    rates,
):
    """Selected historical bytes only; malformed complete transcripts never pass."""
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= LIMIT
        or provenance.digest(raw) != expected_sha256
    ):
        raise ValueError("selected_gateway_tls_archive")
    previous = None
    rows = []
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or provenance.canonical(row) + b"\n" != line
            or type(row.get("seq")) is not int
            or row["seq"] != len(rows)
            or row.get("previous_sha256") != previous
        ):
            raise ValueError("gateway_tls_chain")
        if any(type(row.get(k)) is not int or row[k] <= 0 for k in ("utc_ns", "monotonic_ns")):
            raise ValueError("gateway_tls_clock")
        if rows and (
            any(row[k] < rows[-1][k] for k in ("utc_ns", "monotonic_ns"))
            or abs(
                (row["utc_ns"] - rows[0]["utc_ns"])
                - (row["monotonic_ns"] - rows[0]["monotonic_ns"])
            )
            > 50_000_000
        ):
            raise ValueError("gateway_tls_clock")
        rows.append(row)
        previous = provenance.digest(line)
    if not rows:
        raise ValueError("empty_gateway_tls_archive")
    first = rows[0]
    common = {"seq", "previous_sha256", "kind", "utc_ns", "monotonic_ns"}
    if (
        set(first)
        != common
        | {
            "profile",
            "binding_sha256",
            "attempt_prefix_sha256",
            "lifecycle_prefix_sha256",
            "endpoint",
            "peer",
            "trust_sha256",
        }
        or first["kind"] != "connection_prepared"
        or first["profile"] != PROFILE
        or first["binding_sha256"] != binding_sha256
        or first["endpoint"] != ENDPOINT
        or first["peer"] != list(PEER)
        or first["trust_sha256"] != trust_sha256
        or not isinstance(trust_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", trust_sha256) is None
    ):
        raise ValueError("gateway_tls_selection")
    # Verify complete companion archives before selecting their acknowledged prefixes.
    ledger_module.replay(
        attempts, expected_sha256=provenance.digest(attempts), binding_sha256=binding_sha256
    )
    gateway_module["replay_lifecycle"](
        ledger_module,
        lifecycle,
        expected_sha256=provenance.digest(lifecycle),
        attempts=attempts,
        binding_sha256=binding_sha256,
    )

    def prefix(raw, pin):
        end = 0
        for line in raw.splitlines(keepends=True):
            end += len(line)
            if provenance.digest(raw[:end]) == pin:
                selected = raw[:end]
                last = json.loads(line)
                if any(last[k] > first[k] for k in ("utc_ns", "monotonic_ns")):
                    raise ValueError("gateway_tls_precedes_preparation")
                return selected
        raise ValueError("gateway_tls_original_prefix_missing")

    prepared = prefix(attempts, first["attempt_prefix_sha256"])
    granted = prefix(lifecycle, first["lifecycle_prefix_sha256"])
    attempt = ledger_module.replay(
        prepared, expected_sha256=provenance.digest(prepared), binding_sha256=binding_sha256
    )
    grant = gateway_module["replay_lifecycle"](
        ledger_module,
        granted,
        expected_sha256=provenance.digest(granted),
        attempts=prepared,
        binding_sha256=binding_sha256,
    )
    if (
        attempt["pending_attempt"] != 0
        or attempt["recorded_attempts"] != 1
        or attempt["status"] != "incomplete_no_resume"
        or grant["last_record"] != "activated"
    ):
        raise ValueError("gateway_tls_pending_attempt_and_grant_required")
    stage = "connection_prepared"
    response = bytearray()
    header_receipt = body_receipt = accepted = None
    request_prepared = False
    for row in rows[1:]:
        kind = row["kind"]
        fields = set(row) - common
        if (
            kind == "aborted"
            and stage not in {"completed", "aborted"}
            and fields == {"reason"}
            and isinstance(row["reason"], str)
        ):
            stage = kind
            continue
        if kind == "tls_connected" and stage == "connection_prepared":
            if (
                fields
                != {
                    "peer",
                    "server_hostname",
                    "peer_certificate_sha256",
                    "tls_version",
                    "cipher",
                    "check_hostname",
                    "verify_mode",
                    "tls_minimum_version",
                }
                or row["peer"] != list(PEER)
                or row["server_hostname"] != "rest.fixture.invalid"
                or row["check_hostname"] is not True
                or row["verify_mode"] != "CERT_REQUIRED"
                or row["tls_minimum_version"] != "TLSv1.2"
                or row["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
            ):
                raise ValueError("gateway_tls_verification")
            if (
                not isinstance(row["peer_certificate_sha256"], str)
                or re.fullmatch("[0-9a-f]{64}", row["peer_certificate_sha256"]) is None
                or not isinstance(row["cipher"], list)
                or len(row["cipher"]) != 3
            ):
                raise ValueError("gateway_tls_certificate")
        elif kind == "request_prepared" and stage == "tls_connected":
            if (
                fields != {"raw_b64", "raw_sha256"}
                or base64.b64decode(row["raw_b64"], validate=True) != REQUEST
                or row["raw_sha256"] != provenance.digest(REQUEST)
            ):
                raise ValueError("gateway_tls_fixed_request")
            request_prepared = True
        elif kind == "response_chunk" and stage in {"request_prepared", "response_chunk"}:
            if fields != {"raw_b64", "raw_sha256"}:
                raise ValueError("gateway_tls_chunk_fields")
            chunk = base64.b64decode(row["raw_b64"], validate=True)
            if (
                not 0 < len(chunk) <= 4096
                or provenance.digest(chunk) != row["raw_sha256"]
                or len(response) + len(chunk) > provenance.MAX_HEADER + BODY_LIMIT + 4096
            ):
                raise ValueError("gateway_tls_chunk")
            response.extend(chunk)
            if header_receipt is None and b"\r\n\r\n" in response:
                header_receipt = {k: row[k] for k in ("seq", "utc_ns", "monotonic_ns")}
            if header_receipt is not None:
                end = response.index(b"\r\n\r\n") + 4
                try:
                    status, pairs = provenance.response_headers(bytes(response[:end]))
                    length = provenance._validate_response("rest", status, pairs, None)
                except ValueError:
                    pass  # A failed transcript may retain malformed original headers.
                else:
                    if (
                        end <= provenance.MAX_HEADER
                        and 0 < length <= BODY_LIMIT
                        and len(response) == end + length
                    ):
                        body_receipt = {k: row[k] for k in ("seq", "utc_ns", "monotonic_ns")}
        elif kind == "response_accepted" and stage == "response_chunk":
            if fields != {"header_sha256", "body_sha256"} or header_receipt is None:
                raise ValueError("gateway_tls_missing_originals")
            end = response.index(b"\r\n\r\n") + 4
            headers, body = bytes(response[:end]), bytes(response[end:])
            status, pairs = provenance.response_headers(headers)
            length = provenance._validate_response("rest", status, pairs, None)
            if (
                end > provenance.MAX_HEADER
                or not 0 < length <= BODY_LIMIT
                or len(body) != length
                or row["header_sha256"] != provenance.digest(headers)
                or row["body_sha256"] != provenance.digest(body)
            ):
                raise ValueError("gateway_tls_response_changed")
            accepted = rates.rest_rate_evidence(body, pairs)
        elif (
            kind == "transport_closed"
            and stage == "response_accepted"
            and not fields
            or kind == "completed"
            and stage == "transport_closed"
            and not fields
        ):
            pass
        else:
            raise ValueError("gateway_tls_transition")
        stage = kind
    return {
        "schema_version": PROFILE,
        "archive_sha256": expected_sha256,
        "binding_sha256": binding_sha256,
        "status": "complete" if stage == "completed" else "incomplete_no_resume",
        "last_record": stage,
        "prepared_tcp_connections": 1,
        "http_request_prepared": request_prepared,
        "rate_evidence": accepted if stage == "completed" else None,
        "header_receipt": header_receipt,
        "body_receipt": body_receipt,
        "header_age_at_body_ns": None
        if header_receipt is None or body_receipt is None
        else body_receipt["monotonic_ns"] - header_receipt["monotonic_ns"],
        "provider_connection_charge": None,
        "current_usage_upper_bound": None,
        "source_authenticated_for_real_venue": False,
        "restart_allowed": False,
        "complete_caller_coverage_verified": False,
        "network_admitted": False,
        "trading_admitted": False,
    }

"""Fixed-scope local TLS acceptance for the separate one-GET REST bootstrap.

The real provider/source/helper integration is deliberately unavailable. This
profile connects only to the established rest.fixture.invalid loopback peer.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

from apps.strategies_nautilus import portfolio_tls_provenance as tls
from apps.strategies_nautilus.portfolio_rate_evidence import rest_rate_evidence

PROFILE = "portfolio.loopback_rest_bootstrap.v1"
SCOPE = "fixture-rest-bootstrap-v1"
BODY_LIMIT = 8 * 1024 * 1024
ARCHIVE_LIMIT = 16 * 1024 * 1024
RESERVE = 4096
POLICY = {
    "profile": PROFILE,
    "scope": SCOPE,
    "gets": 1,
    "tcp_attempts": 1,
    "tls_attempts": 1,
    "documented_weight_for_future_real_operation": 20,
    "transport_dns_requests": 0,
    "retries": 0,
    "redirects": 0,
    "credentials": False,
    "deadline_seconds": 10,
    "close_allowance_seconds": 2,
    "body_limit": BODY_LIMIT,
    "archive_limit": ARCHIVE_LIMIT,
    "incident_reserve": RESERVE,
    "network_admitted": False,
}
README = b"""# Local REST bootstrap acceptance scope
Purpose: retain one consumed loopback-only TLS/GET attempt.
Phase: transport acceptance; no real venue/helper integration or admission.
Boundary: no reopen, retry, refund, resume, credentials or production destination.
Next entrypoint: review the original capture.jsonl with retained hashes.
"""


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def consume(root):
    root = Path(root)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise tls.ProvenanceError("private_fixture_parent_required")
    directory = root / SCOPE
    directory.mkdir(mode=0o700)
    _sync(root)  # Empty/partial directory already permanently consumes this scope.
    _write(directory / "README.md", README)
    _write(directory / "policy.json", tls.canonical(POLICY) + b"\n")
    _sync(directory)
    return directory


async def capture(root, *, endpoint, trust_pem, trust_sha256):
    # Reject real authorities and unbound trust before consuming local state.
    tls._selection(endpoint, "rest", trust_pem, trust_sha256)
    directory = consume(root)
    await tls.capture_loopback_tls(
        directory / "capture.jsonl",
        endpoint=endpoint,
        role="rest",
        trust_pem=trust_pem,
        trust_sha256=trust_sha256,
        timeout=10,
        max_body=BODY_LIMIT,
        max_archive=ARCHIVE_LIMIT - 4096,
        incident_reserve=RESERVE,
        close_timeout=2,
    )
    raw = (directory / "capture.jsonl").read_bytes()
    return review(directory, expected_sha256=tls.digest(raw))


def review(directory, *, expected_sha256):
    directory = Path(directory)
    fd = os.open(directory / "policy.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise tls.ProvenanceError("private_bootstrap_policy_required")
        if stream.read(4097) != tls.canonical(POLICY) + b"\n":
            raise tls.ProvenanceError("bootstrap_policy_changed")
    path = directory / "capture.jsonl"
    # Hold one original-byte snapshot for transport replay and rate parsing.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > ARCHIVE_LIMIT - 4096
        ):
            raise tls.ProvenanceError("private_bootstrap_archive_required")
        raw = stream.read(ARCHIVE_LIMIT - 4096 + 1)
    if len(raw) > ARCHIVE_LIMIT - 4096 or tls.digest(raw) != expected_sha256:
        raise tls.ProvenanceError("bootstrap_archive_hash")
    provenance = tls._replay(raw, expected_sha256)
    if provenance["selection"]["role"] != "rest":
        raise tls.ProvenanceError("bootstrap_rest_only")
    rows = [json.loads(line) for line in raw.splitlines()]
    wire = b"".join(
        base64.b64decode(row["raw_b64"], validate=True)
        for row in rows
        if row["kind"] == "response_chunk"
    )
    body = wire.split(b"\r\n\r\n", 1)[1]
    if len(body) > BODY_LIMIT:
        raise tls.ProvenanceError("bootstrap_body_limit")
    closed = next(row for row in rows if row["kind"] == "transport_closed")
    accepted = next(row for row in rows if row["kind"] == "response_accepted")
    if (
        accepted["monotonic_ns"] - rows[0]["monotonic_ns"] > 10_000_000_000
        or closed["monotonic_ns"] - accepted["monotonic_ns"] > 2_000_000_000
    ):
        raise tls.ProvenanceError("bootstrap_observed_deadline_exceeded")
    return {
        "schema_version": PROFILE,
        "status": "historical_loopback_bootstrap_replayed",
        "archive_sha256": expected_sha256,
        "policy_sha256": tls.digest(tls.canonical(POLICY) + b"\n"),
        "transport": provenance,
        "rates": rest_rate_evidence(body, provenance["header_pairs"]),
        "scope_consumed": True,
        "resume_allowed": False,
        "network_admitted": False,
        "pre_request_capacity_verified": False,
        "real_helper_integration_verified": False,
        "venue_requests_made": 0,
    }

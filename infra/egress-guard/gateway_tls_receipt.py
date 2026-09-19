"""Deliver one fixed fixture HTTPS response to the isolated UID, without descriptors.

The pinned ControlChannel still authenticates every packet. This extension only
adds bounded data tokens; it does not accept destinations, requests or credentials.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import stat
import time

PROFILE = "portfolio.installed_tls_receipt.v1"
MAX_PAYLOAD = 180000
CHUNK = 512
DEADLINE = 5
JOURNAL_LIMIT = 8192
NATIVE_PROFILES = {
    "portfolio.installed_native_receipt.v1",
    "portfolio.installed_native_account_receipt.v1",
    "portfolio.installed_native_orders_receipt.v1",
    "portfolio.installed_native_books_receipt.v1",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class DataToken:
    def __contains__(self, token):
        if not isinstance(token, str) or not token.startswith("data:"):
            return False
        try:
            raw = base64.b64decode(token[5:], validate=True)
            return 0 < len(raw) <= CHUNK and base64.b64encode(raw).decode() == token[5:]
        except ValueError:
            return False


def payload_from_tls(raw, report):
    """Call only after full TLS replay; preserve original root recv clocks verbatim."""
    if report["status"] != "complete" or report["archive_sha256"] != digest(raw):
        raise ValueError("complete_selected_tls_required")
    response = b"".join(
        base64.b64decode(row["raw_b64"], validate=True)
        for row in map(json.loads, raw.splitlines())
        if row["kind"] == "response_chunk"
    )
    return canonical(
        {
            "profile": PROFILE,
            "tls_sha256": digest(raw),
            "header_receipt": report["header_receipt"],
            "body_receipt": report["body_receipt"],
            "response_b64": base64.b64encode(response).decode(),
        }
    )


def validate_payload(raw, provenance, rates):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PAYLOAD:
        raise ValueError("receipt_size")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or canonical(value) != raw
        or set(value) != {"profile", "tls_sha256", "header_receipt", "body_receipt", "response_b64"}
        or value["profile"] != PROFILE
        or not isinstance(value["tls_sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", value["tls_sha256"]) is None
    ):
        raise ValueError("receipt_schema")
    for name in ("header_receipt", "body_receipt"):
        stamp = value[name]
        if (
            not isinstance(stamp, dict)
            or set(stamp) != {"seq", "utc_ns", "monotonic_ns"}
            or any(type(v) is not int or v <= 0 for v in stamp.values())
        ):
            raise ValueError("receipt_clock")
    if any(value["body_receipt"][k] < v for k, v in value["header_receipt"].items()):
        raise ValueError("receipt_clock_order")
    response = base64.b64decode(value["response_b64"], validate=True)
    if base64.b64encode(response).decode() != value["response_b64"]:
        raise ValueError("receipt_encoding")
    end = response.index(b"\r\n\r\n") + 4
    status, pairs = provenance.response_headers(response[:end])
    length = provenance._validate_response("rest", status, pairs, None)
    if end > 65536 or not 0 < length <= 65536 or len(response) != end + length:
        raise ValueError("receipt_response_size")
    return rates.rest_rate_evidence(response[end:], pairs)


def receive_payload(channel, provenance, rates, *, native=None):
    """Finite stop-and-wait transfer; the acknowledgement covers parsed exact bytes."""
    deadline = time.monotonic() + DEADLINE
    raw = bytearray()

    def bounded():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("receipt_deadline")
        channel.connection.settimeout(remaining)

    for seq in range(2, 2 + (MAX_PAYLOAD + CHUNK - 1) // CHUNK + 1):
        bounded()

        class Allowed:
            def __contains__(self, token):
                return token == "end:" + digest(raw) or token in DataToken()

        token = channel.receive(Allowed(), seq)
        if token.startswith("end:"):
            validate_payload(bytes(raw), provenance, rates)
            result = native(bytes(raw)) if native is not None else None
            token = (
                "accepted:" + digest(raw)
                if result is None
                else "native:" + digest(canonical(result)) + ":" + digest(raw)
            )
            bounded()  # Parsing cannot extend permission to acknowledge.
            channel.send(token, seq)
            bounded()
            return bytes(raw)
        chunk = base64.b64decode(token[5:], validate=True)
        raw.extend(chunk)
        if len(raw) > MAX_PAYLOAD:
            raise ValueError("receipt_size")
        bounded()
        channel.send("part", seq)
    raise ValueError("receipt_packet_limit")


def child_loop(fd, parent):
    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=10)
    try:
        if globals().get("NATIVE_PREPARE") is not None:
            globals()["NATIVE_PREPARE"]()
        channel.send("ready", 0)
        channel.receive({"start"}, 1)
        channel.send("exchange_info", 1)
        receive_payload(
            channel,
            globals()["PROVENANCE"],
            globals()["RATES"],
            native=globals().get("NATIVE_VALIDATE"),
        )
        channel.receive({"close"}, 1000)
        channel.send("closed", 1000)
    finally:
        channel.close()


def launch(authority, sources, launcher, *, runtime=None):
    authority.verify()
    reader = launcher["load_source"](authority.source("inspect_binding.py").decode())[
        "process_identity"
    ]

    def identity(pid):
        authority.verify()
        if runtime is not None:
            runtime.verify()
        return {
            **reader(pid),
            "installation_manifest_sha256": authority.manifest_sha256,
            **({"native_runtime_sha256": runtime.pin} if runtime is not None else {}),
        }

    source = "import types\n"
    for name, raw in (
        ("RATES", sources.source("portfolio_rate_evidence.py")),
        ("PROVENANCE", sources.source("portfolio_tls_provenance.py")),
    ):
        source += f"{name}=types.ModuleType({name!r})\nexec(compile({raw!r},'<held-source>','exec'),{name}.__dict__)\n"
    for raw in (
        authority.source("collector_launcher.py"),
        sources.source("gateway_tls_receipt.py"),
    ):
        source += f"exec(compile({raw!r},'<held-source>','exec'))\n"
    if runtime is not None:
        runtime.verify()
        raw = sources.source("gateway_native_receipt.py")
        source += f"native_scope={{'__name__':'held_native_consumer'}}\nexec(compile({raw!r},'<held-native-consumer>','exec'),native_scope)\nNATIVE_PREPARE=native_scope['prepare_native']\nNATIVE_VALIDATE=native_scope['validate_native']\n"
        launcher["FixtureCollector"].__init__.__globals__["PYTHON"] = (
            "/run/trader-native-runtime/bin/python3.12"
        )
    return launcher["FixtureCollector"](
        source,
        identity,
        collector_uid=authority.account["uid"],
        collector_gid=authority.account["gid"],
    )


def authorize(collector):
    collector.verify()
    if collector.used:
        raise ValueError("receipt_request_consumed")
    collector.used = True
    collector.channel.send("start", 1)
    collector.channel.receive({"exchange_info"}, 1)
    collector.verify()
    return {"ok": True}


def deliver(
    collector, ledger, lifecycle, payload, provenance, *, on_prepared=None, native_result=None
):
    """Kernel permission must already be revoked. Failure never refunds the attempt."""
    if native_result is not None and native_result.get("profile") not in NATIVE_PROFILES:
        raise ValueError("native_receipt_profile_required")
    if not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError("receipt_size")
    if (
        ledger.state.pending != 0
        or len(ledger.state.attempts) != 1
        or json.loads(lifecycle.expected.splitlines()[-1])["kind"] != "revoked"
    ):
        raise ValueError("pending_attempt_and_revoked_kernel_required")
    links = {
        "attempt_prefix_sha256": digest(ledger.expected),
        "lifecycle_prefix_sha256": digest(lifecycle.expected),
    }
    path = ledger.path / "receipt.jsonl"
    ledger.checkpoint()
    journal = provenance._Journal(path, limit=JOURNAL_LIMIT)
    reader = None
    expected = b""
    deadline = time.monotonic() + DEADLINE
    try:
        reader = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        identity = os.fstat(reader)

        def healthy():
            ledger.checkpoint()
            collector.verify()
            info = path.stat(follow_symlinks=False)
            if (
                (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.pread(reader, JOURNAL_LIMIT + 1, 0) != expected
            ):
                raise ValueError("receipt_storage_changed")
            bounded()

        def bounded():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("receipt_deadline")
            collector.channel.connection.settimeout(remaining)

        def append(kind):
            nonlocal expected
            healthy()
            row = dict(
                seq=journal.seq,
                previous_sha256=journal.previous,
                kind=kind,
                utc_ns=time.time_ns(),
                monotonic_ns=time.monotonic_ns(),
                profile=PROFILE if native_result is None else native_result["profile"],
                **({"native_result": native_result} if native_result is not None else {}),
                binding_sha256=ledger.state.binding_sha256,
                payload_sha256=digest(payload),
                tls_sha256=json.loads(payload)["tls_sha256"],
                **links,
            )
            journal.append(
                kind,
                **{k: v for k, v in row.items() if k not in {"kind", "seq", "previous_sha256"}},
            )
            expected += canonical(row) + b"\n"
            healthy()

        append("prepared")
        if on_prepared:
            on_prepared()
        for seq, start in enumerate(range(0, len(payload), CHUNK), 2):
            healthy()
            collector.channel.send(
                "data:" + base64.b64encode(payload[start : start + CHUNK]).decode(), seq
            )
            bounded()  # A blocked send consumes the same total transfer budget.
            collector.channel.receive({"part"}, seq)
        seq += 1
        healthy()
        collector.channel.send("end:" + digest(payload), seq)
        bounded()
        token = (
            "accepted:" + digest(payload)
            if native_result is None
            else "native:" + digest(canonical(native_result)) + ":" + digest(payload)
        )
        collector.channel.receive({token}, seq)
        append("acknowledged")
        # Keep the child alive until ledger outcome/close; process identity remains verifiable.
        return True
    finally:
        if reader is not None:
            os.close(reader)
        os.close(journal.fd)


def close(collector):
    try:
        collector.channel.send("close", 1000)
        collector.channel.receive({"closed"}, 1000)
        collector.process.wait(timeout=1)
    finally:
        collector.cleanup()


def replay(
    raw,
    *,
    expected_sha256,
    tls_raw,
    attempts,
    lifecycle,
    binding_sha256,
    trust_sha256,
    ledger_module,
    gateway_module,
    transport,
    provenance,
    rates,
    native=None,
):
    """Reconstruct payload from selected raw TLS; bind pending/revoked original prefixes."""
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= JOURNAL_LIMIT
        or digest(raw) != expected_sha256
    ):
        raise ValueError("receipt_archive_selection")
    tls_report = transport["replay"](
        tls_raw,
        expected_sha256=digest(tls_raw),
        attempts=attempts,
        lifecycle=lifecycle,
        binding_sha256=binding_sha256,
        trust_sha256=trust_sha256,
        ledger_module=ledger_module,
        gateway_module=gateway_module,
        provenance=provenance,
        rates=rates,
    )
    complete = ledger_module.replay(
        attempts,
        expected_sha256=digest(attempts),
        binding_sha256=binding_sha256,
    )
    if complete["recorded_attempts"] != 1:
        raise ValueError("receipt_single_attempt_required")
    payload = payload_from_tls(tls_raw, tls_report)
    validate_payload(payload, provenance, rates)
    first = json.loads(raw.splitlines()[0])
    native_result = None
    if native is not None:
        if (
            native.get("PROFILE") not in NATIVE_PROFILES
            or first.get("profile") != native["PROFILE"]
        ):
            raise ValueError("native_receipt_profile_required")
        native_result = native["expected_result"](payload)
    elif first.get("profile") in NATIVE_PROFILES:
        raise ValueError("native_receipt_parser_required")

    def prefix(original, key):
        end = 0
        for line in original.splitlines(keepends=True):
            end += len(line)
            if digest(original[:end]) == first.get(key):
                return original[:end]
        raise ValueError("receipt_original_prefix_missing")

    prepared = prefix(attempts, "attempt_prefix_sha256")
    revoked = prefix(lifecycle, "lifecycle_prefix_sha256")
    before = ledger_module.replay(
        prepared,
        expected_sha256=digest(prepared),
        binding_sha256=binding_sha256,
    )
    kernel = gateway_module["replay_lifecycle"](
        ledger_module,
        revoked,
        expected_sha256=digest(revoked),
        attempts=prepared,
        binding_sha256=binding_sha256,
    )
    if (
        before["pending_attempt"] != 0
        or before["recorded_attempts"] != 1
        or before["status"] != "incomplete_no_resume"
        or kernel["last_record"] != "revoked"
    ):
        raise ValueError("receipt_pending_and_revocation_required")
    predecessor = [json.loads(value.splitlines()[-1]) for value in (prepared, revoked, tls_raw)]
    previous = None
    rows = []
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        row = json.loads(line)
        expected = dict(
            seq=seq,
            previous_sha256=previous,
            kind="prepared" if seq == 0 else "acknowledged",
            utc_ns=row.get("utc_ns"),
            monotonic_ns=row.get("monotonic_ns"),
            profile=PROFILE if native_result is None else native_result["profile"],
            **({"native_result": native_result} if native_result is not None else {}),
            binding_sha256=binding_sha256,
            payload_sha256=digest(payload),
            tls_sha256=tls_report["archive_sha256"],
            attempt_prefix_sha256=digest(prepared),
            lifecycle_prefix_sha256=digest(revoked),
        )
        if (
            seq > 1
            or row != expected
            or type(row.get("seq")) is not int
            or canonical(row) + b"\n" != line
        ):
            raise ValueError("receipt_archive_chain")
        for key in ("utc_ns", "monotonic_ns"):
            if type(row[key]) is not int or any(row[key] < r[key] for r in predecessor + rows):
                raise ValueError("receipt_archive_clock")
        anchor = predecessor[-1]
        if (
            abs((row["utc_ns"] - anchor["utc_ns"]) - (row["monotonic_ns"] - anchor["monotonic_ns"]))
            > 50_000_000
        ):
            raise ValueError("receipt_archive_clock_jump")
        rows.append(row)
        previous = digest(line)
    attempt_rows = list(map(json.loads, attempts.splitlines()))
    terminals = [r for r in attempt_rows if r["kind"] in {"aborted", "closed"}]
    if any(r[k] < rows[-1][k] for r in terminals for k in ("utc_ns", "monotonic_ns")):
        raise ValueError("receipt_terminal_precedes_transfer")
    outcomes = [r for r in attempt_rows if r["kind"] == "outcome"]
    outcome = {"index": 0, "result": "succeeded"}
    if complete["schema_version"] in {
        "portfolio.fixture_signed_account_tls_ledger.v1",
        "portfolio.fixture_signed_orders_tls_ledger.v1",
        "portfolio.fixture_books_tls_ledger.v1",
    }:
        prepared_row = next(r for r in attempt_rows if r["kind"] == "prepared")
        outcome["request_sha256"] = prepared_row["payload"]["request_sha256"]
    if outcomes and outcomes[0]["payload"] != outcome:
        raise ValueError("receipt_outcome_mismatch")
    if outcomes and (
        len(rows) != 2 or any(outcomes[0][k] < rows[-1][k] for k in ("utc_ns", "monotonic_ns"))
    ):
        raise ValueError("receipt_outcome_precedes_acknowledgement")
    return {
        "schema_version": PROFILE if native_result is None else native_result["profile"],
        **(
            {
                "native_result": native_result,
                (
                    "native_books_acknowledged"
                    if native_result["profile"] == "portfolio.installed_native_books_receipt.v1"
                    else "native_orders_acknowledged"
                    if native_result["profile"] == "portfolio.installed_native_orders_receipt.v1"
                    else "native_account_acknowledged"
                    if native_result["profile"] == "portfolio.installed_native_account_receipt.v1"
                    else "native_metadata_acknowledged"
                ): len(rows) == 2,
            }
            if native_result is not None
            else {}
        ),
        "archive_sha256": expected_sha256,
        "tls_sha256": tls_report["archive_sha256"],
        "payload_sha256": digest(payload),
        "status": "acknowledged" if len(rows) == 2 else "incomplete_no_resume",
        "attempt_outcome_recorded": bool(outcomes),
        "header_receipt": tls_report["header_receipt"],
        "body_receipt": tls_report["body_receipt"],
        "native_collector_integrated": False,
        "restart_allowed": False,
        "network_admitted": False,
        "trading_admitted": False,
    }

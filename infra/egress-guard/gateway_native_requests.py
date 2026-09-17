"""Fixed native signed-request custody rehearsal. No socket dispatch or real key API."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
from contextlib import suppress
from urllib.parse import urlencode

PROFILE = "portfolio.fixture_native_requests.v1"
VERSION = "1.226.0"
LIMIT = 262144
# Public RFC 8032 test vector, deliberately not an operator credential.
SEED = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
API_KEY = "public-fixture-key-not-for-a-venue"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_challenge(value, index):
    if (
        not isinstance(value, dict)
        or set(value) != {"index", "nonce", "utc_ns", "monotonic_ns"}
        or type(value["index"]) is not int
        or value["index"] != index
        or type(index) is not int
        or not 0 <= index < 20
        or not isinstance(value["nonce"], str)
        or re.fullmatch("[0-9a-f]{32}", value["nonce"]) is None
        or any(type(value[k]) is not int or value[k] <= 0 for k in ("utc_ns", "monotonic_ns"))
    ):
        raise ValueError("native_request_challenge")


def selected_request(challenge):
    """Root-selected fixed fixture selectors; never accept caller endpoints or costs."""
    index = challenge["index"]
    validate_challenge(challenge, index)
    stamp = challenge["utc_ns"] // 1_000_000
    if index in {1, 9}:
        return {
            "kind": "connect",
            "role": "account" if index == 1 else "market",
            "target": "/ws-api/v3"
            if index == 1
            else "/stream?streams=" + "/".join(s.lower() + "@depth@100ms" for s in SYMBOLS),
        }
    if index in {2, 19}:
        return {
            "kind": "ws",
            "id": f"fixture-{index}",
            "method": "userDataStream.subscribe.signature"
            if index == 2
            else "userDataStream.unsubscribe",
            "params": {"apiKey": API_KEY, "recvWindow": 5000, "timestamp": stamp}
            if index == 2
            else {"subscriptionId": 0},
        }
    path, params, headers = "/api/v3/time", {}, {}
    if index in {3, 6, 14, 17}:
        path = "/api/v3/account"
    elif index in {4, 5, 15, 16}:
        path = "/api/v3/openOrders"
    elif index == 7:
        path = "/api/v3/exchangeInfo"
    elif index == 8:
        path = "/api/v3/ticker/bookTicker"
    elif index in {10, 11, 12}:
        path, params = "/api/v3/depth", {"symbol": SYMBOLS[index - 10], "limit": "100"}
    if index in {3, 4, 5, 6, 14, 15, 16, 17}:
        params.update(timestamp=str(stamp), recvWindow="5000")
        headers["X-MBX-APIKEY"] = API_KEY
    return {"kind": "rest", "method": "GET", "path": path, "params": params, "headers": headers}


def signing_text(request):
    if request["kind"] == "rest" and request["headers"]:
        return urlencode(request["params"])
    if request["kind"] == "ws" and request["method"] == "userDataStream.subscribe.signature":
        return "&".join(f"{key}={request['params'][key]}" for key in sorted(request["params"]))
    return None


def native_request(challenge):
    if os.geteuid() == 0:
        raise ValueError("native_signing_as_root_refused")
    from nautilus_trader.core.nautilus_pyo3 import NAUTILUS_VERSION, ed25519_signature

    if NAUTILUS_VERSION != VERSION:
        raise ValueError("native_version_changed")
    request = selected_request(challenge)
    text = signing_text(request)
    if text is not None:
        request["params"]["signature"] = ed25519_signature(bytes.fromhex(SEED), text)
    return canonical(
        {"profile": PROFILE, "challenge_sha256": digest(canonical(challenge)), "request": request}
    )


def verify_signature(message, signature):
    """Use system OpenSSL, never import native/project packages in the root verifier."""
    raw = base64.b64decode(signature, validate=True)
    if len(raw) != 64 or base64.b64encode(raw).decode() != signature:
        raise ValueError("native_request_signature_encoding")
    public = bytes.fromhex("302a300506032b6570032100" + PUBLIC)
    fds = []
    try:
        for data in (public, message.encode(), raw):
            fd = os.memfd_create("fixture-ed25519-verification", os.MFD_CLOEXEC)
            fds.append(fd)
            if os.write(fd, data) != len(data):
                raise OSError("verification_input_write")
            os.lseek(fd, 0, os.SEEK_SET)
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-keyform",
                "DER",
                "-inkey",
                f"/proc/self/fd/{fds[0]}",
                "-rawin",
                "-in",
                f"/proc/self/fd/{fds[1]}",
                "-sigfile",
                f"/proc/self/fd/{fds[2]}",
            ],
            pass_fds=fds,
            capture_output=True,
            timeout=2,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "OPENSSL_CONF": "/dev/null"},
        )
        if result.returncode:
            raise ValueError("native_request_signature_invalid")
    finally:
        for fd in fds:
            os.close(fd)


def validate_request(raw, challenge, *, received):
    validate_challenge(challenge, challenge["index"])
    if (
        not isinstance(received, tuple)
        or len(received) != 2
        or any(type(v) is not int for v in received)
        or not 0 <= received[0] - challenge["utc_ns"] <= 5_000_000_000
        or not 0 <= received[1] - challenge["monotonic_ns"] <= 5_000_000_000
        or abs((received[0] - challenge["utc_ns"]) - (received[1] - challenge["monotonic_ns"]))
        > 50_000_000
    ):
        raise ValueError("native_request_stale_or_clock_change")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 850:
        raise ValueError("native_request_size")
    value = json.loads(raw)
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError("native_request_canonical")
    expected = selected_request(challenge)
    text = signing_text(expected)
    if text is not None:
        request = value.get("request")
        if not isinstance(request, dict) or not isinstance(request.get("params"), dict):
            raise ValueError("native_request_schema")
        signature = request["params"].get("signature")
        if not isinstance(signature, str):
            raise ValueError("native_request_signature_required")
        expected["params"]["signature"] = signature
    if value != {
        "profile": PROFILE,
        "challenge_sha256": digest(canonical(challenge)),
        "request": expected,
    }:
        raise ValueError("native_request_selector")
    if text is not None:
        verify_signature(text, signature)
    return digest(raw)


class JsonToken:
    def __contains__(self, token):
        return isinstance(token, str) and len(token.encode()) <= 850 and token.startswith("{")


def child_loop(fd, parent):
    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=5)
    try:
        # Import before ready, as in the native metadata consumer.
        if os.geteuid() == 0:
            raise ValueError("native_signing_as_root_refused")
        from nautilus_trader.core.nautilus_pyo3 import NAUTILUS_VERSION

        if NAUTILUS_VERSION != VERSION:
            raise ValueError("native_nonroot_version_required")
        channel.send("ready", 0)
        for index in range(20):
            raw = channel.receive(JsonToken(), index + 1).encode()
            challenge = json.loads(raw)
            validate_challenge(challenge, index)
            if canonical(challenge) != raw:
                raise ValueError("native_challenge_canonical")
            request = native_request(challenge)
            channel.send(request.decode(), index + 1)
            channel.receive({"prepared:" + digest(request)}, index + 1)
            channel.send("received:" + digest(request), index + 1)
        channel.receive({"close"}, 21)
        channel.send("closed", 21)
    finally:
        channel.close()


def launch(authority, sources, launcher, runtime):
    reader = launcher["load_source"](authority.source("inspect_binding.py").decode())[
        "process_identity"
    ]

    def identity(pid):
        authority.verify()
        runtime.verify()
        return {
            **reader(pid),
            "installation_manifest_sha256": authority.manifest_sha256,
            "native_runtime_sha256": runtime.pin,
        }

    runtime.verify()
    source = "".join(
        f"exec(compile({raw!r},'<held-native-request>','exec'))\n"
        for raw in (
            authority.source("collector_launcher.py"),
            sources.source("gateway_native_requests.py"),
        )
    )
    launcher["FixtureCollector"].__init__.__globals__["PYTHON"] = (
        "/run/trader-native-runtime/bin/python3.12"
    )
    return launcher["FixtureCollector"](
        source,
        identity,
        collector_uid=authority.account["uid"],
        collector_gid=authority.account["gid"],
    )


class RequestJournal:
    def __init__(self, ledger, provenance):
        self.ledger, self.provenance = ledger, provenance
        self.path = ledger.path / "requests.jsonl"
        self.journal = provenance._Journal(self.path, limit=LIMIT)
        self.reader = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.identity = os.fstat(self.reader)
        self.expected = b""

    def verify(self):
        self.ledger.checkpoint()
        info = self.path.stat(follow_symlinks=False)
        if (
            (info.st_dev, info.st_ino) != (self.identity.st_dev, self.identity.st_ino)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or os.pread(self.reader, LIMIT + 1, 0) != self.expected
        ):
            raise ValueError("native_request_journal_changed")

    def append(self, kind, **fields):
        self.verify()
        row = {
            "seq": self.journal.seq,
            "previous_sha256": self.journal.previous,
            "kind": kind,
            "profile": PROFILE,
            "binding_sha256": self.ledger.state.binding_sha256,
            "utc_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        }
        self.journal.append(
            kind, **{k: v for k, v in row.items() if k not in {"seq", "previous_sha256", "kind"}}
        )
        self.expected += canonical(row) + b"\n"
        self.verify()

    def close(self):
        os.close(self.reader)
        os.close(self.journal.fd)


def validate_budget(module, ledger):
    operations = (
        "time",
        "account_connect",
        "account_subscribe",
        "account_read",
        "open_orders",
        "open_orders",
        "account_read",
        "exchange_info",
        "book_ticker",
        "market_connect",
        "depth_100",
        "depth_100",
        "depth_100",
        "time",
        "account_read",
        "open_orders",
        "open_orders",
        "account_read",
        "time",
        "account_unsubscribe",
    )
    if (
        ledger.state.profile != module.REQUEST_PROFILE
        or tuple(op for _, op in module.IPC_STEPS) != operations
    ):
        raise ValueError("native_request_fixed_budget_profile")
    units = [module.JOINT_OPERATIONS[op] for op in operations]
    if (
        sum(r["documented_weight"] or 0 for r in units) != 448
        or sum(r["raw_requests"] for r in units) != 16
        or sum(r["connections"] for r in units) != 2
        or sum(r["documented_weight"] is None for r in units) != 1
    ):
        raise ValueError("native_request_fixed_budget_units")


def run_session(collector, ledger, module, provenance, *, on_prepared=None):
    validate_budget(module, ledger)
    journal = RequestJournal(ledger, provenance)
    deadline = time.monotonic() + 30

    def healthy():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native_request_session_deadline")
        collector.verify()
        journal.verify()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native_request_session_deadline")
        collector.channel.connection.settimeout(min(5, remaining))

    try:
        for index, (_, operation) in enumerate(module.IPC_STEPS):
            healthy()
            challenge = {
                "index": index,
                "nonce": os.urandom(16).hex(),
                "utc_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
            }
            journal.append("challenge", challenge=challenge)
            healthy()
            collector.channel.send(canonical(challenge).decode(), index + 1)
            healthy()
            raw = collector.channel.receive(JsonToken(), index + 1).encode()
            received = (time.time_ns(), time.monotonic_ns())
            pin = validate_request(raw, challenge, received=received)
            healthy()
            # Validation and fsync precede any success receipt; no dispatch follows.
            ledger.prepare(caller="collector", operation=operation, request_sha256=pin)
            journal.append(
                "prepared",
                index=index,
                request=json.loads(raw),
                received=list(received),
                attempt_prefix_sha256=digest(ledger.expected),
            )
            if on_prepared is not None:
                on_prepared(index)
            healthy()
            collector.channel.send("prepared:" + pin, index + 1)
            healthy()
            collector.channel.receive({"received:" + pin}, index + 1)
            healthy()
            journal.append("acknowledged", index=index, request_sha256=pin)
            ledger.outcome(index=index, result="succeeded", request_sha256=pin)
        healthy()
        ledger.close()
        collector.channel.send("close", 21)
        collector.channel.receive({"closed"}, 21)
        collector.process.wait(timeout=1)
        return {
            "status": "native_request_custody_completed",
            "operations": 20,
            "signed_requests": 9,
            "transport_dispatch_verified": False,
            "network_admitted": False,
        }
    except BaseException as exc:
        if not ledger.closed and not ledger.failed:
            ledger._abort(exc)
        raise
    finally:
        journal.close()
        with suppress(Exception):
            ledger.close()
        collector.cleanup()


def run_installed(entry, authority, sources):
    collector = ledger = runtime = None
    try:
        entry["fixture_context"](authority)
        gateway = entry["load"](sources.source("ledger_gateway.py"))
        module = gateway["load_ledger"](
            {name: sources.source(name).decode() for name in entry["FILES"]}
        )
        runtime = entry["load"](sources.source("gateway_native_runtime.py"))["NativeRuntime"](
            authority
        )
        launcher = entry["load"](authority.source("collector_launcher.py"))
        collector = launch(authority, sources, launcher, runtime)
        guards = entry["load"](sources.source("selftest.py"))
        binding = entry["InstalledBinding"](authority, sources, collector, guards)
        ledger = module.AttemptLedger(
            entry["STORAGE"],
            binding=binding,
            binding_sha256=binding.pin,
            profile=module.REQUEST_PROFILE,
        )
        print(
            json.dumps(
                {
                    "stage": "joint_ipc_ready",
                    "binding": binding.selected,
                    "binding_sha256": binding.pin,
                }
            ),
            flush=True,
        )
        if sys.stdin.readline() != "continue\n":
            raise ValueError("fixture_parent_release_required")

        def prepared(index):
            if index == 9:
                print(json.dumps({"stage": "joint_ipc_prepared", "index": index}), flush=True)
                if sys.stdin.readline() != "continue\n":
                    raise ValueError("fixture_parent_release_required")

        try:
            result = run_session(
                collector,
                ledger,
                module,
                sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                on_prepared=prepared,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            result = {"status": "refused", "reason": type(exc).__name__, "network_admitted": False}
        print(json.dumps(result), flush=True)
    finally:
        if ledger is not None and not ledger.closed:
            with suppress(Exception):
                ledger.close()
        if collector is not None and not collector.closed:
            collector.cleanup()
        if runtime is not None:
            runtime.close()
        authority.close()


def replay(raw, *, expected_sha256, attempts, binding_sha256, module):
    """Verify original signed selectors and ordered ledger receipts, without network."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT or digest(raw) != expected_sha256:
        raise ValueError("selected_native_request_archive")
    report = module.replay(
        attempts,
        expected_sha256=digest(attempts),
        binding_sha256=binding_sha256,
        profile=module.REQUEST_PROFILE,
    )
    ledger_rows = [json.loads(line) for line in attempts.splitlines()]
    prefixes, prefix = {}, b""
    for row, line in zip(ledger_rows, attempts.splitlines(keepends=True), strict=True):
        prefix += line
        prefixes[digest(prefix)] = (prefix, row)
    prepared_rows = [row for row in ledger_rows if row["kind"] == "prepared"]
    outcomes = {row["payload"]["index"]: row for row in ledger_rows if row["kind"] == "outcome"}
    terminals = [row for row in ledger_rows if row["kind"] in {"closed", "aborted"}]
    rows, previous, challenge, request_pin = [], None, None, None
    prepared, acknowledged, signed = 0, 0, 0
    common = {
        "seq",
        "previous_sha256",
        "kind",
        "profile",
        "binding_sha256",
        "utc_ns",
        "monotonic_ns",
    }

    def before(left, right):
        return all(left[k] <= right[k] for k in ("utc_ns", "monotonic_ns"))

    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or canonical(row) + b"\n" != line
            or type(row.get("seq")) is not int
            or row["seq"] != len(rows)
            or row.get("previous_sha256") != previous
            or row.get("profile") != PROFILE
            or row.get("binding_sha256") != binding_sha256
            or any(type(row.get(k)) is not int or row[k] <= 0 for k in ("utc_ns", "monotonic_ns"))
        ):
            raise ValueError("native_request_chain")
        if rows and (
            not before(rows[-1], row)
            or abs(
                (row["utc_ns"] - rows[0]["utc_ns"])
                - (row["monotonic_ns"] - rows[0]["monotonic_ns"])
            )
            > 50_000_000
        ):
            raise ValueError("native_request_clock")
        if terminals and not before(row, terminals[0]):
            raise ValueError("native_request_after_terminal")
        fields = set(row) - common
        if row["kind"] == "challenge" and challenge is None and prepared == acknowledged:
            if fields != {"challenge"}:
                raise ValueError("native_request_challenge_fields")
            challenge = row["challenge"]
            validate_challenge(challenge, prepared)
            if not before(challenge, row) or not before(ledger_rows[0], challenge):
                raise ValueError("native_request_challenge_order")
            if prepared and (
                prepared - 1 not in outcomes or not before(outcomes[prepared - 1], challenge)
            ):
                raise ValueError("native_request_previous_outcome_required")
        elif row["kind"] == "prepared" and challenge is not None and request_pin is None:
            if (
                fields != {"index", "request", "received", "attempt_prefix_sha256"}
                or type(row["index"]) is not int
                or row["index"] != prepared
            ):
                raise ValueError("native_request_prepared_fields")
            received = row["received"]
            if not isinstance(received, list) or len(received) != 2:
                raise ValueError("native_request_received_clock")
            request_pin = validate_request(
                canonical(row["request"]), challenge, received=tuple(received)
            )
            if not before(
                rows[-1], dict(zip(("utc_ns", "monotonic_ns"), received, strict=True))
            ) or not before(dict(zip(("utc_ns", "monotonic_ns"), received, strict=True)), row):
                raise ValueError("native_request_received_order")
            linked = prefixes.get(row["attempt_prefix_sha256"])
            if linked is None or not before(linked[1], row):
                raise ValueError("native_request_preparation_prefix")
            state = module.replay(
                linked[0],
                expected_sha256=digest(linked[0]),
                binding_sha256=binding_sha256,
                profile=module.REQUEST_PROFILE,
            )
            if (
                state["pending_attempt"] != prepared
                or state["recorded_attempts"] != prepared + 1
                or state["status"] != "incomplete_no_resume"
            ):
                raise ValueError("native_request_pending_prefix_required")
            if (
                prepared >= len(prepared_rows)
                or prepared_rows[prepared]["payload"]["request_sha256"] != request_pin
                or not before(
                    dict(zip(("utc_ns", "monotonic_ns"), received, strict=True)),
                    prepared_rows[prepared],
                )
            ):
                raise ValueError("native_request_ledger_digest")
            prepared += 1
            signed += signing_text(selected_request(challenge)) is not None
        elif row["kind"] == "acknowledged" and request_pin is not None:
            if (
                fields != {"index", "request_sha256"}
                or type(row["index"]) is not int
                or row["index"] != acknowledged
                or row["request_sha256"] != request_pin
            ):
                raise ValueError("native_request_ack_fields")
            if acknowledged in outcomes and (
                not before(row, outcomes[acknowledged])
                or outcomes[acknowledged]["payload"]["result"] != "succeeded"
            ):
                raise ValueError("native_request_outcome_precedes_ack")
            acknowledged += 1
            challenge = request_pin = None
        else:
            raise ValueError("native_request_transition")
        rows.append(row)
        previous = digest(line)
    if not rows or len(prepared_rows) != prepared or any(i >= acknowledged for i in outcomes):
        raise ValueError("native_request_unbound_attempt_or_outcome")
    return {
        "schema_version": PROFILE,
        "archive_sha256": expected_sha256,
        "binding_sha256": binding_sha256,
        "prepared_requests": prepared,
        "acknowledged_requests": acknowledged,
        "verified_signatures": signed,
        "status": "complete"
        if acknowledged == 20 and len(outcomes) == 20 and report["status"] == "closed"
        else "incomplete_no_resume",
        "request_outcomes_recorded": len(outcomes),
        "native_version": VERSION,
        "routes_derived_from_same_run": False,
        "transport_dispatch_verified": False,
        "kernel_permission_granted": False,
        "network_admitted": False,
        "trading_admitted": False,
    }

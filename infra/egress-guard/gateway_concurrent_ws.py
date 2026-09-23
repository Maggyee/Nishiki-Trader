"""Two concurrent fixture-only gateway WebSockets bound to same-run route originals.

Upgrade/control acceptance only: no signed subscription, private data, native event
receipt, caller-selected destination, retry, socket handoff or real venue mode.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import os
import re
import socket
import ssl
import stat
import sys
import time

PROFILE = "portfolio.installed_concurrent_ws.v1"
SCOPE = "concurrent-ws-v1"
ROLES = ("account", "market")
PEER = ("198.51.100.2", 23456)
MARK = 0x7472
LIMIT = 256 * 1024
WIRE_LIMIT = 8192
WINDOW_NS = 4_000_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def selection(raw, bundles, sequence_code, modules):
    report = sequence_code["replay"](
        raw, expected_sha256=digest(raw), bundles=bundles, modules=modules, routes=True
    )
    if report["status"] != "complete":
        raise ValueError("ws_completed_original_routes_required")
    selected = report["route_selection"]
    symbols = selected["symbols"]
    if (
        not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 3
        or symbols != sorted(set(symbols))
        or any(not isinstance(s, str) or not re.fullmatch("[A-Z0-9]{2,20}", s) for s in symbols)
    ):
        raise ValueError("ws_bounded_nonempty_symbols_required")
    first, last = json.loads(raw.splitlines()[0]), json.loads(raw.splitlines()[-1])
    binding = json.loads(bundles[-1]["binding"])
    return {
        "route_archive_sha256": digest(raw),
        "route_bundles_sha256": digest(canonical(bundles)),
        "route_selection_sha256": digest(canonical(selected)),
        "symbols": symbols,
        **{
            k: first["payload"][k]
            for k in ("base_manifest_sha256", "gateway_manifest_sha256", "tls_trust_sha256")
        },
        "environment_sha256": digest(canonical({k: binding[k] for k in ("rules", "route", "net")})),
        "route_completed": {k: last[k] for k in ("utc_ns", "monotonic_ns")},
    }


def endpoint(role, selected):
    if role not in ROLES:
        raise ValueError("ws_fixed_role")
    path = (
        "/ws-api/v3"
        if role == "account"
        else "/stream?streams="
        + "/".join(name.lower() + "@depth@100ms" for name in selected["symbols"])
    )
    return f"wss://{role}.fixture.invalid:23456{path}", path


def request(role, selected, nonce):
    raw = base64.b64decode(nonce, validate=True)
    if len(raw) != 16 or base64.b64encode(raw).decode() != nonce:
        raise ValueError("ws_nonce")
    _, path = endpoint(role, selected)
    return (
        f"GET {path} HTTP/1.1\r\nHost: {role}.fixture.invalid:23456\r\n"
        f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode()


def original(payload):
    raw = base64.b64decode(payload["raw_b64"], validate=True)
    if digest(raw) != payload["raw_sha256"]:
        raise ValueError("ws_original_digest")
    return raw


def client_control(raw, opcode, payload):
    if len(raw) != 6 + len(payload) or raw[:2] != bytes([0x80 | opcode, 0x80 | len(payload)]):
        raise ValueError("ws_masked_control_required")
    mask = raw[2:6]
    if bytes(b ^ mask[i % 4] for i, b in enumerate(raw[6:])) != payload:
        raise ValueError("ws_control_payload_changed")


class State:
    """Replay only original events; incomplete prefixes never authorize resume."""

    PROFILE = PROFILE

    def __init__(self, selected, provenance, frames):
        self.selected, self.provenance, self.frames = selected, provenance, frames
        self.stage = None
        self.wires = {}
        self.start = self.last = self.grant_clock = None
        self.revoked = self.closed = self.complete = self.aborted = False
        self.overlap = False

    def __deepcopy__(self, memo):
        result = type(self)(self.selected, self.provenance, self.frames)
        for key, value in self.__dict__.items():
            if key not in {"selected", "provenance", "frames"}:
                setattr(result, key, copy.deepcopy(value, memo))
        return result

    def clock(self, payload, now, mono):
        if self.complete or self.aborted:
            raise ValueError("ws_terminal")
        if not isinstance(payload, dict) or any(type(v) is not int or v <= 0 for v in (now, mono)):
            raise ValueError("ws_event_fields")
        if self.last and (
            now < self.last[0]
            or mono < self.last[1]
            or abs((now - self.start[0]) - (mono - self.start[1])) > 50_000_000
        ):
            raise ValueError("ws_clock_discontinuity")
        self.last = (now, mono)

    def feed(self, kind, payload, now, mono):
        self.clock(payload, now, mono)
        if self.stage is None:
            if kind != "started" or payload != self.selected:
                raise ValueError("ws_selected_originals")
            completed = self.selected["route_completed"]
            delta = [now - completed["utc_ns"], mono - completed["monotonic_ns"]]
            if (
                any(not 0 <= n <= 5_000_000_000 for n in delta)
                or abs(delta[0] - delta[1]) > 50_000_000
            ):
                raise ValueError("ws_original_route_window")
            self.start = (now, mono)
            self.stage = "preparing"
            return
        if kind == "connection_prepared" and self.stage == "preparing":
            if set(payload) != {"role", "endpoint", "nonce", "peer"}:
                raise ValueError("ws_connection_fields")
            role = payload["role"]
            if (
                len(self.wires) >= len(ROLES)
                or role != ROLES[len(self.wires)]
                or payload["endpoint"] != endpoint(role, self.selected)[0]
                or payload["peer"] != list(PEER)
            ):
                raise ValueError("ws_fixed_connection")
            request(role, self.selected, payload["nonce"])
            self.wires[role] = {
                "nonce": payload["nonce"],
                "stage": "prepared",
                "raw": b"",
                "controls": [],
                "receipts": [],
            }
            return
        if kind == "grant_prepared" and self.stage == "preparing":
            if set(self.wires) != set(ROLES) or payload != {"mark": MARK, "ttl_ms": 5000}:
                raise ValueError("ws_both_attempts_before_grant")
            self.grant_clock = mono
            self.stage = kind
            return
        if kind == "activated" and self.stage == "grant_prepared" and payload == {}:
            self.stage = "active"
            return
        if (
            kind == "sockets_closed"
            and self.stage in {"preparing", "grant_prepared", "active"}
            and payload == {}
        ):
            self.closed = True
            self.stage = kind
            return
        if kind == "stop_requested" and self.stage == "sockets_closed" and payload == {}:
            self.stage = kind
            return
        if kind == "revoked" and self.stage == "stop_requested" and payload == {}:
            self.revoked = True
            self.stage = kind
            return
        if kind in {"completed", "aborted"} and self.stage == "revoked":
            if kind == "completed":
                if (
                    payload
                    or not self.overlap
                    or any(w["stage"] != "peer_closed" for w in self.wires.values())
                ):
                    raise ValueError("ws_complete_requires_both_closed")
                self.complete = True
            else:
                if (
                    set(payload) != {"reason"}
                    or not isinstance(payload["reason"], str)
                    or not 0 < len(payload["reason"]) <= 160
                ):
                    raise ValueError("ws_abort_reason")
                self.aborted = True
            self.stage = kind
            return
        if self.stage != "active" or mono - self.grant_clock > WINDOW_NS:
            raise ValueError("ws_inactive_or_deadline")
        role = payload.get("role")
        if role not in self.wires:
            raise ValueError("ws_fixed_role")
        wire = self.wires[role]
        fields = set(payload) - {"role"}
        if kind == "tls_connected" and wire["stage"] == "prepared":
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
                or payload["peer"] != list(PEER)
                or payload["server_hostname"] != role + ".fixture.invalid"
                or payload["check_hostname"] is not True
                or payload["verify_mode"] != "CERT_REQUIRED"
                or payload["tls_minimum_version"] != "TLSv1.2"
                or payload["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
                or not isinstance(payload["peer_certificate_sha256"], str)
                or re.fullmatch("[0-9a-f]{64}", payload["peer_certificate_sha256"]) is None
                or not isinstance(payload["cipher"], list)
                or len(payload["cipher"]) != 3
            ):
                raise ValueError("ws_tls_verification")
            wire["stage"] = "tls"
        elif kind == "request_prepared" and wire["stage"] == "tls":
            if fields != {"raw_b64", "raw_sha256"} or original(payload) != request(
                role, self.selected, wire["nonce"]
            ):
                raise ValueError("ws_fixed_upgrade_request")
            wire["stage"] = "requested"
        elif kind == "response_chunk" and wire["stage"] in {
            "requested",
            "upgraded",
            "ping",
            "pong",
            "closing",
        }:
            if fields != {"raw_b64", "raw_sha256"}:
                raise ValueError("ws_chunk_fields")
            chunk = original(payload)
            if not 0 < len(chunk) <= 4096 or len(wire["raw"]) + len(chunk) > WIRE_LIMIT:
                raise ValueError("ws_wire_limit")
            wire["raw"] += chunk
            wire["receipts"].append({"end": len(wire["raw"]), "utc_ns": now, "monotonic_ns": mono})
        elif kind == "upgrade_accepted" and wire["stage"] == "requested" and not fields:
            self.headers(role)
            wire["stage"] = "upgraded"
        elif kind == "peer_control" and wire["stage"] in {"upgraded", "closing"}:
            if fields != {"opcode", "raw_b64", "raw_sha256"}:
                raise ValueError("ws_peer_control_fields")
            events = self.events(role)
            index = len(wire["controls"])
            if index >= len(events) or (payload["opcode"], original(payload)) != events[index]:
                raise ValueError("ws_peer_control_original")
            expected = (
                (9, b"fixture:" + role.encode())
                if wire["stage"] == "upgraded"
                else (8, b"\x03\xe8")
            )
            if events[index] != expected or type(payload["opcode"]) is not int:
                raise ValueError("ws_fixture_control_only")
            wire["controls"].append(events[index])
            wire["stage"] = "ping" if expected[0] == 9 else "peer_closed"
        elif kind == "pong_prepared" and wire["stage"] == "ping":
            if fields != {"raw_b64", "raw_sha256"}:
                raise ValueError("ws_pong_fields")
            client_control(original(payload), 10, b"fixture:" + role.encode())
            wire["stage"] = "pong"
        elif kind == "close_prepared" and wire["stage"] == "pong":
            if fields != {"raw_b64", "raw_sha256"} or any(
                w["stage"] not in {"pong", "closing", "peer_closed"} for w in self.wires.values()
            ):
                raise ValueError("ws_both_live_before_close")
            client_control(original(payload), 8, b"\x03\xe8")
            self.overlap = True
            wire["stage"] = "closing"
        else:
            raise ValueError("ws_transition")

    def headers(self, role):
        wire = self.wires[role]
        raw = wire["raw"]
        if b"\r\n\r\n" not in raw:
            raise ValueError("ws_headers_incomplete")
        end = raw.index(b"\r\n\r\n") + 4
        status, pairs = self.provenance.response_headers(raw[:end])
        self.provenance._validate_response(role, status, pairs, wire["nonce"])
        return end

    def events(self, role):
        wire = self.wires[role]
        return self.frames["ServerFrames"]().feed(wire["raw"][self.headers(role) :])

    def report(self):
        return {
            "schema_version": self.PROFILE,
            "status": "complete" if self.complete else "incomplete_no_resume",
            "last_record": self.stage,
            "prepared_connections": len(self.wires),
            "symbols": self.selected["symbols"],
            "both_channels_live_before_close": self.overlap,
            "revocation_recorded": self.revoked,
            "sockets_closed_recorded": self.closed,
            "channels": {
                role: {
                    "stage": w["stage"],
                    "received_bytes": len(w["raw"]),
                    "header_receipt": next(
                        (
                            {k: r[k] for k in ("utc_ns", "monotonic_ns")}
                            for r in w["receipts"]
                            if b"\r\n\r\n" in w["raw"]
                            and r["end"] >= w["raw"].index(b"\r\n\r\n") + 4
                        ),
                        None,
                    ),
                }
                for role, w in self.wires.items()
            },
            "documented_account_connect_weight": 2 if "account" in self.wires else 0,
            "market_connection_charge": None,
            "actual_usage_upper_bound": None,
            "account_subscription_authenticated": False,
            "native_events_delivered": False,
            "stream_fence_verified": False,
            "restart_allowed": False,
            "network_admitted": False,
            "trading_admitted": False,
        }


def replay(raw, *, expected_sha256, selected, provenance, frames, state_type=State):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT or digest(raw) != expected_sha256:
        raise ValueError("ws_selected_archive")
    state, previous = state_type(selected, provenance, frames), None
    for index, line in enumerate(raw.splitlines(keepends=True)):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row)
            != {"seq", "previous_sha256", "kind", "utc_ns", "monotonic_ns", "profile", "payload"}
            or row["profile"] != state.PROFILE
            or type(row["seq"]) is not int
            or row["seq"] != index
            or row["previous_sha256"] != previous
            or canonical(row) + b"\n" != line
        ):
            raise ValueError("ws_chain")
        state.feed(row["kind"], row["payload"], row["utc_ns"], row["monotonic_ns"])
        previous = digest(line)
    return {**state.report(), "archive_sha256": expected_sha256}


class Journal:
    def __init__(self, path, selected, provenance, frames, check, *, state_type=State):
        self.path, self.check = path, check
        self.owner, self.failed, self.expected = os.getpid(), False, b""
        self.closed = False
        self.state = state_type(selected, provenance, frames)
        self.reader = None
        check()
        self.journal = provenance._Journal(path, limit=LIMIT, reserve=4096)
        try:
            self.reader = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.identity = os.fstat(self.reader)
            self.append("started", selected)
        except BaseException:
            self.close()
            raise

    def append(self, kind, payload, clocks=None):
        if self.failed or self.closed or os.getpid() != self.owner:
            raise ValueError("ws_journal_ended_or_foreign_owner")
        try:
            self.check()
            info = self.path.stat(follow_symlinks=False)
            if (
                (info.st_dev, info.st_ino) != (self.identity.st_dev, self.identity.st_ino)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.pread(self.reader, LIMIT + 1, 0) != self.expected
            ):
                raise ValueError("ws_archive_changed")
            now, mono = clocks or (time.time_ns(), time.monotonic_ns())
            future = copy.deepcopy(self.state)
            # Modules are references, not copied; State.__deepcopy__ preserves them.
            future.feed(kind, payload, now, mono)
            row = {
                "seq": self.journal.seq,
                "previous_sha256": self.journal.previous,
                "kind": kind,
                "utc_ns": now,
                "monotonic_ns": mono,
                "profile": self.state.PROFILE,
                "payload": payload,
            }
            self.journal.append(
                kind,
                **{k: v for k, v in row.items() if k not in {"kind", "seq", "previous_sha256"}},
            )
            self.expected += canonical(row) + b"\n"
            if os.pread(self.reader, LIMIT + 1, 0) != self.expected:
                raise ValueError("ws_persisted_bytes_changed")
            self.state = future
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if os.getpid() != self.owner:
            raise ValueError("ws_journal_foreign_owner")
        if not self.closed:
            self.closed = True
            if self.reader is not None:
                os.close(self.reader)
                self.reader = None
            os.close(self.journal.fd)


async def capture(journal, trust, frames, check, grant, revoke, notify, session=None):
    """One event-loop owner; two fixed marked sockets, one unrenewable kernel window."""
    writers, sockets, tasks = [], [], []
    failure = None
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=trust.decode("ascii"))
        if digest(trust) != journal.state.selected["tls_trust_sha256"]:
            raise ValueError("ws_trust_changed")
        nonces = {role: base64.b64encode(os.urandom(16)).decode() for role in ROLES}
        for role in ROLES:
            journal.append(
                "connection_prepared",
                {
                    "role": role,
                    "endpoint": endpoint(role, journal.state.selected)[0],
                    "nonce": nonces[role],
                    "peer": list(PEER),
                },
            )
        snapshot_code = getattr(session, "snapshot_code", None)
        if snapshot_code is not None:
            for symbol in journal.state.selected["symbols"]:
                journal.append(
                    "snapshot_connection_prepared",
                    {
                        "symbol": symbol,
                        "endpoint": f"https://rest.fixture.invalid:23456/api/v3/depth?symbol={symbol}&limit=100",
                        "peer": list(PEER),
                    },
                )
        notify("ws_prepared")
        journal.append("grant_prepared", {"mark": MARK, "ttl_ms": 5000})
        deadline = journal.state.grant_clock / 1e9 + 4
        check()
        grant()
        journal.append("activated", {})
        notify("ws_activated")
        ready = {role: asyncio.Event() for role in ROLES}
        exchanges_done = {role: asyncio.Event() for role in ROLES}
        snapshots_done = asyncio.Event()
        if snapshot_code is None:
            snapshots_done.set()
        loop = asyncio.get_running_loop()

        def before_wire():
            check()
            if time.monotonic() >= deadline:
                raise TimeoutError("ws_total_deadline")

        async def one(role):
            before_wire()
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(raw)
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)
            raw.setblocking(False)
            await loop.sock_connect(raw, PEER)
            before_wire()
            reader, writer = await asyncio.open_connection(
                sock=raw,
                ssl=context,
                server_hostname=role + ".fixture.invalid",
                ssl_handshake_timeout=max(0.001, deadline - time.monotonic()),
            )
            writers.append(writer)
            tls = writer.get_extra_info("ssl_object")
            certificate = tls.getpeercert(binary_form=True)
            if not certificate:
                raise ValueError("ws_certificate_missing")
            journal.append(
                "tls_connected",
                {
                    "role": role,
                    "peer": list(writer.get_extra_info("peername")),
                    "server_hostname": tls.server_hostname,
                    "peer_certificate_sha256": digest(certificate),
                    "tls_version": tls.version(),
                    "cipher": list(tls.cipher()),
                    "check_hostname": context.check_hostname,
                    "verify_mode": "CERT_REQUIRED"
                    if context.verify_mode == ssl.CERT_REQUIRED
                    else "invalid",
                    "tls_minimum_version": "TLSv1.2",
                },
            )

            async def send(kind, raw):
                journal.append(kind, {"role": role, **journal.state.provenance.raw_fields(raw)})
                before_wire()
                writer.write(raw)
                await writer.drain()

            async def chunk():
                before_wire()
                data = await reader.read(4096)
                clocks = time.time_ns(), time.monotonic_ns()
                if not data:
                    raise ValueError("ws_unexpected_eof")
                journal.append(
                    "response_chunk",
                    {"role": role, **journal.state.provenance.raw_fields(data)},
                    clocks,
                )

            await send("request_prepared", request(role, journal.state.selected, nonces[role]))
            while b"\r\n\r\n" not in journal.state.wires[role]["raw"]:
                await chunk()
            journal.append("upgrade_accepted", {"role": role})
            while not journal.state.events(role):
                await chunk()
            opcode, data = journal.state.events(role)[0]
            journal.append(
                "peer_control",
                {"role": role, "opcode": opcode, **journal.state.provenance.raw_fields(data)},
            )
            await send("pong_prepared", frames["client_frame"](data, 10))
            ready[role].set()
            await ready[ROLES[1 - ROLES.index(role)]].wait()
            if role == "account":
                notify("ws_both_live")
                if session is not None:
                    await session.exchange(journal, writer, chunk, before_wire, deadline)
            elif session is not None:
                await session.exchange_market(journal, chunk)
            exchanges_done[role].set()
            await exchanges_done[ROLES[1 - ROLES.index(role)]].wait()
            await snapshots_done.wait()
            await send("close_prepared", frames["client_frame"](b"\x03\xe8", 8))
            while len(journal.state.events(role)) < 2:
                await chunk()
            opcode, data = journal.state.events(role)[1]
            journal.append(
                "peer_control",
                {"role": role, "opcode": opcode, **journal.state.provenance.raw_fields(data)},
            )

        async def snapshots():
            await asyncio.gather(*(event.wait() for event in ready.values()))

            async def one_snapshot(symbol):
                before_wire()
                raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(raw)
                raw.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)
                raw.setblocking(False)
                await loop.sock_connect(raw, PEER)
                before_wire()
                reader, writer = await asyncio.open_connection(
                    sock=raw,
                    ssl=context,
                    server_hostname="rest.fixture.invalid",
                    ssl_handshake_timeout=max(0.001, deadline - time.monotonic()),
                )
                writers.append(writer)
                tls = writer.get_extra_info("ssl_object")
                certificate = tls.getpeercert(binary_form=True)
                if not certificate:
                    raise ValueError("snapshot_certificate_missing")
                journal.append(
                    "snapshot_tls_connected",
                    {
                        "symbol": symbol,
                        "peer": list(writer.get_extra_info("peername")),
                        "server_hostname": tls.server_hostname,
                        "peer_certificate_sha256": digest(certificate),
                        "tls_version": tls.version(),
                        "cipher": list(tls.cipher()),
                        "check_hostname": context.check_hostname,
                        "verify_mode": "CERT_REQUIRED"
                        if context.verify_mode == ssl.CERT_REQUIRED
                        else "invalid",
                        "tls_minimum_version": "TLSv1.2",
                    },
                )
                request_bytes = snapshot_code["request"](symbol)
                journal.append(
                    "snapshot_request_prepared",
                    {"symbol": symbol, **journal.state.provenance.raw_fields(request_bytes)},
                )
                before_wire()
                writer.write(request_bytes)
                await writer.drain()
                while True:
                    before_wire()
                    chunk = await reader.read(4096)
                    clocks = time.time_ns(), time.monotonic_ns()
                    if not chunk:
                        break
                    journal.append(
                        "snapshot_chunk",
                        {"symbol": symbol, **journal.state.provenance.raw_fields(chunk)},
                        clocks,
                    )
                journal.append("snapshot_accepted", {"symbol": symbol})

            await asyncio.gather(
                *(one_snapshot(symbol) for symbol in journal.state.selected["symbols"])
            )
            snapshots_done.set()

        tasks = [asyncio.create_task(one(role)) for role in ROLES]
        if snapshot_code is not None:
            tasks.append(asyncio.create_task(snapshots()))
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=max(0, deadline - time.monotonic()))
    except BaseException as exc:
        failure = exc
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        close_failed = False
        for close in [
            *(writer.transport.abort for writer in writers),
            *(raw.close for raw in sockets),
        ]:
            try:
                close()
            except BaseException as exc:
                close_failed = True
                failure = failure or exc
        # Persistence or socket-close failure must never bypass kernel revocation.
        try:
            if close_failed:
                raise RuntimeError("ws_socket_close_uncertain")
            journal.append("sockets_closed", {})
            journal.append("stop_requested", {})
        except BaseException as exc:
            failure = failure or exc
        try:
            revoke()
            journal.append("revoked", {})
            if failure is None and session is not None:
                session.deliver(journal, notify)
            journal.append(
                "completed" if failure is None else "aborted",
                {} if failure is None else {"reason": type(failure).__name__},
            )
        except BaseException as exc:
            failure = failure or exc
    if failure is not None:
        raise failure


def capture_result(*args):
    try:
        asyncio.run(capture(*args))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:  # noqa: UP041 -- root uses Python 3.10
        return {
            "status": "concurrent_ws_refused",
            "reason": type(exc).__name__,
            "network_admitted": False,
        }
    return {"status": "concurrent_ws_completed", "network_admitted": False}


def run_installed(
    entry, authority, sources, sequence, *, signed=False, market=False, snapshot=False
):
    if market and not signed:
        raise ValueError("market_ws_requires_signed_account")
    if snapshot and not market:
        raise ValueError("snapshot_requires_market")
    code = entry["load"](sources.source("gateway_read_sequence.py"))
    frames = entry["load"](sources.source("portfolio_ws_frames.py"))
    guards = entry["load"](sources.source("selftest.py"))
    selected = selection(sequence.expected, sequence.bundles, code, sequence.modules)
    last_binding = json.loads(sequence.bundles[-1]["binding"])
    run, nft = guards["run"], guards["NFT"]

    def check():
        sequence.verify()
        authority.verify()
        rules = guards["stable_rules"](
            json.loads(run(nft, "-j", "list", "table", "inet", "fixture_ledger_gateway"))
        )
        for row in rules["nftables"]:
            if "set" in row:
                row["set"].pop("elem", None)
        if (
            rules != last_binding["rules"]
            or json.loads(run(guards["IP"], "-j", "route", "get", "198.51.100.2"))
            != last_binding["route"]
            or os.readlink("/proc/self/ns/net") != last_binding["net"]
        ):
            raise ValueError("ws_original_environment_changed")

    def grant():
        run(
            nft,
            "-f",
            "-",
            text=f"add element inet fixture_ledger_gateway permits {{ {MARK} timeout 5s }}\n",
        )

    def revoke():
        run(nft, "flush", "set", "inet", "fixture_ledger_gateway", "permits")
        value = json.loads(
            run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
        )
        if any(row.get("set", {}).get("elem") for row in value["nftables"]):
            raise RuntimeError("ws_revocation_failed")

    def notify(stage):
        print(json.dumps({"stage": stage}), flush=True)
        if sys.stdin.readline() != "continue\n":
            raise ValueError("fixture_parent_release_required")

    check()
    extension = entry["load"](sources.source("gateway_account_ws.py")) if signed else None
    if signed:
        selected = extension["selection"](selected, sequence.bundles)
    market_code = entry["load"](sources.source("gateway_market_ws.py")) if market else None
    if market:
        selected = market_code["selection"](selected, sequence.bundles)
    snapshot_code = entry["load"](sources.source("gateway_snapshot_ws.py")) if snapshot else None
    scope = (
        snapshot_code["SCOPE"]
        if snapshot
        else market_code["SCOPE"]
        if market
        else extension["SCOPE"]
        if signed
        else SCOPE
    )
    path = sequence.path / scope
    os.mkdir(scope, 0o700, dir_fd=sequence.directory)
    os.fsync(sequence.directory)
    sequence.hold(path, directory=True)
    sequence.write(
        path / "README.md",
        (
            b"Fixture REST depth anchors and concurrent native account/market receipts. Phase: disposable acceptance. Consumed on creation; no synchronized book, stream fence or live admission. Next: full joint collector integration.\n"
            if snapshot
            else b"Fixture account and market increment native receipts. Phase: disposable acceptance. Consumed on creation, no synchronized book or live admission. Next: original replay and REST depth snapshot integration.\n"
            if market
            else b"Fixture signed subscription and partial native event receipt. Phase: disposable acceptance. Consumed on creation; no live admission. Next: offline original replay and full collector integration.\n"
            if signed
            else b"Two fixed concurrent fixture TLS/WebSocket upgrades and control exchanges. Consumed on creation. No signing, account subscription, native events or live admission. Next: offline original replay, then signed/native integration.\n"
        ),
    )
    fd = authority.open_file("/etc/trader/egress-gateway-fixture-ca.pem", 0o444)
    trust = os.pread(fd, 65537, 0)
    session = journal = None
    try:
        if signed:
            session = extension["Session"](
                entry, authority, sources, market=market, snapshot=snapshot
            )
            if market:
                session.exchange_market = lambda journal, chunk: market_code["exchange"](
                    journal, chunk
                )
            if snapshot:
                session.snapshot_code = snapshot_code
        state_type = extension["state_type"](globals(), session.requests) if signed else State
        if market:
            state_type = market_code["state_type"](globals(), extension, session.requests)
        if snapshot:
            state_type = snapshot_code["state_type"](
                globals(), extension, session.requests, market_code
            )
        journal = Journal(
            path / "ws.jsonl",
            selected,
            sequence.modules["provenance"],
            frames,
            check,
            state_type=state_type,
        )
        if signed:
            journal.append("signer_prepared", session.collector.selected)
        return capture_result(journal, trust, frames, check, grant, revoke, notify, session)
    finally:
        if journal is not None:
            journal.close()
        if session is not None:
            session.close()

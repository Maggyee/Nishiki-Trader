"""Staged fixture account WebSocket for the installed ordered joint prefix.

The root parent owns the TLS socket across the connect and subscribe steps.
No account interval, account event or live venue authority is inferred.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import ssl
import sys
import time

PROFILE = "portfolio.installed_joint_account_channel.v1"
PEER = ("198.51.100.2", 23456)
MARK = 0x7472
LIMIT = 65536
WINDOW_NS = 5_000_000_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def original(fields):
    raw = base64.b64decode(fields["raw_b64"], validate=True)
    if base64.b64encode(raw).decode() != fields["raw_b64"] or digest(raw) != fields["raw_sha256"]:
        raise ValueError("joint_ws_original_changed")
    return raw


def review_step(bundle, index, context, selected, modules, previous, *, market_events=False):
    if not isinstance(bundle, dict) or set(bundle) - {"binding", "ws"}:
        raise ValueError("joint_ws_bundle_fields")
    if not bundle:
        return {"complete": False, "native_result": None}
    if "binding" not in bundle:
        raise ValueError("joint_ws_binding_required")
    binding = json.loads(bundle["binding"])
    anchor = json.loads(previous[0]["binding"])
    if (
        canonical(binding).decode() != bundle["binding"]
        or binding.get("read_sequence") != context
        or set(binding) != set(anchor) | {"clock_anchor_sha256"}
        or binding["clock_anchor_sha256"] != digest(previous[0]["binding"].encode())
        or any(binding[k] != anchor[k] for k in anchor if k != "read_sequence")
        or any(
            binding[k] != selected[k]
            for k in selected
            if k.endswith("manifest_sha256") or k == "tls_trust_sha256"
        )
    ):
        raise ValueError("joint_ws_binding_changed")
    if "ws" not in bundle:
        return {"complete": False, "native_result": None}
    raw = bundle["ws"].encode()
    if not 0 < len(raw) <= LIMIT:
        raise ValueError("joint_ws_archive_limit")
    rows, prior, start = [], None, None
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row)
            != {"seq", "previous_sha256", "kind", "utc_ns", "monotonic_ns", "profile", "payload"}
            or row["seq"] != len(rows)
            or type(row["seq"]) is not int
            or row["previous_sha256"] != prior
            or row["profile"] != PROFILE
            or canonical(row) + b"\n" != line
            or type(row["utc_ns"]) is not int
            or type(row["monotonic_ns"]) is not int
            or any(row[k] <= 0 or rows and row[k] < rows[-1][k] for k in ("utc_ns", "monotonic_ns"))
        ):
            raise ValueError("joint_ws_archive_chain")
        if start is None:
            start = row
        if (
            abs((row["utc_ns"] - start["utc_ns"]) - (row["monotonic_ns"] - start["monotonic_ns"]))
            > 50_000_000
        ):
            raise ValueError("joint_ws_clock_jump")
        rows.append(row)
        prior = digest(line)
    stages = [r["kind"] for r in rows]
    if not stages or stages[0] != "intent":
        raise ValueError("joint_ws_preparation_order")
    if index in {1, 9}:
        expected = ["intent", "grant_prepared", "activated", "tls_connected", "request_prepared"]
        chunks = "response_chunk"
        conclusion = "upgrade_accepted"
        intent = rows[0]["payload"]
        ws = modules["ws"]
        role = "account" if index == 1 else "market"
        route = (
            modules["joint_route_selection"](previous, selected, modules) if index == 9 else None
        )
        route_fields = (
            {
                "route_selection_sha256": digest(canonical(route)),
                "route_bundles_sha256": digest(canonical(previous)),
            }
            if route is not None
            else {"clock_bundle_sha256": digest(canonical(previous[0]))}
        )
        symbols = {"symbols": route["symbols"]} if route is not None else {}
        if (
            set(intent) != {"endpoint", "peer", "nonce"} | set(route_fields)
            or intent["endpoint"] != ws["endpoint"](role, symbols)[0]
            or intent["peer"] != list(PEER)
            or any(intent[key] != value for key, value in route_fields.items())
        ):
            raise ValueError("joint_ws_fixed_connection")
        nonce = intent["nonce"]
        expected_request = ws["request"](role, symbols, nonce)
        if len(rows) >= 4 and stages[3] == "tls_connected":
            tls = rows[3]["payload"]
            if (
                set(tls)
                != {
                    "peer",
                    "server_hostname",
                    "peer_certificate_sha256",
                    "tls_version",
                    "cipher",
                    "check_hostname",
                    "verify_mode",
                }
                or tls["peer"] != list(PEER)
                or tls["server_hostname"] != role + ".fixture.invalid"
                or tls["check_hostname"] is not True
                or tls["verify_mode"] != "CERT_REQUIRED"
                or tls["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
                or re.fullmatch("[0-9a-f]{64}", tls["peer_certificate_sha256"]) is None
                or not isinstance(tls["cipher"], list)
            ):
                raise ValueError("joint_ws_tls_identity")
        if (
            len(rows) >= 5
            and stages[4] == "request_prepared"
            and (
                set(rows[4]["payload"]) != {"raw_b64", "raw_sha256"}
                or original(rows[4]["payload"]) != expected_request
            )
        ):
            raise ValueError("joint_ws_upgrade_request")
    elif index == 2:
        expected = ["intent", "signature_prepared", "grant_prepared", "activated", "write_prepared"]
        chunks = "response_chunk"
        conclusion = "subscription_accepted"
        intent = rows[0]["payload"]
        if set(intent) != {"connection_bundle_sha256", "signer"} or intent[
            "connection_bundle_sha256"
        ] != digest(canonical(previous[1])):
            raise ValueError("joint_ws_preceding_connection")
        signer = intent["signer"]
        clock_process = anchor["collector"]["process"]
        process = signer.get("process") if isinstance(signer, dict) else None
        if (
            not isinstance(process, dict)
            or set(signer) != {"process", "launcher_source_sha256"}
            or not isinstance(signer["launcher_source_sha256"], str)
            or re.fullmatch("[0-9a-f]{64}", signer["launcher_source_sha256"]) is None
            or set(process) != set(clock_process)
            or type(process["pid"]) is not int
            or type(process["start_ticks"]) is not int
            or process["pid"] <= 0
            or process["start_ticks"] <= 0
            or (process["pid"], process["start_ticks"])
            == (clock_process["pid"], clock_process["start_ticks"])
            or any(
                process[k] != clock_process[k]
                for k in clock_process
                if k not in {"pid", "start_ticks", "namespaces"}
            )
            or set(process["namespaces"]) != set(clock_process["namespaces"])
            or any(
                process["namespaces"][k] != clock_process["namespaces"][k]
                for k in clock_process["namespaces"]
                if k != "net"
            )
            or process["namespaces"]["net"] == binding["net"]
        ):
            raise ValueError("joint_ws_native_signer_identity")
        if len(rows) >= 2:
            signed = rows[1]["payload"]
            if set(signed) != {"challenge", "request", "received", "raw_b64", "raw_sha256"}:
                raise ValueError("joint_ws_signature_fields")
            requests = modules["requests"]
            requests["validate_challenge"](signed["challenge"], 2)
            if not isinstance(signed["received"], list) or len(signed["received"]) != 2:
                raise ValueError("joint_ws_signature_receipt")
            requests["validate_request"](
                canonical(signed["request"]),
                signed["challenge"],
                received=tuple(signed["received"]),
            )
            wire = original(signed)
            if modules["account_ws"]["unmask"](wire) != modules["account_ws"]["wire_request"](
                signed["request"]
            ):
                raise ValueError("joint_ws_signed_wire")
            for k, value in zip(("utc_ns", "monotonic_ns"), signed["received"], strict=True):
                if type(value) is not int or not signed["challenge"][k] <= value <= rows[1][k]:
                    raise ValueError("joint_ws_signature_clock")
            if (
                len(rows) >= 5
                and stages[4] == "write_prepared"
                and any(
                    not 0 <= rows[4][k] - signed["challenge"][k] < WINDOW_NS
                    for k in ("utc_ns", "monotonic_ns")
                )
            ):
                raise ValueError("joint_ws_signature_expired_before_send")
        if len(rows) >= 5 and stages[4] == "write_prepared" and rows[4]["payload"] != {}:
            raise ValueError("joint_ws_write_fields")
    else:
        raise ValueError("joint_ws_step_index")
    grant_index = 1 if index in {1, 9} else 2
    if len(rows) > grant_index and rows[grant_index]["payload"] != {"mark": MARK, "ttl_ms": 5000}:
        raise ValueError("joint_ws_grant_intent")
    early_revoked = (
        stages[-1] == "revoked" and conclusion not in stages and len(stages) <= len(expected)
    )
    prefix = stages[: min(len(stages) - int(early_revoked), len(expected))]
    if prefix != expected[: len(prefix)]:
        raise ValueError("joint_ws_fixed_stage_order")
    if early_revoked:
        if "grant_prepared" not in prefix or rows[-1]["payload"] != {}:
            raise ValueError("joint_ws_early_revocation")
        return {"complete": False, "native_result": None, "ws_archive_sha256": digest(raw)}
    offset = len(expected)
    end = offset
    response = bytearray()
    while end < len(rows) and stages[end] == chunks:
        fields = rows[end]["payload"]
        if set(fields) != {"raw_b64", "raw_sha256"}:
            raise ValueError("joint_ws_chunk_fields")
        response.extend(original(fields))
        if len(response) > 8192:
            raise ValueError("joint_ws_response_limit")
        end += 1
    if stages[end : end + 1] == [conclusion]:
        if not response or rows[end]["payload"] != {}:
            raise ValueError("joint_ws_response_required")
        if index in {1, 9}:
            if b"\r\n\r\n" not in response:
                raise ValueError("joint_ws_upgrade_incomplete")
            headers = bytes(response)
            if headers.index(b"\r\n\r\n") + 4 != len(headers):
                raise ValueError("joint_ws_unexpected_upgrade_data")
            status, pairs = modules["provenance"].response_headers(headers)
            modules["provenance"]._validate_response(
                "account" if index == 1 else "market", status, pairs, nonce
            )
        else:
            frames = modules["frames"]["ServerFrames"]().feed(bytes(response))
            if len(frames) != 1 or frames[0][0] != 1:
                raise ValueError("joint_ws_subscription_frame")
            modules["account_ws"]["response"](frames[0][1])
        end += 1
    increments = None
    if market_events:
        if index != 9:
            raise ValueError("joint_market_fixed_step")
        chunks = []
        while stages[end : end + 1] == ["market_chunk"]:
            chunk = rows[end]
            if set(chunk["payload"]) != {"raw_b64", "raw_sha256"}:
                raise ValueError("joint_market_chunk_fields")
            chunks.append(chunk)
            if len(chunks) > 16 or sum(len(original(c["payload"])) for c in chunks) > 8192:
                raise ValueError("joint_market_chunk_limit")
            end += 1
        if stages[end : end + 1] == ["market_accepted"]:
            if conclusion not in stages[:end]:
                raise ValueError("joint_market_before_upgrade")
            selected_market = modules["market"]["selection"](route, [previous[7]])[
                "market_definitions"
            ]
            parser = modules["frames"]["ServerFrames"]()
            items = []
            for chunk in chunks:
                receipt = {key: chunk[key] for key in ("utc_ns", "monotonic_ns")}
                for opcode, payload in parser.feed(original(chunk["payload"])):
                    if opcode != 1:
                        raise ValueError("joint_market_text_required")
                    items.append(
                        {
                            **modules["provenance"].raw_fields(payload),
                            "receipt": receipt,
                        }
                    )
            if parser.retained_bytes or parser.fragment is not None:
                raise ValueError("joint_market_incomplete_frame")
            increments = modules["market"]["increments"](items, selected_market, complete=True)
            if rows[end]["payload"] != {
                "event_sha256": [item["original_sha256"] for item in increments]
            }:
                raise ValueError("joint_market_event_receipt_changed")
            end += 1
        elif stages[end : end + 1] == ["revoked"]:
            if conclusion not in stages[:end] or rows[end]["payload"] != {}:
                raise ValueError("joint_market_revocation_order")
            if end + 1 != len(rows):
                raise ValueError("joint_market_incomplete_acceptance")
            return {"complete": False, "native_result": None, "ws_archive_sha256": digest(raw)}
    if stages[end : end + 1] == ["revoked"]:
        if rows[end]["payload"] != {} or "activated" not in stages[:end]:
            raise ValueError("joint_ws_revoked_without_response")
        end += 1
    if stages[end : end + 1] == ["accepted"]:
        if (
            rows[end]["payload"] != {}
            or stages[end - 1] != "revoked"
            or conclusion not in stages[:end]
            or market_events
            and increments is None
        ):
            raise ValueError("joint_ws_acceptance_before_revocation")
        end += 1
    if end != len(rows):
        raise ValueError("joint_ws_unexpected_stage")
    if (
        len(rows) > grant_index
        and rows[-1]["monotonic_ns"] - rows[grant_index]["monotonic_ns"] > WINDOW_NS
    ):
        raise ValueError("joint_ws_window_expired")
    complete = stages[-1] == "accepted"
    return {
        "complete": complete,
        "native_result": None,
        "ws_archive_sha256": digest(raw),
        "account_connection_upgraded": complete if index == 1 else True,
        "market_connection_upgraded": index == 9 and complete,
        "subscription_acknowledged": complete if index == 2 else False,
        "native_signer_verified": index == 2 and complete,
        "account_interval_complete": False,
        **({"market_events": increments or []} if market_events else {}),
    }


class Channel:
    def __init__(self, entry, authority, sources, sequence):
        self.entry, self.authority, self.sources, self.sequence = (
            entry,
            authority,
            sources,
            sequence,
        )
        self.connection = self.market_connection = self.session = None
        self.guards = entry["load"](sources.source("selftest.py"))
        self.ws = entry["load"](sources.source("gateway_concurrent_ws.py"))
        self.account = entry["load"](sources.source("gateway_account_ws.py"))
        self.requests = entry["load"](sources.source("gateway_native_requests.py"))
        self.provenance = sequence.modules["provenance"]
        self.trust = os.pread(
            authority.open_file("/etc/trader/egress-gateway-fixture-ca.pem", 0o444), 65537, 0
        )
        if digest(self.trust) != json.loads(sequence.bundles[0]["binding"])["tls_trust_sha256"]:
            raise ValueError("joint_ws_original_trust_changed")

    def check(self):
        self.sequence.verify()
        self.authority.verify()
        binding = json.loads(self.sequence.bundles[0]["binding"])
        run = self.guards["run"]
        rules = self.guards["stable_rules"](
            json.loads(
                run(self.guards["NFT"], "-j", "list", "table", "inet", "fixture_ledger_gateway")
            )
        )
        for row in rules["nftables"]:
            if "set" in row:
                row["set"].pop("elem", None)
        if (
            rules != binding["rules"]
            or json.loads(run(self.guards["IP"], "-j", "route", "get", "198.51.100.2"))
            != binding["route"]
            or os.readlink("/proc/self/ns/net") != binding["net"]
        ):
            raise ValueError("joint_ws_original_environment_changed")

    def grant(self):
        self.guards["run"](
            self.guards["NFT"],
            "-f",
            "-",
            text=f"add element inet fixture_ledger_gateway permits {{ {MARK} timeout 5s }}\n",
        )

    def revoke(self):
        run, nft = self.guards["run"], self.guards["NFT"]
        run(nft, "flush", "set", "inet", "fixture_ledger_gateway", "permits")
        rows = json.loads(
            run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
        )
        if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
            raise ValueError("joint_ws_revocation_failed")

    def _binding(self):
        anchor = json.loads(self.sequence.bundles[0]["binding"])
        return {
            **anchor,
            "read_sequence": self.sequence.context,
            "clock_anchor_sha256": digest(self.sequence.bundles[0]["binding"].encode()),
        }

    def run_step(self, index):
        sequence = self.sequence
        self.check()
        sequence.write(sequence.storage / "binding.json", canonical(self._binding()))
        path = sequence.storage / "ws.jsonl"
        journal = self.provenance._Journal(path, limit=LIMIT, reserve=4096)
        try:

            def append(kind, payload, clocks=None):
                self.check()
                now, mono = clocks or (time.time_ns(), time.monotonic_ns())
                journal.append(
                    kind, profile=PROFILE, utc_ns=now, monotonic_ns=mono, payload=payload
                )

            if index in {1, 9}:
                if index == 9 and (self.connection is None or self.market_connection is not None):
                    raise ValueError("joint_market_account_connection_required")
                nonce = base64.b64encode(os.urandom(16)).decode()
                role = "account" if index == 1 else "market"
                route = (
                    sequence.modules["joint_route_selection"](
                        sequence.bundles[:9],
                        json.loads(sequence.expected.splitlines()[0])["payload"],
                        sequence.modules,
                    )
                    if index == 9
                    else None
                )
                symbols = {"symbols": route["symbols"]} if route is not None else {}
                request = self.ws["request"](role, symbols, nonce)
                append(
                    "intent",
                    {
                        "endpoint": self.ws["endpoint"](role, symbols)[0],
                        "peer": list(PEER),
                        "nonce": nonce,
                        **(
                            {
                                "route_selection_sha256": digest(canonical(route)),
                                "route_bundles_sha256": digest(canonical(sequence.bundles[:9])),
                            }
                            if route is not None
                            else {"clock_bundle_sha256": digest(canonical(sequence.bundles[0]))}
                        ),
                    },
                )
                print(
                    json.dumps(
                        {
                            "stage": "joint_ws_prepared" if index == 1 else "joint_market_prepared",
                            "index": index,
                        }
                    ),
                    flush=True,
                )
                if sys.stdin.readline() != "continue\n":
                    raise ValueError("fixture_parent_release_required")
            elif index == 2:
                if self.connection is None:
                    raise ValueError("joint_ws_account_connection_required")
                self.session = self.account["Session"](self.entry, self.authority, self.sources)
                signer = self.session.collector
                signer.verify()
                append(
                    "intent",
                    {
                        "connection_bundle_sha256": digest(canonical(sequence.bundles[1])),
                        "signer": signer.selected,
                    },
                )
                challenge = {
                    "index": 2,
                    "nonce": os.urandom(16).hex(),
                    "utc_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                }
                signer.channel.send(canonical(challenge).decode(), 1)
                raw = signer.channel.receive(self.requests["JsonToken"](), 1).encode()
                received = [time.time_ns(), time.monotonic_ns()]
                envelope = self.account["decode"](raw)
                if canonical(envelope) != raw:
                    raise ValueError("joint_ws_signed_request_canonical")
                self.requests["validate_request"](raw, challenge, received=tuple(received))
                wire = sequence.modules["frames"]["client_frame"](
                    self.account["wire_request"](envelope)
                )
                append(
                    "signature_prepared",
                    {
                        "challenge": challenge,
                        "request": envelope,
                        "received": received,
                        **self.provenance.raw_fields(wire),
                    },
                )
            else:
                raise ValueError("joint_ws_step_index")
            append("grant_prepared", {"mark": MARK, "ttl_ms": 5000})
            try:
                self.check()
                self.grant()
                append("activated", {})
                deadline = time.monotonic() + 4

                def bounded():
                    self.check()
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError("joint_ws_total_deadline")
                    (self.market_connection if index == 9 else self.connection).settimeout(left)

                if index in {1, 9}:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.minimum_version = ssl.TLSVersion.TLSv1_2
                    context.load_verify_locations(cadata=self.trust.decode("ascii"))
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)
                        sock.settimeout(4)
                        sock.connect(PEER)
                        connection = context.wrap_socket(
                            sock, server_hostname=role + ".fixture.invalid"
                        )
                        if index == 1:
                            self.connection = connection
                        else:
                            self.market_connection = connection
                    finally:
                        if (self.market_connection if index == 9 else self.connection) is None:
                            sock.close()
                    certificate = connection.getpeercert(binary_form=True)
                    append(
                        "tls_connected",
                        {
                            "peer": list(connection.getpeername()),
                            "server_hostname": role + ".fixture.invalid",
                            "peer_certificate_sha256": digest(certificate),
                            "tls_version": connection.version(),
                            "cipher": list(connection.cipher()),
                            "check_hostname": context.check_hostname,
                            "verify_mode": "CERT_REQUIRED",
                        },
                    )
                    append("request_prepared", self.provenance.raw_fields(request))
                    bounded()
                    connection.sendall(request)
                    response = bytearray()
                    while b"\r\n\r\n" not in response:
                        bounded()
                        chunk = connection.recv(4096)
                        clocks = (time.time_ns(), time.monotonic_ns())
                        if not chunk:
                            raise ValueError("joint_ws_upgrade_eof")
                        append("response_chunk", self.provenance.raw_fields(chunk), clocks)
                        response.extend(chunk)
                    status, pairs = self.provenance.response_headers(bytes(response))
                    self.provenance._validate_response(role, status, pairs, nonce)
                    append("upgrade_accepted", {})
                    if index == 9 and sequence.joint_linked:
                        market_code = sequence.modules["market"]
                        selected_market = market_code["selection"](route, [sequence.bundles[7]])[
                            "market_definitions"
                        ]
                        parser = sequence.modules["frames"]["ServerFrames"]()
                        events = []
                        chunk_bytes = chunk_count = 0
                        while len(events) < 4:
                            bounded()
                            chunk = self.market_connection.recv(4096)
                            clocks = (time.time_ns(), time.monotonic_ns())
                            if not chunk:
                                raise ValueError("joint_market_increment_eof")
                            append("market_chunk", self.provenance.raw_fields(chunk), clocks)
                            chunk_bytes += len(chunk)
                            chunk_count += 1
                            if chunk_bytes > 8192 or chunk_count > 16:
                                raise ValueError("joint_market_increment_limit")
                            for opcode, payload in parser.feed(chunk):
                                if opcode != 1:
                                    raise ValueError("joint_market_text_required")
                                events.append(
                                    {
                                        **self.provenance.raw_fields(payload),
                                        "receipt": dict(
                                            zip(("utc_ns", "monotonic_ns"), clocks, strict=True)
                                        ),
                                    }
                                )
                            if len(events) > 4 or parser.retained_bytes > 8192:
                                raise ValueError("joint_market_increment_limit")
                        if parser.retained_bytes or parser.fragment is not None:
                            raise ValueError("joint_market_incomplete_frame")
                        increments = market_code["increments"](
                            events, selected_market, complete=True
                        )
                        append(
                            "market_accepted",
                            {"event_sha256": [event["original_sha256"] for event in increments]},
                        )
                else:
                    signer.verify()
                    if signer.used:
                        raise ValueError("joint_ws_native_signer_consumed")
                    signer.used = True
                    self.requests["validate_request"](
                        raw, challenge, received=(time.time_ns(), time.monotonic_ns())
                    )
                    append("write_prepared", {})
                    bounded()
                    self.connection.sendall(wire)
                    response = bytearray()
                    while not sequence.modules["frames"]["ServerFrames"]().feed(bytes(response)):
                        bounded()
                        chunk = self.connection.recv(4096)
                        clocks = (time.time_ns(), time.monotonic_ns())
                        if not chunk:
                            raise ValueError("joint_ws_subscription_eof")
                        append("response_chunk", self.provenance.raw_fields(chunk), clocks)
                        response.extend(chunk)
                    messages = sequence.modules["frames"]["ServerFrames"]().feed(bytes(response))
                    if len(messages) != 1 or messages[0][0] != 1:
                        raise ValueError("joint_ws_subscription_frame")
                    self.account["response"](messages[0][1])
                    append("subscription_accepted", {})
            finally:
                self.revoke()
                append("revoked", {})
            append("accepted", {})
            if index == 2:
                self.session.close()
                self.session = None
            return {"status": "fixture_receipt_succeeded", "revoked": True}
        finally:
            os.close(journal.fd)

    def close(self):
        try:
            if self.market_connection is not None:
                self.market_connection.close()
            if self.connection is not None:
                self.connection.close()
        finally:
            if self.session is not None:
                self.session.close()

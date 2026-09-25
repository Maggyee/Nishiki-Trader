"""Fixture signed subscription and partial native account event receipt, never orders.

Root uses stdlib/OpenSSL only. The isolated native child signs the fixed selector
and acknowledges exact AccountBalance mappings after root has revoked egress.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import time
import zlib
from decimal import Decimal

PROFILE = "portfolio.installed_account_ws.v1"
SCOPE = "signed-account-ws-v1"
RECEIPT = "portfolio.native_partial_account_ws.v1"
UNSUB_RECEIPT = "portfolio.native_partial_account_unsubscribe.v1"
MAX_PAYLOAD = 8192
CHUNK = 512


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("account_ws_duplicate_json_key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def response(raw):
    value = decode(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"id", "status", "result"}
        or value["id"] != "fixture-2"
        or type(value["status"]) is not int
        or value["status"] != 200
        or value["result"] != {"subscriptionId": 0}
        or type(value["result"]["subscriptionId"]) is not int
    ):
        raise ValueError("account_ws_subscription_response")
    return value


def unsubscribe_response(raw, *, request_id="fixture-19"):
    value = decode(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"id", "status", "result"}
        or value["id"] != request_id
        or type(value["status"]) is not int
        or value["status"] != 200
        or value["result"] != {}
    ):
        raise ValueError("account_ws_unsubscribe_response")
    return value


def event(raw):
    value = decode(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"subscriptionId", "event"}
        or type(value["subscriptionId"]) is not int
        or value["subscriptionId"] != 0
        or not isinstance(value["event"], dict)
    ):
        raise ValueError("account_ws_event_subscription")
    row = value["event"]
    if (
        set(row) != {"e", "E", "u", "B"}
        or row["e"] != "outboundAccountPosition"
        or any(type(row[k]) is not int or row[k] <= 0 for k in ("E", "u"))
        or row["u"] > row["E"]
        or not isinstance(row["B"], list)
        or not 1 <= len(row["B"]) <= 4
    ):
        raise ValueError("account_ws_partial_event")
    balances, seen = [], set()
    for balance in row["B"]:
        if (
            not isinstance(balance, dict)
            or set(balance) != {"a", "f", "l"}
            or balance["a"] not in ("BNB", "BTC", "ETH", "USDT")
            or balance["a"] in seen
            or any(
                not isinstance(balance[k], str)
                or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", balance[k]) is None
                for k in ("f", "l")
            )
        ):
            raise ValueError("account_ws_partial_balances")
        seen.add(balance["a"])
        free, locked = Decimal(balance["f"]), Decimal(balance["l"])
        if any(n != n.quantize(Decimal("0.00000001")) for n in (free, locked, free + locked)):
            raise ValueError("account_ws_rounding_refused")
        balances.append(
            {
                "currency": balance["a"],
                "precision": 8,
                "free": str(free),
                "locked": str(locked),
                "total": str(free + locked),
            }
        )
    return row, sorted(balances, key=lambda r: r["currency"])


def expected_result(payload, *, unsubscribe=False):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError("account_ws_receipt_size")
    value = decode(payload)
    if (
        canonical(value) != payload
        or set(value)
        != (
            {
                "profile",
                "request_sha256",
                "response_b64",
                "event_b64",
                "response_receipt",
                "event_receipt",
            }
            | (
                {"unsubscribe_request_sha256", "unsubscribe_b64", "unsubscribe_receipt"}
                if unsubscribe
                else set()
            )
        )
        or value["profile"] != (UNSUB_RECEIPT if unsubscribe else RECEIPT)
        or not isinstance(value["request_sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", value["request_sha256"]) is None
    ):
        raise ValueError("account_ws_receipt_schema")
    for key in ("response_receipt", "event_receipt"):
        stamp = value[key]
        if (
            not isinstance(stamp, dict)
            or set(stamp) != {"utc_ns", "monotonic_ns"}
            or any(type(n) is not int or n <= 0 for n in stamp.values())
        ):
            raise ValueError("account_ws_receipt_clock")
    delta = [
        value["event_receipt"][k] - value["response_receipt"][k] for k in ("utc_ns", "monotonic_ns")
    ]
    if any(n < 0 for n in delta) or abs(delta[0] - delta[1]) > 50_000_000:
        raise ValueError("account_ws_receipt_clock_order")
    originals = {}
    for key in ("response_b64", "event_b64"):
        originals[key] = base64.b64decode(value[key], validate=True)
        if base64.b64encode(originals[key]).decode() != value[key]:
            raise ValueError("account_ws_receipt_encoding")
    response(originals["response_b64"])
    row, balances = event(originals["event_b64"])
    if unsubscribe:
        stamp = value["unsubscribe_receipt"]
        if (
            not isinstance(stamp, dict)
            or set(stamp) != {"utc_ns", "monotonic_ns"}
            or any(type(n) is not int or n <= 0 for n in stamp.values())
            or any(stamp[k] < value["event_receipt"][k] for k in stamp)
            or abs(
                (stamp["utc_ns"] - value["event_receipt"]["utc_ns"])
                - (stamp["monotonic_ns"] - value["event_receipt"]["monotonic_ns"])
            )
            > 50_000_000
            or not isinstance(value["unsubscribe_request_sha256"], str)
            or re.fullmatch("[0-9a-f]{64}", value["unsubscribe_request_sha256"]) is None
        ):
            raise ValueError("account_ws_unsubscribe_receipt")
        original = base64.b64decode(value["unsubscribe_b64"], validate=True)
        if base64.b64encode(original).decode() != value["unsubscribe_b64"]:
            raise ValueError("account_ws_unsubscribe_encoding")
        unsubscribe_response(original)
    return {
        "profile": UNSUB_RECEIPT if unsubscribe else RECEIPT,
        "native_version": "1.226.0",
        "subscription_id": 0,
        "request_sha256": value["request_sha256"],
        "payload_sha256": digest(payload),
        "event_time_ms": row["E"],
        "last_account_update_ms": row["u"],
        "event_receipt": value["event_receipt"],
        **(
            {
                "unsubscribe_request_sha256": value["unsubscribe_request_sha256"],
                "unsubscribe_receipt": value["unsubscribe_receipt"],
                "unsubscribe_acknowledged": True,
            }
            if unsubscribe
            else {}
        ),
        "balances": balances,
        "partial_update": True,
        "omitted_assets_unchanged_or_unknown": True,
        "account_uid": None,
        "full_account_snapshot": False,
        "stream_fence_verified": False,
        "qualified_for_execution": False,
    }


def validate_native(payload, *, unsubscribe=False):
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core.nautilus_pyo3 import (
        NAUTILUS_VERSION,
        AccountBalance,
        Currency,
        CurrencyType,
        Money,
    )

    if NAUTILUS_VERSION != "1.226.0":
        raise ValueError("native_version_changed")
    result = expected_result(payload, unsubscribe=unsubscribe)
    for row in result["balances"]:
        currency = Currency(row["currency"], 8, 0, row["currency"], CurrencyType.CRYPTO)
        amounts = {k: Money(Decimal(row[k]), currency) for k in ("total", "locked", "free")}
        balance = AccountBalance(amounts["total"], amounts["locked"], amounts["free"]).to_dict()
        if balance["currency"] != row["currency"] or any(
            amounts[k].as_decimal() != Decimal(row[k]) or Decimal(balance[k]) != Decimal(row[k])
            for k in amounts
        ):
            raise ValueError("account_ws_native_mapping_changed")
    return result


def signing_window(challenge, now, mono):
    delta = [now - challenge["utc_ns"], mono - challenge["monotonic_ns"]]
    if any(not 0 <= n < 5_000_000_000 for n in delta) or abs(delta[0] - delta[1]) > 50_000_000:
        raise ValueError("account_ws_expired_before_wire")


def wire_request(envelope):
    return canonical({k: v for k, v in envelope["request"].items() if k != "kind"})


def unmask(raw):
    if (
        not isinstance(raw, bytes)
        or not 6 <= len(raw) <= 1024
        or raw[0] != 0x81
        or not raw[1] & 0x80
    ):
        raise ValueError("account_ws_masked_text")
    size, offset = raw[1] & 127, 2
    if size == 127:
        raise ValueError("account_ws_text_size")
    if size == 126:
        size, offset = int.from_bytes(raw[2:4], "big"), 4
        if size < 126:
            raise ValueError("account_ws_noncanonical_length")
    if size >= 1024 or len(raw) != offset + 4 + size:
        raise ValueError("account_ws_text_size")
    mask = raw[offset : offset + 4]
    return bytes(v ^ mask[i % 4] for i, v in enumerate(raw[offset + 4 :]))


def selection(selected, bundles):
    binding = json.loads(bundles[-1]["binding"])
    process = binding["collector"]["process"]
    constraints = {
        k: v for k, v in process.items() if k not in {"pid", "start_ticks", "namespaces"}
    }
    constraints["namespaces"] = {k: v for k, v in process["namespaces"].items() if k != "net"}
    return {
        **selected,
        "native_signer_constraints": constraints,
        "root_network_namespace": binding["net"],
    }


def state_type(base, requests, *, unsubscribe=False):
    class AccountState(base["State"]):
        PROFILE = PROFILE

        def __init__(self, *args):
            super().__init__(*args)
            self.signer = self.subscription = self.accepted = self.update = None
            self.receipt_started = self.acknowledged = None
            self.subscription_clock = None
            self.unsubscribe_request = self.unsubscribe_ack = None

        def all_events(self, role):
            return super().events(role)

        def events(self, role):
            values = self.all_events(role)
            if role == "market":
                if any(op == 1 for op, _ in values):
                    raise ValueError("account_ws_market_control_only")
                return values
            return [(op, data) for op, data in values if op != 1]

        def message(self, index, role="account"):
            wire = self.wires[role]
            parser = self.frames["ServerFrames"]()
            offset, seen = self.headers(role), []
            for stamp in wire["receipts"]:
                end = stamp["end"]
                if end <= offset:
                    continue
                for opcode, raw in parser.feed(wire["raw"][offset:end]):
                    seen.append((opcode, raw, {k: stamp[k] for k in ("utc_ns", "monotonic_ns")}))
                if len(seen) > index:
                    return seen[index]
                offset = end
            raise ValueError("account_ws_original_message_missing")

        def payload(self):
            if self.subscription is None or self.accepted is None or self.update is None:
                raise ValueError("account_ws_originals_required")
            return canonical(
                {
                    "profile": UNSUB_RECEIPT if unsubscribe else RECEIPT,
                    "request_sha256": digest(canonical(self.subscription["request"])),
                    "response_b64": self.accepted["raw_b64"],
                    "event_b64": self.update["raw_b64"],
                    "response_receipt": self.accepted["receipt"],
                    "event_receipt": self.update["receipt"],
                    **(
                        {
                            "unsubscribe_request_sha256": digest(
                                canonical(self.unsubscribe_request["request"])
                            ),
                            "unsubscribe_b64": self.unsubscribe_ack["raw_b64"],
                            "unsubscribe_receipt": self.unsubscribe_ack["receipt"],
                        }
                        if unsubscribe
                        and self.unsubscribe_request is not None
                        and self.unsubscribe_ack is not None
                        else {}
                    ),
                }
            )

        def native_result(self):
            return expected_result(self.payload(), unsubscribe=unsubscribe)

        def feed(self, kind, payload, now, mono):
            custom = {
                "signer_prepared",
                "subscription_prepared",
                "subscription_accepted",
                "account_event",
                *(("unsubscribe_prepared", "unsubscribe_accepted") if unsubscribe else ()),
                "native_receipt_prepared",
                "native_acknowledged",
            }
            if kind not in custom:
                if kind == "grant_prepared" and self.signer is None:
                    raise ValueError("account_ws_signer_required")
                if kind == "close_prepared" and (
                    self.update is None or (unsubscribe and self.unsubscribe_ack is None)
                ):
                    raise ValueError("account_ws_event_before_close")
                if kind == "completed" and self.acknowledged is None:
                    raise ValueError("account_ws_native_ack_required")
                super().feed(kind, payload, now, mono)
                if (
                    kind == "peer_control"
                    and payload["opcode"] == 8
                    and payload["role"] == "account"
                ):
                    values = self.all_events("account")
                    if [op for op, _ in values] != (
                        [9, 1, 1, 1, 8] if unsubscribe else [9, 1, 1, 8]
                    ):
                        raise ValueError("account_ws_exact_message_sequence")
                return
            self.clock(payload, now, mono)
            if kind == "signer_prepared":
                if (
                    self.stage != "preparing"
                    or self.signer is not None
                    or set(payload) != {"process", "launcher_source_sha256"}
                    or not isinstance(payload.get("process"), dict)
                    or not isinstance(payload.get("launcher_source_sha256"), str)
                    or re.fullmatch("[0-9a-f]{64}", payload["launcher_source_sha256"]) is None
                ):
                    raise ValueError("account_ws_signer_identity")
                process = payload["process"]
                constraints = self.selected["native_signer_constraints"]
                if (
                    set(process) != set(constraints) | {"pid", "start_ticks"}
                    or any(
                        type(process[k]) is not int or process[k] <= 0
                        for k in ("pid", "start_ticks")
                    )
                    or any(process[k] != v for k, v in constraints.items() if k != "namespaces")
                    or not isinstance(process["namespaces"], dict)
                    or set(process["namespaces"]) != set(constraints["namespaces"]) | {"net"}
                    or any(
                        process["namespaces"][k] != v for k, v in constraints["namespaces"].items()
                    )
                    or process["namespaces"]["net"] == self.selected["root_network_namespace"]
                ):
                    raise ValueError("account_ws_original_native_identity")
                self.signer = payload
                return
            if kind in {"native_receipt_prepared", "native_acknowledged"}:
                if (
                    self.stage != "revoked"
                    or not self.closed
                    or not self.revoked
                    or any(w["stage"] != "peer_closed" for w in self.wires.values())
                ):
                    raise ValueError("account_ws_revoke_before_delivery")
                result = self.native_result()
                expected = {"payload_sha256": digest(self.payload()), "native_result": result}
                if payload != expected:
                    raise ValueError("account_ws_native_receipt_binding")
                if kind == "native_receipt_prepared":
                    if self.receipt_started is not None:
                        raise ValueError("account_ws_transfer_consumed")
                    self.receipt_started = (now, mono)
                else:
                    if (
                        self.receipt_started is None
                        or self.acknowledged is not None
                        or any(
                            not 0 <= n - start < 5_000_000_000
                            for n, start in zip((now, mono), self.receipt_started, strict=True)
                        )
                    ):
                        raise ValueError("account_ws_transfer_deadline")
                    self.acknowledged = result
                return
            if (
                self.stage != "active"
                or mono - self.grant_clock > base["WINDOW_NS"]
                or any(w["stage"] != "pong" for w in self.wires.values())
            ):
                raise ValueError("account_ws_both_live_required")
            if kind == "subscription_prepared":
                if self.subscription is not None or set(payload) != {
                    "challenge",
                    "request",
                    "received",
                    "raw_b64",
                    "raw_sha256",
                }:
                    raise ValueError("account_ws_subscription_consumed")
                challenge = payload["challenge"]
                requests["validate_challenge"](challenge, 2)
                if (
                    not isinstance(payload["received"], list)
                    or len(payload["received"]) != 2
                    or any(type(n) is not int for n in payload["received"])
                ):
                    raise ValueError("account_ws_signing_receipt")
                requests["validate_request"](
                    canonical(payload["request"]), challenge, received=tuple(payload["received"])
                )
                signing_window(challenge, now, mono)
                if any(
                    not start <= end
                    for start, end in zip(payload["received"], (now, mono), strict=True)
                ) or any(
                    challenge[k] < self.start[i] for i, k in enumerate(("utc_ns", "monotonic_ns"))
                ):
                    raise ValueError("account_ws_signing_clock_order")
                if unmask(base["original"](payload)) != wire_request(payload["request"]):
                    raise ValueError("account_ws_selected_wire")
                self.subscription = payload
                self.subscription_clock = (now, mono)
                return
            if kind == "unsubscribe_prepared":
                if (
                    self.update is None
                    or self.unsubscribe_request is not None
                    or set(payload) != {"challenge", "request", "received", "raw_b64", "raw_sha256"}
                ):
                    raise ValueError("account_ws_unsubscribe_order")
                challenge = payload["challenge"]
                requests["validate_challenge"](challenge, 19)
                if (
                    not isinstance(payload["received"], list)
                    or len(payload["received"]) != 2
                    or any(type(n) is not int for n in payload["received"])
                ):
                    raise ValueError("account_ws_unsubscribe_received")
                requests["validate_request"](
                    canonical(payload["request"]), challenge, received=tuple(payload["received"])
                )
                signing_window(challenge, now, mono)
                if (
                    any(payload["received"][i] > clock for i, clock in enumerate((now, mono)))
                    or any(
                        clock < self.update["receipt"][k]
                        for k, clock in zip(("utc_ns", "monotonic_ns"), (now, mono), strict=True)
                    )
                    or unmask(base["original"](payload)) != wire_request(payload["request"])
                ):
                    raise ValueError("account_ws_unsubscribe_wire")
                self.unsubscribe_request = payload
                return
            index = 1 if kind == "subscription_accepted" else 2 if kind == "account_event" else 3
            if self.subscription is None or (
                self.accepted is not None
                if index == 1
                else self.accepted is None or self.update is not None
                if index == 2
                else self.unsubscribe_request is None or self.unsubscribe_ack is not None
            ):
                raise ValueError("account_ws_message_order")
            opcode, raw, stamp = self.message(index)
            if (
                opcode != 1
                or payload != {**self.provenance.raw_fields(raw), "receipt": stamp}
                or any(
                    stamp[k] < self.subscription_clock[i]
                    for i, k in enumerate(("utc_ns", "monotonic_ns"))
                )
            ):
                raise ValueError("account_ws_message_original")
            if index == 1:
                response(raw)
                self.accepted = payload
            elif index == 2:
                event(raw)
                self.update = payload
            else:
                unsubscribe_response(raw)
                if any(
                    stamp[k] < self.unsubscribe_request["received"][i]
                    for i, k in enumerate(("utc_ns", "monotonic_ns"))
                ):
                    raise ValueError("account_ws_unsubscribe_clock_order")
                self.unsubscribe_ack = payload

        def report(self):
            return {
                **super().report(),
                "fixture_subscription_acknowledged": self.accepted is not None,
                "native_events_delivered": self.acknowledged is not None,
                "native_result": self.acknowledged,
                "documented_subscription_weight": 2 if self.subscription else 0,
                **(
                    {
                        "documented_unsubscribe_weight": 2 if self.unsubscribe_request else 0,
                        "fixture_unsubscribe_acknowledged": self.unsubscribe_ack is not None,
                    }
                    if unsubscribe
                    else {}
                ),
                "real_account_authenticated": False,
            }

    return AccountState


def child_loop(fd, parent):
    globals()["ACCOUNT"]["prepare_native"]()
    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=5)
    requests = globals()["REQUESTS"]
    try:
        channel.send("ready", 0)
        raw = channel.receive(requests["JsonToken"](), 1).encode()
        challenge = json.loads(raw)
        requests["validate_challenge"](challenge, 2)
        if canonical(challenge) != raw:
            raise ValueError("account_ws_canonical_challenge")
        channel.send(requests["native_request"](challenge).decode(), 1)
        unsubscribe = globals().get("UNSUBSCRIBE", False)
        if unsubscribe:
            raw = channel.receive(requests["JsonToken"](), 2).encode()
            challenge = json.loads(raw)
            requests["validate_challenge"](challenge, 19)
            if canonical(challenge) != raw:
                raise ValueError("account_ws_unsubscribe_canonical_challenge")
            channel.send(requests["native_request"](challenge).decode(), 2)
        # Wait for root to close sockets and revoke before starting the transfer clock.
        transfer = 3 if unsubscribe else 2
        channel.receive({"deliver"}, transfer)
        channel.send("ready", transfer)
        deadline, payload = time.monotonic() + 5, bytearray()

        def bounded():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("account_ws_transfer_deadline")
            channel.connection.settimeout(remaining)

        for seq in range(transfer + 1, transfer + 1 + MAX_PAYLOAD // CHUNK + 1):
            bounded()

            class Allowed:
                def __contains__(self, token):
                    return token == "end:" + digest(payload) or token in globals()["DataToken"]()

            token = channel.receive(Allowed(), seq)
            if token.startswith("end:"):
                result = validate_native(bytes(payload))
                bounded()
                channel.send("native:" + digest(canonical(result)) + ":" + digest(payload), seq)
                bounded()
                break
            payload.extend(base64.b64decode(token[5:], validate=True))
            if len(payload) > MAX_PAYLOAD:
                raise ValueError("account_ws_receipt_size")
            bounded()
            channel.send("part", seq)
        else:
            raise ValueError("account_ws_packet_limit")
        channel.receive({"close"}, 1000)
        channel.send("closed", 1000)
    finally:
        channel.close()


def joint_unsubscribe_child_loop(fd, parent):
    if os.geteuid() == 0:
        raise ValueError("joint_unsubscribe_native_root_refused")
    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=5)
    requests = globals()["REQUESTS"]
    try:
        channel.send("ready", 0)
        raw = channel.receive(requests["JsonToken"](), 1).encode()
        challenge = decode(raw)
        requests["validate_challenge"](challenge, 18)
        if canonical(challenge) != raw:
            raise ValueError("joint_unsubscribe_canonical_challenge")
        channel.send(requests["native_request"](challenge).decode(), 1)
        channel.receive({"close"}, 2)
        channel.send("closed", 2)
    finally:
        channel.close()


class Session:
    result = staticmethod(expected_result)

    def __init__(
        self,
        entry,
        authority,
        sources,
        *,
        market=False,
        snapshot=False,
        quotes=False,
        unsubscribe=False,
        joint_route=None,
    ):
        if unsubscribe and not quotes:
            raise ValueError("unsubscribe_requires_quote_scope")
        if joint_route is not None and any((market, snapshot, quotes, unsubscribe)):
            raise ValueError("joint_unsubscribe_scope_conflict")
        self.unsubscribe = unsubscribe
        self.runtime = self.collector = None
        try:
            self.requests = entry["load"](sources.source("gateway_native_requests.py"))
            if joint_route is not None:
                joint = entry["load"](sources.source("gateway_joint_native_requests.py"))
                self.requests = joint["view"](
                    self.requests, joint_route["symbols"], joint_route["route_sha256"]
                )
            self.receipts = entry["load"](sources.source("gateway_tls_receipt.py"))
            launcher = entry["load"](authority.source("collector_launcher.py"))
            self.runtime = entry["load"](sources.source("gateway_native_runtime.py"))[
                "NativeRuntime"
            ](authority)
            reader = entry["load"](authority.source("inspect_binding.py"))["process_identity"]

            def identity(pid):
                authority.verify()
                self.runtime.verify()
                return {
                    **reader(pid),
                    "installation_manifest_sha256": authority.manifest_sha256,
                    "native_runtime_sha256": self.runtime.pin,
                }

            source = ""
            for name, raw in (
                ("REQUESTS", sources.source("gateway_native_requests.py")),
                ("ACCOUNT", sources.source("gateway_native_account.py")),
            ):
                encoded = base64.b64encode(zlib.compress(raw, 9))
                source += f"{name}={{'__name__':{name!r}}}\nexec(compile(__import__('zlib').decompress(__import__('base64').b64decode({encoded!r})),'<held-source>','exec'),{name})\n"
            for raw in (
                authority.source("collector_launcher.py"),
                sources.source("gateway_tls_receipt.py"),
                sources.source("gateway_account_ws.py"),
            ):
                encoded = base64.b64encode(zlib.compress(raw, 9))
                source += f"exec(compile(__import__('zlib').decompress(__import__('base64').b64decode({encoded!r})),'<held-source>','exec'))\n"
            if joint_route is not None:
                raw = sources.source("gateway_joint_native_requests.py")
                encoded = base64.b64encode(zlib.compress(raw, 9))
                source += f"JOINT={{'__name__':'held_joint_requests'}}\nexec(compile(__import__('zlib').decompress(__import__('base64').b64decode({encoded!r})),'<held-joint-requests>','exec'),JOINT)\n"
                source += f"REQUESTS=JOINT['view'](REQUESTS,{joint_route['symbols']!r},{joint_route['route_sha256']!r})\nchild_loop=joint_unsubscribe_child_loop\n"
            if unsubscribe:
                source += "UNSUBSCRIBE=True\naccount_validate_native=validate_native\nvalidate_native=lambda payload:account_validate_native(payload,unsubscribe=True)\n"
                self.result = lambda payload: expected_result(payload, unsubscribe=True)
            if market:
                raw = sources.source("gateway_market_ws.py")
                if snapshot:
                    encoded = base64.b64encode(zlib.compress(raw, 9))
                    market_source = f"__import__('zlib').decompress(base64.b64decode({encoded!r}))"
                else:
                    market_source = repr(raw)
                source += f"market_scope={{'__name__':'held_market_ws'}}\nexec(compile({market_source},'<held-market>','exec'),market_scope)\naccount_native=validate_native\nvalidate_native=lambda payload:market_scope['validate_native'](payload,account_native)\n"
                market_code = entry["load"](raw)
                account_result = self.result
                self.result = lambda payload: market_code["expected_result"](
                    payload, account_result
                )
            if snapshot:
                if not market:
                    raise ValueError("snapshot_requires_market")
                raw = sources.source("gateway_snapshot_ws.py")
                encoded = base64.b64encode(zlib.compress(raw, 9))
                source += f"snapshot_scope={{'__name__':'held_snapshot_ws'}}\nexec(compile(__import__('zlib').decompress(base64.b64decode({encoded!r})),'<held-snapshot>','exec'),snapshot_scope)\nmarket_native=validate_native\nvalidate_native=lambda payload:snapshot_scope['validate_native'](payload,market_native,market_scope)\n"
                snapshot_code = entry["load"](raw)
                market_result = self.result
                self.result = lambda payload: snapshot_code["expected_result"](
                    payload, market_result, market_code
                )
            if quotes:
                if not snapshot:
                    raise ValueError("quote_requires_snapshot")
                raw = sources.source("gateway_native_quote.py")
                encoded = base64.b64encode(zlib.compress(raw, 9))
                source += f"quote_scope={{'__name__':'held_native_quote'}}\nexec(compile(__import__('zlib').decompress(base64.b64decode({encoded!r})),'<held-quote>','exec'),quote_scope)\nvalidate_native=lambda payload:quote_scope['validate_native'](payload,lambda data:snapshot_scope['validate_native'](data,market_native,market_scope,quotes=True),market_scope,snapshot_scope)\n"
                quote_code = entry["load"](raw)
                self.result = lambda payload: quote_code["expected_result"](
                    payload,
                    lambda data: snapshot_code["expected_result"](
                        data, market_result, market_code, quotes=True
                    ),
                    market_code,
                    snapshot_code,
                )
            launcher["FixtureCollector"].__init__.__globals__["PYTHON"] = (
                "/run/trader-native-runtime/bin/python3.12"
            )
            self.collector = launcher["FixtureCollector"](
                source,
                identity,
                collector_uid=authority.account["uid"],
                collector_gid=authority.account["gid"],
            )
        except BaseException:
            self.close()
            raise

    def before_wire(self, deadline):
        self.collector.verify()
        self.requests["validate_request"](
            canonical(self.subscription["request"]),
            self.subscription["challenge"],
            received=(time.time_ns(), time.monotonic_ns()),
        )
        signing_window(self.subscription["challenge"], time.time_ns(), time.monotonic_ns())
        if time.monotonic() >= deadline:
            raise TimeoutError("account_ws_total_deadline")

    async def exchange(self, journal, writer, chunk, before_wire, deadline, snapshots_done=None):
        collector = self.collector
        collector.verify()
        if collector.used:
            raise ValueError("account_ws_subscription_consumed")
        collector.used = True
        challenge = {
            "index": 2,
            "nonce": os.urandom(16).hex(),
            "utc_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
        }

        def bounded():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("account_ws_total_deadline")
            collector.channel.connection.settimeout(remaining)

        bounded()
        collector.channel.send(canonical(challenge).decode(), 1)
        bounded()
        raw = collector.channel.receive(self.requests["JsonToken"](), 1).encode()
        received = [time.time_ns(), time.monotonic_ns()]
        request = decode(raw)
        if canonical(request) != raw:
            raise ValueError("account_ws_canonical_request")
        wire = journal.state.frames["client_frame"](wire_request(request))
        self.subscription = {
            "challenge": challenge,
            "request": request,
            "received": received,
            **journal.state.provenance.raw_fields(wire),
        }
        journal.append("subscription_prepared", self.subscription)
        before_wire()
        self.before_wire(deadline)
        writer.write(wire)
        await writer.drain()
        for index, kind in ((1, "subscription_accepted"), (2, "account_event")):
            while len(journal.state.all_events("account")) <= index:
                await chunk()
            _, raw, stamp = journal.state.message(index)
            journal.append(kind, {**journal.state.provenance.raw_fields(raw), "receipt": stamp})
        if self.unsubscribe:
            await snapshots_done.wait()
            challenge = {
                "index": 19,
                "nonce": os.urandom(16).hex(),
                "utc_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
            }
            bounded()
            collector.channel.send(canonical(challenge).decode(), 2)
            bounded()
            raw = collector.channel.receive(self.requests["JsonToken"](), 2).encode()
            received = [time.time_ns(), time.monotonic_ns()]
            request = decode(raw)
            if canonical(request) != raw:
                raise ValueError("account_ws_unsubscribe_canonical_request")
            wire = journal.state.frames["client_frame"](wire_request(request))
            journal.append(
                "unsubscribe_prepared",
                {
                    "challenge": challenge,
                    "request": request,
                    "received": received,
                    **journal.state.provenance.raw_fields(wire),
                },
            )
            before_wire()
            self.requests["validate_request"](raw, challenge, received=tuple(received))
            signing_window(challenge, time.time_ns(), time.monotonic_ns())
            writer.write(wire)
            await writer.drain()
            while len(journal.state.all_events("account")) <= 3:
                await chunk()
            _, original, stamp = journal.state.message(3)
            journal.append(
                "unsubscribe_accepted",
                {
                    **journal.state.provenance.raw_fields(original),
                    "receipt": stamp,
                },
            )

    async def exchange_market(self, journal, chunk):
        return

    def deliver(self, journal, notify):
        payload = journal.state.payload()
        result = self.result(payload)
        fields = {"payload_sha256": digest(payload), "native_result": result}
        journal.append("native_receipt_prepared", fields)
        deadline = journal.state.receipt_started[1] / 1e9 + 5
        notify("ws_native_receipt_prepared")

        def bounded():
            self.collector.verify()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("account_ws_transfer_deadline")
            self.collector.channel.connection.settimeout(remaining)

        channel = self.collector.channel
        bounded()
        transfer = 3 if self.unsubscribe else 2
        channel.send("deliver", transfer)
        bounded()
        channel.receive({"ready"}, transfer)
        for seq, start in enumerate(range(0, len(payload), CHUNK), transfer + 1):
            bounded()
            channel.send("data:" + base64.b64encode(payload[start : start + CHUNK]).decode(), seq)
            bounded()
            channel.receive({"part"}, seq)
        bounded()
        channel.send("end:" + digest(payload), seq + 1)
        bounded()
        channel.receive({"native:" + digest(canonical(result)) + ":" + digest(payload)}, seq + 1)
        bounded()
        journal.append("native_acknowledged", fields)

    def close(self):
        try:
            if self.collector is not None:
                self.collector.cleanup()
        finally:
            if self.runtime is not None:
                self.runtime.close()

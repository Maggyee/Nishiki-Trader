"""TLS byte-to-message bindings for a distinct, loopback-only joint profile."""

from __future__ import annotations

import base64
import re
from collections import deque
from urllib.parse import urlsplit

from apps.strategies_nautilus.portfolio_joint_observation import digest
from apps.strategies_nautilus.portfolio_joint_routes import RoutedJointEvidence
from apps.strategies_nautilus.portfolio_market_depth import DepthError
from apps.strategies_nautilus.portfolio_tls_provenance import (
    MAX_HEADER,
    _one,
    _validate_response,
    response_headers,
)
from apps.strategies_nautilus.portfolio_ws_frames import ServerFrames

PROFILE = "portfolio.loopback_tls_joint_observation.v1"


def original(row):
    raw = base64.b64decode(row["raw_b64"], validate=True)
    if digest(raw) != row["body_sha256"]:
        raise DepthError("joint_tls_original_bytes_changed")
    return raw


class Wire:
    def __init__(self, row):
        self.opened = row
        self.buffer = bytearray()
        self.headers = None
        self.header_size = 0
        self.header_receipt_ns = None
        self.body_length = None
        self.frames = ServerFrames() if row["role"] != "http" else None
        self.events = deque()
        self.closed = self.close_prepared = False
        self.http_consumed = False
        self.pong_pending = deque()
        self.chunks = 0
        self.message_count = 0

    @property
    def retained_bytes(self):
        return (
            len(self.buffer)
            + self.header_size
            + (self.frames.retained_bytes if self.frames else 0)
            + sum(len(e[1]) for e in self.events)
            + sum(map(len, self.pong_pending))
        )

    def feed(self, row):
        raw = original(row)
        if not 0 < len(raw) <= 4096 or self.closed:
            raise DepthError("joint_tls_chunk_bound_or_closed")
        self.chunks += 1
        if self.headers is None:
            self.buffer.extend(raw)
            if b"\r\n\r\n" not in self.buffer:
                if len(self.buffer) >= MAX_HEADER:
                    raise DepthError("joint_tls_header_limit")
                return
            size = self.buffer.index(b"\r\n\r\n") + 4
            headers = bytes(self.buffer[:size])
            raw = bytes(self.buffer[size:])
            self.buffer.clear()
            status, pairs = response_headers(headers)
            role = "rest" if self.frames is None else self.opened["role"]
            self.body_length = _validate_response(
                role, status, pairs, self.opened["websocket_nonce"]
            )
            self.header_size = size
            self.header_receipt_ns = row["received_ns"]
            self.headers = {"status": status, "pairs": pairs, "sha256": digest(headers)}
        if self.frames is None:
            self.buffer.extend(raw)
            if len(self.buffer) > self.body_length:
                raise DepthError("joint_tls_http_body_exceeded")
        else:
            for opcode, payload in self.frames.feed(raw):
                self.events.append(
                    (opcode, payload, row["seq"], row["received_ns"], row["monotonic_ns"])
                )
                self.message_count += opcode == 1


class TLSJointEvidence(RoutedJointEvidence):
    profile = PROFILE

    def __init__(self):
        super().__init__()
        self.wires = {}
        self.role_connections = {}
        self.original_usage_receipt = None

    @property
    def retained_bytes(self):
        return super().retained_bytes + sum(w.retained_bytes for w in self.wires.values())

    @property
    def retained_events(self):
        return super().retained_events + sum(
            len(w.events)
            + len(w.pong_pending)
            + int(w.frames is not None and w.frames.fragment is not None)
            for w in self.wires.values()
        )

    def validate_manifest(self, manifest):
        super().validate_manifest(manifest)
        if manifest["tls_profile"] != PROFILE or not re.fullmatch(
            "[0-9a-f]{64}", manifest["tls_trust_sha256"]
        ):
            raise DepthError("joint_tls_manifest_required")
        expected = {}
        for role, scheme in (("http", "https"), ("account", "wss"), ("market", "wss")):
            port = urlsplit(manifest["wire_endpoints"][role]).port
            expected[role] = f"{scheme}://{role}.fixture.invalid:{port}"
        if manifest["tls_endpoints"] != expected:
            raise DepthError("joint_tls_fixture_endpoints_required")

    def _event(self, role, opcode, payload, row, processed_ns, processed_mono):
        wire = self.wires[self.role_connections[role]]
        if not wire.events:
            raise DepthError("joint_tls_original_frame_required")
        event = wire.events[0]
        if (
            event[:2] != (opcode, payload)
            or not event[2] < row["seq"]
            or not 0 <= processed_ns - event[3] <= 5_000_000_000
            or not 0 <= processed_mono - event[4] <= 5_000_000_000
        ):
            raise DepthError("joint_tls_frame_binding_or_age")
        if (
            role == "account"
            and opcode == 1
            and self.prepared is not None
            and event[2] < self.prepared["seq"]
        ):
            raise DepthError("joint_tls_reply_before_preparation")
        wire.events.popleft()
        return wire

    def _feed(self, row, processed_ns, processed_mono):
        self.dispatch_time = processed_ns, processed_mono
        kind = row["kind"]
        if kind == "account_wire":
            wire = self.wires[self.role_connections["account"]]
            if wire.events:
                self.original_usage_receipt = wire.events[0][3]
        if kind in {"market_frame", "account_wire"}:
            self._event(
                "market" if kind == "market_frame" else "account",
                1,
                original(row),
                row,
                processed_ns,
                processed_mono,
            )
        elif kind in {"account_pong", "market_pong"}:
            raw = base64.b64decode(row["payload_b64"], validate=True)
            wire = self._event(kind.split("_")[0], 9, raw, row, processed_ns, processed_mono)
            wire.pong_pending.append(raw)
        elif kind == "rest_response":
            wire = self.wires[row["operation_id"]]
            if (
                wire.opened["role"] != "http"
                or not wire.closed
                or wire.http_consumed
                or wire.headers is None
                or len(wire.buffer) != wire.body_length
                or bytes(wire.buffer) != original(row)
                or row["status"] != wire.headers["status"]
                or str(row["used_weight_1m"]) != _one(wire.headers["pairs"], "x-mbx-used-weight-1m")
            ):
                raise DepthError("joint_tls_http_original_response_required")
            self.original_usage_receipt = wire.header_receipt_ns
            wire.http_consumed = True
            wire.buffer.clear()
        elif kind in {"market_connected", "ws_operation"} and (
            kind == "market_connected" or row["operation"] == "ws_api_connection"
        ):
            role = "market" if kind == "market_connected" else "account"
            wire = self.wires[self.role_connections[role]]
            if wire.headers is None or wire.headers["status"] != 101 or wire.closed:
                raise DepthError("joint_tls_upgrade_required")
        elif kind == "closed":
            wire = self.wires[self.role_connections[row["transport"]]]
            if not wire.closed or not wire.frames.closed or not wire.close_prepared:
                raise DepthError("joint_tls_close_handshake_required")
        elif kind == "completed" and (
            len(self.wires) != self.request_index + 2
            or any(
                not w.closed
                or w.events
                or w.pong_pending
                or (w.frames is None and not w.http_consumed)
                for w in self.wires.values()
            )
        ):
            raise DepthError("joint_tls_unfinished_transport")
        super()._feed(row, processed_ns, processed_mono)

    def extra_receipt(self, row):
        kind = row["kind"]
        if not kind.startswith("tls_"):
            return super().extra_receipt(row)
        connection = row["connection_id"]
        if type(connection) is not int or connection < 0:
            raise DepthError("joint_tls_connection_identity_required")
        if kind == "tls_opened":
            prepared = self.prepared
            role = row["role"]
            if (
                prepared is None
                or connection != prepared["operation_id"]
                or connection in self.wires
                or role not in self.manifest["tls_endpoints"]
            ):
                raise DepthError("joint_tls_connection_preparation_required")
            op = prepared["operation"]
            expected_role = (
                "http"
                if op["kind"] == "rest"
                else "account"
                if op.get("operation") == "ws_api_connection"
                else "market"
                if op["kind"] == "market_connection"
                else None
            )
            endpoint = self.manifest["tls_endpoints"][role]
            parsed = urlsplit(endpoint)
            target = (
                op["path"]
                if role == "http"
                else "/ws-api/v3"
                if role == "account"
                else "/stream?streams="
                + "/".join(s.lower() + "@depth@100ms" for s in self.manifest["symbols"])
            )
            if (
                role != expected_role
                or row["endpoint"] != endpoint
                or row["target"] != target
                or row["peer"] != ["127.0.0.1", parsed.port]
                or row["server_hostname"] != parsed.hostname
                or row["trust_sha256"] != self.manifest["tls_trust_sha256"]
                or row["check_hostname"] is not True
                or row["verify_mode"] != "CERT_REQUIRED"
                or row["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
                or not re.fullmatch("[0-9a-f]{64}", row["peer_certificate_sha256"])
                or (role != "http" and role in self.role_connections)
            ):
                raise DepthError("joint_tls_source_binding_changed")
            if role != "http":
                nonce = base64.b64decode(row["websocket_nonce"], validate=True)
                if len(nonce) != 16:
                    raise DepthError("joint_tls_nonce_required")
                self.role_connections[role] = connection
            self.wires[connection] = Wire(row)
            return
        wire = self.wires[connection]
        if kind == "tls_chunk":
            wire.feed(row)
        elif kind == "tls_pong_prepared":
            raw = original(row)
            if not wire.pong_pending or wire.pong_pending.popleft() != raw:
                raise DepthError("joint_tls_pong_without_original_ping")
        elif kind == "tls_close_prepared":
            if (
                wire.frames is None
                or wire.close_prepared
                or wire.closed
                or wire.events
                or wire.pong_pending
            ):
                raise DepthError("joint_tls_close_without_drained_stream")
            wire.close_prepared = True
        elif kind == "tls_peer_control":
            opcode = row["opcode"]
            if opcode not in {8, 10} or (opcode == 8 and not wire.close_prepared):
                raise DepthError("joint_tls_unsolicited_close")
            self._event(
                wire.opened["role"],
                opcode,
                original(row),
                row,
                *self.dispatch_time,
            )
        elif kind == "tls_closed":
            if (
                wire.closed
                or wire.headers is None
                or (
                    wire.frames is not None
                    and (
                        not wire.frames.closed
                        or not wire.close_prepared
                        or wire.events
                        or wire.frames.retained_bytes
                    )
                )
            ):
                raise DepthError("joint_tls_unclean_transport_close")
            wire.closed = True
        else:
            raise DepthError("joint_tls_unknown_receipt")

    def observe_usage(self, value, now):
        if self.original_usage_receipt is None:
            raise DepthError("joint_tls_original_usage_receipt_required")
        super().observe_usage(value, self.original_usage_receipt)

    def summary(self):
        return {
            **super().summary(),
            "tls_source_profile": PROFILE,
            "tls_connections": [
                {
                    "connection_id": key,
                    "role": w.opened["role"],
                    "peer_certificate_sha256": w.opened["peer_certificate_sha256"],
                    "endpoint": w.opened["endpoint"],
                    "headers": w.headers,
                    "chunks": w.chunks,
                    "text_messages": w.message_count,
                    "closed": w.closed,
                }
                for key, w in sorted(self.wires.items())
            ],
            "tls_original_bytes_replayed": True,
            "actual_exchange_source_verified": False,
        }

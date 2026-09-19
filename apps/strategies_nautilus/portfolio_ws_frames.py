"""Bounded JSON WebSocket framing shared by local TLS capture and replay.

RFC 6455 text/continuation/control subset; no binary data or extensions. Server
frames must be unmasked, client frames always use a fresh random mask.
"""

from __future__ import annotations

import os
import struct

MAX_FRAME = 1024 * 1024


class DepthError(ValueError):
    """Codes are fixed project messages, never raw server/parser contents."""


def close_payload(raw):
    if len(raw) == 1 or len(raw) > 125:
        raise DepthError("tls_ws_invalid_close")
    if raw:
        code = int.from_bytes(raw[:2], "big")
        if (
            code not in {1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014}
            and not 3000 <= code <= 4999
        ):
            raise DepthError("tls_ws_invalid_close_code")
        raw[2:].decode("utf8", errors="strict")


def client_frame(raw, opcode=1):
    if opcode not in {1, 8, 10} or not isinstance(raw, bytes) or len(raw) > MAX_FRAME:
        raise DepthError("tls_ws_outbound_frame_refused")
    if opcode >= 8 and len(raw) > 125:
        raise DepthError("tls_ws_control_limit")
    if opcode == 8:
        close_payload(raw)
    elif opcode == 1:
        raw.decode("utf8", errors="strict")
    size = len(raw)
    header = bytes([0x80 | opcode]) + (
        bytes([0x80 | size])
        if size < 126
        else b"\xfe" + struct.pack("!H", size)
        if size < 65536
        else b"\xff" + struct.pack("!Q", size)
    )
    mask = os.urandom(4)
    return header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(raw))


class ServerFrames:
    def __init__(self):
        self.buffer = bytearray()
        self.fragment = None
        self.closed = False

    @property
    def retained_bytes(self):
        return len(self.buffer) + (len(self.fragment) if self.fragment is not None else 0)

    def feed(self, raw):
        if self.closed and raw:
            raise DepthError("tls_ws_bytes_after_close")
        self.buffer.extend(raw)
        events = []
        while len(self.buffer) >= 2:
            first, second = self.buffer[:2]
            final, opcode = bool(first & 0x80), first & 0x0F
            if first & 0x70 or second & 0x80 or opcode not in {0, 1, 8, 9, 10}:
                raise DepthError("tls_ws_server_frame_flags")
            size, offset = second & 0x7F, 2
            if size in {126, 127}:
                width = 2 if size == 126 else 8
                if len(self.buffer) < 2 + width:
                    break
                decoded = int.from_bytes(self.buffer[2 : 2 + width], "big")
                if decoded < (126 if width == 2 else 65536) or decoded >= 2**63:
                    raise DepthError("tls_ws_noncanonical_length")
                size, offset = decoded, 2 + width
            if opcode >= 8:
                if not final or size > 125:
                    raise DepthError("tls_ws_invalid_control")
            elif size + (len(self.fragment) if self.fragment is not None else 0) > MAX_FRAME:
                raise DepthError("tls_ws_message_limit")
            if len(self.buffer) < offset + size:
                break
            payload = bytes(self.buffer[offset : offset + size])
            del self.buffer[: offset + size]
            if opcode == 1:
                if self.fragment is not None:
                    raise DepthError("tls_ws_nested_fragment")
                self.fragment = bytearray(payload)
            elif opcode == 0:
                if self.fragment is None:
                    raise DepthError("tls_ws_orphan_continuation")
                self.fragment.extend(payload)
            if opcode in {0, 1} and final:
                payload = bytes(self.fragment)
                payload.decode("utf8", errors="strict")
                self.fragment = None
                events.append((1, payload))
            elif opcode >= 8:
                if opcode == 8:
                    close_payload(payload)
                    if self.fragment is not None or self.buffer:
                        raise DepthError("tls_ws_incomplete_or_trailing_close")
                    self.closed = True
                events.append((opcode, payload))
        return events

"""Independent RFC wire encodings test the bounded JSON/control subset."""

import struct

import pytest

from apps.strategies_nautilus.portfolio_market_depth import MAX_FRAME, DepthError
from apps.strategies_nautilus.portfolio_ws_frames import ServerFrames, client_frame


def server(raw, *, opcode=1, final=True):
    length = len(raw)
    size = (
        bytes([length])
        if length < 126
        else b"\x7e" + struct.pack("!H", length)
        if length < 65536
        else b"\x7f" + struct.pack("!Q", length)
    )
    return bytes([opcode | (0x80 if final else 0)]) + size + raw


@pytest.mark.parametrize("size", [0, 1, 125, 126, 65535, 65536, MAX_FRAME])
def test_all_length_encodings_with_arbitrary_read_boundaries(size):
    raw = b"x" * size
    wire = server(raw)
    state = ServerFrames()
    events = []
    for part in (wire[:1], wire[1:2], wire[2:7], wire[7:]):
        events.extend(state.feed(part))
    assert events == [(1, raw)]
    assert state.retained_bytes == 0


def test_fragmented_utf8_and_interleaved_controls():
    state = ServerFrames()
    wire = (
        server(b'{"text":"\xe2', final=False)
        + server(b"echo", opcode=9)
        + server(b"ignored", opcode=10)
        + server(b'\x82\xac"}', opcode=0)
    )
    events = []
    for byte in wire:
        events.extend(state.feed(bytes([byte])))
    assert events == [(9, b"echo"), (10, b"ignored"), (1, '{"text":"€"}'.encode())]
    assert state.retained_bytes == 0


@pytest.mark.parametrize(
    "wire",
    [
        b"\xc1\x00",
        b"\xa1\x00",
        b"\x91\x00",
        b"\x81\x80",
        b"\x82\x00",
        b"\x83\x00",
        b"\x09\x00",
        b"\x89\x7e\x00\x7e",
        b"\x81\x7e\x00\x7d",
        b"\x81\x7f\x00\x00\x00\x00\x00\x00\xff\xff",
        b"\x81\x7f\x80\x00\x00\x00\x00\x00\x00\x00",
        b"\x81\x7f" + struct.pack("!Q", MAX_FRAME + 1),
        server(b"\xff"),
        server(b"orphan", opcode=0),
        server(b"first", final=False) + server(b"nested"),
        server(b"\x00", opcode=8),
        server(b"\x03\xed", opcode=8),
        server(b"\x13\x88", opcode=8),
        server(b"\x03\xe8\xff", opcode=8),
        server(b"\x03\xe8", opcode=8) + server(b"after"),
        server(b"unfinished", final=False) + server(b"", opcode=8),
    ],
)
def test_invalid_server_protocol_is_refused(wire):
    with pytest.raises((DepthError, UnicodeDecodeError)):
        ServerFrames().feed(wire)


def test_aggregate_fragment_size_cannot_bypass_message_limit():
    state = ServerFrames()
    assert state.feed(server(b"a" * MAX_FRAME, final=False)) == []
    with pytest.raises(DepthError, match="message_limit"):
        state.feed(server(b"a", opcode=0))


@pytest.mark.parametrize("payload", [b"", b"\x03\xe8", b"\x0b\xb8reason"])
def test_close_is_terminal_across_chunks(payload):
    state = ServerFrames()
    assert state.feed(server(payload, opcode=8)) == [(8, payload)]
    assert state.closed
    with pytest.raises(DepthError, match="bytes_after_close"):
        state.feed(server(b"later"))


@pytest.mark.parametrize(
    "wire", [b"\x81", b"\x81\x7e\x01", b"\x81\x05hi", server(b"start", final=False)]
)
def test_partial_frames_do_not_become_messages(wire):
    state = ServerFrames()
    assert state.feed(wire) == []
    assert state.retained_bytes > 0


@pytest.mark.parametrize("size", [0, 125, 126, 65536])
def test_client_masks_are_fresh_and_independently_decodable(size, monkeypatch):
    masks = iter([b"\x01\x02\x03\x04", b"\x05\x06\x07\x08"])
    monkeypatch.setattr(
        "apps.strategies_nautilus.portfolio_ws_frames.os.urandom", lambda n: next(masks)
    )
    raw = b"x" * size
    frames = [client_frame(raw), client_frame(raw)]
    assert frames[0] != frames[1]
    for wire in frames:
        assert wire[0] == 0x81 and wire[1] & 0x80
        marker = wire[1] & 0x7F
        offset = 2 if marker < 126 else 4 if marker == 126 else 10
        mask = wire[offset : offset + 4]
        assert bytes(b ^ mask[i % 4] for i, b in enumerate(wire[offset + 4 :])) == raw


@pytest.mark.parametrize(
    "raw,opcode", [(b"x", 2), (b"x", 9), (b"x" * 126, 10), (b"x", 8), (b"\xff", 1)]
)
def test_outbound_scope_and_control_limits(raw, opcode):
    with pytest.raises((DepthError, UnicodeDecodeError)):
        client_frame(raw, opcode)

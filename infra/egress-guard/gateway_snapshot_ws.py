"""Fixture-only REST depth anchors for the installed concurrent market stream."""

from __future__ import annotations

import base64
import re

PROFILE = "portfolio.installed_snapshot_ws.v1"
SCOPE = "account-market-snapshot-v1"
RECEIPT = "portfolio.native_account_market_snapshot.v1"
BODY_LIMIT = 4096
MAX_PAYLOAD = 8192


def request(symbol):
    if not isinstance(symbol, str) or re.fullmatch(r"[A-Z0-9]{2,20}", symbol) is None:
        raise ValueError("snapshot_symbol")
    return (
        f"GET /api/v3/depth?symbol={symbol}&limit=100 HTTP/1.1\r\n"
        "Host: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n"
    ).encode()


def response(raw, market):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= BODY_LIMIT + 1024:
        raise ValueError("snapshot_response_limit")
    head, separator, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if not separator or lines[0] != b"HTTP/1.1 200 OK" or len(lines) != 4:
        raise ValueError("snapshot_http_status")
    headers = {}
    for line in lines[1:]:
        key, sep, value = line.partition(b": ")
        if not sep or key.lower() in headers:
            raise ValueError("snapshot_http_header")
        headers[key.lower()] = value
    if set(headers) != {b"content-length", b"connection", b"x-mbx-used-weight-1m"}:
        raise ValueError("snapshot_http_headers")
    if (
        headers[b"connection"].lower() != b"close"
        or not headers[b"content-length"].isdigit()
        or not headers[b"x-mbx-used-weight-1m"].isdigit()
        or not 0 < int(headers[b"content-length"]) <= BODY_LIMIT
        or len(body) != int(headers[b"content-length"])
    ):
        raise ValueError("snapshot_http_body")
    value = market["decode"](body)
    if (
        not isinstance(value, dict)
        or set(value) != {"lastUpdateId", "bids", "asks"}
        or type(value["lastUpdateId"]) is not int
        or not 0 < value["lastUpdateId"] <= market["MAX_U64"]
    ):
        raise ValueError("snapshot_revision")
    for key, reverse in (("bids", True), ("asks", False)):
        rows = value[key]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise ValueError("snapshot_depth")
        prices = []
        for pair in rows:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("snapshot_level")
            prices.append(market["amount"](pair[0], positive=True))
            market["amount"](pair[1], positive=True)
        if prices != sorted(set(prices), reverse=reverse):
            raise ValueError("snapshot_order")
    if market["amount"](value["bids"][0][0]) >= market["amount"](value["asks"][0][0]):
        raise ValueError("snapshot_crossed_book")
    return value


def linked(payload, market_result, market):
    value = market["decode"](payload)
    if (
        not isinstance(value, dict)
        or market["canonical"](value) != payload
        or set(value)
        != {"profile", "account_b64", "definitions", "metadata_tls_sha256", "events", "snapshots"}
        or value["profile"] != RECEIPT
        or not isinstance(value["snapshots"], list)
    ):
        raise ValueError("snapshot_receipt_schema")
    base = {k: v for k, v in value.items() if k != "snapshots"}
    base["profile"] = market["RECEIPT"]
    result = market_result(market["canonical"](base))
    if len(value["snapshots"]) != len(result["definitions"]):
        raise ValueError("snapshot_count")
    anchors = []
    for item, symbol in zip(
        value["snapshots"], (d["symbol"] for d in result["definitions"]), strict=True
    ):
        if not isinstance(item, dict) or set(item) != {"symbol", "request_sha256", "chunks"}:
            raise ValueError("snapshot_original_schema")
        if item["symbol"] != symbol or item["request_sha256"] != market["digest"](request(symbol)):
            raise ValueError("snapshot_original_request")
        if not isinstance(item["chunks"], list) or not 1 <= len(item["chunks"]) <= 16:
            raise ValueError("snapshot_original_chunks")
        raw, previous = bytearray(), None
        for chunk in item["chunks"]:
            if not isinstance(chunk, dict) or set(chunk) != {"raw_b64", "raw_sha256", "receipt"}:
                raise ValueError("snapshot_original_chunk")
            data = base64.b64decode(chunk["raw_b64"], validate=True)
            if (
                not 0 < len(data) <= 4096
                or base64.b64encode(data).decode() != chunk["raw_b64"]
                or market["digest"](data) != chunk["raw_sha256"]
            ):
                raise ValueError("snapshot_original_digest")
            clock = market["stamp"](chunk["receipt"])
            if previous is not None:
                delta = [clock[k] - previous[k] for k in ("utc_ns", "monotonic_ns")]
                if any(n < 0 for n in delta) or abs(delta[0] - delta[1]) > 50_000_000:
                    raise ValueError("snapshot_original_clock")
            previous = clock
            raw.extend(data)
            if len(raw) > BODY_LIMIT + 1024:
                raise ValueError("snapshot_original_limit")
        book = response(bytes(raw), market)
        revision = book["lastUpdateId"]
        events = [e for e in result["market"] if e["symbol"] == symbol]
        if revision < events[0]["first_update_id"]:
            raise ValueError("snapshot_behind_first_buffered_event")
        active = [e for e in events if e["last_update_id"] > revision]
        if (
            not active
            or not active[0]["first_update_id"] <= revision + 1 <= active[0]["last_update_id"]
        ):
            raise ValueError("snapshot_bootstrap_gap")
        previous_id = revision
        for event in active:
            if not event["first_update_id"] <= previous_id + 1 <= event["last_update_id"]:
                raise ValueError("snapshot_increment_gap")
            previous_id = event["last_update_id"]
        anchors.append(
            {
                "symbol": symbol,
                "snapshot_sha256": market["digest"](bytes(raw)),
                "snapshot_receipt": previous,
                "snapshot_last_update_id": revision,
                "linked_last_update_id": previous_id,
                "obsolete_events": len(events) - len(active),
                "linked_event_sha256": [e["original_sha256"] for e in active],
            }
        )
    return {
        **result,
        "profile": RECEIPT,
        "payload_sha256": market["digest"](payload),
        "anchors": anchors,
        "unanchored_depth_segment": False,
        "snapshot_linked": True,
        "order_book_synchronized": False,
        "quote_ticks_created": False,
        "stream_fence_verified": False,
        "qualified_for_execution": False,
    }


def expected_result(payload, market_result, market):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_PAYLOAD:
        raise ValueError("snapshot_receipt_size")
    return linked(payload, market_result, market)


def validate_native(payload, market_native, market):
    if market["os"].geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    return expected_result(payload, market_native, market)


def state_type(base, account, requests, market):
    Parent = market["state_type"](base, account, requests)

    class SnapshotState(Parent):
        PROFILE = PROFILE

        def __init__(self, *args):
            super().__init__(*args)
            self.snapshots = {}

        def payload(self):
            value = market["decode"](super().payload())
            value["profile"] = RECEIPT
            value["snapshots"] = [
                {"symbol": symbol, "request_sha256": row["request_sha256"], "chunks": row["chunks"]}
                for symbol, row in self.snapshots.items()
            ]
            return market["canonical"](value)

        def native_result(self):
            return expected_result(
                self.payload(),
                lambda raw: market["expected_result"](raw, account["expected_result"]),
                market,
            )

        def feed(self, kind, payload, now, mono):
            if kind == "close_prepared":
                if set(self.snapshots) != set(self.selected["symbols"]) or any(
                    row["stage"] != "accepted" for row in self.snapshots.values()
                ):
                    raise ValueError("snapshot_all_required_before_close")
                self.native_result()
            if kind not in {
                "snapshot_connection_prepared",
                "snapshot_tls_connected",
                "snapshot_request_prepared",
                "snapshot_chunk",
                "snapshot_accepted",
            }:
                return super().feed(kind, payload, now, mono)
            self.clock(payload, now, mono)
            symbol = payload.get("symbol")
            if symbol not in self.selected["symbols"]:
                raise ValueError("snapshot_selected_symbol")
            if kind == "snapshot_connection_prepared":
                if (
                    self.stage != "preparing"
                    or list(self.snapshots) != self.selected["symbols"][: len(self.snapshots)]
                    or symbol != self.selected["symbols"][len(self.snapshots)]
                    or payload
                    != {
                        "symbol": symbol,
                        "endpoint": f"https://rest.fixture.invalid:23456/api/v3/depth?symbol={symbol}&limit=100",
                        "peer": list(base["PEER"]),
                    }
                ):
                    raise ValueError("snapshot_fixed_attempt")
                self.snapshots[symbol] = {"stage": "prepared", "request_sha256": None, "chunks": []}
                return
            if self.stage != "active" or mono - self.grant_clock > base["WINDOW_NS"]:
                raise ValueError("snapshot_inactive_or_expired")
            row = self.snapshots.get(symbol)
            if row is None:
                raise ValueError("snapshot_unprepared")
            if kind == "snapshot_tls_connected" and row["stage"] == "prepared":
                if (
                    set(payload)
                    != {
                        "symbol",
                        "peer",
                        "server_hostname",
                        "peer_certificate_sha256",
                        "tls_version",
                        "cipher",
                        "check_hostname",
                        "verify_mode",
                        "tls_minimum_version",
                    }
                    or payload["peer"] != list(base["PEER"])
                    or payload["server_hostname"] != "rest.fixture.invalid"
                    or payload["check_hostname"] is not True
                    or payload["verify_mode"] != "CERT_REQUIRED"
                    or payload["tls_minimum_version"] != "TLSv1.2"
                    or payload["tls_version"] not in {"TLSv1.2", "TLSv1.3"}
                    or not isinstance(payload["peer_certificate_sha256"], str)
                    or re.fullmatch("[0-9a-f]{64}", payload["peer_certificate_sha256"]) is None
                    or not isinstance(payload["cipher"], list)
                    or len(payload["cipher"]) != 3
                ):
                    raise ValueError("snapshot_tls_identity")
                row["stage"] = "tls"
            elif kind == "snapshot_request_prepared" and row["stage"] == "tls":
                if set(payload) != {"symbol", "raw_b64", "raw_sha256"} or base["original"](
                    payload
                ) != request(symbol):
                    raise ValueError("snapshot_request_changed")
                row["request_sha256"] = payload["raw_sha256"]
                row["stage"] = "requested"
            elif kind == "snapshot_chunk" and row["stage"] in {"requested", "receiving"}:
                if set(payload) != {"symbol", "raw_b64", "raw_sha256"}:
                    raise ValueError("snapshot_chunk_fields")
                raw = base["original"](payload)
                if (
                    not 0 < len(raw) <= 4096
                    or sum(len(base["original"](v)) for v in row["chunks"]) + len(raw)
                    > BODY_LIMIT + 1024
                ):
                    raise ValueError("snapshot_chunk_limit")
                row["chunks"].append(
                    {
                        "raw_b64": payload["raw_b64"],
                        "raw_sha256": payload["raw_sha256"],
                        "receipt": {"utc_ns": now, "monotonic_ns": mono},
                    }
                )
                row["stage"] = "receiving"
            elif kind == "snapshot_accepted" and row["stage"] == "receiving":
                if payload != {"symbol": symbol}:
                    raise ValueError("snapshot_accept_fields")
                response(b"".join(base["original"](v) for v in row["chunks"]), market)
                row["stage"] = "accepted"
            else:
                raise ValueError("snapshot_transition")

        def report(self):
            result = super().report()
            return {
                **result,
                "snapshot_attempts_consumed": len(self.snapshots),
                "snapshots_accepted": sum(
                    r["stage"] == "accepted" for r in self.snapshots.values()
                ),
                "snapshot_linked": self.acknowledged is not None,
                "order_book_synchronized": False,
                "quote_ticks_created": False,
            }

    return SnapshotState

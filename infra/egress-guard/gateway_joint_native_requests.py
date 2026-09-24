"""Original-route-bound fixture selectors for the two-depth, 19-step joint plan."""

from __future__ import annotations

import json
import os
import re

PROFILE = "portfolio.fixture_joint_native_requests.v1"
ACCOUNT = {3, 6, 13, 16}
ORDERS = {4, 5, 14, 15}


def view(base, symbols, route_sha256):
    if (
        not isinstance(symbols, list)
        or len(symbols) != 2
        or symbols != sorted(set(symbols))
        or any(not isinstance(s, str) or re.fullmatch("[A-Z0-9]{2,20}", s) is None for s in symbols)
        or not isinstance(route_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", route_sha256) is None
    ):
        raise ValueError("joint_request_original_route_required")
    symbols = tuple(symbols)

    def validate_challenge(challenge, index):
        if (
            not isinstance(challenge, dict)
            or set(challenge) != {"index", "nonce", "utc_ns", "monotonic_ns", "route_sha256"}
            or challenge.get("route_sha256") != route_sha256
            or type(index) is not int
            or not 0 <= index < 19
        ):
            raise ValueError("joint_request_route_challenge")
        base["validate_challenge"](
            {key: challenge[key] for key in ("index", "nonce", "utc_ns", "monotonic_ns")},
            index,
        )

    def selected_request(challenge):
        index = challenge["index"]
        validate_challenge(challenge, index)
        stamp = challenge["utc_ns"] // 1_000_000
        if index in {1, 9}:
            return {
                "kind": "connect",
                "role": "account" if index == 1 else "market",
                "target": "/ws-api/v3" if index == 1 else "/stream?streams=" + "/".join(
                    symbol.lower() + "@depth@100ms" for symbol in symbols
                ),
            }
        if index in {2, 18}:
            return {
                "kind": "ws", "id": f"fixture-{index}",
                "method": "userDataStream.subscribe.signature" if index == 2 else "userDataStream.unsubscribe",
                "params": {"apiKey": base["API_KEY"], "recvWindow": 5000, "timestamp": stamp}
                if index == 2 else {"subscriptionId": 0},
            }
        path, params, headers = "/api/v3/time", {}, {}
        if index in ACCOUNT:
            path = "/api/v3/account"
        elif index in ORDERS:
            path = "/api/v3/openOrders"
        elif index == 7:
            path = "/api/v3/exchangeInfo"
        elif index == 8:
            path = "/api/v3/ticker/bookTicker"
        elif index in {10, 11}:
            path, params = "/api/v3/depth", {"symbol": symbols[index - 10], "limit": "100"}
        if index in ACCOUNT | ORDERS:
            params.update(timestamp=str(stamp), recvWindow="5000")
            headers["X-MBX-APIKEY"] = base["API_KEY"]
        return {"kind": "rest", "method": "GET", "path": path, "params": params, "headers": headers}

    def native_request(challenge):
        if os.geteuid() == 0:
            raise ValueError("native_signing_as_root_refused")
        from nautilus_trader.core.nautilus_pyo3 import NAUTILUS_VERSION, ed25519_signature

        if base["VERSION"] != NAUTILUS_VERSION:
            raise ValueError("native_version_changed")
        request = selected_request(challenge)
        signing = base["signing_text"](request)
        if signing is not None:
            request["params"]["signature"] = ed25519_signature(bytes.fromhex(base["SEED"]), signing)
        return base["canonical"]({
            "profile": PROFILE,
            "challenge_sha256": base["digest"](base["canonical"](challenge)),
            "request": request,
        })

    def validate_request(raw, challenge, *, received):
        validate_challenge(challenge, challenge["index"])
        # The base validator enforces both clocks and the bounded envelope before
        # this route-specific selector and signature are examined.
        plain = {key: challenge[key] for key in ("index", "nonce", "utc_ns", "monotonic_ns")}
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 850:
            raise ValueError("joint_request_size")
        value = json.loads(raw)
        if not isinstance(value, dict) or base["canonical"](value) != raw:
            raise ValueError("joint_request_canonical")
        expected = selected_request(challenge)
        signing = base["signing_text"](expected)
        if signing is not None:
            actual = value.get("request")
            if not isinstance(actual, dict) or not isinstance(actual.get("params"), dict):
                raise ValueError("joint_request_schema")
            signature = actual["params"].get("signature")
            if not isinstance(signature, str):
                raise ValueError("joint_request_signature_required")
            expected["params"]["signature"] = signature
        if value != {
            "profile": PROFILE,
            "challenge_sha256": base["digest"](base["canonical"](challenge)),
            "request": expected,
        }:
            raise ValueError("joint_request_selector")
        # Verify the base time window without accepting its incompatible 20-step
        # request map. The envelope's route hash was checked above.
        if (
            not isinstance(received, tuple) or len(received) != 2
            or any(type(v) is not int for v in received)
            or any(not 0 <= received[i] - plain[k] <= 5_000_000_000 for i, k in enumerate(("utc_ns", "monotonic_ns")))
            or abs((received[0] - plain["utc_ns"]) - (received[1] - plain["monotonic_ns"])) > 50_000_000
        ):
            raise ValueError("joint_request_stale_or_clock_change")
        if signing is not None:
            base["verify_signature"](signing, signature)
        return base["digest"](raw)

    return {
        **base,
        "PROFILE": PROFILE,
        "validate_challenge": validate_challenge,
        "selected_request": selected_request,
        "native_request": native_request,
        "validate_request": validate_request,
    }

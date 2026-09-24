"""First ordered joint operation: fixed HTTPS server clock and native receipt.

This fixture prefix has no source authority or live admission. The next
operation is the account WebSocket connection under the same parent scope.
"""

from __future__ import annotations

import base64
import json
import os

PROFILE = "portfolio.installed_native_joint_clock.v1"
SELECTION_PROFILE = "portfolio.installed_joint_clock_request.v1"
TLS_PROFILE = "portfolio.installed_joint_clock_tls.v1"
ENDPOINT = "https://rest.fixture.invalid:23456/api/v3/time"
SECOND_NS = 1_000_000_000


def expected_result(payload):
    value = json.loads(payload)
    if (
        not isinstance(value, dict)
        or set(value) != {"profile", "tls_sha256", "header_receipt", "body_receipt", "response_b64"}
        or value["profile"] != "portfolio.installed_tls_receipt.v1"
    ):
        raise ValueError("joint_clock_receipt_schema")
    raw = base64.b64decode(value["response_b64"], validate=True)
    if base64.b64encode(raw).decode() != value["response_b64"]:
        raise ValueError("joint_clock_original_encoding")
    head, separator, body = raw.partition(b"\r\n\r\n")
    if not separator or not head.startswith(b"HTTP/1.1 200 OK\r\n"):
        raise ValueError("joint_clock_original_http")

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("joint_clock_duplicate_key")
            result[key] = item
        return result

    parsed = json.loads(body, object_pairs_hook=unique)
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"serverTime"}
        or type(parsed["serverTime"]) is not int
        or not 0 < parsed["serverTime"] < 2**63 // 1_000_000
    ):
        raise ValueError("joint_clock_server_time")
    header, complete = value["header_receipt"], value["body_receipt"]
    for stamp in (header, complete):
        if (
            not isinstance(stamp, dict)
            or set(stamp) != {"seq", "utc_ns", "monotonic_ns"}
            or any(type(n) is not int or n <= 0 for n in stamp.values())
        ):
            raise ValueError("joint_clock_receipt_clock")
    if (
        any(complete[k] < header[k] for k in header)
        or abs(
            (complete["utc_ns"] - header["utc_ns"])
            - (complete["monotonic_ns"] - header["monotonic_ns"])
        )
        > 50_000_000
    ):
        raise ValueError("joint_clock_receipt_order")
    # A fixture server clock must be near the original receive clock; no
    # clock offset or real venue time qualification is inferred from it.
    if abs(header["utc_ns"] - parsed["serverTime"] * 1_000_000) > 5 * SECOND_NS:
        raise ValueError("joint_clock_fixture_time_drift")
    return {
        "profile": PROFILE,
        "native_version": "1.226.0",
        "server_time_ms": parsed["serverTime"],
        "tls_sha256": value["tls_sha256"],
        "header_receipt": header,
        "body_receipt": complete,
        "provider_clock_qualified": False,
        "qualified_for_execution": False,
    }


def validate_native(payload):
    if os.geteuid() == 0:
        raise ValueError("joint_clock_native_root_refused")
    from nautilus_trader.core.nautilus_pyo3 import NAUTILUS_VERSION

    if NAUTILUS_VERSION != "1.226.0":
        raise ValueError("joint_clock_native_version_changed")
    return expected_result(payload)


def view(account):
    """Specialize the held single-use selector and its signed-request channel."""

    class ClockContract(account["AccountContract"]):
        SELECTION_PROFILE = SELECTION_PROFILE
        TLS_PROFILE = TLS_PROFILE
        ENDPOINT = ENDPOINT
        LEDGER_PROFILE = "portfolio.fixture_joint_clock_tls_ledger.v1"
        CHALLENGE_INDEX = 0
        PATH = "/api/v3/time"
        SELECTION_FILE = "time-request.json"

    def ledger_view(module):
        return account["ledger_view"](
            module, profile=module.CLOCK_PROFILE, scope=module.CLOCK_SCOPE
        )

    def authorize(collector, ledger, authority, requests):
        return account["authorize"](
            collector, ledger, authority, requests, contract_type=ClockContract
        )

    def launch(authority, sources, launcher, runtime):
        return account["launch"](authority, sources, launcher, runtime, clock=True)

    return {
        "PROFILE": PROFILE,
        "SELECTION_PROFILE": SELECTION_PROFILE,
        "AccountContract": ClockContract,
        "ledger_view": ledger_view,
        "rates_view": account["rates_view"],
        "transport_view": account["transport_view"],
        "authorize": authorize,
        "launch": launch,
        "expected_result": expected_result,
        "validate_native": validate_native,
    }


def child_loop(fd, parent):
    globals()["ACCOUNT"]["child_loop"](fd, parent, index=0, native=validate_native)

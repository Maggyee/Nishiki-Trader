"""One signed fixture account GET: native child, owned TLS, exact balance receipt."""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import time
import types
from decimal import Decimal
from urllib.parse import urlencode

PROFILE = "portfolio.installed_native_account_receipt.v1"
SELECTION_PROFILE = "portfolio.installed_signed_account_request.v1"
TLS_PROFILE = "portfolio.installed_signed_account_tls.v1"
ENDPOINT = "https://rest.fixture.invalid:23456/api/v3/account"
UID = 41001
ASSETS = ("BNB", "BTC", "ETH", "USDT")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def ledger_view(module, *, profile=None, scope=None):
    """Explicit account-profile reader; never infer a profile from untrusted bytes."""
    profile = module.ACCOUNT_PROFILE if profile is None else profile
    scope = module.ACCOUNT_SCOPE if scope is None else scope
    if (profile, scope) not in {
        (module.ACCOUNT_PROFILE, module.ACCOUNT_SCOPE),
        (module.ORDERS_PROFILE, module.ORDERS_SCOPE),
        (module.BOOKS_PROFILE, module.BOOKS_SCOPE),
        (module.METADATA_PROFILE, module.METADATA_SCOPE),
        (module.DEPTH_PROFILE, module.DEPTH_SCOPE),
        (module.CLOCK_PROFILE, module.CLOCK_SCOPE),
    }:
        raise ValueError("signed_read_profile_required")
    values = dict(vars(module))
    values.update(PROFILE=profile, SCOPE=scope)

    def replay(*args, **kwargs):
        kwargs.setdefault("profile", profile)
        return module.replay(*args, **kwargs)

    values["replay"] = replay
    return types.SimpleNamespace(**values)


def rate_evidence(body, headers):
    # Account responses do not advertise exchangeInfo limits. Preserve unknowns.
    values = [
        (name.lower(), value)
        for name, value in headers
        if name.lower().startswith("x-mbx-used-weight-")
    ]
    if (
        len(values) != 1
        or values[0][0] != "x-mbx-used-weight-1m"
        or re.fullmatch("[0-9]{1,20}", values[0][1]) is None
    ):
        raise ValueError("account_original_weight_header_required")
    return {
        "schema_version": "portfolio.fixture_account_rate_receipt.v1",
        "used_weight_1m": int(values[0][1]),
        "limit": None,
        "raw_requests_usage": None,
        "connection_charge": None,
        "source_authenticated": False,
        "freshness_verified": False,
        "network_admitted": False,
    }


def rates_view():
    return types.SimpleNamespace(rest_rate_evidence=rate_evidence)


def amount(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,16})?", value) is None:
        raise ValueError("account_decimal_required")
    return Decimal(value)


def expected_result(payload):
    value = json.loads(payload)
    response = base64.b64decode(value["response_b64"], validate=True)
    body = json.loads(response.split(b"\r\n\r\n", 1)[1])
    if type(body.get("uid")) is not int or body["uid"] != UID or body.get("accountType") != "SPOT":
        raise ValueError("fixture_account_identity_required")
    balances = body.get("balances")
    if not isinstance(balances, list) or len(balances) != len(ASSETS):
        raise ValueError("fixture_account_assets_required")
    result, seen = [], set()
    for row in balances:
        if (
            not isinstance(row, dict)
            or set(row) != {"asset", "free", "locked"}
            or row["asset"] not in ASSETS
            or row["asset"] in seen
        ):
            raise ValueError("fixture_account_assets_required")
        seen.add(row["asset"])
        free, locked = amount(row["free"]), amount(row["locked"])
        result.append(
            {
                "currency": row["asset"],
                "precision": 8,
                "free": format(free, "f"),
                "locked": format(locked, "f"),
                "total": format(free + locked, "f"),
            }
        )
    return {
        "profile": PROFILE,
        "native_version": "1.226.0",
        "account_uid": UID,
        "balances": sorted(result, key=lambda r: r["currency"]),
        "tls_sha256": value["tls_sha256"],
        "header_receipt": value["header_receipt"],
        "body_receipt": value["body_receipt"],
        "qualified_for_execution": False,
    }


def prepare_native():
    if os.geteuid() == 0:
        raise ValueError("native_import_as_root_refused")
    from nautilus_trader.core.nautilus_pyo3 import NAUTILUS_VERSION

    if NAUTILUS_VERSION != "1.226.0":
        raise ValueError("native_version_changed")


def validate_native(payload):
    prepare_native()
    from nautilus_trader.core.nautilus_pyo3 import AccountBalance, Currency, CurrencyType, Money

    result = expected_result(payload)
    for row in result["balances"]:
        currency = Currency(row["currency"], 8, 0, row["currency"], CurrencyType.CRYPTO)
        values = {key: Money(Decimal(row[key]), currency) for key in ("total", "locked", "free")}
        if any(values[key].as_decimal() != Decimal(row[key]) for key in values):
            raise ValueError("native_account_rounding_refused")
        balance = AccountBalance(values["total"], values["locked"], values["free"]).to_dict()
        if balance["currency"] != row["currency"] or any(
            Decimal(balance[k]) != Decimal(row[k]) for k in values
        ):
            raise ValueError("native_account_mapping_changed")
    return result


class AccountContract:
    TLS_PROFILE, ENDPOINT = TLS_PROFILE, ENDPOINT
    SELECTION_PROFILE = SELECTION_PROFILE
    LEDGER_PROFILE = "portfolio.fixture_signed_account_tls_ledger.v1"
    CHALLENGE_INDEX = 3
    PATH = "/api/v3/account"
    SELECTION_FILE = "account-request.json"
    CHALLENGE_FIELDS = {}

    def __init__(self, requests, selection):
        if (
            not isinstance(selection, dict)
            or set(selection) != {"profile", "binding_sha256", "challenge", "request", "received"}
            or selection["profile"] != self.SELECTION_PROFILE
            or not isinstance(selection["binding_sha256"], str)
            or re.fullmatch("[0-9a-f]{64}", selection["binding_sha256"]) is None
            or not isinstance(selection["received"], list)
            or len(selection["received"]) != 2
        ):
            raise ValueError("signed_account_selection")
        requests["validate_challenge"](selection["challenge"], self.CHALLENGE_INDEX)
        self.requests = requests
        self.selection = json.loads(canonical(selection))
        self.raw = canonical(selection)
        self.pin = digest(self.raw)
        self.request_pin = requests["validate_request"](
            canonical(selection["request"]),
            selection["challenge"],
            received=tuple(selection["received"]),
        )
        expected = requests["selected_request"](selection["challenge"])
        if expected["headers"]:
            expected["params"]["signature"] = selection["request"]["request"]["params"]["signature"]
        query = urlencode(expected["params"])
        self.request = (
            "GET "
            + self.PATH
            + ("?" + query if query else "")
            + " HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\n"
            + "".join(k + ": " + v + "\r\n" for k, v in expected["headers"].items())
            + "Connection: close\r\n\r\n"
        ).encode("ascii")

    def validate_at(self, utc_ns, monotonic_ns):
        if canonical(self.selection) != self.raw:
            raise ValueError("signed_account_selection_changed")
        self.requests["validate_request"](
            canonical(self.selection["request"]),
            self.selection["challenge"],
            received=(utc_ns, monotonic_ns),
        )

    def check(self, ledger):
        ledger.checkpoint()
        if (
            ledger.state.profile != self.LEDGER_PROFILE
            or ledger.state.binding_sha256 != self.selection["binding_sha256"]
            or ledger.state.pending != 0
            or len(ledger.state.attempts) != 1
            or ledger.state.attempts[0]["request_sha256"] != self.request_pin
        ):
            raise ValueError("signed_account_pending_request_required")
        self.validate_at(time.time_ns(), time.monotonic_ns())
        # Signature verification and binding checks consume the original window.
        challenge = self.selection["challenge"]
        ages = (
            time.time_ns() - challenge["utc_ns"],
            time.monotonic_ns() - challenge["monotonic_ns"],
        )
        if any(not 0 <= age < 5_000_000_000 for age in ages) or abs(ages[0] - ages[1]) > 50_000_000:
            raise ValueError("signed_account_expired_before_wire")
        return (5_000_000_000 - max(ages)) / 1_000_000_000

    def validate_attempts(self, attempts, binding_sha256):
        rows = list(map(json.loads, attempts.splitlines()))
        prepared = [r for r in rows if r["kind"] == "prepared"]
        if (
            binding_sha256 != self.selection["binding_sha256"]
            or len(prepared) != 1
            or prepared[0]["profile"] != self.LEDGER_PROFILE
            or prepared[0]["payload"].get("request_sha256") != self.request_pin
            or any(
                not rows[0][key]
                <= self.selection["challenge"][key]
                <= self.selection["received"][i]
                <= prepared[0][key]
                for i, key in enumerate(("utc_ns", "monotonic_ns"))
            )
        ):
            raise ValueError("signed_account_preparation_binding")


def transport_view(transport, contract):
    def capture(*args, **kwargs):
        return transport["capture"](*args, **kwargs, account=contract)

    def replay(*args, **kwargs):
        return transport["replay"](*args, **kwargs, account=contract)

    return {**transport, "capture": capture, "replay": replay}


def authorize(collector, ledger, authority, requests, *, contract_type=AccountContract):
    collector.verify()
    if collector.used:
        raise ValueError("signed_account_request_consumed")
    collector.used = True
    challenge = {
        "index": contract_type.CHALLENGE_INDEX,
        "nonce": os.urandom(16).hex(),
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        **contract_type.CHALLENGE_FIELDS,
    }
    collector.channel.connection.settimeout(5)
    collector.channel.send(canonical(challenge).decode(), 1)
    raw = collector.channel.receive(requests["JsonToken"](), 1).encode()
    received = [time.time_ns(), time.monotonic_ns()]
    collector.verify()
    selection = {
        "profile": contract_type.SELECTION_PROFILE,
        "binding_sha256": ledger.state.binding_sha256,
        "challenge": challenge,
        "request": json.loads(raw),
        "received": received,
    }
    if canonical(selection["request"]) != raw:
        raise ValueError("signed_account_canonical_request")
    contract = contract_type(requests, selection)
    path = ledger.path / contract_type.SELECTION_FILE
    ledger.checkpoint()
    with path.open("xb") as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(contract.raw)
        out.flush()
        os.fsync(out.fileno())
    directory = os.open(ledger.path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    authority.open_file(str(path), 0o600)
    ledger.checkpoint()
    return contract


def child_loop(fd, parent, *, index=3, native=validate_native, rates=None):
    prepare_native()
    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=5)
    try:
        channel.send("ready", 0)
        raw = channel.receive(globals()["REQUESTS"]["JsonToken"](), 1).encode()
        challenge = json.loads(raw)
        globals()["REQUESTS"]["validate_challenge"](challenge, index)
        if canonical(challenge) != raw:
            raise ValueError("signed_account_challenge_canonical")
        channel.send(globals()["REQUESTS"]["native_request"](challenge).decode(), 1)
        globals()["RECEIVE"](channel, globals()["PROVENANCE"], rates or rates_view(), native=native)
        channel.receive({"close"}, 1000)
        channel.send("closed", 1000)
    finally:
        channel.close()


def launch(
    authority,
    sources,
    launcher,
    runtime,
    *,
    orders=False,
    books=False,
    clock=False,
    metadata=False,
    depth=False,
    depth_symbols=None,
    depth_route_sha=None,
    depth_index=10,
    clock_index=0,
    clock_symbols=None,
    clock_route_sha=None,
    request_index=None,
):
    if sum((orders, books, clock, metadata, depth)) > 1:
        raise ValueError("signed_read_type_conflict")
    if depth and (
        not isinstance(depth_symbols, list)
        or not isinstance(depth_route_sha, str)
        or depth_index not in {10, 11}
    ):
        raise ValueError("joint_depth_route_required")
    if (
        clock_index not in {0, 12}
        or (clock_index == 12 and not clock)
        or (clock_index == 0 and (clock_symbols is not None or clock_route_sha is not None))
        or (
            clock
            and clock_index == 12
            and (not isinstance(clock_symbols, list) or not isinstance(clock_route_sha, str))
        )
    ):
        raise ValueError("joint_clock_route_required")
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

    source = "import types\n"
    for name, filename in (
        ("PROVENANCE", "portfolio_tls_provenance.py"),
        ("REQUESTS", "gateway_native_requests.py"),
        *((("RATES", "portfolio_rate_evidence.py"),) if metadata else ()),
    ):
        raw = sources.source(filename)
        source += f"{name}=types.ModuleType({name!r})\nexec(compile({raw!r},'<held-source>','exec'),{name}.__dict__)\n"
    if depth or (clock and clock_index == 12):
        raw = sources.source("gateway_joint_native_requests.py")
        symbols = depth_symbols if depth else clock_symbols
        route_sha = depth_route_sha if depth else clock_route_sha
        source += f"joint_request_scope={{'__name__':'held_joint_requests'}}\nexec(compile({raw!r},'<held-joint-requests>','exec'),joint_request_scope)\nREQUESTS=joint_request_scope['view'](REQUESTS.__dict__,{symbols!r},{route_sha!r})\n"
    for raw in (
        authority.source("collector_launcher.py"),
        sources.source("gateway_tls_receipt.py"),
    ):
        source += f"exec(compile({raw!r},'<held-source>','exec'))\n"
    raw = sources.source("gateway_native_account.py")
    requests = "REQUESTS" if depth or (clock and clock_index == 12) else "REQUESTS.__dict__"
    source += f"account_scope={{'__name__':'held_account','ControlChannel':ControlChannel,'REQUESTS':{requests},'PROVENANCE':PROVENANCE,'RECEIVE':receive_payload}}\nexec(compile({raw!r},'<held-account>','exec'),account_scope)\nchild_loop=account_scope['child_loop']\n"
    if depth:
        source += f"SYMBOL={depth_symbols[depth_index - 10]!r}\nINDEX={depth_index!r}\n"
    elif clock and clock_index == 12:
        source += "INDEX=12\n"
    if orders or books or clock or metadata or depth:
        raw = sources.source(
            "gateway_native_time.py"
            if clock
            else "gateway_book_routes.py"
            if books
            else "gateway_native_receipt.py"
            if metadata
            else "gateway_joint_native_depth.py"
            if depth
            else "gateway_native_orders.py"
        )
        extra = ",'RATES':RATES" if metadata else ""
        if depth:
            extra = ",'SYMBOL':SYMBOL,'INDEX':INDEX"
        elif clock and clock_index == 12:
            extra = ",'INDEX':INDEX"
        source += f"orders_scope={{'__name__':'held_orders','ACCOUNT':account_scope{extra}}}\nexec(compile({raw!r},'<held-orders>','exec'),orders_scope)\nchild_loop=orders_scope['child_loop']\n"
    if request_index is not None:
        if request_index not in ({4, 5} if orders else {3, 6} if not (books or clock) else set()):
            raise ValueError("signed_read_fixed_index")
        scope = "orders_scope" if orders else "account_scope"
        native = f",native={scope}['validate_native']" if orders else ""
        source += f"child_loop=lambda fd,parent:account_scope['child_loop'](fd,parent,index={request_index}{native})\n"
    runtime.verify()
    launcher["FixtureCollector"].__init__.__globals__["PYTHON"] = (
        "/run/trader-native-runtime/bin/python3.12"
    )
    return launcher["FixtureCollector"](
        source,
        identity,
        collector_uid=authority.account["uid"],
        collector_gid=authority.account["gid"],
    )


def view_for_index(index):
    if index not in {3, 6}:
        raise ValueError("signed_account_fixed_index")

    class FixedAccountContract(AccountContract):
        CHALLENGE_INDEX = index

    def fixed_authorize(collector, ledger, authority, requests):
        return authorize(collector, ledger, authority, requests, contract_type=FixedAccountContract)

    def fixed_launch(authority, sources, launcher, runtime):
        return launch(authority, sources, launcher, runtime, request_index=index)

    return {
        "PROFILE": PROFILE,
        "SELECTION_PROFILE": SELECTION_PROFILE,
        "AccountContract": FixedAccountContract,
        "ledger_view": ledger_view,
        "rates_view": rates_view,
        "transport_view": transport_view,
        "authorize": fixed_authorize,
        "launch": fixed_launch,
        "expected_result": expected_result,
        "validate_native": validate_native,
    }

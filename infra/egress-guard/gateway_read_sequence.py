"""Fixed metadata/account/account fixture sequence; no resume or real venue mode."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import time
from contextlib import suppress
from decimal import Decimal, localcontext
from pathlib import Path

PROFILE = "portfolio.installed_read_sequence.v1"
SCOPE = "fixture-read-sequence-v1"
STEPS = ("metadata", "account_first", "account_second")
ORDER_PROFILE = "portfolio.installed_order_sequence.v1"
ORDER_SCOPE = "fixture-order-sequence-v1"
ORDER_STEPS = ("metadata", "account_first", "orders_first", "orders_second", "account_second")
ROUTE_PROFILE = "portfolio.installed_route_sequence.v1"
ROUTE_SCOPE = "fixture-route-sequence-v1"
ROUTE_STEPS = (*ORDER_STEPS, "books")
QUOTE_ROUTE_PROFILE = "portfolio.installed_quote_route_sequence.v1"
QUOTE_ROUTE_SCOPE = "fixture-quote-route-sequence-v1"
LIMIT = 65536
FILES = {
    "binding": "binding.json",
    "attempts": "events.jsonl",
    "lifecycle": "kernel.jsonl",
    "tls": "tls.jsonl",
    "receipt": "receipt.jsonl",
    "selection": "account-request.json",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def load_sources(sources):
    def load(name):
        scope = {"__name__": "held_read_sequence"}
        exec(compile(sources[name], "<held-read-sequence>", "exec"), scope)
        return scope

    gateway = load("ledger_gateway.py")
    ledger = gateway["load_ledger"](sources)
    account = load("gateway_native_account.py")
    return {
        "gateway": gateway,
        "ledger": ledger,
        "tls": load("gateway_tls.py"),
        "receipt": load("gateway_tls_receipt.py"),
        "account": account,
        "orders": load("gateway_native_orders.py")["view"](account),
        "books": load("gateway_book_routes.py")["view"](account),
        "metadata": load("gateway_native_receipt.py"),
        "requests": load("gateway_native_requests.py"),
        "provenance": sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
        "rates": sys.modules["apps.strategies_nautilus.portfolio_rate_evidence"],
    }


def review_bundle(bundle, index, context, selected, modules, *, orders=False, routes=False):
    """Verify originals before considering a step complete; never trust a saved report."""
    allowed = set(FILES) - ({"selection"} if index == 0 else set())
    if (
        not isinstance(bundle, dict)
        or set(bundle) - allowed
        or any(
            not isinstance(raw, str) or not 0 < len(raw.encode()) <= 2 * 1024 * 1024
            for raw in bundle.values()
        )
    ):
        raise ValueError("sequence_bundle_fields")
    if not bundle:
        return {"complete": False, "native_result": None}
    if "binding" not in bundle:
        raise ValueError("sequence_binding_required")
    binding = json.loads(bundle["binding"])
    if canonical(binding).decode() != bundle["binding"] or binding.get("read_sequence") != context:
        raise ValueError("sequence_step_binding")
    for key in ("base_manifest_sha256", "gateway_manifest_sha256", "tls_trust_sha256"):
        if binding.get(key) != selected[key]:
            raise ValueError("sequence_installation_changed")
    pin = digest(bundle["binding"].encode())
    result = {"complete": False, "native_result": None, "binding_sha256": pin}
    if "attempts" not in bundle:
        if set(bundle) != {"binding"}:
            raise ValueError("sequence_attempts_required")
        return result
    account = (
        modules["books"]
        if routes and index == 5
        else modules["orders"]
        if orders and index in {2, 3}
        else modules["account"]
    )
    ledger = account["ledger_view"](modules["ledger"]) if index else modules["ledger"]
    attempts = bundle["attempts"].encode()
    result["attempts"] = ledger.replay(
        attempts, expected_sha256=digest(attempts), binding_sha256=pin
    )
    if "lifecycle" not in bundle:
        if set(bundle) != {"binding", "attempts"}:
            raise ValueError("sequence_lifecycle_required")
        return result
    lifecycle = bundle["lifecycle"].encode()
    result["lifecycle"] = modules["gateway"]["replay_lifecycle"](
        ledger, lifecycle, expected_sha256=digest(lifecycle), attempts=attempts, binding_sha256=pin
    )
    transport = modules["tls"]
    rates = account["rates_view"]() if index else modules["rates"]
    if index and "selection" in bundle:
        contract = account["AccountContract"](modules["requests"], json.loads(bundle["selection"]))
        if contract.raw.decode() != bundle["selection"]:
            raise ValueError("sequence_canonical_selection")
        transport = account["transport_view"](transport, contract)
    elif index and "tls" in bundle:
        raise ValueError("sequence_selected_request_required")
    if "tls" not in bundle:
        if "receipt" in bundle:
            raise ValueError("sequence_tls_required")
        return result
    kwargs = dict(
        attempts=attempts,
        lifecycle=lifecycle,
        binding_sha256=pin,
        trust_sha256=selected["tls_trust_sha256"],
        ledger_module=ledger,
        gateway_module=modules["gateway"],
        provenance=modules["provenance"],
        rates=rates,
    )
    tls = bundle["tls"].encode()
    result["tls"] = transport["replay"](tls, expected_sha256=digest(tls), **kwargs)
    if "receipt" not in bundle:
        return result
    raw = bundle["receipt"].encode()
    receipt = modules["receipt"]["replay"](
        raw,
        expected_sha256=digest(raw),
        tls_raw=tls,
        transport=transport,
        native=account if index else modules["metadata"],
        **kwargs,
    )
    result["receipt"] = receipt
    result["complete"] = (
        receipt["status"] == "acknowledged"
        and receipt["attempt_outcome_recorded"]
        and result["lifecycle"]["revocation_recorded"]
        and result["attempts"]["status"] == "closed"
    )
    result["native_result"] = receipt["native_result"]
    return result


def reconcile(results, *, orders=False):
    """Fixed fixture precision and equal endpoint amounts, never a stream fence."""
    metadata = results[0]["native_result"]
    if metadata["currencies"] != [
        {"code": asset, "precision": 8} for asset in ("BNB", "BTC", "ETH", "USDT")
    ]:
        raise ValueError("sequence_metadata_precision_mismatch")
    if orders and len(results) >= 3:
        reconcile_orders(results)
    total = len(ORDER_STEPS if orders else STEPS)
    if len(results) >= total:
        first, second = (results[i]["native_result"] for i in (1, total - 1))

        def amounts(value):
            return [
                (
                    r["currency"],
                    r["precision"],
                    *(Decimal(r[k]) for k in ("total", "locked", "free")),
                )
                for r in value["balances"]
            ]

        if first["account_uid"] != second["account_uid"] or amounts(first) != amounts(second):
            raise ValueError("sequence_account_balances_changed")
    return {"metadata_precision_matched": True, "repeated_balances_equal": len(results) >= total}


def reconcile_orders(results):
    first = results[2]["native_result"]["orders"]
    if len(results) >= 4:

        def normalized(rows):
            return [
                {
                    k: (
                        Decimal(v)
                        if k
                        in {
                            "price",
                            "origQty",
                            "executedQty",
                            "cummulativeQuoteQty",
                            "icebergQty",
                            "stopPrice",
                            "origQuoteOrderQty",
                            "remainingQty",
                        }
                        else v
                    )
                    for k, v in row.items()
                }
                for row in rows
            ]

        if normalized(first) != normalized(results[3]["native_result"]["orders"]):
            raise ValueError("sequence_open_orders_changed")
    balances = results[1]["native_result"]["balances"]
    with localcontext() as context:
        context.prec = 80
        locks = {row["currency"]: Decimal(0) for row in balances}
        for row in first:
            remaining = Decimal(row["origQty"]) - Decimal(row["executedQty"])
            currency = "USDT" if row["side"] == "BUY" else row["symbol"][:-4]
            locks[currency] += (
                remaining * Decimal(row["price"]) if row["side"] == "BUY" else remaining
            )
        if any(locks[row["currency"]] != Decimal(row["locked"]) for row in balances):
            raise ValueError("sequence_order_locks_mismatch")


def route_result(results, bundles, modules):
    first, last = (
        results[0]["native_result"]["header_receipt"],
        results[5]["native_result"]["body_receipt"],
    )
    if (
        any(not 0 <= last[k] - first[k] <= 60_000_000_000 for k in ("utc_ns", "monotonic_ns"))
        or abs((last["utc_ns"] - first["utc_ns"]) - (last["monotonic_ns"] - first["monotonic_ns"]))
        > 50_000_000
        or first["utc_ns"] // 86_400_000_000_000 != last["utc_ns"] // 86_400_000_000_000
    ):
        raise ValueError("route_input_interval_invalid")
    payload = modules["receipt"]["payload_from_tls"](bundles[0]["tls"].encode(), results[0]["tls"])
    return modules["books"]["derive"](
        payload, results[4]["native_result"], results[5]["native_result"]
    )


def replay(raw, *, expected_sha256, bundles, modules, orders=False, routes=False, quotes=False):
    if quotes and not routes:
        raise ValueError("quote_route_required")
    orders = orders or routes
    profile = (
        QUOTE_ROUTE_PROFILE
        if quotes
        else ROUTE_PROFILE
        if routes
        else ORDER_PROFILE
        if orders
        else PROFILE
    )
    steps = ROUTE_STEPS if routes else ORDER_STEPS if orders else STEPS
    total = len(steps)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIMIT or digest(raw) != expected_sha256:
        raise ValueError("sequence_original_required")
    if not isinstance(bundles, list) or len(bundles) > total:
        raise ValueError("sequence_bundles")
    rows, previous, prefix = [], None, b""
    results, pending, accepted, selected, context = [], None, 0, None, None
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row)
            != {"seq", "previous_sha256", "kind", "utc_ns", "monotonic_ns", "profile", "payload"}
            or type(row["seq"]) is not int
            or row["seq"] != len(rows)
            or row["previous_sha256"] != previous
            or row["profile"] != profile
            or canonical(row) + b"\n" != line
        ):
            raise ValueError("sequence_chain")
        for key in ("utc_ns", "monotonic_ns"):
            if type(row[key]) is not int or row[key] <= 0 or (rows and row[key] < rows[-1][key]):
                raise ValueError("sequence_clock")
        if (
            rows
            and abs(
                (row["utc_ns"] - rows[0]["utc_ns"])
                - (row["monotonic_ns"] - rows[0]["monotonic_ns"])
            )
            > 50_000_000
        ):
            raise ValueError("sequence_clock")
        kind, value = row["kind"], row["payload"]
        stage = rows[-1]["kind"] if rows else None
        if stage is None and kind == "started":
            if not isinstance(value, dict) or set(value) != {
                "nonce",
                "base_manifest_sha256",
                "gateway_manifest_sha256",
                "tls_trust_sha256",
            }:
                raise ValueError("sequence_selection")
            if any(
                not isinstance(v, str)
                or re.fullmatch("[0-9a-f]{" + str(32 if k == "nonce" else 64) + "}", v) is None
                for k, v in value.items()
            ):
                raise ValueError("sequence_selection")
            selected = value
        elif kind == "prepared" and stage in {"started", "accepted"} and accepted < total:
            if (
                value != {"index": accepted, "step": steps[accepted]}
                or type(value["index"]) is not int
            ):
                raise ValueError("sequence_fixed_step")
            pending = accepted
            context = {"profile": profile, "index": pending, "prefix_sha256": digest(prefix + line)}
            if len(bundles) <= pending:
                raise ValueError("sequence_pending_original_required")
            bundle = bundles[pending]
            report = review_bundle(
                bundle, pending, context, selected, modules, orders=orders, routes=routes
            )
            # Every child archive follows preparation, and each whole step ends
            # before its acceptance. Original clocks never come from replay time.
            for key, content in bundle.items():
                if key in {"binding", "selection"}:
                    continue
                for child in map(json.loads, content.splitlines()):
                    if any(child[k] < row[k] for k in ("utc_ns", "monotonic_ns")):
                        raise ValueError("sequence_child_precedes_preparation")
            results.append(report)
        elif kind == "accepted" and stage == "prepared":
            if (
                value != {"index": pending, "bundle_sha256": digest(canonical(bundles[pending]))}
                or type(value["index"]) is not int
                or not results[-1]["complete"]
            ):
                raise ValueError("sequence_native_receipt_required")
            for key, content in bundles[pending].items():
                if key in {"binding", "selection"}:
                    continue
                child = json.loads(content.splitlines()[-1])
                if any(child[k] > row[k] for k in ("utc_ns", "monotonic_ns")):
                    raise ValueError("sequence_acceptance_precedes_child")
            reconcile(results, orders=orders)
            if routes and pending == 5:
                route_result(results, bundles, modules)
            # Same trust/install/rules/route/network/runtime throughout, distinct
            # child PIDs are expected. No caller-supplied run identity suffices.
            if pending:
                old, new = (json.loads(bundles[i]["binding"]) for i in (0, pending))
                for key in ("rules", "route", "net"):
                    if old[key] != new[key]:
                        raise ValueError("sequence_environment_changed")
                for key in ("native_runtime_sha256", "installation_manifest_sha256"):
                    if old["collector"]["process"][key] != new["collector"]["process"][key]:
                        raise ValueError("sequence_runtime_changed")
            accepted += 1
            pending = None
        elif (
            kind == "completed"
            and stage == "accepted"
            and accepted == total
            and value == {}
            or (
                kind == "refused"
                and stage in {"prepared", "accepted"}
                and isinstance(value, dict)
                and set(value) == {"reason"}
                and isinstance(value["reason"], str)
            )
        ):
            pass
        else:
            raise ValueError("sequence_transition")
        rows.append(row)
        prefix += line
        previous = digest(line)
    if len(bundles) != len(results):
        raise ValueError("sequence_extra_originals")
    complete = rows[-1]["kind"] == "completed"
    return {
        "schema_version": profile,
        "archive_sha256": expected_sha256,
        "status": "complete" if complete else "incomplete_no_resume",
        "prepared_steps": len(results),
        "accepted_steps": accepted,
        "pending_step": pending,
        "steps": results,
        "metadata_precision_matched": accepted > 0,
        "repeated_balances_equal": accepted >= (5 if orders else 3),
        **(
            {
                "routes_derived_from_same_run": accepted == total,
                "route_selection": route_result(results, bundles, modules)
                if accepted == total
                else None,
            }
            if routes
            else {}
        ),
        **(
            {"repeated_open_orders_equal": accepted >= 4, "open_order_locks_matched": accepted >= 3}
            if orders
            else {}
        ),
        "same_run_receipts_verified": complete,
        "atomic_account_snapshot": False,
        "stream_fence_verified": False,
        "qualified_for_execution": False,
        "network_admitted": False,
        "trading_admitted": False,
        "restart_allowed": False,
    }


class Sequence:
    def __init__(
        self, entry, authority, sources, modules, *, orders=False, routes=False, quotes=False
    ):
        if quotes and not routes:
            raise ValueError("quote_route_required")
        orders = orders or routes
        self.orders, self.routes, self.quotes = orders, routes, quotes
        self.profile = (
            QUOTE_ROUTE_PROFILE
            if quotes
            else ROUTE_PROFILE
            if routes
            else ORDER_PROFILE
            if orders
            else PROFILE
        )
        self.scope = (
            QUOTE_ROUTE_SCOPE
            if quotes
            else ROUTE_SCOPE
            if routes
            else ORDER_SCOPE
            if orders
            else SCOPE
        )
        self.steps = ROUTE_STEPS if routes else ORDER_STEPS if orders else STEPS
        self.authority, self.modules = authority, modules
        self.owner = os.getpid()
        self.expected, self.bundles, self.index = b"", [], None
        self.fds, self.held = [], {}
        self.failed = False
        self.path = Path(entry["STORAGE"]) / self.scope
        self.journal = None
        try:
            root = self.hold(Path(entry["STORAGE"]), directory=True)
            os.mkdir(self.scope, 0o700, dir_fd=root)
            os.fsync(root)
            self.directory = self.hold(self.path, directory=True)
            self.write(
                self.path / "README.md",
                b"Fixed disposable metadata/account reads and optional repeated open-order sequence. Consumed on creation; no resume. Each step uses its own expiring permission and native receipt. Next entrypoint: offline original replay; no live admission.\n",
            )
            self.journal = modules["provenance"]._Journal(
                self.path / "sequence.jsonl", limit=LIMIT, reserve=4096
            )
            self.reader = os.open(self.path / "sequence.jsonl", os.O_RDONLY | os.O_NOFOLLOW)
            self.fds.append(self.reader)
            self.journal_identity = os.fstat(self.reader)
            trust = authority.open_file("/etc/trader/egress-gateway-fixture-ca.pem", 0o444)
            self.append(
                "started",
                {
                    "nonce": os.urandom(16).hex(),
                    "base_manifest_sha256": authority.manifest_sha256,
                    "gateway_manifest_sha256": sources.manifest_sha256,
                    "tls_trust_sha256": digest(os.pread(trust, 65537, 0)),
                },
            )
        except BaseException:
            self.close()
            raise

    def write(self, path, raw):
        with path.open("xb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.hold(path)

    @staticmethod
    def identity(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_uid,
            info.st_mode,
            info.st_nlink if stat.S_ISREG(info.st_mode) else None,
        )

    def hold(self, path, *, directory=False):
        path = Path(path)
        if path in self.held:
            self.verify()
            return self.held[path][0]
        self.authority.verify()
        fd = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | (os.O_DIRECTORY if directory else 0)
        )
        self.fds.append(fd)
        info = os.fstat(fd)
        if (
            info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (
                not directory
                and (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_size > 2 * 1024 * 1024
                )
            )
        ):
            raise ValueError("sequence_original_authority")
        raw = None if directory else os.pread(fd, 2 * 1024 * 1024 + 1, 0)
        self.held[path] = (fd, self.identity(info), raw)
        return fd

    def verify(self):
        if self.failed:
            raise ValueError("sequence_authority_ended")
        try:
            return self._verify()
        except BaseException:
            self.failed = True
            raise

    def _verify(self):
        if self.journal is not None and self.journal.failed:
            raise ValueError("sequence_persistence_failed")
        if os.getpid() != self.owner:
            raise ValueError("sequence_foreign_owner")
        self.authority.verify()
        for path, (fd, identity, raw) in self.held.items():
            if (
                self.identity(os.fstat(fd)) != identity
                or self.identity(path.stat(follow_symlinks=False)) != identity
                or (raw is not None and os.pread(fd, 2 * 1024 * 1024 + 1, 0) != raw)
            ):
                raise ValueError("sequence_held_original_changed")
        info = (self.path / "sequence.jsonl").stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino)
            != (self.journal_identity.st_dev, self.journal_identity.st_ino)
            or os.pread(self.reader, LIMIT + 1, 0) != self.expected
        ):
            raise ValueError("sequence_archive_changed")
        return self.context if self.index is not None else None

    def append(self, kind, value):
        self.verify()
        row = {
            "seq": self.journal.seq,
            "previous_sha256": self.journal.previous,
            "kind": kind,
            "profile": self.profile,
            "utc_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            "payload": value,
        }
        future = self.expected + canonical(row) + b"\n"
        # Verify before persisting terminal claims. Preparation's empty bundle is
        # a conservative prefix until the child originals exist.
        replay(
            future,
            expected_sha256=digest(future),
            bundles=self.bundles,
            modules=self.modules,
            orders=self.orders,
            routes=self.routes,
            quotes=self.quotes,
        )
        self.journal.append(
            kind, **{k: v for k, v in row.items() if k not in {"seq", "previous_sha256", "kind"}}
        )
        self.expected = future
        self.verify()

    def prepare(self, index):
        self.index = None
        self.bundles.append({})
        self.append("prepared", {"index": index, "step": self.steps[index]})
        self.index = index
        self.context = {
            "profile": self.profile,
            "index": index,
            "prefix_sha256": digest(self.expected),
        }
        self.storage = self.path / self.steps[index]
        self.storage.mkdir(mode=0o700)
        os.fsync(self.directory)
        self.hold(self.storage, directory=True)
        self.write(
            self.storage / "README.md",
            b"One fixed sequence step. Isolated child and single-use attempt/kernel/TLS/native receipt originals. Next: parent sequence replay; never reopen.\n",
        )

    def bind(self, binding):
        self.verify()
        self.write(self.storage / "binding.json", canonical(binding))

    def read_bundle(self):
        kind = (
            "books"
            if self.routes and self.index == 5
            else "orders"
            if self.orders and self.index in {2, 3}
            else "account"
            if self.index
            else "metadata"
        )
        ledger = (
            self.modules[kind]["ledger_view"](self.modules["ledger"])
            if self.index
            else self.modules["ledger"]
        )
        scope = self.storage / ledger.SCOPE
        bundle = {}
        for key, name in FILES.items():
            if key == "selection" and kind in {"orders", "books"}:
                name = kind + "-request.json"
            path = self.storage / name if key == "binding" else scope / name
            if path.exists():
                self.hold(path.parent, directory=True)
                fd = self.hold(path)
                bundle[key] = os.pread(fd, 1024 * 1024 + 1, 0).decode()
        self.bundles[self.index] = bundle
        return bundle

    def close(self):
        if self.journal is not None:
            os.close(self.journal.fd)
            self.journal = None
        for fd in self.fds:
            os.close(fd)
        self.fds = []


def run_installed(
    entry,
    authority,
    sources,
    *,
    orders=False,
    routes=False,
    concurrent=False,
    signed=False,
    market=False,
    snapshot=False,
    quotes=False,
):
    if quotes and not snapshot:
        raise ValueError("quote_requires_snapshot")
    if snapshot and not market:
        raise ValueError("snapshot_requires_market")
    if market and not signed:
        raise ValueError("market_ws_requires_signed")
    if signed and not concurrent:
        raise ValueError("signed_ws_requires_concurrent")
    if concurrent and not routes:
        raise ValueError("concurrent_ws_requires_routes")
    orders = orders or routes
    sequence = None
    try:
        authority.verify()
        modules = load_sources({name: sources.source(name).decode() for name in entry["FILES"]})
        sequence = Sequence(
            entry, authority, sources, modules, orders=orders, routes=routes, quotes=quotes
        )
        try:
            for index in range(len(sequence.steps)):
                sequence.prepare(index)
                outcome = entry["run_controller"](
                    tls=True,
                    receipt=True,
                    native=True,
                    account=index != 0,
                    orders=orders and index in {2, 3},
                    books=routes and index == 5,
                    sequence=sequence,
                )
                bundle = sequence.read_bundle()
                if outcome["status"] != "fixture_receipt_succeeded" or not outcome["revoked"]:
                    raise ValueError("sequence_child_step_refused")
                sequence.append(
                    "accepted", {"index": index, "bundle_sha256": digest(canonical(bundle))}
                )
                print(json.dumps({"stage": "sequence_step_accepted", "index": index}), flush=True)
                if sys.stdin.readline() != "continue\n":
                    raise ValueError("fixture_parent_release_required")
            sequence.append("completed", {})
        except (OSError, ValueError, RuntimeError) as exc:
            with suppress(Exception):
                sequence.read_bundle()
                sequence.append("refused", {"reason": str(exc)[:160]})
            print(
                json.dumps(
                    {
                        "status": "sequence_refused",
                        "reason": str(exc)[:160],
                        "network_admitted": False,
                    }
                ),
                flush=True,
            )
        else:
            transport = None
            if concurrent:
                code = entry["load"](sources.source("gateway_concurrent_ws.py"))
                transport = code["run_installed"](
                    entry,
                    authority,
                    sources,
                    sequence,
                    signed=signed,
                    market=market,
                    snapshot=snapshot,
                    quotes=quotes,
                )
            print(
                json.dumps(
                    {
                        "status": "sequence_completed",
                        "network_admitted": False,
                        **({"concurrent_ws": transport} if concurrent else {}),
                    }
                ),
                flush=True,
            )
    finally:
        if sequence is not None:
            sequence.close()
        authority.close()

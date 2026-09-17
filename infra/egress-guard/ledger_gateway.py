"""Disposable ledger-to-kernel gateway acceptance; no deployable or venue mode."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
MARK = 0x7472
RULES = """
table inet fixture_ledger_gateway {
    set permits { type mark; flags timeout; timeout 5s; }
    counter output_denied {}
    counter forward_denied {}
    chain output {
        type filter hook output priority 50; policy drop;
        meta mark @permits ip daddr 198.51.100.2 tcp dport 23456 accept
        counter name output_denied drop
    }
    chain forward {
        type filter hook forward priority 50; policy drop;
        counter name forward_denied drop
    }
}
"""


LIFECYCLE_PROFILE = "portfolio.fixture_gateway_lifecycle.v1"
LIFECYCLE_LIMIT = 16384


def replay_lifecycle(module, raw, *, expected_sha256, attempts, binding_sha256):
    """Read selected historical bytes; never infer current kernel state or resume."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= LIFECYCLE_LIMIT:
        raise ValueError("lifecycle_archive_size")
    if module.digest(raw) != expected_sha256:
        raise ValueError("lifecycle_archive_selection")
    module.replay(attempts, expected_sha256=module.digest(attempts), binding_sha256=binding_sha256)
    prefixes = {}
    end = 0
    for line in attempts.splitlines(keepends=True):
        end += len(line)
        prefixes[module.digest(attempts[:end])] = end
    previous = last = start = stage = None
    activation = acknowledged = revoked = False
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "seq",
                "previous_sha256",
                "kind",
                "utc_ns",
                "monotonic_ns",
                "profile",
                "binding_sha256",
                "payload",
            }
            or type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous_sha256"] != previous
            or module.canonical(row) + b"\n" != line
            or row["profile"] != LIFECYCLE_PROFILE
            or row["binding_sha256"] != binding_sha256
        ):
            raise ValueError("lifecycle_chain_invalid")
        now, mono = row["utc_ns"], row["monotonic_ns"]
        if any(type(v) is not int or v <= 0 for v in (now, mono)) or (
            last
            and (
                now < last[0]
                or mono < last[1]
                or abs((now - start[0]) - (mono - start[1])) > 50_000_000
            )
        ):
            raise ValueError("lifecycle_clock_discontinuity")
        kind, payload = row["kind"], row["payload"]
        if stage is None:
            valid = kind == "started" and payload == {}
        elif kind == "activation_prepared" and stage == "started":
            valid = isinstance(payload, dict) and set(payload) == {
                "attempt_prefix_sha256",
                "mark",
                "ttl_ms",
            }
            if valid:
                selected_end = (
                    prefixes.get(payload["attempt_prefix_sha256"])
                    if isinstance(payload["attempt_prefix_sha256"], str)
                    else None
                )
                valid = (
                    type(payload["mark"]) is int
                    and payload["mark"] == MARK
                    and type(payload["ttl_ms"]) is int
                    and payload["ttl_ms"] == 5000
                    and selected_end is not None
                )
                if valid:
                    selected = attempts[:selected_end]
                    last_attempt_row = json.loads(selected.splitlines()[-1])
                    report = module.replay(
                        selected,
                        expected_sha256=module.digest(selected),
                        binding_sha256=binding_sha256,
                    )
                    valid = (
                        report["pending_attempt"] == 0
                        and report["recorded_attempts"] == 1
                        and report["status"] == "incomplete_no_resume"
                        and report["counts"][0]["caller_label"] == "collector"
                        and report["counts"][0]["role"] == "rest"
                        and last_attempt_row["utc_ns"] <= now
                        and last_attempt_row["monotonic_ns"] <= mono
                    )
            activation = bool(valid)
        elif kind == "activated" and stage == "activation_prepared":
            valid = payload == {}
            acknowledged = bool(valid)
        elif kind == "stop_requested" and stage in {"started", "activation_prepared", "activated"}:
            valid = payload == {}
        elif kind == "revoked" and stage == "stop_requested":
            valid = payload == {}
            revoked = bool(valid)
        else:
            valid = False
        if not valid:
            raise ValueError("lifecycle_transition")
        start = start or (now, mono)
        last, previous, stage = (now, mono), module.digest(line), kind
    return {
        "schema_version": LIFECYCLE_PROFILE,
        "archive_sha256": expected_sha256,
        "attempt_archive_sha256": module.digest(attempts),
        "binding_sha256": binding_sha256,
        "last_record": stage,
        "activation_prepared": activation,
        "activation_acknowledged": acknowledged,
        "revocation_recorded": revoked,
        "activation_uncertain": activation and not acknowledged,
        "current_kernel_permission": None,
        "restart_allowed": False,
        "complete_caller_coverage_verified": False,
        "network_admitted": False,
        "trading_admitted": False,
    }


class GatewayLifecycle:
    """Exclusive sibling journal, bound to the owned attempt ledger's storage."""

    def __init__(self, ledger, module):
        self.ledger, self.module = ledger, module
        self.path = ledger.path / "kernel.jsonl"
        self.closed = self.failed = False
        self.expected = b""
        ledger._storage()
        self.journal = module._Journal(self.path, limit=LIFECYCLE_LIMIT)
        self.reader = None
        try:
            self.reader = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            self.identity = os.fstat(self.reader)
            self.record("started")
        except BaseException:
            self.close()
            raise

    def record(self, kind, payload=None):
        self.ledger._owner()
        if self.closed or self.failed:
            raise ValueError("lifecycle_ended")
        try:
            self.ledger._storage()
            info = self.path.stat(follow_symlinks=False)
            if (
                (info.st_dev, info.st_ino) != (self.identity.st_dev, self.identity.st_ino)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or os.pread(self.reader, LIFECYCLE_LIMIT + 1, 0) != self.expected
            ):
                raise ValueError("lifecycle_storage_changed")
            row = {
                "seq": self.journal.seq,
                "previous_sha256": self.journal.previous,
                "kind": kind,
                "utc_ns": time.time_ns(),
                "monotonic_ns": time.monotonic_ns(),
                "profile": LIFECYCLE_PROFILE,
                "binding_sha256": self.ledger.state.binding_sha256,
                "payload": {} if payload is None else payload,
            }
            future = self.expected + self.module.canonical(row) + b"\n"
            replay_lifecycle(
                self.module,
                future,
                expected_sha256=self.module.digest(future),
                attempts=self.ledger.expected,
                binding_sha256=self.ledger.state.binding_sha256,
            )
            self.journal.append(
                kind,
                **{k: v for k, v in row.items() if k not in {"kind", "seq", "previous_sha256"}},
            )
            self.expected = future
        except BaseException:
            self.failed = True
            raise

    def prepare(self):
        self.record(
            "activation_prepared",
            {
                "attempt_prefix_sha256": self.module.digest(self.ledger.expected),
                "mark": MARK,
                "ttl_ms": 5000,
            },
        )

    def close(self):
        self.ledger._owner()
        if not self.closed:
            self.closed = True
            if self.reader is not None:
                os.close(self.reader)
            os.close(self.journal.fd)


class FixtureLedgerGateway:
    """Trusted fixture owner. Callbacks are harness code, never client inputs.

    One authenticated fixed operation. No address/payload/label from the caller,
    no socket handoff, no renewal or recovery. Real admission stays false.
    """

    def __init__(self, ledger, *, authorize, grant, send, revoke, lifecycle=None):
        self.ledger = ledger
        self.lifecycle = lifecycle
        self.authorize, self.grant, self.send, self.revoke = authorize, grant, send, revoke
        self.owner = os.getpid()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.used = self.closed = self.revocation_attempted = self.revoked = False

    def _owner(self):
        if os.getpid() != self.owner:
            raise ValueError("gateway_foreign_owner")

    def _revoke(self):
        self.stop.set()
        if not self.revocation_attempted:
            self.revocation_attempted = True
            try:
                if self.lifecycle is not None:
                    self.lifecycle.record("stop_requested")
            finally:
                self.revoke()  # Audit failure cannot suppress kernel revocation.
                self.revoked = True
            if self.lifecycle is not None:
                self.lifecycle.record("revoked")
        if not self.revoked:
            raise RuntimeError("gateway_revocation_incomplete")

    def dispatch(self):
        self._owner()
        with self.lock:
            if self.used or self.closed or self.stop.is_set():
                raise ValueError("gateway_consumed_or_stopped")
            self.used = True
            try:
                # Kernel SCM_CREDENTIALS + pidfd binding, not a supplied label.
                if self.authorize() != {"ok": True}:
                    raise ValueError("gateway_authentication_failed")
                receipt = self.ledger.prepare(caller="collector", operation="exchange_info")
                self.ledger.checkpoint()
                if self.stop.is_set():
                    raise ValueError("gateway_stop_before_grant")
                if self.lifecycle is not None:
                    self.lifecycle.prepare()
                    self.ledger.checkpoint()
                    if self.stop.is_set():
                        raise ValueError("gateway_stop_before_grant")
                self.grant()
                if self.lifecycle is not None:
                    self.lifecycle.record("activated")
                self.ledger.checkpoint()
                if self.stop.is_set():
                    raise ValueError("gateway_stop_before_send")
                result = self.send()  # Owned fixed socket; never returned to client.
                self.ledger.outcome(
                    index=receipt["index"], result="succeeded" if result else "failed"
                )
                if not result:
                    raise RuntimeError("gateway_transport_failed")
                return {"fixture_sent": True, "network_admitted": False}
            finally:
                # Pending preparation remains uncertain if any step above raises.
                self._revoke()

    def shutdown(self):
        self._owner()
        self.stop.set()  # Do not let queued dispatch overtake revocation.
        with self.lock:
            self._revoke()

    def close(self):
        self._owner()
        self.stop.set()
        with self.lock:
            if self.closed:
                return
            try:
                self._revoke()
            finally:
                self.closed = True
                try:
                    if self.lifecycle is not None:
                        self.lifecycle.close()
                finally:
                    self.ledger.close()


def load(source):
    scope = {"__name__": "ledger_gateway_dependency"}
    exec(compile(source, "<fixture-dependency>", "exec"), scope)
    return scope


def load_ledger(sources):
    # Embed exact project bytes without enabling repository/site imports in -I.
    for name in ("apps", "apps.strategies_nautilus"):
        package = types.ModuleType(name)
        package.__path__ = []
        sys.modules[name] = package
    for short in ("portfolio_rate_evidence", "portfolio_tls_provenance", "portfolio_egress_ledger"):
        name = "apps.strategies_nautilus." + short
        module = types.ModuleType(name)
        sys.modules[name] = module
        exec(compile(sources[short + ".py"], "<" + short + ">", "exec"), module.__dict__)
    return module


def marked_echo():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.6)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, MARK)
        connection.connect(("198.51.100.2", 23456))
        connection.sendall(b"fixture-echo\n")
        result = bytearray()
        while len(result) < len(b"fixture-echo\n"):
            chunk = connection.recv(128)
            if not chunk:
                break
            result.extend(chunk)
        return result == b"fixture-echo\n"


def worker(payload):
    def expired(_signum, _frame):
        raise TimeoutError("ledger_gateway_fixture_deadline")

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(70)
    guards = load(payload["sources"]["selftest.py"])
    guards["require_isolation"](payload["original"])
    launch = load(payload["sources"]["collector_launcher.py"])
    identity = load(payload["sources"]["inspect_binding.py"])
    ledger_module = load_ledger(payload["sources"])
    run, ip, nft = guards["run"], guards["IP"], guards["NFT"]
    run("/usr/bin/mount", "-t", "tmpfs", "-o", "size=2m,nosuid,nodev,noexec", "tmpfs", "/tmp")
    children = []
    reports, checks = [], []
    try:
        peer = guards["Child"](payload["sources"]["selftest.py"])
        children.append(peer)
        client = guards["Child"](payload["sources"]["selftest.py"])
        children.append(client)
        run(ip, "link", "set", "lo", "up")
        for local, remote, child, subnet in (
            ("wan", "peer", peer, "198.51.100"),
            ("lan", "client", client, "192.0.2"),
        ):
            run(ip, "link", "add", local, "type", "veth", "peer", "name", remote)
            run(ip, "link", "set", remote, "netns", str(child.process.pid))
            run(ip, "link", "set", local, "up")
            run(ip, "address", "add", subnet + ".1/24", "dev", local)
            child.ip("link", "set", remote, "up")
            child.ip("address", "add", subnet + ".2/24", "dev", remote)
        peer.ip("address", "add", "198.51.100.3/24", "dev", "peer")
        client.ip("route", "add", "198.51.100.0/24", "via", "192.0.2.1")
        peer.ip("route", "add", "192.0.2.0/24", "via", "198.51.100.1")
        run(ip, "-6", "address", "add", "fd00:7472:2::1/64", "dev", "wan", "nodad")
        peer.ip("-6", "address", "add", "fd00:7472:2::2/64", "dev", "peer", "nodad")
        peer.ip("-6", "address", "add", "fd00:7472:2::3/64", "dev", "peer", "nodad")
        Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
        if peer.request({"action": "serve"}) != {"ok": True}:
            raise RuntimeError("peer_not_ready")
        host = guards["Probe"]()
        request = {"action": "once", "key": "fixture", "address": "198.51.100.2"}
        if not host.request(request)["ok"] or not client.request(request)["ok"]:
            raise RuntimeError("baseline_fixture_connectivity_missing")
        checks.append("local_host_and_forwarded_baselines_reach_peer")
        run(nft, "-f", "-", text=RULES)

        def counter(name):
            rows = json.loads(
                run(nft, "-j", "list", "counter", "inet", "fixture_ledger_gateway", name)
            )
            return next(r["counter"]["packets"] for r in rows["nftables"] if "counter" in r)

        def denied(name, actor, command, field):
            before = counter(field)
            if actor.request(command)["ok"] or counter(field) <= before:
                raise RuntimeError(name + "_not_kernel_denied")
            checks.append(name)

        denied("unrecorded_host_denied", host, request, "output_denied")
        denied("unrecorded_forwarding_denied", client, request, "forward_denied")
        denied(
            "ipv6_fallback_denied", host, {**request, "address": "fd00:7472:2::2"}, "output_denied"
        )

        def revoke():
            run(nft, "flush", "set", "inet", "fixture_ledger_gateway", "permits")
            rows = json.loads(
                run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("kernel_revocation_failed")

        def grant():
            run(
                nft,
                "-f",
                "-",
                text=f"add element inet fixture_ledger_gateway permits {{ {MARK} timeout 5s }}\n",
            )

        def exercise(scenario):
            collector = launch["FixtureCollector"](
                payload["sources"]["collector_launcher.py"], identity["process_identity"]
            )
            root = Path("/tmp/" + scenario)
            root.mkdir(mode=0o700)
            (root / "README.md").write_text(
                "Disposable gateway acceptance scope. No resume. Next: offline replay.\n"
            )
            gateway = writer = None
            try:

                class Binding:
                    ended = False

                    def current(self):
                        collector.verify()
                        rules = guards["stable_rules"](
                            json.loads(
                                run(nft, "-j", "list", "table", "inet", "fixture_ledger_gateway")
                            )
                        )
                        for row in rules["nftables"]:
                            if "set" in row:
                                row["set"].pop("elem", None)
                        return {
                            "collector": collector.selected,
                            "rules": rules,
                            "route": json.loads(run(ip, "-j", "route", "get", "198.51.100.2")),
                            "net": os.readlink("/proc/self/ns/net"),
                        }

                    def verify(self):
                        if self.ended:
                            raise ValueError("fixture_binding_ended")
                        try:
                            if self.current() != selected:
                                raise ValueError("fixture_binding_drift")
                            return {"binding_sha256": pin}
                        except BaseException:
                            self.ended = True
                            raise

                binding = Binding()
                selected = binding.current()
                pin = ledger_module.digest(ledger_module.canonical(selected))
                (root / "binding.json").write_text(json.dumps(selected, sort_keys=True))
                writer = ledger_module.AttemptLedger(root, binding=binding, binding_sha256=pin)
                lifecycle = GatewayLifecycle(writer, ledger_module)
                original_record = lifecycle.record

                def record(kind, payload=None):
                    original_record(kind, payload)
                    if scenario == "crash_before_grant" and kind == "activation_prepared":
                        os.kill(os.getpid(), signal.SIGKILL)

                lifecycle.record = record
                sent = []
                entered, release = threading.Event(), threading.Event()

                def send():
                    if scenario == "crash_before_send":
                        os.kill(os.getpid(), signal.SIGKILL)
                    # Assert the persisted on-disk prefix immediately at transport entry.
                    raw = (writer.path / "events.jsonl").read_bytes()
                    before = ledger_module.replay(
                        raw, expected_sha256=ledger_module.digest(raw), binding_sha256=pin
                    )
                    if before["pending_attempt"] != 0 or before["recorded_attempts"] != 1:
                        raise RuntimeError("send_without_durable_preparation")
                    sent.append(True)
                    if scenario == "success":
                        denied(
                            "unmarked_host_denied_while_permit_active",
                            host,
                            request,
                            "output_denied",
                        )
                        denied(
                            "forwarded_client_denied_while_permit_active",
                            client,
                            request,
                            "forward_denied",
                        )
                    if scenario == "concurrent_stop":
                        entered.set()
                        if not release.wait(2):
                            raise RuntimeError("send_not_released")
                    return marked_echo()

                def selected_grant():
                    grant()
                    if scenario == "crash_after_grant":
                        os.kill(os.getpid(), signal.SIGKILL)
                    if scenario == "rule_drift_after_grant":
                        run(nft, "add", "counter", "inet", "fixture_ledger_gateway", "unexpected")

                def selected_revoke():
                    revoke()
                    if scenario == "crash_after_revoke":
                        os.kill(os.getpid(), signal.SIGKILL)

                gateway = FixtureLedgerGateway(
                    writer,
                    authorize=collector.observe,
                    grant=selected_grant,
                    send=send,
                    revoke=selected_revoke,
                    lifecycle=lifecycle,
                )
                original_prepare = writer.prepare

                def prepared(**kwargs):
                    result = original_prepare(**kwargs)
                    if scenario == "stop_after_prepare":
                        gateway.stop.set()
                    elif scenario == "rule_drift":
                        run(nft, "add", "counter", "inet", "fixture_ledger_gateway", "unexpected")
                    return result

                writer.prepare = prepared
                original_sync = os.fsync
                syncs = 0

                def fail_sync(fd):
                    nonlocal syncs
                    if fd == writer.journal.fd:
                        syncs += 1
                        if syncs == 2:
                            raise OSError("fixture_preparation_fsync_failed")
                    return original_sync(fd)

                if scenario == "fsync_failure":
                    os.fsync = fail_sync
                try:
                    if scenario == "concurrent_stop":
                        with ThreadPoolExecutor(max_workers=3) as pool:
                            active = pool.submit(gateway.dispatch)
                            try:
                                if not entered.wait(2):
                                    raise RuntimeError("send_not_entered")
                                stopping = pool.submit(gateway.shutdown)
                                if not gateway.stop.wait(2):
                                    raise RuntimeError("stop_not_requested")
                                queued = pool.submit(gateway.dispatch)
                            finally:
                                release.set()
                            if not active.result(timeout=3)["fixture_sent"]:
                                raise RuntimeError("active_send_missing")
                            stopping.result(timeout=3)
                            try:
                                queued.result(timeout=3)
                            except ValueError:
                                checks.append("queued_send_refused_after_concurrent_stop")
                            else:
                                raise RuntimeError("queued_send_executed")
                    elif scenario == "success" or scenario.startswith("crash_"):
                        if not gateway.dispatch()["fixture_sent"]:
                            raise RuntimeError("success_send_missing")
                    else:
                        try:
                            gateway.dispatch()
                        except (ValueError, OSError):
                            pass
                        else:
                            raise RuntimeError("fault_did_not_stop_dispatch")
                finally:
                    os.fsync = original_sync
                if (
                    len(sent) != int(scenario in {"success", "concurrent_stop"})
                    or not gateway.revoked
                ):
                    raise RuntimeError("send_or_revocation_count_mismatch")
                checks.append(scenario + "_durable_dispatch_or_refusal")
                with suppress(ValueError):
                    gateway.close()
                raw = (writer.path / "events.jsonl").read_bytes()
                replay = ledger_module.replay(
                    raw, expected_sha256=ledger_module.digest(raw), binding_sha256=pin
                )
                reports.append(
                    {
                        "scenario": scenario,
                        "binding_sha256": pin,
                        "binding": selected,
                        "archive": raw.decode(),
                        "replay": replay,
                        "sent": len(sent),
                        "revoked": gateway.revoked,
                        "lifecycle_archive": lifecycle.path.read_text(),
                        "lifecycle_replay": replay_lifecycle(
                            ledger_module,
                            lifecycle.path.read_bytes(),
                            expected_sha256=ledger_module.digest(lifecycle.path.read_bytes()),
                            attempts=raw,
                            binding_sha256=pin,
                        ),
                    }
                )
                try:
                    ledger_module.AttemptLedger(root, binding=binding, binding_sha256=pin)
                except FileExistsError:
                    checks.append(scenario + "_scope_reopen_refused")
                else:
                    raise RuntimeError("scope_reopened")
            finally:
                if gateway is not None:
                    with suppress(Exception):
                        gateway.close()
                elif writer is not None:
                    with suppress(Exception):
                        writer.close()
                collector.close()
                if scenario in {"rule_drift", "rule_drift_after_grant"}:
                    run(nft, "delete", "counter", "inet", "fixture_ledger_gateway", "unexpected")

        for scenario in (
            "success",
            "concurrent_stop",
            "stop_after_prepare",
            "rule_drift",
            "rule_drift_after_grant",
            "fsync_failure",
        ):
            exercise(scenario)
        for scenario in (
            "crash_before_grant",
            "crash_after_grant",
            "crash_before_send",
            "crash_after_revoke",
        ):
            pid = os.fork()
            if pid == 0:
                try:
                    exercise(scenario)
                finally:
                    os._exit(3)
            _, status = os.waitpid(pid, 0)
            if not os.WIFSIGNALED(status) or os.WTERMSIG(status) != signal.SIGKILL:
                raise RuntimeError("controller_did_not_die_at_crash_stage")
            rows = json.loads(
                run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            active = any(row.get("set", {}).get("elem") for row in rows["nftables"])
            if active != (scenario in {"crash_after_grant", "crash_before_send"}):
                raise RuntimeError("unexpected_post_crash_kernel_permission")
            if active:
                time.sleep(5.2)  # Kernel timeout, no controller cleanup or renewal.
            before = counter("output_denied")
            try:
                marked_echo()
            except OSError:
                pass
            else:
                raise RuntimeError("marked_sender_survived_crash_expiry")
            if counter("output_denied") <= before:
                raise RuntimeError("crash_expiry_not_kernel_denied")
            checks.append(scenario + "_kernel_denied_without_controller_cleanup")
            root = Path("/tmp/" + scenario)
            selected = json.loads((root / "binding.json").read_bytes())
            pin = ledger_module.digest(ledger_module.canonical(selected))
            scope = root / ledger_module.SCOPE
            raw = (scope / "events.jsonl").read_bytes()
            kernel = (scope / "kernel.jsonl").read_bytes()
            report = replay_lifecycle(
                ledger_module,
                kernel,
                expected_sha256=ledger_module.digest(kernel),
                attempts=raw,
                binding_sha256=pin,
            )
            if report["revocation_recorded"]:
                raise RuntimeError("crash_invented_durable_revocation")
            reports.append(
                {
                    "scenario": scenario,
                    "binding": selected,
                    "binding_sha256": pin,
                    "archive": raw.decode(),
                    "replay": ledger_module.replay(
                        raw, expected_sha256=ledger_module.digest(raw), binding_sha256=pin
                    ),
                    "lifecycle_archive": kernel.decode(),
                    "lifecycle_replay": report,
                    "controller_sigkill": True,
                    "permit_present_after_death": active,
                    "marked_probe_denied_after_expiry": True,
                }
            )
            try:
                ledger_module.AttemptLedger(root, binding=None, binding_sha256=pin)
            except FileExistsError:
                checks.append(scenario + "_scope_reopen_refused")
            else:
                raise RuntimeError("crashed_scope_reopened")
        denied("unrecorded_host_denied_after_revocation", host, request, "output_denied")
        # An unprivileged process in the gateway namespace cannot manufacture a marked socket.
        probe = "import socket\ns=socket.socket()\ntry:\n s.setsockopt(socket.SOL_SOCKET,socket.SO_MARK,29810)\nexcept PermissionError:\n print('denied')\nelse:\n raise SystemExit(3)\n"
        result = run(
            "/usr/bin/setpriv",
            "--bounding-set=-all",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--no-new-privs",
            "/usr/bin/python3",
            "-I",
            "-c",
            probe,
        )
        if result.strip() != "denied":
            raise RuntimeError("mark_forgery_not_denied")
        checks.append("capability_dropped_process_cannot_forge_socket_mark")
        return {
            "status": "passed",
            "checks": checks,
            "scenarios": reports,
            "source_sha256": {
                k: hashlib.sha256(v.encode()).hexdigest() for k, v in payload["sources"].items()
            },
            "host_firewall_modified": False,
            "external_requests": 0,
            "gateway_coverage_qualified": False,
            "network_admitted": False,
            "trading_admitted": False,
            "uncontrolled_privileged_mutation_race_closed": False,
        }
    finally:
        for child in reversed(children):
            child.stop()
        signal.alarm(0)


def main():
    if len(sys.argv) != 1 or os.geteuid() == 0:
        print("Run as an ordinary user with no arguments.", file=sys.stderr)
        return 2
    directory = Path(__file__).resolve().parent
    sources = {
        name: (directory / name).read_text()
        for name in (
            "ledger_gateway.py",
            "selftest.py",
            "collector_launcher.py",
            "inspect_binding.py",
        )
    }
    for name in ("portfolio_rate_evidence", "portfolio_tls_provenance", "portfolio_egress_ledger"):
        sources[name + ".py"] = (
            directory.parents[1] / "apps/strategies_nautilus" / (name + ".py")
        ).read_text()
    original = {
        name: os.readlink("/proc/self/ns/" + name) for name in ("user", "net", "mnt", "pid")
    }
    bootstrap = (
        "import json,sys\npayload=json.load(sys.stdin)\nscope={'__name__':'gateway_fixture'}\n"
        "exec(compile(payload['sources']['ledger_gateway.py'],'<gateway>','exec'),scope)\n"
        "print(json.dumps(scope['worker'](payload),sort_keys=True))\n"
    )
    process = subprocess.Popen(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--mount",
            "--net",
            "--pid",
            "--fork",
            "--kill-child",
            "--mount-proc",
            "--propagation",
            "private",
            "/usr/bin/python3",
            "-I",
            "-c",
            bootstrap,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(
            json.dumps({"sources": sources, "original": original}), timeout=75
        )
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if original != {name: os.readlink("/proc/self/ns/" + name) for name in original}:
        raise RuntimeError("caller_namespace_changed")
    if process.returncode:
        print(stderr.strip(), file=sys.stderr)
        return 1
    print(stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Disposable ledger-to-kernel gateway acceptance; no deployable or venue mode."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
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


class FixtureLedgerGateway:
    """Trusted fixture owner. Callbacks are harness code, never client inputs.

    One authenticated fixed operation. No address/payload/label from the caller,
    no socket handoff, no renewal or recovery. Real admission stays false.
    """

    def __init__(self, ledger, *, authorize, grant, send, revoke):
        self.ledger = ledger
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
            self.revoke()  # Audit failure cannot suppress kernel revocation.
            self.revoked = True
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
                self.grant()
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
    signal.alarm(40)
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
                writer = ledger_module.AttemptLedger(root, binding=binding, binding_sha256=pin)
                sent = []
                entered, release = threading.Event(), threading.Event()

                def send():
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
                    if scenario == "rule_drift_after_grant":
                        run(nft, "add", "counter", "inet", "fixture_ledger_gateway", "unexpected")

                gateway = FixtureLedgerGateway(
                    writer,
                    authorize=collector.observe,
                    grant=selected_grant,
                    send=send,
                    revoke=revoke,
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
                    elif scenario == "success":
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
            json.dumps({"sources": sources, "original": original}), timeout=45
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

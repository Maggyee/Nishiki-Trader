#!/usr/bin/python3 -I
"""Exercise egress hooks inside disposable user/network/mount/PID namespaces only."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
IP = "/usr/sbin/ip"
NFT = "/usr/sbin/nft"
PYTHON = "/usr/bin/python3"
PORT = 23456
NAMESPACES = ("user", "net", "mnt", "pid")
EARLY_RULES = """
table inet fixture_early {
    chain output {
        type filter hook output priority 0; policy accept;
        counter accept
    }
    chain forward {
        type filter hook forward priority 0; policy accept;
        counter accept
    }
}
"""
# Literal fixture addresses only. This is NOT a deployable provider allowlist.
GUARD_RULES = """
table inet trader_fixture_guard {
    counter output4 {}
    counter output6 {}
    counter forward4 {}
    counter forward6 {}
    counter spoof4 {}
    counter spoof6 {}
    chain output {
        type filter hook output priority 10; policy accept;
        ip daddr 198.51.100.2 tcp dport 23456 counter name output4 drop
        ip6 daddr fd00:7472:2::2 tcp dport 23456 counter name output6 drop
    }
    chain forward {
        type filter hook forward priority 10; policy accept;
        iifname "br-fixture" ip saddr != 192.0.2.2 counter name spoof4 drop
        iifname "br-fixture" ip6 saddr != fd00:7472:1::2 counter name spoof6 drop
        ip daddr 198.51.100.2 tcp dport 23456 counter name forward4 drop
        ip6 daddr fd00:7472:2::2 tcp dport 23456 counter name forward6 drop
    }
}
"""

# A separate IPv4-only fixture identity. No real egress address is selected here.
LEASE_RULES = """
table inet fixture_lease {
    set destinations {
        type ipv4_addr
        flags timeout
        timeout 30s
    }
    counter denied {}
    chain output {
        type filter hook output priority 20; policy accept;
        ip daddr 198.51.100.2 tcp dport 23456 counter name denied drop
    }
    chain forward {
        type filter hook forward priority 20; policy drop;
        iifname "br-fixture" ip saddr 192.0.2.2 ip daddr @destinations tcp dport 23456 accept
        iifname "wan" ip saddr 198.51.100.2 ip daddr 192.0.2.2 tcp sport 23456 accept
        counter name denied drop
    }
}
"""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FixtureDispatchGuard:
    """Bounded local supervisor exercise; NOT a production lease or quota authority."""

    def __init__(self, path: Path, *, selected: dict, observe, actor):
        self.path, self.observe, self.actor = path, observe, actor
        self.selected = canonical(selected)
        self.lock = threading.Lock()
        self.owner_pid = os.getpid()
        self.stop_requested = threading.Event()
        self.halted = False
        self.closed = False
        self.attempts = 0
        self.expected = b""
        self.fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600)

    def verify_journal(self):
        self.check_owner()
        held, current = os.fstat(self.fd), self.path.stat(follow_symlinks=False)
        if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError("fixture_audit_replaced")
        if held.st_size != len(self.expected) or os.pread(self.fd, 65536, 0) != self.expected:
            raise RuntimeError("fixture_audit_gap_or_rewrite")

    def check_owner(self):
        if os.getpid() != self.owner_pid:
            raise RuntimeError("fixture_controller_process_changed")

    def halt_after_failure(self):
        self.halted = True

    def append(self, kind: str):
        self.verify_journal()
        row = (
            canonical(
                {
                    "kind": kind,
                    "attempt": self.attempts,
                    "monotonic_ns": time.monotonic_ns(),
                    "identity_sha256": hashlib.sha256(self.selected).hexdigest(),
                    "previous_sha256": hashlib.sha256(self.expected).hexdigest(),
                }
            )
            + b"\n"
        )
        if len(self.expected) + len(row) > 65536:
            raise RuntimeError("fixture_audit_bound")
        remaining = row
        while remaining:
            written = os.write(self.fd, remaining)
            if written <= 0:
                raise OSError("fixture_audit_short_write")
            remaining = remaining[written:]
        os.fsync(self.fd)
        self.expected += row

    def dispatch(self):
        # The worker owns the client; concurrent callers cannot interleave local records.
        self.check_owner()  # Before locking: fork may inherit a permanently held lock.
        with self.lock:
            if self.halted or self.stop_requested.is_set():
                raise RuntimeError("fixture_dispatch_halted")
            try:
                self.verify_journal()
                if canonical(self.observe()) != self.selected:
                    raise RuntimeError("fixture_identity_or_guard_changed")
                if self.attempts >= 4:
                    raise RuntimeError("fixture_attempt_bound")
                self.attempts += 1  # Failed/uncertain preparation is never refunded.
                self.append("prepared")
                if canonical(self.observe()) != self.selected:
                    raise RuntimeError("fixture_changed_during_preparation")
                self.verify_journal()
                result = self.actor.request(
                    {
                        "action": "once",
                        "key": "lease",
                        "address": "198.51.100.2",
                        "source": "192.0.2.2",
                    }
                )
                if not result["ok"]:
                    self.append("failed")
                    raise RuntimeError("fixture_transport_failed")
                if canonical(self.observe()) != self.selected:
                    raise RuntimeError("fixture_changed_during_transport")
                self.append("succeeded")
                return result
            except BaseException:
                # An incomplete prepared record retains the uncertain attempt.
                self.halt_after_failure()
                raise

    def close(self):
        self.check_owner()
        self.stop_requested.set()
        with self.lock:
            self.halted = True
            if not self.closed:
                self.closed = True
                os.close(self.fd)


class ControlledFixtureGuard(FixtureDispatchGuard):
    """One trusted owner serializes sends and terminal permission revocation."""

    def __init__(self, path: Path, *, selected: dict, observe, actor, revoke):
        super().__init__(path, selected=selected, observe=observe, actor=actor)
        self.revoke = revoke
        self.revocation_attempted = self.revoked = False

    def revoke_under_lock(self):
        self.halted = True
        if self.revocation_attempted:
            if not self.revoked:
                raise RuntimeError("fixture_revocation_incomplete")
            return
        self.revocation_attempted = True
        # Journal failure must not prevent attempting the kernel deny operation.
        try:
            self.append("stop_requested")
        finally:
            self.revoke()
            self.revoked = True
        self.append("revoked")

    def shutdown(self):
        self.check_owner()
        self.stop_requested.set()  # Reject queued sends even before we acquire the lock.
        with self.lock:
            self.revoke_under_lock()

    def halt_after_failure(self):
        self.stop_requested.set()
        self.revoke_under_lock()

    def close(self):
        try:
            self.shutdown()
        finally:
            super().close()


def run(*args: str, text: str | None = None) -> str:
    result = subprocess.run(
        args, input=text, text=True, capture_output=True, env=ENV, cwd="/", timeout=10
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def namespace_ids() -> dict[str, str]:
    return {name: os.readlink(f"/proc/self/ns/{name}") for name in NAMESPACES}


def require_isolation(original: dict[str, str]) -> None:
    current = namespace_ids()
    if any(current[name] == original[name] for name in NAMESPACES):
        raise RuntimeError("Refusing to mutate a namespace inherited from the caller")
    links = json.loads(run(IP, "-j", "link", "show"))
    if [link["ifname"] for link in links] != ["lo"]:
        raise RuntimeError("Fresh fixture namespace must contain loopback only")
    for family in ("-4", "-6"):
        if json.loads(run(IP, family, "-j", "route", "show", "table", "all")):
            raise RuntimeError("Fresh fixture namespace unexpectedly has routes")
    rules = json.loads(run(NFT, "-j", "list", "ruleset"))
    if any("metainfo" not in entry for entry in rules["nftables"]):
        raise RuntimeError("Fresh fixture namespace unexpectedly has firewall rules")


class Probe:
    def __init__(self) -> None:
        self.connections: dict[str, socket.socket] = {}

    def request(self, request: dict) -> dict:
        action = request["action"]
        if action == "check_authority":
            status = dict(
                line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines()
            )
            blocked = []
            for command in (
                (IP, "route", "del", "198.51.100.0/24"),
                ("/usr/bin/nsenter", "--target", "1", "--net", IP, "link", "show"),
            ):
                result = subprocess.run(command, capture_output=True, text=True, env=ENV, timeout=3)
                blocked.append(
                    result.returncode != 0
                    and any(
                        reason in result.stderr
                        for reason in ("Operation not permitted", "Permission denied")
                    )
                )
            return {
                "caps": {
                    k: int(status[k], 16)
                    for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb")
                },
                "no_new_privs": int(status["NoNewPrivs"]),
                "admin_calls_blocked": blocked,
            }
        if action == "serve":
            for family, address in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
                listener = socket.socket(family, socket.SOCK_STREAM)
                if family == socket.AF_INET6:
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind((address, PORT))
                listener.listen(16)
                threading.Thread(target=self.accept, args=(listener,), daemon=True).start()
            return {"ok": True}
        if action == "close":
            for connection in self.connections.values():
                connection.close()
            self.connections.clear()
            return {"ok": True}
        key = request["key"]
        connection = None
        try:
            if action in ("once", "open"):
                family = socket.AF_INET6 if ":" in request["address"] else socket.AF_INET
                connection = socket.socket(family, socket.SOCK_STREAM)
                connection.settimeout(0.6)
                if request.get("source"):
                    connection.bind((request["source"], 0))
                connection.connect((request["address"], PORT))
            elif action == "send":
                connection = self.connections[key]
            else:
                raise ValueError("Unknown probe action")
            payload = b"fixture-echo\n"
            connection.sendall(payload)
            received = b""
            while len(received) < len(payload):
                chunk = connection.recv(len(payload) - len(received))
                if not chunk:
                    break
                received += chunk
            if received != payload:
                raise RuntimeError("Fixture echo mismatch")
            if action == "open":
                self.connections[key] = connection
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__}
        finally:
            if connection is not None and (
                action == "once" or (action == "open" and key not in self.connections)
            ):
                connection.close()

    @staticmethod
    def echo(connection: socket.socket) -> None:
        with connection:
            connection.settimeout(30)
            try:
                while data := connection.recv(64):
                    connection.sendall(data)
            except OSError:
                pass

    @classmethod
    def accept(cls, listener: socket.socket) -> None:
        while True:
            connection, _ = listener.accept()
            threading.Thread(target=cls.echo, args=(connection,), daemon=True).start()


def child_loop() -> None:
    probe = Probe()
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        print(json.dumps(probe.request(json.loads(line))), flush=True)


def embedded(source: str, entrypoint: str) -> str:
    return (
        "scope = {'__name__': 'trader_fixture'}\n"
        f"exec(compile({source!r}, '<trader-fixture>', 'exec'), scope)\n" + entrypoint
    )


class Child:
    def __init__(self, source: str) -> None:
        self.process = subprocess.Popen(
            [
                "/usr/bin/unshare",
                "--net",
                "/usr/bin/setpriv",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                PYTHON,
                "-I",
                "-c",
                embedded(source, "scope['child_loop']()"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=ENV,
            cwd="/",
        )
        if json.loads(self.process.stdout.readline()) != {"ready": True}:
            raise RuntimeError("Fixture child did not start")

    def ip(self, *args: str) -> str:
        return run("/usr/bin/nsenter", "-t", str(self.process.pid), "--net", IP, *args)

    def request(self, request: dict) -> dict:
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def stop(self) -> None:
        # PID-namespace init can pass ignored SIGTERM dispositions to children.
        # EOF lets the fixed command loop finish; kill remains a bounded fallback.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)


def counters() -> dict[str, int]:
    entries = json.loads(run(NFT, "-j", "list", "table", "inet", "trader_fixture_guard"))
    return {
        entry["counter"]["name"]: entry["counter"]["packets"]
        for entry in entries["nftables"]
        if "counter" in entry
    }


def early_structure() -> list[dict]:
    entries = json.loads(run(NFT, "-j", "list", "table", "inet", "fixture_early"))
    result = []
    for entry in entries["nftables"]:
        if "metainfo" in entry:
            continue
        for expression in entry.get("rule", {}).get("expr", []):
            if "counter" in expression:
                expression["counter"] = {}  # Traffic changes counters, not the earlier policy.
        result.append(entry)
    return result


def lease_checks(client: Child, host: Probe) -> tuple[list[str], list[str]]:
    """Actual kernel expiry plus observed-state/audit refusal; no atomicity claim."""
    checks = []
    # /tmp is mounted only in the private mount namespace already verified by worker.
    run("/usr/bin/mount", "-t", "tmpfs", "-o", "size=1m,nosuid,nodev,noexec", "tmpfs", "/tmp")
    run(NFT, "-f", "-", text=LEASE_RULES)

    def grant(duration="20s"):
        run(NFT, "flush", "set", "inet", "fixture_lease", "destinations")
        run(
            NFT,
            "-f",
            "-",
            text=(
                "add element inet fixture_lease destinations "
                "{ 198.51.100.2 timeout " + duration + " }\n"
            ),
        )

    def snapshot():
        def stable(value):
            if isinstance(value, dict):
                return {
                    k: stable(v)
                    for k, v in value.items()
                    if k not in {"metainfo", "expires", "packets", "bytes"}
                }
            if isinstance(value, list):
                return [stable(v) for v in value if not (isinstance(v, dict) and "metainfo" in v)]
            return value

        return {
            "rules": stable(json.loads(run(NFT, "-j", "list", "table", "inet", "fixture_lease"))),
            "route": json.loads(client.ip("-j", "route", "get", "198.51.100.2")),
            "namespace": os.readlink(f"/proc/{client.process.pid}/ns/net"),
            "source": "192.0.2.2",
        }

    def denied_packets():
        rows = json.loads(run(NFT, "-j", "list", "counter", "inet", "fixture_lease", "denied"))
        return next(e["counter"]["packets"] for e in rows["nftables"] if "counter" in e)

    def denied(name, actor, *, action="once", address="198.51.100.2", source_ip=None, record=True):
        before = denied_packets()
        result = actor.request(
            {"action": action, "key": "expiry", "address": address, "source": source_ip}
        )
        if result["ok"] or denied_packets() <= before:
            raise RuntimeError(f"{name}: expected a kernel-counted refusal")
        if record:
            checks.append(name)

    denied("lease_absent_blocks", client)
    grant()
    denied("lease_rejects_host_caller", host)
    denied("lease_rejects_spoofed_source", client, source_ip="192.0.2.99")
    denied("lease_rejects_ipv6_fallback", client, address="fd00:7472:2::2")

    class CountedActor:
        calls = 0

        def request(self, request):
            self.calls += 1
            return client.request(request)

    def exercise_loss(name, mutate, restore):
        grant()
        actor = CountedActor()
        guard = FixtureDispatchGuard(
            Path("/tmp/" + name), selected=snapshot(), observe=snapshot, actor=actor
        )
        try:
            guard.dispatch()
            checks.append(name + "_initial_dispatch")
            mutate(guard)
            try:
                guard.dispatch()
            except (RuntimeError, OSError):
                pass
            else:
                raise RuntimeError(name + ": loss was not detected")
            if actor.calls != 1 or not guard.halted or guard.attempts != 1:
                raise RuntimeError(name + ": loss triggered another transport call")
            checks.append(name + "_blocks_before_transport")
            restore()
            try:
                guard.dispatch()
            except RuntimeError as exc:
                if str(exc) != "fixture_dispatch_halted":
                    raise
            else:
                raise RuntimeError(name + ": restoration reset the halt")
            checks.append(name + "_restoration_keeps_halt")
        finally:
            guard.close()

    exercise_loss(
        "lease_table_removed",
        lambda _guard: run(NFT, "delete", "table", "inet", "fixture_lease"),
        lambda: run(NFT, "-f", "-", text=LEASE_RULES),
    )
    exercise_loss(
        "lease_route_changed",
        lambda _guard: client.ip(
            "route", "replace", "198.51.100.0/24", "via", "192.0.2.1", "src", "192.0.2.99"
        ),
        lambda: client.ip("route", "replace", "198.51.100.0/24", "via", "192.0.2.1"),
    )
    exercise_loss("lease_audit_gap", lambda guard: os.ftruncate(guard.fd, 0), lambda: None)
    exercise_loss(
        "lease_revoked",
        lambda _guard: run(NFT, "flush", "set", "inet", "fixture_lease", "destinations"),
        grant,
    )
    # Expose the remaining race honestly: a privileged deletion after the final
    # observation can permit a send. A post-send check can only mark it uncertain.
    grant()

    class DeleteDuringSend(CountedActor):
        def request(self, request):
            run(NFT, "delete", "table", "inet", "fixture_lease")
            result = super().request(request)
            if not result["ok"]:
                raise AssertionError("Race fixture did not reach the local peer")
            return result

    race_actor = DeleteDuringSend()
    race_guard = FixtureDispatchGuard(
        Path("/tmp/lease-race"), selected=snapshot(), observe=snapshot, actor=race_actor
    )
    try:
        try:
            race_guard.dispatch()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Race did not invalidate the completed send")
        rows = [json.loads(row) for row in race_guard.path.read_bytes().splitlines()]
        if (
            race_actor.calls != 1
            or not race_guard.halted
            or [r["kind"] for r in rows] != ["prepared"]
        ):
            raise RuntimeError("Race must retain one uncertain preparation")
        checks.append("lease_privileged_deletion_race_retains_uncertain_send")
    finally:
        race_guard.close()
        run(NFT, "-f", "-", text=LEASE_RULES)
    grant("2s")
    if not client.request({"action": "open", "key": "expiry", "address": "198.51.100.2"})["ok"]:
        raise RuntimeError("Could not establish the expiring fixture connection")
    checks.append("lease_live_connection_allowed")
    time.sleep(2.2)  # No renewal: expiry must work without a polling supervisor.
    denied("lease_expiry_blocks_existing_socket", client, action="send")
    denied("lease_expiry_blocks_new_socket", client)
    client.request({"action": "close"})
    controlled = controller_checks(client, snapshot, grant, denied)
    run(NFT, "delete", "table", "inet", "fixture_lease")
    return checks, controlled


def controller_checks(client, snapshot, grant, denied):
    checks = []
    authority = client.request({"action": "check_authority"})
    if any(authority["caps"].values()) or authority["no_new_privs"] != 1:
        raise RuntimeError("Fixture sender retained privileges")
    if authority["admin_calls_blocked"] != [True, True]:
        raise RuntimeError("Fixture sender can mutate or escape its network namespace")
    checks.extend(
        ["sender_capabilities_dropped", "sender_route_admin_refused", "sender_setns_refused"]
    )

    def revoke():
        run(NFT, "flush", "set", "inet", "fixture_lease", "destinations")
        rows = json.loads(run(NFT, "-j", "list", "set", "inet", "fixture_lease", "destinations"))
        if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
            raise RuntimeError("Fixture revocation not acknowledged")

    entered, release, changed = threading.Event(), threading.Event(), threading.Event()

    class PausedActor:
        calls = 0

        def request(self, request):
            self.calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Fixture controlled send was not released")
            if changed.is_set():
                raise RuntimeError("Managed rule mutation overlapped a send")
            return client.request(request)

    def managed_revoke():
        changed.set()
        revoke()

    grant()
    actor = PausedActor()
    guard = ControlledFixtureGuard(
        Path("/tmp/controlled-send"),
        selected=snapshot(),
        observe=snapshot,
        actor=actor,
        revoke=managed_revoke,
    )
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            sending = pool.submit(guard.dispatch)
            try:
                if not entered.wait(timeout=3):
                    raise RuntimeError("Fixture send did not enter")
                stopping = pool.submit(guard.shutdown)
                if not guard.stop_requested.wait(timeout=3):
                    raise RuntimeError("Fixture stop did not enter")
                queued = pool.submit(guard.dispatch)
                if changed.is_set() or stopping.done():
                    raise RuntimeError("Revocation failed to wait for in-flight dispatch")
            finally:
                release.set()
            if not sending.result(timeout=5)["ok"]:
                raise RuntimeError("Controlled in-flight request did not complete")
            stopping.result(timeout=5)
            try:
                queued.result(timeout=5)
            except RuntimeError as exc:
                if str(exc) != "fixture_dispatch_halted":
                    raise
            else:
                raise RuntimeError("Queued send escaped the stop request")
        if actor.calls != 1 or not guard.revoked:
            raise RuntimeError("Managed stop did not retain exactly one send")
        kinds = [json.loads(row)["kind"] for row in guard.path.read_bytes().splitlines()]
        if kinds != ["prepared", "succeeded", "stop_requested", "revoked"]:
            raise RuntimeError("Managed stop audit order differs from send/revoke order")
        checks.extend(
            [
                "managed_revoke_waits_for_send",
                "queued_send_refused_on_stop",
                "managed_stop_audit_order",
            ]
        )
        denied("managed_revoke_blocks_raw_sender", client, record=False)
        checks.append("managed_revoke_blocks_raw_sender")
    finally:
        guard.close()

    # A dead controller cannot renew. Existing permission can remain until its
    # bounded TTL expires; retained preparation is not permission to restart.
    pid = os.fork()
    if pid == 0:
        try:
            grant("2s")

            class CrashActor:
                def request(self, request):
                    os._exit(19)

            crashed = ControlledFixtureGuard(
                Path("/tmp/controller-crash"),
                selected=snapshot(),
                observe=snapshot,
                actor=CrashActor(),
                revoke=revoke,
            )
            crashed.dispatch()
        finally:
            os._exit(20)
    _pid, result = os.waitpid(pid, 0)
    if not os.WIFEXITED(result) or os.WEXITSTATUS(result) != 19:
        raise RuntimeError("Controller crash fixture did not stop during preparation")
    rows = [json.loads(row) for row in Path("/tmp/controller-crash").read_bytes().splitlines()]
    if [row["kind"] for row in rows] != ["prepared"]:
        raise RuntimeError("Controller crash lost its pending preparation")
    checks.append("controller_crash_keeps_pending_preparation")
    time.sleep(2.2)
    denied("controller_crash_expiry_blocks_raw_sender", client, record=False)
    checks.append("controller_crash_expiry_blocks_raw_sender")
    return checks


def worker(original: dict[str, str], source: str) -> dict:
    def deadline(_signum, _frame):
        raise TimeoutError("Fixture exceeded its 90-second deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(90)
    require_isolation(original)  # Must precede EVERY network mutation.
    children = []
    checks = []
    host = Probe()
    try:
        client = Child(source)
        children.append(client)
        peer = Child(source)
        children.append(peer)
        for child in children:
            if os.readlink(f"/proc/{child.process.pid}/ns/net") == namespace_ids()["net"]:
                raise RuntimeError("Fixture child shares router network namespace")
        run(IP, "link", "set", "lo", "up")
        run(IP, "link", "add", "br-fixture", "type", "bridge")
        run(IP, "link", "set", "br-fixture", "up")
        for local, remote, child in (("lan", "client", client), ("wan", "peer", peer)):
            run(IP, "link", "add", local, "type", "veth", "peer", "name", remote)
            run(IP, "link", "set", remote, "netns", str(child.process.pid))
            run(IP, "link", "set", local, "up")
            child.ip("link", "set", "lo", "up")
            child.ip("link", "set", remote, "up")
        run(IP, "link", "set", "lan", "master", "br-fixture")
        for interface, v4, v6 in (
            ("br-fixture", "192.0.2.1/24", "fd00:7472:1::1/64"),
            ("wan", "198.51.100.1/24", "fd00:7472:2::1/64"),
        ):
            run(IP, "address", "add", v4, "dev", interface)
            run(IP, "-6", "address", "add", v6, "dev", interface, "nodad")
        for child, interface, v4, v6 in (
            (client, "client", "192.0.2.2/24", "fd00:7472:1::2/64"),
            (peer, "peer", "198.51.100.2/24", "fd00:7472:2::2/64"),
            (peer, "peer", "198.51.100.3/24", "fd00:7472:2::3/64"),
        ):
            child.ip("address", "add", v4, "dev", interface)
            child.ip("-6", "address", "add", v6, "dev", interface, "nodad")
        # sysctls below belong to the already verified disposable network namespace.
        Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
        Path("/proc/sys/net/ipv6/conf/all/forwarding").write_text("1\n")
        client.ip("route", "add", "198.51.100.0/24", "via", "192.0.2.1")
        peer.ip("route", "add", "192.0.2.0/24", "via", "198.51.100.1")
        client.ip("-6", "route", "add", "fd00:7472:2::/64", "via", "fd00:7472:1::1")
        peer.ip("-6", "route", "add", "fd00:7472:1::/64", "via", "fd00:7472:2::1")
        if peer.request({"action": "serve"}) != {"ok": True}:
            raise RuntimeError("Fixture server not ready")
        run(NFT, "-f", "-", text=EARLY_RULES)
        earlier = early_structure()
        targets = {"4": "198.51.100.2", "6": "fd00:7472:2::2"}
        controls = {"4": "198.51.100.3", "6": "fd00:7472:2::3"}

        def check(name, actor, action, family, allowed, address=None, source_ip=None, counter=None):
            before = counters()[counter] if counter else None
            result = actor.request(
                {
                    "action": action,
                    "key": family,
                    "address": address or targets[family],
                    "source": source_ip,
                }
            )
            if result["ok"] != allowed:
                raise RuntimeError(f"{name}: unexpected fixture outcome {result}")
            if counter and counters()[counter] <= before:
                raise RuntimeError(f"{name}: failure did not hit its intended guard counter")
            checks.append(name)

        for label, actor in (("host", host), ("bridge", client)):
            for family in targets:
                check(f"baseline_{label}_ipv{family}", actor, "open", family, True)
        # Separate base chain, after earlier unconditional accepts; no established bypass.
        run(NFT, "--check", "-f", "-", text=GUARD_RULES)
        run(NFT, "-f", "-", text=GUARD_RULES)
        for label, actor, hook in (("host", host, "output"), ("bridge", client, "forward")):
            for family in targets:
                for action in ("once", "send"):
                    check(
                        f"blocked_{label}_ipv{family}_{action}",
                        actor,
                        action,
                        family,
                        False,
                        counter=hook + family,
                    )
                check(
                    f"control_{label}_ipv{family}",
                    actor,
                    "once",
                    family,
                    True,
                    address=controls[family],
                )
        client.ip("address", "add", "192.0.2.99/24", "dev", "client")
        client.ip("-6", "address", "add", "fd00:7472:1::99/64", "dev", "client", "nodad")
        for family, address in (("4", "192.0.2.99"), ("6", "fd00:7472:1::99")):
            check(
                f"blocked_spoof_ipv{family}",
                client,
                "once",
                family,
                False,
                address=controls[family],
                source_ip=address,
                counter="spoof" + family,
            )
        observed = counters()
        host.request({"action": "close"})
        client.request({"action": "close"})
        run(NFT, "delete", "table", "inet", "trader_fixture_guard")
        for label, actor in (("host", host), ("bridge", client)):
            for family in targets:
                check(f"rollback_{label}_ipv{family}", actor, "once", family, True)
        if early_structure() != earlier:
            raise RuntimeError("Rollback changed the earlier independent policy")
        checks.append("rollback_preserves_earlier_policy")
        leases, controlled = lease_checks(client, host)
        return {
            "status": "passed",
            "checks": checks,
            "lease_checks": leases,
            "controller_checks": controlled,
            "guard_packet_counts": observed,
            "isolated_namespaces": list(NAMESPACES),
            "host_firewall_modified": False,
            "external_requests": 0,
            "gateway_coverage_qualified": False,
            "capture_admitted": False,
            "uncontrolled_rule_mutation_race_closed": False,
            "managed_revocation_serialized": True,
        }
    finally:
        host.request({"action": "close"})
        for child in reversed(children):
            child.stop()
        signal.alarm(0)


def main() -> int:
    if len(sys.argv) != 1:
        print("This fixture accepts no arguments.", file=sys.stderr)
        return 2
    if os.geteuid() == 0:
        print("Run as an ordinary user; this fixture does not need host sudo.", file=sys.stderr)
        return 2
    source = Path(__file__).read_text()
    original = namespace_ids()
    entrypoint = (
        f"result = scope['worker']({original!r}, {source!r})\n"
        f"result['script_sha256'] = {hashlib.sha256(source.encode()).hexdigest()!r}\n"
        "print(scope['json'].dumps(result, sort_keys=True))\n"
    )
    command = [
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
        PYTHON,
        "-I",
        "-c",
        embedded(source, entrypoint),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=100)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if namespace_ids() != original:
        raise RuntimeError("Caller namespace identity changed")
    if process.returncode:
        print(stderr.strip(), file=sys.stderr)
        return 1
    print(stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

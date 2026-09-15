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
        return {
            "status": "passed",
            "checks": checks,
            "guard_packet_counts": observed,
            "isolated_namespaces": list(NAMESPACES),
            "host_firewall_modified": False,
            "external_requests": 0,
            "gateway_coverage_qualified": False,
            "capture_admitted": False,
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

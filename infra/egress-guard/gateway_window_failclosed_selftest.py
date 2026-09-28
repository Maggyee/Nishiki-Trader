"""Disposable kernel check that expiry and owner exit retain a default deny."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
IP = "/usr/sbin/ip"
NFT = "/usr/sbin/nft"
PYTHON = "/usr/bin/python3"
TABLE = "fixture_joint_failclosed"
KINDS = ("inet", "netdev")
NAMESPACES = ("user", "net", "mnt", "pid")
PEER = """
import socket,sys,select
print('ready',flush=True)
if sys.stdin.readline().strip()!='serve': raise RuntimeError('peer_not_started')
listeners=[]
for family,address in ((socket.AF_INET,'198.51.100.2'),(socket.AF_INET6,'2001:db8:2::2')):
 sock=socket.socket(family);sock.bind((address,443));sock.listen(8);listeners.append(sock)
print('serving',flush=True)
while True:
 readable,_,_=select.select(listeners,[],[])
 for listener in readable:
  connection,_=listener.accept();connection.close()
"""
CLIENT = """
import json,socket,sys
try:
 with socket.create_connection((sys.argv[1],443),timeout=0.3): connected=True
except OSError: connected=False
print(json.dumps({'connected':connected}))
"""
BASELINE = f"""table inet {TABLE} {{
 set blackout {{ type nf_proto; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy drop;
  oifname "lo" accept; meta nfproto @blackout counter drop; counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy drop;
  meta nfproto @blackout counter drop; counter drop; }}
}}
table netdev {TABLE} {{
 set blackout {{ type ether_type; flags timeout; }}
 chain egress {{ type filter hook egress device "wan" priority 0; policy drop;
  ether type @blackout counter drop; counter drop; }}
}}"""
LEASE = f"""add element inet {TABLE} blackout {{ ipv4 timeout 3000ms, ipv6 timeout 3000ms }}
add element netdev {TABLE} blackout {{ 0x0800 timeout 3000ms, 0x86dd timeout 3000ms }}
"""


def _run(*args, input=None):
    result = subprocess.run(
        args, input=input, capture_output=True, env=ENV, cwd="/", timeout=4, check=False
    )
    if result.returncode:
        raise RuntimeError("private_failclosed_command_failed: " + result.stderr.decode()[-350:])
    return result.stdout


def _namespaces():
    return {name: os.readlink("/proc/self/ns/" + name) for name in NAMESPACES}


def _empty_private_root(original):
    if os.getpid() != 1 or any(_namespaces()[name] == original[name] for name in NAMESPACES):
        raise ValueError("private_failclosed_new_namespaces_required")
    links = json.loads(_run(IP, "-j", "link", "show"))
    rules = json.loads(_run(NFT, "-j", "list", "ruleset"))["nftables"]
    if [row["ifname"] for row in links] != ["lo"] or any("metainfo" not in row for row in rules):
        raise ValueError("private_failclosed_empty_network_required")


def _state():
    tables = {
        family: json.loads(_run(NFT, "-j", "list", "table", family, TABLE)) for family in KINDS
    }
    static = {}
    active = {}
    fallback = {}
    for family, doc in tables.items():
        rows = []
        for item in doc["nftables"]:
            if "metainfo" in item:
                continue
            kind, value = next(iter(item.items()))
            value = json.loads(json.dumps(value))
            value.pop("handle", None)
            if kind == "set":
                if value["name"] == "blackout":
                    active[family] = len(value.get("elem", []))
                value.pop("elem", None)
            for expression in value.get("expr", []):
                if "counter" in expression:
                    fallback[(family, value["chain"])] = expression["counter"].get("packets", 0)
                    expression["counter"].pop("packets", None)
                    expression["counter"].pop("bytes", None)
            rows.append({kind: value})
        static[family] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if set(active) != set(KINDS):
        raise ValueError("private_failclosed_missing_blackout_set")
    return static, active, fallback


def _connect(address, *, pid=None):
    command = (PYTHON, "-I", "-c", CLIENT, address)
    if pid is not None:
        command = ("/usr/bin/nsenter", "-t", str(pid), "--net", *command)
    return json.loads(_run(*command))["connected"]


def _worker(original):
    _empty_private_root(original)
    peers = []
    try:
        for _ in range(2):
            child = subprocess.Popen(
                ["/usr/bin/unshare", "--net", PYTHON, "-I", "-c", PEER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
            )
            peers.append(child)
            if child.stdout.readline().strip() != "ready":
                raise RuntimeError("private_failclosed_peer_not_ready")
        peer, caller = peers
        _run(IP, "link", "set", "lo", "up")
        for local, remote, pid, ipv4, ipv6, remote4, remote6 in (
            (
                "wan",
                "peer",
                peer.pid,
                "198.51.100.1/24",
                "2001:db8:2::1/64",
                "198.51.100.2/24",
                "2001:db8:2::2/64",
            ),
            (
                "br-fixture",
                "caller",
                caller.pid,
                "192.0.2.1/24",
                "2001:db8:1::1/64",
                "192.0.2.2/24",
                "2001:db8:1::2/64",
            ),
        ):
            _run(IP, "link", "add", local, "type", "veth", "peer", "name", remote)
            _run(IP, "link", "set", remote, "netns", str(pid))
            for family, address in (("-4", ipv4), ("-6", ipv6)):
                _run(
                    IP,
                    family,
                    "address",
                    "add",
                    address,
                    "dev",
                    local,
                    *(("nodad",) if family == "-6" else ()),
                )
            _run(IP, "link", "set", local, "up")
            _run("/usr/bin/nsenter", "-t", str(pid), "--net", IP, "link", "set", remote, "up")
            for family, address in (("-4", remote4), ("-6", remote6)):
                _run(
                    "/usr/bin/nsenter",
                    "-t",
                    str(pid),
                    "--net",
                    IP,
                    family,
                    "address",
                    "add",
                    address,
                    "dev",
                    remote,
                    *(("nodad",) if family == "-6" else ()),
                )
        _run(
            "/usr/bin/nsenter",
            "-t",
            str(caller.pid),
            "--net",
            IP,
            "-4",
            "route",
            "add",
            "198.51.100.0/24",
            "via",
            "192.0.2.1",
        )
        _run(
            "/usr/bin/nsenter",
            "-t",
            str(caller.pid),
            "--net",
            IP,
            "-6",
            "route",
            "add",
            "2001:db8:2::/64",
            "via",
            "2001:db8:1::1",
        )
        _run(
            "/usr/bin/nsenter",
            "-t",
            str(peer.pid),
            "--net",
            IP,
            "-4",
            "route",
            "add",
            "192.0.2.0/24",
            "via",
            "198.51.100.1",
        )
        _run(
            "/usr/bin/nsenter",
            "-t",
            str(peer.pid),
            "--net",
            IP,
            "-6",
            "route",
            "add",
            "2001:db8:1::/64",
            "via",
            "2001:db8:2::1",
        )
        Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
        Path("/proc/sys/net/ipv6/conf/all/forwarding").write_text("1\n")
        peer.stdin.write("serve\n")
        peer.stdin.flush()
        if peer.stdout.readline().strip() != "serving":
            raise RuntimeError(
                "private_failclosed_peer_not_listening: " + peer.stderr.read()[-300:]
            )
        cases = (
            ("198.51.100.2", None),
            ("2001:db8:2::2", None),
            ("198.51.100.2", caller.pid),
            ("2001:db8:2::2", caller.pid),
        )
        if not all(_connect(address, pid=pid) for address, pid in cases):
            raise ValueError("private_failclosed_baseline_route_missing")
        _run(NFT, "-f", "-", input=BASELINE.encode("ascii"))
        baseline, inactive, _ = _state()
        if any(inactive.values()) or any(_connect(address, pid=pid) for address, pid in cases):
            raise ValueError("private_failclosed_baseline_did_not_deny")
        child = os.fork()
        if child == 0:
            try:
                _run(NFT, "-f", "-", input=LEASE.encode("ascii"))
            except BaseException:
                os._exit(24)
            os._exit(23)
        _, status = os.waitpid(child, 0)
        if os.waitstatus_to_exitcode(status) != 23:
            raise ValueError("private_failclosed_owner_write_failed")
        active_static, active, _ = _state()
        if active_static != baseline or active != {"inet": 2, "netdev": 2}:
            raise ValueError("private_failclosed_lease_not_active_after_exit")
        if any(_connect(address, pid=pid) for address, pid in cases):
            raise ValueError("private_failclosed_owner_exit_reopened_route")
        deadline = time.monotonic() + 5
        while True:
            final_static, remaining, counters_before = _state()
            if remaining == {"inet": 0, "netdev": 0}:
                break
            if time.monotonic() >= deadline:
                raise ValueError("private_failclosed_lease_did_not_expire")
            time.sleep(0.1)
        if final_static != baseline or any(_connect(address, pid=pid) for address, pid in cases):
            raise ValueError("private_failclosed_expiry_reopened_route")
        _, _, counters_after = _state()
        if not all(
            counters_after.get(key, 0) > counters_before.get(key, 0)
            for key in (("inet", "output"), ("inet", "forward"))
        ):
            raise ValueError("private_failclosed_default_drop_not_reached")
        return {
            "status": "private_failclosed_expiry_observed_unqualified",
            "reachable_before_baseline": 4,
            "denied_after_owner_exit": 4,
            "denied_after_expiry": 4,
            "owner_exited_before_expiry": True,
            "permanent_rules_unchanged": True,
            "network_admitted": False,
            "host_firewall_modified": False,
        }
    finally:
        for child in reversed(peers):
            if child.stdin and not child.stdin.closed:
                child.stdin.close()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "--worker":
        try:
            print(json.dumps(_worker(json.loads(args[1])), sort_keys=True))
            return 0
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if len(args) != 2 or args[0] != "--report" or os.geteuid() == 0:
        return 2
    path = Path(args[1])
    original = _namespaces()
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
            PYTHON,
            "-I",
            str(Path(__file__).resolve()),
            "--worker",
            json.dumps(original),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
        cwd="/",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=25)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if _namespaces() != original or process.returncode:
        raise RuntimeError("private_failclosed_isolation_failed: " + stderr.decode()[-500:])
    report = json.loads(stdout)
    if (
        report.get("status") != "private_failclosed_expiry_observed_unqualified"
        or report.get("network_admitted") is not False
    ):
        raise RuntimeError("private_failclosed_report_invalid")
    raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

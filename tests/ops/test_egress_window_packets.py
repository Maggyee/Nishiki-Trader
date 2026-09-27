"""Real joint-rule packet paths in disposable namespaces, without a host install."""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "infra/egress-guard"
PEER_SOURCE = """
import socket,sys
print('ready',flush=True)
if sys.stdin.readline() != 'serve\\n': raise RuntimeError('peer_not_started')
listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
listener.bind(('198.51.100.2',443));listener.listen(16)
print('serving',flush=True)
while True:
 connection,_=listener.accept()
 with connection:
  connection.settimeout(2)
  data=b''
  while len(data)<128 and not data.endswith(b'\\n'):
   part=connection.recv(128-len(data))
   if not part: break
   data+=part
  connection.sendall((connection.getpeername()[0]+'\\n').encode() if data == b'fixture-peer\\n' else data)
"""


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(original):
    guard = load("selftest")
    kernel = load("gateway_window_kernel")
    guard.require_isolation(original)
    signal.alarm(40)
    run, ip, nft = guard.run, guard.IP, guard.NFT
    source = (ROOT / "selftest.py").read_text().replace("PORT = 23456\n", "PORT = 443\n", 1)
    if "PORT = 443\n" not in source:
        raise RuntimeError("fixture_client_port_not_selected")
    guard.PORT = 443
    children = []
    peer = None
    try:
        collector = guard.Child(source)
        competitor = guard.Child(source)
        children.extend((collector, competitor))
        peer = subprocess.Popen(
            ["/usr/bin/unshare", "--net", "/usr/bin/python3", "-I", "-c", PEER_SOURCE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=guard.ENV,
            cwd="/",
        )
        if peer.stdout.readline().strip() != "ready":
            raise RuntimeError("fixture_peer_not_ready")
        run(ip, "link", "set", "lo", "up")
        for local, remote, pid, host_ip, child_ip in (
            ("gw-jc1", "client", collector.process.pid, "192.0.2.1/24", "192.0.2.2/24"),
            ("wan", "peer", peer.pid, "198.51.100.1/24", "198.51.100.2/24"),
            ("other-host", "other", competitor.process.pid, "203.0.113.1/24", "203.0.113.2/24"),
        ):
            run(ip, "link", "add", local, "type", "veth", "peer", "name", remote)
            run(ip, "link", "set", remote, "netns", str(pid))
            run(ip, "link", "set", local, "up")
            run(ip, "address", "add", host_ip, "dev", local)
            run("/usr/bin/nsenter", "-t", str(pid), "--net", ip, "link", "set", remote, "up")
            run(
                "/usr/bin/nsenter",
                "-t",
                str(pid),
                "--net",
                ip,
                "address",
                "add",
                child_ip,
                "dev",
                remote,
            )
        collector.ip("route", "add", "198.51.100.0/24", "via", "192.0.2.1")
        competitor.ip("route", "add", "198.51.100.0/24", "via", "203.0.113.1")
        run(
            "/usr/bin/nsenter",
            "-t",
            str(peer.pid),
            "--net",
            ip,
            "route",
            "add",
            "192.0.2.0/24",
            "via",
            "198.51.100.1",
        )
        Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
        peer.stdin.write("serve\n")
        peer.stdin.flush()
        if peer.stdout.readline().strip() != "serving":
            raise RuntimeError("fixture_peer_bind_failed")

        name = kernel.TABLE
        rules = f"""table inet {name} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept;
  meta mark 0x6f720002 counter drop; oifname "lo" accept; meta nfproto @blackout counter drop; }}
 chain input {{ type filter hook input priority -310; policy accept; iifname "gw-jc1" counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept;
  iifname "gw-jc1" oifname "wan" ip saddr 192.0.2.2 ip daddr @permits tcp dport 443 meta mark set 0x6f720002 accept;
  oifname "gw-jc1" iifname "wan" ip saddr @permits ip daddr 192.0.2.2 tcp sport 443 ct state established accept;
  iifname "gw-jc1" counter drop; oifname "gw-jc1" counter drop; meta nfproto @blackout counter drop;
 }}
}}
table netdev {name} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "wan" priority 0; policy accept;
  meta mark 0x6f720002 ip saddr 198.51.100.1 ip daddr @permits tcp dport 443 accept;
  meta mark 0x6f720002 counter drop; ether type @blackout counter drop;
 }}
}}
table ip fixture_joint_nat {{
 chain source {{ type nat hook postrouting priority 100; policy accept;
  oifname "wan" ip daddr 198.51.100.0/24 snat to 198.51.100.1;
 }}
}}
table inet fixture_joint_trace {{
 chain forward {{ type filter hook forward priority -309; policy accept;
  iifname "gw-jc1" meta mark 0x6f720002 counter;
 }}
}}
table netdev fixture_joint_trace {{
 chain egress {{ type filter hook egress device "wan" priority 1; policy accept;
  meta mark 0x6f720002 counter;
 }}
}}"""
        run(nft, "-f", "-", text=rules)
        run(
            nft,
            "-f",
            "-",
            text=f"""add element inet {name} blackout {{ ipv4 timeout 30000ms, ipv6 timeout 30000ms }}
add element netdev {name} blackout {{ 0x0800 timeout 30000ms, 0x86dd timeout 30000ms }}""",
        )
        collector_selection = {
            "host_link": "gw-jc1",
            "child_ipv4": "192.0.2.2",
            "source_ipv4": "198.51.100.1",
        }
        pins = {
            family: kernel.digest(kernel._static(kernel.read_table(family)["nftables"]))
            for family in kernel.KINDS
        }
        observed = kernel.observe(
            expected_static_sha256=pins, wan_interface="wan", collector=collector_selection
        )
        if (
            observed["network_admitted"]
            or observed["status"] != "local_kernel_timers_observed_unqualified"
        ):
            raise RuntimeError("fixture_observer_admitted_network")

        def count(family, table, chain, index):
            rows = json.loads(run(nft, "-j", "list", "table", family, table))["nftables"]
            rules = [row["rule"] for row in rows if "rule" in row and row["rule"]["chain"] == chain]
            return next(
                expr["counter"]["packets"] for expr in rules[index]["expr"] if "counter" in expr
            )

        def denied(label, actor, request, family="inet", chain="forward", index=2):
            before = count(family, name, chain, index)
            result = actor.request(
                {"action": "once", "key": label, "address": "198.51.100.2", **request}
            )
            if result["ok"] or count(family, name, chain, index) <= before:
                raise RuntimeError(f"{label}: expected kernel denial, got {result}")

        host = guard.Probe()
        denied("empty_permit", collector, {})
        run(
            nft,
            "-f",
            "-",
            text=f"""add element inet {name} permits {{ 198.51.100.2 timeout 25000ms }}
add element netdev {name} permits {{ 198.51.100.2 timeout 25000ms }}""",
        )
        forward_before = count("inet", "fixture_joint_trace", "forward", 0)
        wan_before = count("netdev", "fixture_joint_trace", "egress", 0)
        result = collector.request(
            {"action": "once", "key": "allowed", "address": "198.51.100.2", "observe_peer": True}
        )
        if result != {"ok": True, "peer": "198.51.100.1"}:
            raise RuntimeError(f"selected_collector_not_snat_to_peer: {result}")
        if (
            count("inet", "fixture_joint_trace", "forward", 0) <= forward_before
            or count("netdev", "fixture_joint_trace", "egress", 0) <= wan_before
        ):
            raise RuntimeError("selected_packet_did_not_cross_marked_forward_and_wan_hooks")
        denied("host_output", host, {}, chain="output", index=2)
        denied("other_forward", competitor, {}, index=4)
        collector.ip("address", "add", "192.0.2.99/24", "dev", "client")
        denied("wrong_child_source", collector, {"source": "192.0.2.99"})
        denied("wrong_tcp_port", collector, {"port": 444})
        denied("udp", collector, {"action": "udp"})
        denied("collector_to_host", collector, {"address": "192.0.2.1"}, chain="input", index=0)
        before = count("inet", name, "output", 0)
        with socket.socket() as forged:
            forged.settimeout(0.6)
            forged.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, kernel.COLLECTOR_MARK)
            try:
                forged.connect(("198.51.100.2", 443))
            except OSError:
                pass
            else:
                raise RuntimeError("forged_host_mark_reached_peer")
        if count("inet", name, "output", 0) <= before:
            raise RuntimeError("forged_host_mark_missed_output_denial")
        for family in kernel.KINDS:
            rows = kernel.read_table(family)["nftables"]
            sets = {row["set"]["name"]: row["set"] for row in rows if "set" in row}
            kernel._elements(sets["blackout"], family)
            permits = sets["permits"].get("elem", [])
            if (
                len(permits) != 1
                or permits[0].get("elem", {}).get("val") != "198.51.100.2"
                or permits[0]["elem"].get("expires", 0) <= 0
            ):
                raise RuntimeError("fixture_permit_expired_before_denials_completed")
        return {
            "status": "isolated_joint_packet_paths_passed_unqualified",
            "peer_source": result["peer"],
            "forward_mark_seen": True,
            "wan_mark_seen": True,
            "denials": 8,
            "network_admitted": False,
            "host_firewall_modified": False,
            "external_requests": 0,
        }
    finally:
        for child in reversed(children):
            child.stop()
        if peer is not None:
            peer.kill()
            peer.communicate(timeout=3)
        signal.alarm(0)


def test_real_joint_collector_veth_mark_snat_wan_packet_paths():
    guard = load("selftest")
    original = guard.namespace_ids()
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
        "/usr/bin/python3",
        "-I",
        str(Path(__file__).resolve()),
        json.dumps(original),
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    )
    try:
        stdout, stderr = process.communicate(timeout=50)
    except BaseException:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    assert process.returncode == 0, stderr[-3000:]
    assert guard.namespace_ids() == original
    assert json.loads(stdout) == {
        "status": "isolated_joint_packet_paths_passed_unqualified",
        "peer_source": "198.51.100.1",
        "forward_mark_seen": True,
        "wan_mark_seen": True,
        "denials": 8,
        "network_admitted": False,
        "host_firewall_modified": False,
        "external_requests": 0,
    }


def test_packet_worker_refuses_the_callers_own_namespaces():
    original = load("selftest").namespace_ids()
    try:
        worker(original)
    except RuntimeError as exc:
        assert str(exc) == "Refusing to mutate a namespace inherited from the caller"
    else:
        raise AssertionError("packet worker accepted an unisolated caller")


if __name__ == "__main__":
    print(json.dumps(worker(json.loads(sys.argv[1])), sort_keys=True))

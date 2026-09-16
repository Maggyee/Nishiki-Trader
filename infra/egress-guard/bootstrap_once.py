"""Reviewed one-shot public REST bootstrap under an expiring host blackout.

Root controls fixed scope, topology and journal. A dedicated nonroot child has
one TCP/TLS/GET attempt; per-message kernel credentials bind its bounded channel.
No retry, service, private request, arbitrary command or trading operation.
"""

from __future__ import annotations

import argparse
import array
import base64
import hashlib
import ipaddress
import json
import os
import pwd
import select
import socket
import ssl
import stat
import struct
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path("/var/lib/trader/egress/rest-bootstrap-v1")
CODE = Path("/usr/local/lib/trader-egress-bootstrap-v1")
PLAN = Path("/etc/trader/egress-bootstrap-v1.json")
NS = "trader-egress-bootstrap-v1"
HOST_LINK = "teg-bh1"
CHILD_LINK = "teg-bc1"
HOST_IP = "169.254.254.1"
CHILD_IP = "169.254.254.2"
TABLE = "trader_egress_bootstrap_v1"
TAG = "trader-egress-bootstrap-v1-owned"
MARK = "0x6f720001"
AUTHORITY = "testnet.binance.vision"
TARGET = "/api/v3/exchangeInfo"
CAFILE = "/etc/ssl/certs/ca-certificates.crt"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
CREDS = struct.Struct("3i")
MAX_BODY = 8 * 1024 * 1024
MAX_ARCHIVE = 16 * 1024 * 1024
PACKET = 16384


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(*args, text=None):
    result = subprocess.run(
        args, input=text, text=True, capture_output=True, env=ENV, cwd="/", timeout=3
    )
    if result.returncode:
        raise RuntimeError("command_failed:" + Path(args[0]).name + ":" + result.stderr[-300:])
    return result.stdout


def nft(text):
    return run("/usr/sbin/nft", "-f", "-", text=text)


def load(raw):
    scope = {"__name__": "reviewed_bootstrap_dependency"}
    exec(compile(raw, "<reviewed>", "exec"), scope)
    return scope


def protected(path, mode, limit=1024 * 1024):
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("untrusted_parent")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_size > limit
        ):
            raise ValueError("untrusted_file")
        raw = os.pread(fd, limit + 1, 0)
        if len(raw) != info.st_size:
            raise ValueError("changed_file")
        return raw
    finally:
        os.close(fd)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Journal:
    def __init__(self, plan, raw_plan):
        ROOT.mkdir(mode=0o700)  # Durable consumption even if later preparation fails.
        sync_dir(ROOT.parent)
        self.fds = []
        self.bytes = self.seq = 0
        self.previous = None
        for name, data in [
            (
                "README.md",
                b"One-shot real REST bootstrap scope. Consumed before kernel/network operations. Never reopen, reset, resume or retry. Next: offline review only.\n",
            ),
            ("plan.json", raw_plan),
        ]:
            fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            self.bytes += len(data)
        self.fd = os.open(
            ROOT / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        self.fds.append(self.fd)
        self.wire = os.open(
            ROOT / "response.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        self.fds.append(self.wire)
        sync_dir(ROOT)
        self.append(
            "scope_consumed", plan_sha256=digest(raw_plan), source_commit=plan["source_commit"]
        )

    def append(self, kind, **fields):
        row = {
            "seq": self.seq,
            "previous_sha256": self.previous,
            "kind": kind,
            "utc_ns": time.time_ns(),
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        }
        raw = canonical(row) + b"\n"
        limit = MAX_ARCHIVE if kind in ("failed", "cleanup") else MAX_ARCHIVE - 4096
        if self.bytes + len(raw) > limit:
            raise ValueError("archive_limit")
        self.write(self.fd, raw)
        self.bytes += len(raw)
        self.seq += 1
        self.previous = digest(raw)

    @staticmethod
    def write(fd, raw):
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short_write")
            view = view[count:]
        os.fsync(fd)

    def chunk(self, raw):
        if not 0 < len(raw) <= 4096 or self.bytes + len(raw) + 1024 > MAX_ARCHIVE - 4096:
            raise ValueError("chunk_limit")
        self.write(self.wire, raw)
        self.bytes += len(raw)
        self.append("response_chunk", size=len(raw), sha256=digest(raw))

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds.clear()


class Channel:
    def __init__(self, sock, peer):
        self.sock, self.peer = sock, peer
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        sock.settimeout(11)

    def send(self, kind, seq, data=None):
        raw = canonical({"kind": kind, "seq": seq, "data": data})
        if len(raw) > PACKET or self.sock.send(raw) != len(raw):
            raise ValueError("channel_send")

    def receive(self):
        raw, ancillary, flags, _ = self.sock.recvmsg(
            PACKET, socket.CMSG_SPACE(CREDS.size) + socket.CMSG_SPACE(64), socket.MSG_CMSG_CLOEXEC
        )
        credentials = []
        unexpected = False
        for level, kind, value in ancillary:
            if (
                level == socket.SOL_SOCKET
                and kind == socket.SCM_CREDENTIALS
                and len(value) == CREDS.size
            ):
                credentials.append(CREDS.unpack(value))
            elif level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds = array.array("i")
                fds.frombytes(value[: len(value) - len(value) % fds.itemsize])
                for fd in fds:
                    os.close(fd)
                unexpected = True
            else:
                unexpected = True
        if (
            not raw
            or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
            or unexpected
            or credentials != [self.peer]
        ):
            raise ValueError("channel_peer")
        row = json.loads(raw)
        if (
            not isinstance(row, dict)
            or set(row) != {"kind", "seq", "data"}
            or type(row["seq"]) is not int
            or raw != canonical(row)
        ):
            raise ValueError("channel_frame")
        return row


def child(fd, parent_pid, destination):
    account = pwd.getpwnam("trader-egress")
    if (
        os.getuid() != account.pw_uid
        or os.getuid() == 0
        or os.getgid() != account.pw_gid
        or os.getgroups()
    ):
        raise ValueError("child_identity")
    ipaddress.IPv4Address(destination)
    parser = load(protected(CODE / "http_parser.py", 0o444))
    channel = Channel(socket.socket(fileno=fd), (parent_pid, 0, 0))
    sequence = 0

    def event(kind, data=None):
        nonlocal sequence
        channel.send(kind, sequence, data)
        ack = channel.receive()
        if ack != {"kind": "ack", "seq": sequence, "data": None}:
            raise ValueError("invalid_ack")
        sequence += 1

    event("ready")
    deadline = time.monotonic() + 10

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("request_deadline")
        channel.sock.settimeout(value)
        return value

    context = ssl.create_default_context(cafile=CAFILE)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.bind((CHILD_IP, 0))
    wire = None
    try:
        connection.settimeout(remaining())
        connection.connect((destination, 443))
        connection.settimeout(remaining())
        wire = context.wrap_socket(connection, server_hostname=AUTHORITY)
        event(
            "tls",
            {
                "peer": list(wire.getpeername()),
                "local": list(wire.getsockname()),
                "certificate_der_b64": base64.b64encode(
                    wire.getpeercert(binary_form=True)
                ).decode(),
                "version": wire.version(),
                "cipher": list(wire.cipher()),
                "hostname": AUTHORITY,
                "check_hostname": context.check_hostname,
                "verify_mode": int(context.verify_mode),
            },
        )
        event("get_prepared")
        wire.settimeout(remaining())
        wire.sendall(
            f"GET {TARGET} HTTP/1.1\r\nHost: {AUTHORITY}\r\nConnection: close\r\n\r\n".encode()
        )
        response = bytearray()

        def receive(maximum=4096):
            wire.settimeout(remaining())
            raw = wire.recv(maximum)
            if not raw:
                raise ValueError("response_truncated")
            remaining()
            event("chunk", base64.b64encode(raw).decode())
            response.extend(raw)

        while b"\r\n\r\n" not in response:
            if len(response) >= 65536:
                raise ValueError("header_limit")
            receive()
        length = response.index(b"\r\n\r\n") + 4
        status, pairs = parser["response_headers"](bytes(response[:length]))
        body_length = parser["_validate_response"]("rest", status, pairs, None)
        if body_length > MAX_BODY:
            raise ValueError("body_limit")
        while len(response) < length + body_length:
            receive(min(4096, length + body_length - len(response)))
        if len(response) != length + body_length:
            raise ValueError("trailing_response")
        remaining()
        event(
            "response",
            {
                "status": status,
                "headers": pairs,
                "body_length": body_length,
                "body_sha256": digest(bytes(response[length:])),
            },
        )
    finally:
        if wire is not None:
            wire.close()
        connection.close()
    event("closed")
    channel.sock.close()


def rules(plan):
    wan = plan["wan_interface"]
    destination = plan["destination_ipv4"]
    source = plan["private_ipv4"]
    return f'''table inet {TABLE} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept;
  oifname "lo" accept
  meta nfproto @blackout counter drop
 }}
 chain input {{ type filter hook input priority -310; policy accept;
  iifname "{HOST_LINK}" counter drop
 }}
 chain forward {{ type filter hook forward priority -310; policy accept;
  iifname "{HOST_LINK}" oifname "{wan}" ip saddr {CHILD_IP} ip daddr @permits tcp dport 443 meta mark set {MARK} accept
  oifname "{HOST_LINK}" iifname "{wan}" ip saddr @permits ip daddr {CHILD_IP} tcp sport 443 ct state established accept
  iifname "{HOST_LINK}" counter drop
  oifname "{HOST_LINK}" counter drop
  meta nfproto @blackout counter drop
 }}
}}
table netdev {TABLE} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "{wan}" priority 0; policy accept;
  meta mark {MARK} ip saddr {source} ip daddr @permits tcp dport 443 accept
  meta mark {MARK} counter drop
  ether type @blackout counter drop
 }}
}}
table ip {TABLE} {{
 chain postrouting {{ type nat hook postrouting priority 99; policy accept;
  ip saddr {CHILD_IP} ip daddr {destination} oifname "{wan}" tcp dport 443 snat to {source}
 }}
}}
'''


def timers_present():
    for family in ("inet", "netdev"):
        rows = json.loads(run("/usr/sbin/nft", "-j", "list", "table", family, TABLE))["nftables"]
        sets = {row["set"]["name"]: row["set"] for row in rows if "set" in row}
        if (
            set(sets) != {"blackout", "permits"}
            or len(sets["blackout"].get("elem", [])) != 2
            or len(sets["permits"].get("elem", [])) != 1
        ):
            raise ValueError("window_permission_missing")


def execute(expected):
    if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
        raise ValueError("isolated_root_required")
    raw_plan = protected(PLAN, 0o600, 65536)
    if digest(raw_plan) != expected:
        raise ValueError("plan_hash")
    plan = json.loads(raw_plan)
    if (
        plan["schema_version"] != "portfolio.egress_bootstrap_execution.v1"
        or plan["scope"] != "portfolio.testnet_rest_bootstrap.v1"
        or plan["maintenance_accepted"] is not True
        or plan["unknown_prior_usage_accepted"] is not True
    ):
        raise ValueError("fixed_approved_plan_required")
    if (
        plan["wan_interface"] != "enp0s6"
        or plan["private_ipv4"] != "10.0.0.136"
        or plan["public_ipv4"] != "149.118.158.46"
    ):
        raise ValueError("fixed_host_selection")
    ipaddress.IPv4Address(plan["destination_ipv4"])
    if (
        type(plan["created_ns"]) is not int
        or not 0 <= time.time_ns() - plan["created_ns"] <= 300_000_000_000
        or plan["host_boot_id"] != Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    ):
        raise ValueError("stale_plan_or_host_restart")
    links = json.loads(run("/usr/sbin/ip", "-j", "link", "show", "dev", plan["wan_interface"]))
    if len(links) != 1 or links[0].get("address") != plan["vnic_mac"]:
        raise ValueError("selected_vnic_changed")
    if (
        digest(protected(CODE / "bootstrap_once.py", 0o444)) != plan["helper_sha256"]
        or digest(protected(CODE / "http_parser.py", 0o444)) != plan["parser_sha256"]
        or digest(protected(Path(CAFILE), 0o644)) != plan["ca_sha256"]
    ):
        raise ValueError("source_hash")
    if Path("/proc/sys/net/ipv4/ip_forward").read_text().strip() != "1":
        raise ValueError("forwarding_unavailable")
    root_verifier = load(protected(Path("/usr/local/lib/trader-egress/helper_entry.py"), 0o444))[
        "load_verifier"
    ]()
    authority = root_verifier()
    journal = None
    proc = None
    channel = None
    parent = None
    pidfd = None
    created = {"namespace": False, "link": False, "rules": False, "forward": False}
    cleanup_errors = []
    outcome = None
    failure = None
    try:
        if (
            authority.manifest_sha256 != plan["installation_manifest_sha256"]
            or authority.account != plan["collector"]
        ):
            raise ValueError("installation_plan_binding")
        route = json.loads(
            run("/usr/sbin/ip", "-4", "-j", "route", "get", plan["destination_ipv4"])
        )
        if (
            len(route) != 1
            or route[0].get("dev") != plan["wan_interface"]
            or route[0].get("prefsrc") != plan["private_ipv4"]
        ):
            raise ValueError("route_changed")
        rows = json.loads(run("/usr/sbin/nft", "-j", "list", "ruleset"))["nftables"]
        if any(row.get("table", {}).get("name") == TABLE for row in rows):
            raise ValueError("owned_table_exists")
        if any(row.get("rule", {}).get("comment") == TAG for row in rows):
            raise ValueError("owned_forward_exists")
        if (
            Path("/run/netns", NS).exists()
            or Path("/sys/class/net", HOST_LINK).exists()
            or Path("/sys/class/net", CHILD_LINK).exists()
        ):
            raise ValueError("owned_topology_exists")
        if any(
            CHILD_IP in canonical(row).decode() or HOST_IP in canonical(row).decode()
            for row in json.loads(run("/usr/sbin/ip", "-4", "-j", "address", "show"))
        ):
            raise ValueError("subnet_collision")
        journal = Journal(plan, raw_plan)
        journal.append("topology_prepared")
        run("/usr/sbin/ip", "netns", "add", NS)
        created["namespace"] = True
        run("/usr/sbin/ip", "link", "add", HOST_LINK, "type", "veth", "peer", "name", CHILD_LINK)
        created["link"] = True
        run("/usr/sbin/ip", "link", "set", CHILD_LINK, "netns", NS)
        run("/usr/sbin/ip", "address", "add", HOST_IP + "/30", "dev", HOST_LINK)
        run("/usr/sbin/ip", "link", "set", HOST_LINK, "up")
        run("/usr/sbin/ip", "-n", NS, "address", "add", CHILD_IP + "/30", "dev", CHILD_LINK)
        run("/usr/sbin/ip", "-n", NS, "link", "set", CHILD_LINK, "up")
        run("/usr/sbin/ip", "-n", NS, "route", "add", "default", "via", HOST_IP)
        nft(rules(plan))
        created["rules"] = True
        # Existing Docker FORWARD defaults to DROP; insert only our narrow veth
        # flow. The independent earlier guard still enforces TTL/quarantine.
        nft(
            f'insert rule ip filter FORWARD iifname "{HOST_LINK}" oifname "{plan["wan_interface"]}" ip saddr {CHILD_IP} ip daddr {plan["destination_ipv4"]} tcp dport 443 accept comment "{TAG}"\ninsert rule ip filter FORWARD oifname "{HOST_LINK}" iifname "{plan["wan_interface"]}" ip saddr {plan["destination_ipv4"]} ip daddr {CHILD_IP} tcp sport 443 ct state established accept comment "{TAG}"\n'
        )
        created["forward"] = True
        authority.verify()
        parent, sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        for item in (parent, sock):
            item.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        account = authority.account
        try:
            proc = subprocess.Popen(
                [
                    "/usr/sbin/ip",
                    "netns",
                    "exec",
                    NS,
                    "/usr/bin/setpriv",
                    f"--reuid={account['uid']}",
                    f"--regid={account['gid']}",
                    "--clear-groups",
                    "--bounding-set=-all",
                    "--inh-caps=-all",
                    "--ambient-caps=-all",
                    "--no-new-privs",
                    "/usr/bin/python3",
                    "-I",
                    str(CODE / "bootstrap_once.py"),
                    "--child",
                    str(sock.fileno()),
                    str(os.getpid()),
                    plan["destination_ipv4"],
                ],
                pass_fds=(sock.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=ENV,
                cwd="/",
            )
        finally:
            sock.close()
        pidfd = os.pidfd_open(proc.pid)
        channel = Channel(parent, (proc.pid, account["uid"], account["gid"]))
        ready = channel.receive()
        if ready != {"kind": "ready", "seq": 0, "data": None}:
            raise ValueError("child_not_ready")
        reader = load(authority.source("inspect_binding.py"))["process_identity"]
        identity = reader(proc.pid)
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
            or any(identity["capabilities"].values())
            or identity["no_new_privileges"] != 1
            or identity["namespaces"]["net"] == os.readlink("/proc/self/ns/net")
        ):
            raise ValueError("child_boundary")
        journal.append("child_ready", identity=identity)
        journal.append("window_prepared", collector_ms=12000, blackout_ms=20000)
        nft(
            f"add element inet {TABLE} blackout {{ ipv4 timeout 20000ms, ipv6 timeout 20000ms }}\nadd element inet {TABLE} permits {{ {plan['destination_ipv4']} timeout 12000ms }}\n"
            f"add element netdev {TABLE} blackout {{ 0x0800 timeout 20000ms, 0x86dd timeout 20000ms }}\nadd element netdev {TABLE} permits {{ {plan['destination_ipv4']} timeout 12000ms }}\n"
        )
        started = time.monotonic()
        timers_present()
        journal.append("window_active")
        journal.append("tcp_prepared", destination=plan["destination_ipv4"], port=443)
        channel.send("ack", 0)
        sequence = 1
        state = "tls"
        wire_size = 0
        while state != "done":
            channel.sock.settimeout(max(0.001, 12 - (time.monotonic() - started)))
            row = channel.receive()
            if row["seq"] != sequence or select.select([pidfd], [], [], 0)[0]:
                raise ValueError("child_sequence_or_death")
            authority.verify()
            if reader(proc.pid) != identity:
                raise ValueError("child_identity_changed")
            timers_present()
            kind, data = row["kind"], row["data"]
            if state == "tls" and kind == "tls":
                if (
                    data["peer"] != [plan["destination_ipv4"], 443]
                    or data["local"][0] != CHILD_IP
                    or data["hostname"] != AUTHORITY
                    or data["check_hostname"] is not True
                    or data["verify_mode"] != int(ssl.CERT_REQUIRED)
                    or data["version"] not in ("TLSv1.2", "TLSv1.3")
                ):
                    raise ValueError("tls_binding")
                cert = base64.b64decode(data["certificate_der_b64"], validate=True)
                if not 0 < len(cert) <= 8192:
                    raise ValueError("certificate_limit")
                journal.append("tls_verified", **data)
                state = "get"
            elif state == "get" and kind == "get_prepared" and data is None:
                journal.append(
                    "get_prepared",
                    method="GET",
                    authority=AUTHORITY,
                    path=TARGET,
                    documented_weight=20,
                )
                state = "body"
            elif state == "body" and kind == "chunk":
                raw = base64.b64decode(data, validate=True)
                wire_size += len(raw)
                if wire_size > MAX_BODY + 65536:
                    raise ValueError("response_limit")
                journal.chunk(raw)
            elif state == "body" and kind == "response":
                journal.append("response_complete", **data)
                outcome = data
                state = "close"
            elif state == "close" and kind == "closed" and data is None:
                journal.append("child_transport_closed")
                state = "done"
            else:
                raise ValueError("child_protocol")
            channel.send("ack", sequence)
            sequence += 1
        proc.wait(timeout=2)
        if proc.returncode:
            raise ValueError("child_exit")
        journal.append("completed", gets=1, network_admitted=False)
    except BaseException as exc:
        failure = exc
        if journal is not None:
            with suppress(Exception):
                journal.append("failed", error_type=type(exc).__name__)
    finally:
        # Revoke permissions before deleting topology or restoring ordinary traffic.
        if created["rules"]:
            try:
                nft(
                    f"flush set inet {TABLE} permits\nflush set netdev {TABLE} permits\nflush set inet {TABLE} blackout\nflush set netdev {TABLE} blackout\n"
                )
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if channel is not None:
            channel.sock.close()
        elif parent is not None:
            parent.close()
        if proc is not None:
            if proc.poll() is None:
                with suppress(ProcessLookupError):
                    proc.kill()
            with suppress(Exception):
                proc.wait(timeout=2)
        if pidfd is not None:
            os.close(pidfd)
        if created["forward"]:
            try:
                rows = json.loads(
                    run("/usr/sbin/nft", "-j", "list", "chain", "ip", "filter", "FORWARD")
                )["nftables"]
                handles = [
                    row["rule"]["handle"]
                    for row in rows
                    if row.get("rule", {}).get("comment") == TAG
                ]
                if len(handles) != 2:
                    raise ValueError("owned_forward_handles")
                nft(
                    "".join(
                        f"delete rule ip filter FORWARD handle {handle}\n" for handle in handles
                    )
                )
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for enabled, command in (
            (created["link"], ("/usr/sbin/ip", "link", "delete", HOST_LINK)),
            (created["namespace"], ("/usr/sbin/ip", "netns", "delete", NS)),
        ):
            if enabled:
                try:
                    run(*command)
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
        if created["rules"]:
            try:
                nft(
                    f"delete table inet {TABLE}\ndelete table netdev {TABLE}\ndelete table ip {TABLE}\n"
                )
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if journal is not None:
            try:
                journal.append("cleanup", errors=cleanup_errors)
            except Exception as exc:
                cleanup_errors.append("cleanup_record:" + type(exc).__name__)
            journal.close()
        authority.close()
    return {
        "status": "completed"
        if failure is None and not cleanup_errors
        else "failed_consumed_no_retry",
        "failure_type": type(failure).__name__ if failure else None,
        "cleanup_errors": cleanup_errors,
        "response": outcome,
        "scope_consumed": journal is not None or ROOT.exists(),
        "network_admitted": False,
        "trading_admitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--execute", metavar="PLAN_SHA256")
    group.add_argument("--child", nargs=3, metavar=("FD", "PARENT_PID", "DESTINATION"))
    args = parser.parse_args()
    if args.child:
        fd, pid, destination = args.child
        child(int(fd), int(pid), destination)
        return 0
    result = execute(args.execute)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

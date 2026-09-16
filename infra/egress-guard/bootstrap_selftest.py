"""Disposable privileged acceptance of the exact one-shot host bootstrap runner."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import signal
import socket
import struct
import subprocess
import time
from pathlib import Path

ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def namespaces():
    return {key: os.readlink("/proc/self/ns/" + key) for key in ("mnt", "net", "pid")}


def run(*args, text=None):
    p = subprocess.run(args, input=text, text=True, capture_output=True, env=ENV, timeout=5)
    if p.returncode:
        raise RuntimeError(p.stderr[-1500:])
    return p.stdout


def write(path, raw, mode=0o444):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fchmod(out.fileno(), mode)
        os.fsync(out.fileno())


SERVER = r"""
import json,socket,ssl,threading,time
from pathlib import Path
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain('/run/fixture.pem','/run/fixture.key')
def plain():
 s=socket.socket();s.bind(('10.0.0.254',8080));s.listen()
 while True:
  c,_=s.accept();c.sendall(b'control');c.close()
threading.Thread(target=plain,daemon=True).start()
def datagrams():
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('10.0.0.254',8081));count=0
 while True:
  s.recvfrom(1024);count+=1;Path('/run/raw-count').write_text(str(count))
threading.Thread(target=datagrams,daemon=True).start()
s=socket.socket();s.bind(('10.0.0.254',443));s.listen()
Path('/run/peer-ready').write_text('ready')
c,_=s.accept()
with ctx.wrap_socket(c,server_side=True) as tls:
 request=b''
 while b'\r\n\r\n' not in request: request+=tls.recv(4096)
 Path('/run/received-request').write_bytes(request)
 time.sleep(0.8)
 body=b'{"rateLimits":[{"rateLimitType":"REQUEST_WEIGHT","interval":"MINUTE","intervalNum":1,"limit":6000}]}'
 tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-MBX-USED-WEIGHT-1M: 20\r\n\r\n'+body)
 try: tls.recv(1)
 except OSError: pass
time.sleep(30)
"""


def probe():
    s = socket.socket()
    s.settimeout(0.2)
    try:
        s.connect(("10.0.0.254", 8080))
        return s.recv(16) == b"control"
    except OSError:
        return False
    finally:
        s.close()


def raw_probe(*, blocked=False):
    host = json.loads(run("/usr/sbin/ip", "-j", "link", "show", "enp0s6"))[0]["address"]
    peer = json.loads(
        run("/usr/sbin/ip", "-n", "bootstrap-peer", "-j", "link", "show", "peer-wan")
    )[0]["address"]
    payload = b"raw-control"
    udp = struct.pack("!4H", 33333, 8081, 8 + len(payload), 0) + payload
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(udp),
        1,
        0,
        64,
        17,
        0,
        socket.inet_aton("10.0.0.136"),
        socket.inet_aton("10.0.0.254"),
    )
    total = sum(struct.unpack("!10H", header))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    header = header[:10] + struct.pack("!H", (~total) & 65535) + header[12:]
    frame = (
        bytes.fromhex(peer.replace(":", ""))
        + bytes.fromhex(host.replace(":", ""))
        + b"\x08\x00"
        + header
        + udp
    )
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))
    try:
        s.bind(("enp0s6", 0))
        try:
            s.send(frame)
        except OSError as exc:
            if not blocked or exc.errno != errno.ENOBUFS:
                raise
    finally:
        s.close()
    time.sleep(0.05)
    return int(Path("/run/raw-count").read_text()) if Path("/run/raw-count").exists() else 0


def worker(payload):
    signal.signal(
        signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("fixture_deadline"))
    )
    signal.alarm(55)
    if (
        os.getuid() != 0
        or os.getpid() != 1
        or any(namespaces()[key] == value for key, value in payload["original"].items())
    ):
        raise ValueError("fresh_root_namespaces_required")
    installed = Path("/usr/local/lib/trader-egress")
    sources = {p.name: p.read_bytes() for p in installed.iterdir() if p.name.endswith(".py")}
    manifest = Path("/etc/trader/egress-install.json").read_bytes()
    run("/usr/bin/mount", "--make-rprivate", "/")
    for target in ("/usr/local/lib", "/etc/trader", "/var/lib/trader/egress", "/run", "/tmp"):
        run(
            "/usr/bin/mount",
            "-t",
            "tmpfs",
            "-o",
            "size=32m,mode=0755,nosuid,nodev",
            "tmpfs",
            target,
        )
    Path("/var/lib/trader/egress").chmod(0o700)
    installed.mkdir(mode=0o755)
    for name, raw in sources.items():
        write(installed / name, raw)
    write("/etc/trader/egress-install.json", manifest, 0o600)
    code = Path("/usr/local/lib/trader-egress-bootstrap-v1")
    code.mkdir(mode=0o755)
    write(
        code / "README.md",
        b"Disposable acceptance copies only. No host activation. Next: fixed bootstrap runner.\n",
    )
    write(code / "bootstrap_once.py", payload["runner"].encode())
    write(code / "http_parser.py", payload["parser"].encode())
    run(
        "/usr/bin/openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=testnet.binance.vision",
        "-addext",
        "subjectAltName=DNS:testnet.binance.vision",
        "-keyout",
        "/run/fixture.key",
        "-out",
        "/run/fixture.pem",
    )
    run("/usr/bin/mount", "--bind", "/run/fixture.pem", "/etc/ssl/certs/ca-certificates.crt")
    run("/usr/sbin/ip", "netns", "add", "bootstrap-peer")
    run("/usr/sbin/ip", "link", "add", "enp0s6", "type", "veth", "peer", "name", "peer-wan")
    run("/usr/sbin/ip", "link", "set", "peer-wan", "netns", "bootstrap-peer")
    run("/usr/sbin/ip", "address", "add", "10.0.0.136/24", "dev", "enp0s6")
    run("/usr/sbin/ip", "link", "set", "enp0s6", "up")
    run(
        "/usr/sbin/ip", "-n", "bootstrap-peer", "address", "add", "10.0.0.254/24", "dev", "peer-wan"
    )
    run("/usr/sbin/ip", "-n", "bootstrap-peer", "link", "set", "peer-wan", "up")
    run("/usr/sbin/sysctl", "-w", "net.ipv4.ip_forward=1")
    run(
        "/usr/sbin/nft",
        "-f",
        "-",
        text="table ip filter {\n chain FORWARD { type filter hook forward priority 0; policy drop; }\n}\n",
    )
    server = subprocess.Popen(
        ["/usr/sbin/ip", "netns", "exec", "bootstrap-peer", "/usr/bin/python3", "-I", "-c", SERVER],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
    )
    deadline = time.monotonic() + 3
    while not Path("/run/peer-ready").exists():
        if server.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("peer_failed:" + server.communicate()[1].decode()[-1000:])
        time.sleep(0.01)
    assert probe()
    assert raw_probe() == 1
    document = json.loads(manifest)
    plan = {
        "schema_version": "portfolio.egress_bootstrap_execution.v1",
        "scope": "portfolio.testnet_rest_bootstrap.v1",
        "maintenance_accepted": True,
        "unknown_prior_usage_accepted": True,
        "wan_interface": "enp0s6",
        "private_ipv4": "10.0.0.136",
        "public_ipv4": "149.118.158.46",
        "destination_ipv4": "10.0.0.254",
        "source_commit": "fixture-only",
        "installation_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "collector": document["collector"],
        "helper_sha256": hashlib.sha256(payload["runner"].encode()).hexdigest(),
        "parser_sha256": hashlib.sha256(payload["parser"].encode()).hexdigest(),
        "ca_sha256": hashlib.sha256(
            Path("/etc/ssl/certs/ca-certificates.crt").read_bytes()
        ).hexdigest(),
        "fixture_only": True,
        "created_ns": time.time_ns(),
        "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "vnic_mac": json.loads(run("/usr/sbin/ip", "-j", "link", "show", "enp0s6"))[0]["address"],
    }
    raw = (json.dumps(plan, sort_keys=True) + "\n").encode()
    write("/etc/trader/egress-bootstrap-v1.json", raw, 0o600)
    pin = hashlib.sha256(raw).hexdigest()
    command = ["/usr/bin/python3", "-I", str(code / "bootstrap_once.py"), "--execute", pin]
    helper = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    active = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if helper.poll() is not None:
            break
        p = Path("/var/lib/trader/egress/rest-bootstrap-v1/events.jsonl")
        if p.exists() and b'"kind":"window_active"' in p.read_bytes():
            active = True
            break
        time.sleep(0.005)
    if not active:
        out, err = helper.communicate(timeout=3)
        raise RuntimeError("no_active_window:" + out.decode() + err.decode())
    assert not probe(), "competing host escaped blackout"
    assert raw_probe(blocked=True) == 1, "AF_PACKET IP escaped physical egress guard"
    netdev = json.loads(
        run("/usr/sbin/nft", "-j", "list", "table", "netdev", "trader_egress_bootstrap_v1")
    )["nftables"]
    assert any(
        "@blackout" in json.dumps(row.get("rule", {}))
        and any(
            expr.get("counter", {}).get("packets", 0) > 0
            for expr in row.get("rule", {}).get("expr", [])
        )
        for row in netdev
    )
    if payload["case"] == "crash":
        helper.kill()
        helper.communicate(timeout=2)
        assert not probe()
        deadline = time.monotonic() + 21
        while not probe():
            if time.monotonic() > deadline:
                raise RuntimeError("ordinary_traffic_not_restored_by_kernel")
            time.sleep(0.2)
        script = "import socket; s=socket.socket();s.settimeout(.2);s.connect(('10.0.0.254',443))"
        denied = subprocess.run(
            [
                "/usr/sbin/ip",
                "netns",
                "exec",
                "trader-egress-bootstrap-v1",
                "/usr/bin/python3",
                "-I",
                "-c",
                script,
            ],
            capture_output=True,
            env=ENV,
            timeout=2,
        )
        assert denied.returncode != 0, "collector escaped expired permission"
        result = {
            "status": "crash_expiry_passed",
            "ordinary_traffic_restored": True,
            "collector_still_quarantined": True,
        }
    else:
        out, err = helper.communicate(timeout=15)
        if helper.returncode:
            raise RuntimeError(out.decode() + err.decode())
        result = json.loads(out)
        assert result["status"] == "completed"
        assert probe()
        request = Path("/run/received-request").read_bytes()
        assert (
            request
            == b"GET /api/v3/exchangeInfo HTTP/1.1\r\nHost: testnet.binance.vision\r\nConnection: close\r\n\r\n"
        )
        assert not Path("/run/netns/trader-egress-bootstrap-v1").exists()
        current = json.loads(run("/usr/sbin/nft", "-j", "list", "ruleset"))["nftables"]
        assert all(
            row.get("table", {}).get("name") != "trader_egress_bootstrap_v1" for row in current
        )
        assert all(
            row.get("rule", {}).get("comment") != "trader-egress-bootstrap-v1-owned"
            for row in current
        )
        result.update(
            {
                "one_fixed_get": True,
                "competing_host_blocked": True,
                "ordinary_traffic_restored": True,
                "owned_rules_and_topology_removed": True,
            }
        )
    assert raw_probe() == 2, "raw IP not restored after window"
    result["raw_ip_blocked_and_restored"] = True
    original = Path("/var/lib/trader/egress/rest-bootstrap-v1/events.jsonl").read_bytes()
    again = subprocess.run(command, capture_output=True, env=ENV, timeout=5)
    assert again.returncode != 0
    assert Path("/var/lib/trader/egress/rest-bootstrap-v1/events.jsonl").read_bytes() == original
    result.update(
        {
            "case": payload["case"],
            "reexecution_refused": True,
            "host_network_modified": False,
            "venue_requests_made": 0,
            "runner_sha256": plan["helper_sha256"],
        }
    )
    server.kill()
    server.communicate(timeout=3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("success", "crash"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("run ordinary-user namespace wrapper")
    directory = Path(__file__).resolve().parent
    root = directory.parents[1]
    payload = {
        "source": Path(__file__).read_text(),
        "runner": (directory / "bootstrap_once.py").read_text(),
        "parser": (root / "apps/strategies_nautilus/portfolio_tls_provenance.py").read_text(),
        "original": namespaces(),
        "case": args.case,
    }
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        bootstrap = "import json,sys; p=json.load(sys.stdin); s={'__name__':'fixture'}; exec(compile(p['source'],'<fixture>','exec'),s); print(json.dumps(s['worker'](p),sort_keys=True))"
        result = subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/bin/unshare",
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
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=ENV,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:])
        assert namespaces() == payload["original"]
        raw = result.stdout.encode()
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    print(
        json.dumps(
            {
                "case": args.case,
                "status": "passed",
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "host_network_modified": False,
                "venue_requests_made": 0,
            }
        )
    )


if __name__ == "__main__":
    main()

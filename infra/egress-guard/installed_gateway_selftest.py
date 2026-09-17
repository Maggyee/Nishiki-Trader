"""Disposable fixed installation/UID gateway integration; never install on the host."""

from __future__ import annotations

import argparse
import base64
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

SCENARIOS = ("success", "code_drift", "account_drift", "storage_drift", "controller_crash")
TLS_SCENARIOS = (
    "tls_success",
    "tls_slow_body",
    "tls_bad_certificate",
    "tls_duplicate_weight",
    "tls_truncated",
    "tls_crash",
)
RECEIPT_SCENARIOS = TLS_SCENARIOS + (
    "receipt_child_death",
    "receipt_controller_crash",
    "receipt_code_drift",
    "receipt_storage_drift",
)
IPC_SCENARIOS = (
    "ipc_success",
    "ipc_child_death",
    "ipc_code_drift",
    "ipc_account_drift",
    "ipc_storage_drift",
    "ipc_controller_crash",
)
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def load(raw):
    scope = {"__name__": "installed_gateway_acceptance"}
    exec(compile(raw, "<fixed-fixture-source>", "exec"), scope)
    return scope


PROBE = r"""
import errno,json,os,socket
from pathlib import Path
checks=[]
def denied(name, operation):
    try:
        result=operation()
    except OSError as exc:
        if exc.errno not in (errno.EACCES,errno.EPERM): raise
        checks.append(name)
    else:
        if isinstance(result,int): os.close(result)
        raise RuntimeError('unexpected_permission:'+name)
code=Path('/usr/local/lib/trader-egress')
for name in ('installed_gateway.py','gateway_tls.py','gateway_joint_ipc.py','gateway_tls_receipt.py','ledger_gateway.py','selftest.py','portfolio_rate_evidence.py','portfolio_tls_provenance.py','portfolio_egress_ledger.py'):
    path=code/name
    assert path.read_bytes()
    denied('write:'+name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+name,lambda:os.unlink(path))
    denied('chmod:'+name,lambda:os.chmod(path,0o644))
for path in (Path('/etc/trader/egress-gateway-fixture.json'),Path('/run/trader-egress-gateway-fixture.json'),Path('/var/lib/trader/egress/local-egress-attempts-v1/events.jsonl'),Path('/var/lib/trader/egress/local-egress-attempts-v1/kernel.jsonl')):
    denied('read:'+path.name,lambda:os.open(path,os.O_RDONLY))
    denied('write:'+path.name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+path.name,lambda:os.unlink(path))
denied('create_alternative_scope',lambda:os.mkdir('/var/lib/trader/egress/replacement'))
with socket.socket() as s:
    denied('forge_socket_mark',lambda:s.setsockopt(socket.SOL_SOCKET,socket.SO_MARK,29810))
with socket.socket() as s:
    s.settimeout(0.3)
    try: s.connect(('198.51.100.2',23456))
    except (TimeoutError,PermissionError): checks.append('unmarked_egress_denied')
    else: raise RuntimeError('unmarked_egress_allowed')
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
assert os.getuid()!=0 and status['Groups'].strip()=='' and status['NoNewPrivs'].strip()=='1'
assert all(int(status[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
print(json.dumps({'checks':checks,'uid':os.getuid(),'gid':os.getgid()}))
"""


TLS_PEER = r"""
import hashlib,json,os,socket,ssl,sys,time
scenario=sys.argv[1]
body=json.dumps({'rateLimits':[
 {'rateLimitType':'REQUEST_WEIGHT','interval':'MINUTE','intervalNum':1,'limit':6000},
 {'rateLimitType':'RAW_REQUESTS','interval':'MINUTE','intervalNum':5,'limit':61000},
 {'rateLimitType':'CONNECTIONS','interval':'MINUTE','intervalNum':5,'limit':300}
]},separators=(',',':')).encode()
headers=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-MBX-USED-WEIGHT-1M: 20\r\n'
if scenario=='tls_duplicate_weight': headers+=b'x-mbx-used-weight-1m: 20\r\n'
headers+=b'Connection: close\r\n\r\n'
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/etc/trader/egress-gateway-fixture-ca.pem','/run/gateway-tls-key.pem')
report={'tls_connections':0,'http_requests':0,'request_sha256':None}
def save():
    with open('/run/gateway-tls-peer.json','w') as out:
        json.dump(report,out,sort_keys=True)
        out.flush();os.fsync(out.fileno())
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('198.51.100.2',23456));listener.listen(1);listener.settimeout(10)
    print('ready',flush=True)
    raw,_=listener.accept();report['tls_connections']=1;save()
    try:
        with context.wrap_socket(raw,server_side=True) as connection:
            connection.settimeout(5)
            request=b''
            while b'\r\n\r\n' not in request:
                chunk=connection.recv(4096)
                if not chunk: raise ValueError('no_request')
                request+=chunk
                if len(request)>4096: raise ValueError('request_limit')
            expected=b'GET /api/v3/exchangeInfo HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n'
            if request!=expected: raise ValueError('unexpected_request')
            report['http_requests']=1;report['request_sha256']=hashlib.sha256(request).hexdigest();save()
            connection.sendall(headers)
            if scenario in {'tls_slow_body','tls_crash'}: time.sleep(1.2 if scenario=='tls_slow_body' else 2)
            connection.sendall(body[:5] if scenario=='tls_truncated' else body)
    except (ssl.SSLError,OSError,ValueError) as exc:
        report['ended_with']=type(exc).__name__;save()
"""


def worker(payload):
    base = load(payload["base_source"])
    base["require_isolation"](payload["original"])
    receipt = payload.get("tls_receipt_profile", False)
    tls = payload.get("tls_profile", False) or receipt
    ipc = payload.get("joint_ipc_profile", False)
    if (
        type(receipt) is not bool
        or type(tls) is not bool
        or type(ipc) is not bool
        or (tls and ipc)
        or payload["scenario"]
        not in (
            IPC_SCENARIOS
            if ipc
            else RECEIPT_SCENARIOS
            if receipt
            else TLS_SCENARIOS
            if tls
            else SCENARIOS
        )
    ):
        raise ValueError("unknown_fixture_scenario")
    # The existing pinned installer and its 40 checks run before extension staging.
    installed = base["worker"](payload)
    signal.alarm(60)
    run, write = base["run"], base["write"]
    entry = load(payload["sources"]["installed_gateway.py"])
    if set(payload["sources"]) != set(entry["FILES"]):
        raise ValueError("fixture_source_inventory")
    pins = {name: base["sha"](raw.encode()) for name, raw in payload["sources"].items()}
    if pins != payload["source_sha256"]:
        raise ValueError("fixture_source_selection")
    for name in entry["FILES"]:
        write(entry["CODE"] + "/" + name, payload["sources"][name].encode(), 0o444)
    base_manifest = Path("/etc/trader/egress-install.json").read_bytes()
    manifest = {
        "schema_version": entry["PROFILE"],
        "base_manifest_sha256": base["sha"](base_manifest),
        "files": pins,
    }
    write(entry["MANIFEST"], json.dumps(manifest, sort_keys=True).encode(), 0o600)
    write(
        entry["CONTEXT"],
        json.dumps(
            {
                "profile": entry["PROFILE"],
                "original": payload["original"],
                "isolated": base["namespaces"](),
            },
            sort_keys=True,
        ).encode(),
        0o600,
    )
    guards = load(payload["sources"]["selftest.py"])
    gateway = load(payload["sources"]["ledger_gateway.py"])
    ledger_module = gateway["load_ledger"](payload["sources"])
    peer = guards["Child"](payload["sources"]["selftest.py"])
    controller = tls_peer = None
    try:
        ip, nft, network_run = guards["IP"], guards["NFT"], guards["run"]
        network_run(ip, "link", "set", "lo", "up")
        network_run(ip, "link", "add", "wan", "type", "veth", "peer", "name", "peer")
        network_run(ip, "link", "set", "peer", "netns", str(peer.process.pid))
        network_run(ip, "link", "set", "wan", "up")
        network_run(ip, "address", "add", "198.51.100.1/24", "dev", "wan")
        peer.ip("link", "set", "peer", "up")
        for address in ("198.51.100.2/24", "198.51.100.3/24"):
            peer.ip("address", "add", address, "dev", "peer")
        for address in ("fd00:7472:2::2/64", "fd00:7472:2::3/64"):
            peer.ip("-6", "address", "add", address, "dev", "peer", "nodad")
        if tls:
            hostname = (
                "wrong.fixture.invalid"
                if payload["scenario"] == "tls_bad_certificate"
                else "rest.fixture.invalid"
            )
            run(
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-config",
                "/dev/null",
                "-subj",
                "/CN=" + hostname,
                "-addext",
                "subjectAltName=DNS:" + hostname,
                "-keyout",
                "/run/gateway-tls-key.pem",
                "-out",
                "/etc/trader/egress-gateway-fixture-ca.pem",
            )
            Path("/etc/trader/egress-gateway-fixture-ca.pem").chmod(0o444)
            Path("/run/gateway-tls-key.pem").chmod(0o600)
            tls_peer = subprocess.Popen(
                [
                    "/usr/bin/nsenter",
                    f"--net=/proc/{peer.process.pid}/ns/net",
                    "/usr/bin/setpriv",
                    "--bounding-set=-all",
                    "--inh-caps=-all",
                    "--ambient-caps=-all",
                    "--no-new-privs",
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    TLS_PEER,
                    payload["scenario"],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
            )
            if tls_peer.stdout.readline().strip() != "ready":
                raise RuntimeError("tls_peer_failed:" + tls_peer.stderr.read()[-2000:])
        elif peer.request({"action": "serve"}) != {"ok": True}:
            raise RuntimeError("fixture_peer_not_ready")
        network_run(nft, "-f", "-", text=gateway["RULES"])
        if ipc:
            return worker_ipc(payload, installed, entry, guards, ledger_module, manifest)
        command = [
            "/usr/bin/python3",
            "-I",
            entry["CODE"] + "/installed_gateway.py",
            "--tls-receipt-fixture" if receipt else "--tls-fixture" if tls else "--fixture",
        ]
        controller = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=ENV,
            cwd="/",
        )
        line = controller.stdout.readline()
        if not line:
            raise RuntimeError("installed_controller_not_ready:" + controller.stderr.read()[-3000:])
        ready = json.loads(line)
        if ready["stage"] != "activated":
            raise RuntimeError("installed_controller_wrong_stage")
        identity = ready["binding"]["collector"]["process"]
        account = installed["fixture_account"]
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
        ):
            raise RuntimeError("installed_collector_identity")
        descriptors = [os.readlink(p) for p in Path(f"/proc/{identity['pid']}/fd").iterdir()]
        if any(
            any(
                prefix in target
                for prefix in ("/var/lib/trader", entry["CODE"], "/etc/trader", entry["CONTEXT"])
            )
            for target in descriptors
        ):
            raise RuntimeError("privileged_file_descriptor_inherited")
        checks = [
            "fixed_root_owned_sources_and_manifest_loaded",
            "distinct_uid_authenticated_before_preparation",
            "collector_has_no_privileged_file_descriptors",
        ]

        def denied_counter():
            rows = json.loads(
                network_run(
                    nft, "-j", "list", "counter", "inet", "fixture_ledger_gateway", "output_denied"
                )
            )
            return next(row["counter"]["packets"] for row in rows["nftables"] if "counter" in row)

        before = denied_counter()
        probe = json.loads(
            run(
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
                "-c",
                PROBE,
            )
        )
        if (probe["uid"], probe["gid"]) != (
            account["uid"],
            account["gid"],
        ) or denied_counter() <= before:
            raise RuntimeError("dedicated_uid_or_packet_denial_missing")
        checks.extend(probe["checks"])
        scenario = payload["scenario"]
        restore = None
        if scenario == "code_drift":
            target = Path(entry["CODE"]) / "ledger_gateway.py"
            original = target.read_bytes()
            target.write_bytes(original + b"\n# injected fixture drift\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "account_drift":
            target = Path("/etc/group")
            original = target.read_bytes()
            target.write_bytes(original + b"foreign:x:22000:trader-egress\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "storage_drift":
            target = Path(entry["STORAGE"])
            target.chmod(0o755)

            def restore():
                target.chmod(0o700)

        late_receipt = scenario.startswith("receipt_")
        if late_receipt:
            controller.stdin.write("continue\n")
            controller.stdin.flush()
            for stage in ("tls_headers_persisted", "receipt_prepared"):
                if json.loads(controller.stdout.readline()) != {"stage": stage}:
                    raise RuntimeError("receipt_barrier_missing")
            rows = json.loads(
                network_run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("receipt_wait_retained_permission")
            checks.append("kernel_revoked_before_receipt_wait")
            if scenario == "receipt_child_death":
                child_fd = os.pidfd_open(identity["pid"])
                try:
                    signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                    if not select.select([child_fd], [], [], 2)[0]:
                        raise RuntimeError("receipt_child_not_dead")
                finally:
                    os.close(child_fd)
            elif scenario == "receipt_code_drift":
                target = Path(entry["CODE"]) / "gateway_tls_receipt.py"
                original = target.read_bytes()
                target.write_bytes(original + b"\n# fixture drift\n")

                def restore():
                    target.write_bytes(original)
            elif scenario == "receipt_storage_drift":
                target = Path(entry["STORAGE"])
                target.chmod(0o755)

                def restore():
                    target.chmod(0o700)

        if scenario == "receipt_controller_crash":
            orphan_fd = os.pidfd_open(identity["pid"])
            controller.kill()
            controller.communicate(timeout=5)
            try:
                if (
                    controller.returncode != -signal.SIGKILL
                    or not select.select([orphan_fd], [], [], 5)[0]
                ):
                    raise RuntimeError("receipt_controller_or_orphan_survived")
                os.waitpid(identity["pid"], 0)
            finally:
                os.close(orphan_fd)
            terminal = {"status": "controller_sigkill", "revoked": True}
            checks.append("receipt_controller_death_exits_child_with_no_kernel_permit")
        elif scenario in {"controller_crash", "tls_crash"}:
            if tls:
                controller.stdin.write("continue\n")
                controller.stdin.flush()
                if json.loads(controller.stdout.readline()) != {"stage": "tls_headers_persisted"}:
                    raise RuntimeError("tls_crash_header_persistence_not_acknowledged")
            controller.kill()
            stdout, stderr = controller.communicate(timeout=5)
            if controller.returncode != -signal.SIGKILL:
                raise RuntimeError("controller_sigkill_failed")
            rows = json.loads(
                network_run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if not any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("crash_permission_not_observed")
            time.sleep(5.2)
            terminal = {"status": "controller_sigkill", "revoked": None}
            checks.append("controller_death_retains_permit_until_kernel_expiry")
        else:
            stdout, stderr = controller.communicate(
                "continue\ncontinue\n" if receipt and not late_receipt else "continue\n", timeout=10
            )
            if controller.returncode:
                raise RuntimeError("installed_controller_failed:" + stderr[-3000:])
            messages = [json.loads(line) for line in stdout.splitlines()]
            expected_progress = (
                [{"stage": "tls_headers_persisted"}]
                if tls and scenario != "tls_bad_certificate"
                else []
            )
            if receipt and scenario in {"tls_success", "tls_slow_body"}:
                expected_progress.append({"stage": "receipt_prepared"})
            if late_receipt:
                expected_progress = []
            if not messages or messages[:-1] != expected_progress:
                raise RuntimeError("unexpected_controller_progress")
            terminal = messages[-1]
            if (
                terminal["status"]
                != (
                    ("fixture_receipt_succeeded" if receipt else "fixture_tls_succeeded")
                    if scenario in {"tls_success", "tls_slow_body"}
                    else "fixture_echo_succeeded"
                    if scenario == "success"
                    else "refused"
                )
                or not terminal["revoked"]
            ):
                raise RuntimeError("wrong_installed_gateway_outcome")
        if restore is not None:
            restore()
        before = denied_counter()
        try:
            gateway["marked_echo"]()
        except OSError:
            pass
        else:
            raise RuntimeError("marked_socket_not_denied_after_terminal")
        if denied_counter() <= before:
            raise RuntimeError("terminal_deny_counter_missing")
        checks.append("marked_socket_kernel_denied_after_terminal_or_expiry")
        scope = Path(entry["STORAGE"]) / ledger_module.SCOPE
        attempts, lifecycle = (
            (scope / "events.jsonl").read_bytes(),
            (scope / "kernel.jsonl").read_bytes(),
        )
        attempt_report = ledger_module.replay(
            attempts,
            expected_sha256=ledger_module.digest(attempts),
            binding_sha256=ready["binding_sha256"],
        )
        life_report = gateway["replay_lifecycle"](
            ledger_module,
            lifecycle,
            expected_sha256=ledger_module.digest(lifecycle),
            attempts=attempts,
            binding_sha256=ready["binding_sha256"],
        )
        if attempt_report["pending_attempt"] != (
            None if scenario in {"success", "tls_success", "tls_slow_body"} else 0
        ):
            raise RuntimeError("pending_attempt_lost")
        if life_report["revocation_recorded"] != (
            scenario not in {"controller_crash", "storage_drift", "tls_crash"}
        ):
            raise RuntimeError("invented_or_missing_revocation_record")
        tls_result = {}
        if tls:
            raw_tls = (scope / "tls.jsonl").read_bytes()
            transport = load(payload["sources"]["gateway_tls.py"])
            trust = Path("/etc/trader/egress-gateway-fixture-ca.pem").read_bytes()
            replay = transport["replay"](
                raw_tls,
                expected_sha256=base["sha"](raw_tls),
                attempts=attempts,
                lifecycle=lifecycle,
                binding_sha256=ready["binding_sha256"],
                trust_sha256=base["sha"](trust),
                ledger_module=ledger_module,
                gateway_module=gateway,
                provenance=sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                rates=sys.modules["apps.strategies_nautilus.portfolio_rate_evidence"],
            )
            if (replay["status"] == "complete") != (
                scenario in {"tls_success", "tls_slow_body"} or late_receipt
            ):
                raise RuntimeError("tls_replay_completion_mismatch")
            if scenario == "tls_slow_body" and replay["header_age_at_body_ns"] < 1_000_000_000:
                raise RuntimeError("tls_header_receipt_refreshed")
            tls_peer.wait(timeout=5)
            peer_report = json.loads(Path("/run/gateway-tls-peer.json").read_bytes())
            if peer_report["tls_connections"] != 1 or peer_report["http_requests"] != (
                0 if scenario == "tls_bad_certificate" else 1
            ):
                raise RuntimeError("tls_peer_request_count_mismatch")
            checks.append("fixed_tls_request_and_original_header_receipt_verified")
            tls_result = {
                "tls_archive": raw_tls.decode(),
                "tls_replay": replay,
                "tls_trust_sha256": base["sha"](trust),
                "tls_trust_pem": trust.decode(),
                "tls_peer": peer_report,
            }
        if receipt and (scope / "receipt.jsonl").exists():
            receipt_code = load(payload["sources"]["gateway_tls_receipt.py"])
            receipt_raw = (scope / "receipt.jsonl").read_bytes()
            receipt_replay = receipt_code["replay"](
                receipt_raw,
                expected_sha256=base["sha"](receipt_raw),
                tls_raw=raw_tls,
                attempts=attempts,
                lifecycle=lifecycle,
                trust_sha256=base["sha"](trust),
                ledger_module=ledger_module,
                gateway_module=gateway,
                transport=transport,
                provenance=sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                rates=sys.modules["apps.strategies_nautilus.portfolio_rate_evidence"],
                binding_sha256=ready["binding_sha256"],
            )
            if (receipt_replay["status"] == "acknowledged") != (
                scenario in {"tls_success", "tls_slow_body"}
            ):
                raise RuntimeError("receipt_acknowledgement_mismatch")
            tls_result.update(receipt_archive=receipt_raw.decode(), receipt_replay=receipt_replay)
            checks.append("authenticated_consumer_receipt_replays_with_original_tls_clocks")
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or "FileExistsError" not in restarted.stderr
            or restarted.stdout
        ):
            raise RuntimeError("fresh_installed_process_reopened_consumed_scope")
        if (scope / "events.jsonl").read_bytes() != attempts or (
            scope / "kernel.jsonl"
        ).read_bytes() != lifecycle:
            raise RuntimeError("restart_changed_original_journals")
        if tls and (scope / "tls.jsonl").read_bytes() != raw_tls:
            raise RuntimeError("restart_changed_tls_journal")
        if (
            receipt
            and (scope / "receipt.jsonl").exists()
            and (scope / "receipt.jsonl").read_bytes() != receipt_raw
        ):
            raise RuntimeError("restart_changed_receipt_journal")
        checks.append("fresh_installed_process_refuses_scope_without_changing_journals")
        if (
            Path(entry["STORAGE"] + "/consumed.json").read_bytes()
            != b'{"fixture_only":true,"consumed":true}\n'
        ):
            raise RuntimeError("prior_consumed_fixture_state_changed")
        checks.append("prior_consumed_fixture_state_preserved")
        return {
            "scenario": scenario,
            "status": "passed",
            **tls_result,
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "gateway_manifest_sha256": base["sha"](Path(entry["MANIFEST"]).read_bytes()),
            "binding": ready["binding"],
            "binding_sha256": ready["binding_sha256"],
            "terminal": terminal,
            "attempt_archive": attempts.decode(),
            "lifecycle_archive": lifecycle.decode(),
            "attempt_replay": attempt_report,
            "lifecycle_replay": life_report,
        }
    finally:
        if controller is not None and controller.poll() is None:
            controller.kill()
            controller.communicate(timeout=3)
        if tls_peer is not None and tls_peer.poll() is None:
            tls_peer.kill()
            tls_peer.communicate(timeout=3)
        peer.stop()


def worker_ipc(payload, installed, entry, guards, module, manifest):
    """Shared installed fixture environment; IPC never activates a mark grant."""
    command = [
        "/usr/bin/python3",
        "-I",
        entry["CODE"] + "/installed_gateway.py",
        "--joint-ipc-fixture",
    ]
    controller = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
    )
    run, nft = guards["run"], guards["NFT"]
    checks = []
    restore = None
    try:
        line = controller.stdout.readline()
        if not line:
            raise RuntimeError("joint_ipc_controller_not_ready:" + controller.stderr.read()[-3000:])
        ready = json.loads(line)
        if ready["stage"] != "joint_ipc_ready":
            raise RuntimeError("joint_ipc_ready_required")
        identity = ready["binding"]["collector"]["process"]
        account = installed["fixture_account"]
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
        ):
            raise RuntimeError("joint_ipc_distinct_uid_required")
        descriptors = [os.readlink(p) for p in Path(f"/proc/{identity['pid']}/fd").iterdir()]
        if any(
            any(
                prefix in target
                for prefix in ("/var/lib/trader", entry["CODE"], "/etc/trader", entry["CONTEXT"])
            )
            for target in descriptors
        ):
            raise RuntimeError("joint_ipc_privileged_descriptor_inherited")
        checks.extend(
            [
                "fixed_installed_sources_held",
                "dedicated_uid_pid_authenticated",
                "no_privileged_descriptor_handoff",
            ]
        )
        scope = Path(entry["STORAGE"]) / module.IPC_SCOPE
        probe = json.loads(
            run(
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
                "-c",
                PROBE.replace("local-egress-attempts-v1", module.IPC_SCOPE),
            )
        )
        checks.extend(probe["checks"])
        controller.stdin.write("continue\n")
        controller.stdin.flush()
        barrier = controller.stdout.readline()
        if not barrier or json.loads(barrier) != {"stage": "joint_ipc_prepared", "index": 9}:
            raise RuntimeError("joint_ipc_midpoint_missing:" + controller.stderr.read()[-3000:])
        original = (scope / "events.jsonl").read_bytes()
        midway = module.replay(
            original,
            expected_sha256=module.digest(original),
            binding_sha256=ready["binding_sha256"],
            profile=module.IPC_PROFILE,
        )
        if midway["recorded_attempts"] != 10 or midway["pending_attempt"] != 9:
            raise RuntimeError("joint_ipc_unpersisted_receipt")
        checks.append("ten_operations_prepared_before_tenth_receipt")
        permits = json.loads(
            run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
        )
        if any(r.get("set", {}).get("elem") for r in permits["nftables"]):
            raise RuntimeError("ipc_granted_kernel_permission")
        checks.append("ipc_preparations_never_grant_kernel_permission")
        scenario = payload["scenario"]
        if scenario == "ipc_child_death":
            os.kill(identity["pid"], signal.SIGKILL)
        elif scenario == "ipc_code_drift":
            path = Path(entry["CODE"]) / "gateway_joint_ipc.py"
            before = path.read_bytes()
            path.write_bytes(before + b"\n# fixture drift\n")

            def restore():
                path.write_bytes(before)
        elif scenario == "ipc_account_drift":
            path = Path("/etc/group")
            before = path.read_bytes()
            path.write_bytes(before + b"foreign:x:22000:trader-egress\n")

            def restore():
                path.write_bytes(before)
        elif scenario == "ipc_storage_drift":
            path = Path(entry["STORAGE"])
            path.chmod(0o755)

            def restore():
                path.chmod(0o700)

        if scenario == "ipc_controller_crash":
            child_pidfd = os.pidfd_open(identity["pid"])
            try:
                controller.kill()
                stdout, stderr = controller.communicate(timeout=5)
                if controller.returncode != -signal.SIGKILL:
                    raise RuntimeError("joint_ipc_controller_did_not_die")
                if not select.select([child_pidfd], [], [], 2)[0]:
                    raise RuntimeError("joint_ipc_child_survived_channel_loss")
                os.waitpid(identity["pid"], 0)
                checks.append("controller_death_closes_channel_and_reaps_orphan")
            finally:
                os.close(child_pidfd)
            terminal = {"status": "controller_sigkill"}
        else:
            stdout, stderr = controller.communicate("continue\n", timeout=20)
            if controller.returncode:
                raise RuntimeError("joint_ipc_controller_failed:" + stderr[-3000:])
            terminal = json.loads(stdout)
            if terminal["status"] != (
                "joint_ipc_accounting_completed" if scenario == "ipc_success" else "refused"
            ):
                raise RuntimeError("joint_ipc_wrong_terminal")
        if restore:
            restore()
            restore = None
        raw = (scope / "events.jsonl").read_bytes()
        report = module.replay(
            raw,
            expected_sha256=module.digest(raw),
            binding_sha256=ready["binding_sha256"],
            profile=module.IPC_PROFILE,
        )
        expected = 20 if scenario == "ipc_success" else 10
        if report["recorded_attempts"] != expected or report["pending_attempt"] != (
            None if expected == 20 else 9
        ):
            raise RuntimeError("joint_ipc_consumption_lost")
        if not raw.startswith(original):
            raise RuntimeError("joint_ipc_original_prefix_changed")
        checks.append("success_or_failure_keeps_original_consumption")

        # Even a root-owned marked socket must remain denied: no grant ever occurred.
        def count():
            return next(
                r["counter"]["packets"]
                for r in json.loads(
                    run(
                        nft,
                        "-j",
                        "list",
                        "counter",
                        "inet",
                        "fixture_ledger_gateway",
                        "output_denied",
                    )
                )["nftables"]
                if "counter" in r
            )

        before_count = count()
        gateway = load(payload["sources"]["ledger_gateway.py"])
        try:
            gateway["marked_echo"]()
        except OSError:
            pass
        else:
            raise RuntimeError("joint_ipc_marked_connection_allowed")
        if count() <= before_count:
            raise RuntimeError("joint_ipc_missing_kernel_denial")
        checks.append("marked_socket_denied_after_ipc_or_crash")
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or "FileExistsError" not in restarted.stderr
            or restarted.stdout
        ):
            raise RuntimeError("joint_ipc_consumed_scope_reopened")
        if (scope / "events.jsonl").read_bytes() != raw:
            raise RuntimeError("joint_ipc_restart_mutated_archive")
        checks.append("fresh_installed_process_cannot_reopen_scope")
        if (
            Path(entry["STORAGE"] + "/consumed.json").read_bytes()
            != b'{"fixture_only":true,"consumed":true}\n'
        ):
            raise RuntimeError("prior_consumed_scope_changed")
        checks.append("prior_consumed_scope_preserved")
        return {
            "status": "passed",
            "scenario": scenario,
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "gateway_manifest_sha256": module.digest(Path(entry["MANIFEST"]).read_bytes()),
            "binding": ready["binding"],
            "binding_sha256": ready["binding_sha256"],
            "attempt_archive": raw.decode(),
            "attempt_replay": report,
            "terminal": terminal,
            "kernel_permission_granted": False,
            "transport_dispatch_verified": False,
            "venue_requests": 0,
            "network_admitted": False,
            "trading_admitted": False,
        }
    finally:
        if restore:
            restore()
        if controller.poll() is None:
            controller.kill()
        controller.communicate(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--tls-profile", action="store_true")
    profiles.add_argument("--tls-receipt-profile", action="store_true")
    profiles.add_argument("--joint-ipc-profile", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the disposable wrapper as an ordinary user")
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        directory = Path(__file__).resolve().parent
        base_source = (directory / "installation_selftest.py").read_text()
        base = load(base_source)
        installer = (directory / "package.py").read_bytes()
        if base["sha"](installer) != base["INSTALLER_PIN"]:
            raise ValueError("reviewed_installer_changed")
        package = load(installer)
        package["build"].__globals__["__file__"] = str(directory / "package.py")
        bundle = package["build"]()
        package["inspect"](bundle, base["PIN"])
        entry = load((directory / "installed_gateway.py").read_bytes())
        sources = {
            name: (
                (
                    directory.parents[1] / "apps/strategies_nautilus"
                    if name.startswith("portfolio_")
                    else directory
                )
                / name
            ).read_text()
            for name in entry["FILES"]
        }
        payload = {
            "source": Path(__file__).read_text(),
            "tls_profile": args.tls_profile,
            "tls_receipt_profile": args.tls_receipt_profile,
            "joint_ipc_profile": args.joint_ipc_profile,
            "base_source": base_source,
            "installer": installer.decode(),
            "bundle": base64.b64encode(bundle).decode(),
            "original": base["namespaces"](),
            "sources": sources,
            "source_sha256": {name: base["sha"](raw.encode()) for name, raw in sources.items()},
        }
        before = base["host_observation"]()
        reports = []
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'isolated_installed_gateway'}\nexec(compile(p['source'],'<fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
        for scenario in (
            IPC_SCENARIOS
            if args.joint_ipc_profile
            else RECEIPT_SCENARIOS
            if args.tls_receipt_profile
            else TLS_SCENARIOS
            if args.tls_profile
            else SCENARIOS
        ):
            command = [
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
            ]
            process = subprocess.Popen(
                command,
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
                    json.dumps({**payload, "scenario": scenario}), timeout=70
                )
            except BaseException:
                subprocess.run(
                    ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                    capture_output=True,
                    env=ENV,
                    timeout=5,
                    check=False,
                )
                process.communicate(timeout=5)
                raise
            if base["namespaces"]() != payload["original"] or base["host_observation"]() != before:
                raise RuntimeError("host_observation_changed")
            if process.returncode:
                raise RuntimeError(scenario + ":" + stderr[-5000:])
            report = json.loads(stdout)
            if report["status"] != "passed" or report["scenario"] != scenario:
                raise RuntimeError("invalid_installed_gateway_report")
            reports.append(report)
        result = {
            "schema_version": "portfolio.installed_gateway_acceptance.v1",
            "status": "passed",
            "tls_profile": args.tls_profile,
            "tls_receipt_profile": args.tls_receipt_profile,
            "joint_ipc_profile": args.joint_ipc_profile,
            "scenarios": reports,
            "source_sha256": payload["source_sha256"],
            "harness_sha256": base["sha"](payload["source"].encode()),
            "base_harness_sha256": base["sha"](base_source.encode()),
            "bundle_sha256": base["PIN"],
            "host_observations_unchanged": True,
            "host_before_after": before,
            "host_installation_performed": False,
            "venue_requests": 0,
            "power_loss_qualified": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
            "trading_admitted": False,
        }
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "scenarios": len(reports),
                "checks_per_scenario": [len(row["checks"]) for row in reports],
                "report_sha256": base["sha"](raw),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

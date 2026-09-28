"""Disposable installed joint-window --check acceptance; no host deployment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

BASE_HARNESS_PIN = "e2b0e9a59cd3805ebfac2fb4b4b2c1992e8e9d2865862cf70c3876c06e42346e"
ENTRY_PIN = "db9bacd6778111afdc4a163f305361bef6da8fecab56d5ec724b0d1cb66cdc7a"
SOURCES_PIN = "2c923d4b546fd0dbcbcf57fbfc4bafdb80e103611f0f38dcd9358cb6b6dea27f"
WINDOW_INSTALLER_PIN = "4ee75b36a3c902b571727a6383944861f13903ff251dbfb3442fcb6277614ce3"
SOURCES = (
    "gateway_window_entry.py",
    "gateway_window_sources.py",
    "gateway_window_kernel.py",
    "gateway_window_custody.py",
    "gateway_window_witness.py",
    "gateway_window_activation.py",
)
CODE = Path("/usr/local/lib/trader-egress")
MANIFEST = Path("/etc/trader/joint-window-sources-v1.json")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(raw):
    scope = {"__name__": "isolated_joint_window_fixture"}
    exec(compile(raw, "<reviewed-fixture>", "exec"), scope)
    return scope


def observation(base):
    result = base["host_observation"]()
    for path in (str(MANIFEST), str(CODE / SOURCES[0])):
        try:
            info = os.lstat(path)
            result["installation_paths"][path] = [
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_gid,
            ]
        except FileNotFoundError:
            result["installation_paths"][path] = "missing"
    return result


@contextmanager
def isolated_collector_path(base):
    """Build only disposable collector/WAN network namespaces and local veths."""
    if [row["ifname"] for row in json.loads(base["run"]("/usr/sbin/ip", "-j", "link", "show"))] != [
        "lo"
    ]:
        raise RuntimeError("fixture_joint_network_not_empty")
    processes = []
    try:
        for _ in range(2):
            process = subprocess.Popen(
                [
                    "/usr/bin/unshare",
                    "--net",
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    "import sys;print('ready',flush=True);sys.stdin.read()",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
            )
            processes.append(process)
            if process.stdout.readline().strip() != "ready":
                raise RuntimeError("fixture_joint_network_child_failed")
        collector, peer = processes
        ip = "/usr/sbin/ip"
        base["run"](ip, "link", "set", "lo", "up")
        for local, remote, pid, host_ip, child_ip in (
            ("gw-jc1", "client", collector.pid, "192.0.2.1/24", "192.0.2.2/24"),
            ("wan", "peer", peer.pid, "198.51.100.1/24", "198.51.100.2/24"),
        ):
            base["run"](ip, "link", "add", local, "type", "veth", "peer", "name", remote)
            base["run"](ip, "link", "set", remote, "netns", str(pid))
            base["run"](ip, "address", "add", host_ip, "dev", local)
            base["run"](ip, "link", "set", local, "up")
            base["run"](
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
            base["run"](
                "/usr/bin/nsenter", "-t", str(pid), "--net", ip, "link", "set", remote, "up"
            )
        base["run"](
            "/usr/bin/nsenter",
            "-t",
            str(collector.pid),
            "--net",
            ip,
            "route",
            "add",
            "198.51.100.0/24",
            "via",
            "192.0.2.1",
        )
        Path("/proc/sys/net/ipv4/ip_forward").write_text("1\n")
        yield {
            "pid": collector.pid,
            "peer_pid": peer.pid,
            "selection": {
                "host_link": "gw-jc1",
                "child_ipv4": "192.0.2.2",
                "source_ipv4": "198.51.100.1",
            },
        }
    finally:
        for process in reversed(processes):
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def installed_activation_probe(base, sources, base_manifest_sha256, route):
    """Join held installed bytes to a one-shot kernel transaction in private namespaces."""
    verifier = load(sources["gateway_window_entry.py"])["_load_base"]()
    inventory = load(sources["gateway_window_sources.py"])["RootSelectedWindowSources"](verifier())
    try:
        selected = {name: inventory.source(name) for name in SOURCES[2:]}
        account = dict(inventory.authority.account)
        if any(selected[name] != sources[name] for name in selected):
            raise RuntimeError("installed_joint_source_selection_changed")
    finally:
        inventory.close()

    kernel = SimpleNamespace(**load(selected["gateway_window_kernel.py"]))
    custody = SimpleNamespace(**load(selected["gateway_window_custody.py"]))
    witness_module = SimpleNamespace(**load(selected["gateway_window_witness.py"]))
    activation = SimpleNamespace(**load(selected["gateway_window_activation.py"]))
    existing = json.loads(base["run"]("/usr/sbin/nft", "-j", "list", "ruleset"))
    if any("metainfo" not in row for row in existing["nftables"]):
        raise RuntimeError("fixture_joint_nft_rules_preexisting")
    table = kernel.TABLE
    selected_mark = f"0x{kernel.COLLECTOR_MARK:x}"
    rules = f"""table inet {table} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept;
  meta mark {selected_mark} counter drop; oifname "lo" accept;
  meta nfproto @blackout counter drop; }}
 chain input {{ type filter hook input priority -310; policy accept;
  iifname "gw-jc1" counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept;
  iifname "gw-jc1" oifname "wan" ip saddr 192.0.2.2 ip daddr @permits tcp dport 443 meta mark set {selected_mark} accept;
  oifname "gw-jc1" iifname "wan" ip saddr @permits ip daddr 192.0.2.2 tcp sport 443 ct state established accept;
  iifname "gw-jc1" counter drop; oifname "gw-jc1" counter drop;
  meta nfproto @blackout counter drop; }}
}}
table netdev {table} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "wan" priority 0; policy accept;
  meta mark {selected_mark} ip saddr 198.51.100.1 ip daddr @permits tcp dport 443 accept;
  meta mark {selected_mark} counter drop;
  ether type @blackout counter drop; }}
}}
table ip fixture_joint_nat {{
 chain source {{ type nat hook postrouting priority 100; policy accept;
  oifname "wan" ip daddr 198.51.100.0/24 snat to 198.51.100.1;
 }}
}}
table inet fixture_joint_trace {{
 chain forward {{ type filter hook forward priority -309; policy accept;
  iifname "gw-jc1" meta mark {selected_mark} counter;
 }}
}}
table netdev fixture_joint_trace {{
 chain egress {{ type filter hook egress device "wan" priority 1; policy accept;
  meta mark {selected_mark} counter;
 }}
}}"""
    created = subprocess.run(
        ["/usr/sbin/nft", "-f", "-"],
        input=rules.encode(),
        capture_output=True,
        env=ENV,
        cwd="/",
        timeout=3,
        check=False,
    )
    if created.returncode:
        raise RuntimeError("fixture_joint_nft_create_failed:" + created.stderr.decode()[-500:])
    pins = {
        family: kernel.digest(kernel._static(kernel.read_table(family)["nftables"]))
        for family in kernel.KINDS
    }
    plan = {
        "schema_version": custody.PROFILE,
        "base_manifest_sha256": base_manifest_sha256,
        "observer_sha256": sha(selected["gateway_window_kernel.py"]),
        **custody._identity(),
        "wan_interface": "wan",
        "collector": route["selection"],
        "static_rules_sha256": pins,
    }
    base["write"](Path(custody.PLAN), (json.dumps(plan, sort_keys=True) + "\n").encode(), 0o600)
    holder = custody.RootSelectedWindowSnapshot(verifier())
    root = Path("/run/trader-egress-review/window-witness")
    root.mkdir(mode=0o700)
    journal = witness_module.WindowWitness(root, holder)
    try:
        result = activation.activate(holder, journal, duration_ms=10_000)
        archived = witness_module.replay(
            journal.expected, expected_sha256=witness_module.digest(journal.expected)
        )
        if (
            result["status"] != "local_blackout_transaction_observed_unqualified"
            or archived["activation_prepared"] is not True
            or archived["observations"] != 1
            or any(
                result[field] is not False
                for field in (
                    "activation_history_verified",
                    "source_authenticated",
                    "complete_caller_coverage_verified",
                    "network_admitted",
                )
            )
        ):
            raise RuntimeError("installed_joint_activation_unexpected_admission")
        for family in kernel.KINDS:
            sets = [row["set"] for row in kernel.read_table(family)["nftables"] if "set" in row]
            permits = [row for row in sets if row["name"] == "permits"]
            if len(permits) != 1 or permits[0].get("elem"):
                raise RuntimeError("installed_joint_permit_unexpectedly_populated")

        def collector_drop_count():
            rows = kernel.read_table("inet")["nftables"]
            forward = [
                row["rule"] for row in rows if "rule" in row and row["rule"]["chain"] == "forward"
            ]
            return next(
                expr["counter"]["packets"] for expr in forward[2]["expr"] if "counter" in expr
            )

        before_drop = collector_drop_count()
        probe = """
import json,os,socket
status=dict(line.split(':',1) for line in open('/proc/self/status').read().splitlines())
if os.getuid()==0 or int(status['CapEff'],16) or status['NoNewPrivs'].strip()!='1':
 raise RuntimeError('fixture_collector_still_privileged')
with socket.socket() as client:
 client.settimeout(0.6)
 try: client.connect(('198.51.100.2',443))
 except OSError: print(json.dumps({'connected':False}))
 else: print(json.dumps({'connected':True}))
"""
        client_result = json.loads(
            base["run"](
                "/usr/bin/nsenter",
                "-t",
                str(route["pid"]),
                "--net",
                "/usr/bin/setpriv",
                "--reuid",
                str(account["uid"]),
                "--regid",
                str(account["gid"]),
                "--clear-groups",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/usr/bin/python3",
                "-I",
                "-c",
                probe,
            )
        )
        if client_result != {"connected": False} or collector_drop_count() <= before_drop:
            raise RuntimeError("installed_joint_empty_permit_did_not_drop_collector")
        original_events = journal.expected

        def no_second_write(*_args, **_kwargs):
            raise RuntimeError("installed_joint_second_nft_write_attempted")

        try:
            activation.activate(holder, journal, duration_ms=10_000, runner=no_second_write)
        except ValueError as exc:
            if str(exc) != "joint_activation_root_fresh_scope_and_duration_required":
                raise
        else:
            raise RuntimeError("installed_joint_repeat_activation_allowed")
        if journal.expected != original_events:
            raise RuntimeError("installed_joint_repeat_activation_changed_archive")
    finally:
        journal.close()
        holder.close()
    permitted = isolated_permitted_packet(base, kernel, route, pins, account)
    return {
        "status": result["status"],
        "selection_sha256": result["selection_sha256"],
        "archive_sha256": witness_module.digest(journal.expected),
        "observations": archived["observations"],
        "activation_history_verified": result["activation_history_verified"],
        "source_authenticated": result["source_authenticated"],
        "complete_caller_coverage_verified": result["complete_caller_coverage_verified"],
        "collector_empty_permit_denied": True,
        "local_permitted_packet": permitted,
        "network_admitted": False,
    }


def isolated_permitted_packet(base, kernel, route, pins, account):
    """Test a short local grant only after the selected witness has closed."""

    def nft(script):
        process = subprocess.run(
            ["/usr/sbin/nft", "-f", "-"],
            input=script.encode("ascii"),
            capture_output=True,
            env=ENV,
            cwd="/",
            timeout=3,
            check=False,
        )
        if process.returncode:
            raise RuntimeError(
                "fixture_joint_nft_transaction_failed:" + process.stderr.decode()[-500:]
            )

    def count(family, chain):
        rows = json.loads(
            base["run"]("/usr/sbin/nft", "-j", "list", "table", family, "fixture_joint_trace")
        )["nftables"]
        rule = next(row["rule"] for row in rows if "rule" in row and row["rule"]["chain"] == chain)
        return next(expr["counter"]["packets"] for expr in rule["expr"] if "counter" in expr)

    server_source = """
import socket
with socket.socket() as listener:
 listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
 listener.bind(('198.51.100.2',443))
 listener.listen(1)
 listener.settimeout(3)
 print('ready',flush=True)
 with listener.accept()[0] as connection:
  connection.settimeout(2)
  if connection.recv(64)!=b'fixture-peer\\n': raise RuntimeError('fixture_peer_request_changed')
  print(connection.getpeername()[0],flush=True)
  connection.sendall(b'fixture-ok\\n')
"""
    peer = subprocess.Popen(
        [
            "/usr/bin/nsenter",
            "-t",
            str(route["peer_pid"]),
            "--net",
            "/usr/bin/python3",
            "-I",
            "-c",
            server_source,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
    )
    try:
        if peer.stdout.readline().strip() != "ready":
            raise RuntimeError("fixture_joint_peer_not_ready")
        for family in kernel.KINDS:
            rows = kernel.read_table(family)["nftables"]
            blackout = next(
                row["set"] for row in rows if row.get("set", {}).get("name") == "blackout"
            )
            kernel._elements(blackout, family)
        before_forward = count("inet", "forward")
        before_wan = count("netdev", "egress")
        nft(f"""add element inet {kernel.TABLE} permits {{ 198.51.100.2 timeout 5000ms }}
add element netdev {kernel.TABLE} permits {{ 198.51.100.2 timeout 5000ms }}""")
        try:
            try:
                kernel.observe(
                    expected_static_sha256=pins,
                    wan_interface="wan",
                    collector=route["selection"],
                )
            except ValueError as exc:
                if str(exc) != "kernel_window_set_type_or_early_permission":
                    raise
            else:
                raise RuntimeError("installed_joint_observer_accepted_temporary_permit")
            client_source = """
import json,os,socket
status=dict(line.split(':',1) for line in open('/proc/self/status').read().splitlines())
if os.getuid()==0 or int(status['CapEff'],16) or status['NoNewPrivs'].strip()!='1':
 raise RuntimeError('fixture_collector_still_privileged')
with socket.create_connection(('198.51.100.2',443),timeout=1) as connection:
 connection.sendall(b'fixture-peer\\n')
 connection.settimeout(1)
 print(json.dumps({'response':connection.recv(64).decode()}))
"""
            result = json.loads(
                base["run"](
                    "/usr/bin/nsenter",
                    "-t",
                    str(route["pid"]),
                    "--net",
                    "/usr/bin/setpriv",
                    "--reuid",
                    str(account["uid"]),
                    "--regid",
                    str(account["gid"]),
                    "--clear-groups",
                    "--bounding-set=-all",
                    "--inh-caps=-all",
                    "--ambient-caps=-all",
                    "--no-new-privs",
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    client_source,
                )
            )
            stdout, stderr = peer.communicate(timeout=3)
            if (
                peer.returncode
                or stdout.strip() != "198.51.100.1"
                or result != {"response": "fixture-ok\n"}
            ):
                raise RuntimeError(
                    "installed_joint_peer_source_or_response_changed:" + stderr[-500:]
                )
            if (
                count("inet", "forward") <= before_forward
                or count("netdev", "egress") <= before_wan
            ):
                raise RuntimeError("installed_joint_mark_missing_at_forward_or_wan")
        finally:
            nft(f"""flush set inet {kernel.TABLE} permits
flush set netdev {kernel.TABLE} permits""")
        for family in kernel.KINDS:
            rows = kernel.read_table(family)["nftables"]
            if any(
                row["set"].get("elem")
                for row in rows
                if row.get("set", {}).get("name") == "permits"
            ):
                raise RuntimeError("installed_joint_fixture_permit_not_cleared")
        return {
            "peer_source": "198.51.100.1",
            "forward_mark_seen": True,
            "wan_mark_seen": True,
            "observer_refused_temporary_permit": True,
            "permits_cleared": True,
        }
    finally:
        if peer.poll() is None:
            peer.kill()
            peer.communicate(timeout=3)


def worker(payload):
    base_source = payload["base_source"].encode()
    if sha(base_source) != BASE_HARNESS_PIN:
        raise RuntimeError("base_harness_pin_changed")
    base = load(base_source)
    sources = {name: base64.b64decode(payload["sources"][name], validate=True) for name in SOURCES}
    if set(payload["sources"]) != set(SOURCES) or any(
        sha(raw) != payload["source_sha256"][name] for name, raw in sources.items()
    ):
        raise RuntimeError("source_inventory_changed")
    if sha(sources[SOURCES[0]]) != ENTRY_PIN or sha(sources[SOURCES[1]]) != SOURCES_PIN:
        raise RuntimeError("fixed_source_pin_changed")
    base_report = base["worker"](payload)
    if base_report["status"] != "passed" or base_report["network_admitted"] is not False:
        raise RuntimeError("base_fixture_not_inactive")
    base_manifest_sha256 = sha(Path("/etc/trader/egress-install.json").read_bytes())

    installer = payload["window_installer"].encode()
    bundle = base64.b64decode(payload["window_bundle"], validate=True)
    if sha(installer) != WINDOW_INSTALLER_PIN or sha(bundle) != payload["window_bundle_sha256"]:
        raise RuntimeError("reviewed_joint_bundle_changed")
    package = load(installer)
    contents = package["inspect"](bundle, payload["window_bundle_sha256"])
    if contents["install.py"] != installer or any(
        contents[name] != sources[name] for name in SOURCES
    ):
        raise RuntimeError("joint_bundle_source_mismatch")
    staging = Path("/run/trader-egress-review")
    installer_path = staging / "window-install.py"
    bundle_path = staging / "window-bundle.tar"
    base["write"](installer_path, installer, 0o444)
    base["write"](bundle_path, bundle, 0o444)
    install_command = (
        "/usr/bin/python3",
        "-I",
        str(installer_path),
        "apply",
        "--bundle",
        str(bundle_path),
        "--sha256",
        payload["window_bundle_sha256"],
        "--base-sha256",
        base_manifest_sha256,
    )
    wrong_pin_command = (*install_command[:-3], "0" * 64, *install_command[-2:])
    refused_pin = json.loads(base["run"](*wrong_pin_command, expected=1))
    if (
        refused_pin["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("unselected_joint_bundle_wrote_files")
    wrong_base_command = (*install_command[:-1], "0" * 64)
    refused_base = json.loads(base["run"](*wrong_base_command, expected=1))
    if (
        refused_base["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("unselected_base_manifest_wrote_files")
    wrong_mode_path = staging / "window-install-mode.py"
    base["write"](wrong_mode_path, installer, 0o600)
    wrong_mode_command = (
        "/usr/bin/python3",
        "-I",
        str(wrong_mode_path),
        *install_command[3:],
    )
    refused_mode = json.loads(base["run"](*wrong_mode_command, expected=1))
    if (
        refused_mode["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("unprotected_joint_installer_wrote_files")
    audit_command = (*install_command[:3], "audit", *install_command[4:])
    selected_command = (*install_command[:3], "check-entry", *install_command[4:])
    absent_audit = json.loads(base["run"](*audit_command, expected=1))
    if (
        absent_audit["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.exists()
        or (CODE / SOURCES[0]).exists()
    ):
        raise RuntimeError("absent_joint_audit_wrote_files")
    installed = json.loads(base["run"](*install_command))
    if installed["status"] != "joint_window_installed_inactive" or installed["network_admitted"]:
        raise RuntimeError("joint_window_installation_failed")
    audited = json.loads(base["run"](*audit_command))
    if (
        audited["status"] != "joint_window_installed_sources_observed_inactive"
        or audited["network_admitted"]
    ):
        raise RuntimeError("joint_window_installed_source_audit_failed")
    selected = json.loads(base["run"](*selected_command, expected=2))
    if (
        selected["status"] != "joint_window_selected_entry_executed_unqualified"
        or selected["network_admitted"] is not False
        or selected["host_deployment_qualified"] is not False
        or selected["activation_history_verified"] is not False
    ):
        raise RuntimeError("joint_window_selected_entry_unexpected_admission")
    command = ("/usr/bin/python3", "-I", str(CODE / SOURCES[0]), "--check")

    def checked(expected):
        report = json.loads(base["run"](*command, expected=2))
        if report["status"] != expected or any(
            value is not False for key, value in report.items() if key != "status"
        ):
            raise RuntimeError("joint_window_entry_unexpected_admission")

    checked("fixed_joint_window_sources_observed_unqualified")
    with isolated_collector_path(base) as route:
        activation_probe = installed_activation_probe(base, sources, base_manifest_sha256, route)
    original_manifest = MANIFEST.read_bytes()
    refused = json.loads(base["run"](*install_command, expected=1))
    if (
        refused["status"] != "joint_window_bundle_operation_failed"
        or MANIFEST.read_bytes() != original_manifest
    ):
        raise RuntimeError("joint_window_repeat_install_not_refused")
    document = json.loads(original_manifest)
    if document["base_manifest_sha256"] != base_manifest_sha256:
        raise RuntimeError("joint_window_base_manifest_selection_changed")
    target = CODE / SOURCES[-1]
    target.chmod(0o600)
    target.write_bytes(sources[SOURCES[-1]] + b"\n")
    target.chmod(0o444)
    document["files"][SOURCES[-1]] = sha(target.read_bytes())
    MANIFEST.write_text(json.dumps(document, sort_keys=True))
    checked("fixed_joint_window_sources_observed_unqualified")
    if (
        json.loads(base["run"](*audit_command, expected=1))["status"]
        != "joint_window_bundle_operation_failed"
    ):
        raise RuntimeError("joint_window_audit_accepted_reinventoried_source")
    if (
        json.loads(base["run"](*selected_command, expected=1))["status"]
        != "joint_window_bundle_operation_failed"
    ):
        raise RuntimeError("joint_window_selected_entry_accepted_reinventoried_source")
    target.chmod(0o600)
    target.write_bytes(sources[SOURCES[-1]])
    target.chmod(0o444)
    MANIFEST.write_bytes(original_manifest)
    checked("fixed_joint_window_sources_observed_unqualified")
    document["files"][SOURCES[-1]] = "0" * 64
    with MANIFEST.open("w") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    checked("joint_window_sources_missing_or_changed")
    if (
        json.loads(base["run"](*audit_command, expected=1))["status"]
        != "joint_window_bundle_operation_failed"
    ):
        raise RuntimeError("joint_window_audit_accepted_manifest_drift")
    document["files"][SOURCES[-1]] = sha(sources[SOURCES[-1]])
    with MANIFEST.open("w") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    target.chmod(0o600)
    checked("joint_window_sources_missing_or_changed")
    if (
        json.loads(base["run"](*audit_command, expected=1))["status"]
        != "joint_window_bundle_operation_failed"
    ):
        raise RuntimeError("joint_window_audit_accepted_source_mode_drift")
    return {
        "schema_version": "portfolio.joint_window_installed_isolated_acceptance.v1",
        "status": "passed",
        "base_checks": len(base_report["checks"]),
        "checks": [
            "wrong_bundle_selection_refused_before_mutation",
            "wrong_base_manifest_selection_refused_before_mutation",
            "unprotected_installer_refused_before_mutation",
            "audit_refuses_absent_installation_without_mutation",
            "reviewed_first_install_into_existing_base",
            "independent_installed_source_audit_observed_inactive",
            "selected_entry_executed_from_protected_installer_unqualified",
            "fresh_process_fixed_root_entry_remains_unqualified",
            "repeat_install_refused_without_state_change",
            "self_consistent_source_drift_refused_by_selected_bundle_audit",
            "self_consistent_source_drift_refused_before_selected_entry_execution",
            "manifest_pin_drift_refused",
            "manifest_pin_drift_refused_by_audit",
            "source_mode_drift_refused",
            "source_mode_drift_refused_by_audit",
            "installed_sources_selected_for_isolated_kernel_activation",
            "isolated_one_shot_blackout_and_empty_permits",
            "isolated_repeat_activation_refused_unqualified",
            "installed_selected_collector_denied_by_empty_permits",
            "installed_selected_collector_local_permit_snat_and_wan",
        ],
        "base_manifest_sha256": document["base_manifest_sha256"],
        "window_bundle_sha256": payload["window_bundle_sha256"],
        "window_installer_sha256": WINDOW_INSTALLER_PIN,
        "source_sha256": {name: sha(raw) for name, raw in sources.items()},
        "activation_probe": activation_probe,
        "host_installation_performed": False,
        "host_deployment_qualified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the disposable wrapper as an ordinary user")
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        directory = Path(__file__).resolve().parent
        base_source = (directory / "installation_selftest.py").read_bytes()
        installer = (directory / "package.py").read_bytes()
        sources = {name: (directory / name).read_bytes() for name in SOURCES}
        if sha(base_source) != BASE_HARNESS_PIN:
            raise ValueError("base_harness_pin_changed")
        if sha(sources[SOURCES[0]]) != ENTRY_PIN or sha(sources[SOURCES[1]]) != SOURCES_PIN:
            raise ValueError("fixed_source_pin_changed")
        base = load(base_source)
        if sha(installer) != base["INSTALLER_PIN"]:
            raise ValueError("reviewed_installer_changed")
        base_package = load(installer)
        base_package["build"].__globals__["__file__"] = str(directory / "package.py")
        bundle = base_package["build"]()
        base_package["inspect"](bundle, base["PIN"])
        window_installer = (directory / "gateway_window_package.py").read_bytes()
        if sha(window_installer) != WINDOW_INSTALLER_PIN:
            raise ValueError("reviewed_joint_installer_changed")
        window_package = load(window_installer)
        if tuple(window_package["FILES"]) != SOURCES:
            raise ValueError("joint_bundle_fixed_sources_changed")
        window_package["build"].__globals__["__file__"] = str(
            directory / "gateway_window_package.py"
        )
        window_bundle = window_package["build"]()
        window_package["inspect"](window_bundle, sha(window_bundle))
        original = base["namespaces"]()
        before = observation(base)
        payload = {
            "source": Path(__file__).read_text(),
            "base_source": base_source.decode(),
            "installer": installer.decode(),
            "bundle": base64.b64encode(bundle).decode(),
            "window_installer": window_installer.decode(),
            "window_bundle": base64.b64encode(window_bundle).decode(),
            "window_bundle_sha256": sha(window_bundle),
            "sources": {name: base64.b64encode(raw).decode() for name, raw in sources.items()},
            "source_sha256": {name: sha(raw) for name, raw in sources.items()},
            "original": original,
        }
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'joint_window_fixture'}\nexec(compile(p['source'],'<fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
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
            stdout, stderr = process.communicate(json.dumps(payload), timeout=55)
        except BaseException:
            subprocess.run(
                ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                env=ENV,
                capture_output=True,
                timeout=5,
                check=False,
            )
            process.communicate(timeout=5)
            raise
        if base["namespaces"]() != original or observation(base) != before:
            raise RuntimeError("host_observation_changed")
        if process.returncode:
            raise RuntimeError("isolated_joint_window_failed:" + stderr[-3000:])
        report = json.loads(stdout)
        if report["status"] != "passed" or report["source_sha256"] != payload["source_sha256"]:
            raise RuntimeError("invalid_joint_window_report")
        report["host_observations_unchanged"] = True
        report["harness_sha256"] = sha(payload["source"].encode())
        raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "checks": len(report["checks"]),
                "report_sha256": sha(raw),
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

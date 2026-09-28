"""One-shot installed-source nft probe in self-created private namespaces.

The outer process only reads selected root-owned files. No host nft writer,
collector grant, transport, or admission path is exposed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ENTRY = "/run/trader-egress-window-probe-v1/probe.py"
STARTUP = "/run/trader-egress-window-startup-v1/startup-check.py"
STARTUP_PIN = "36c9f10a3c4e11140029e709f8493b6d08cd3b0659faf7bdd6b22fbf1ccecbbc"
CODE = "/usr/local/lib/trader-egress"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
BASE_MANIFEST = "/etc/trader/egress-install.json"
JOINT_MANIFEST = "/etc/trader/joint-window-sources-v1.json"
DURATION_MS = 5000


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load(raw, name):
    path = STARTUP if name == "startup_check" else CODE + "/gateway_window_" + name + ".py"
    scope = {"__name__": "joint_isolated_selected_" + name, "__file__": path}
    exec(compile(raw, path, "exec"), scope)
    return SimpleNamespace(**scope)


def _startup():
    if __file__ != ENTRY:
        raise ValueError("joint_probe_fixed_entry_required")
    raw = Path(STARTUP).read_bytes()
    if _sha(raw) != STARTUP_PIN:
        raise ValueError("joint_probe_startup_pin_changed")
    startup = _load(raw, "startup_check")
    if (
        startup.protected_entry() != raw
        or startup.protected_bytes(ENTRY) != Path(ENTRY).read_bytes()
    ):
        raise ValueError("joint_probe_unprotected_startup")
    return startup


def _manifest(path, selected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or not 0 < before.st_size < 65536
        ):
            raise ValueError("joint_probe_manifest_unprotected")
        raw = os.pread(fd, 65536, 0)
        after = os.fstat(fd)
        fields = (
            "st_dev",
            "st_ino",
            "st_uid",
            "st_gid",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            len(raw) != before.st_size
            or any(getattr(after, key) != getattr(before, key) for key in fields)
            or _sha(raw) != selected
        ):
            raise ValueError("joint_probe_manifest_selection_changed")
        return raw
    finally:
        os.close(fd)


def _run(*command, input=None):
    result = subprocess.run(
        command, input=input, capture_output=True, env=ENV, cwd="/", timeout=4, check=False
    )
    if result.returncode:
        raise ValueError("joint_probe_isolated_setup_failed")
    return result.stdout


def _write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("joint_probe_short_write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _inner(base_pin, joint_pin):
    if os.getpid() != 1:
        raise ValueError("joint_probe_private_pid_required")
    startup = _startup()
    startup.select(base_pin)
    base_manifest = _manifest(BASE_MANIFEST, base_pin)
    joint_manifest = _manifest(JOINT_MANIFEST, joint_pin)
    existing = json.loads(_run("/usr/sbin/nft", "-j", "list", "ruleset"))
    links = json.loads(_run("/usr/sbin/ip", "-j", "link", "show"))
    if any("metainfo" not in row for row in existing["nftables"]) or [
        row["ifname"] for row in links
    ] != ["lo"]:
        raise ValueError("joint_probe_private_network_not_empty")

    _run("/usr/bin/mount", "--make-rprivate", "/")
    _run(
        "/usr/bin/mount",
        "-t",
        "tmpfs",
        "-o",
        "size=1m,mode=0755,nosuid,nodev",
        "tmpfs",
        "/etc/trader",
    )
    _run("/usr/bin/mount", "-t", "tmpfs", "-o", "size=1m,mode=1777,nosuid,nodev", "tmpfs", "/tmp")
    _write(BASE_MANIFEST, base_manifest)
    _write(JOINT_MANIFEST, joint_manifest)
    directory = os.open("/etc/trader", os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    startup.select(base_pin)
    entry = _load(startup.protected_bytes(CODE + "/gateway_window_entry.py"), "entry")
    verifier = entry._load_base()
    held = entry._held_sources(verifier())
    try:
        selected = {name: held.source(name) for name in startup.SOURCES}
    finally:
        held.close()
    kernel = _load(selected["gateway_window_kernel.py"], "kernel")
    custody = _load(selected["gateway_window_custody.py"], "custody")
    witness_module = _load(selected["gateway_window_witness.py"], "witness")
    activation = _load(selected["gateway_window_activation.py"], "activation")
    table = kernel.TABLE
    rules = f"""table inet {table} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept;
  oifname "lo" accept; meta nfproto @blackout counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept;
  meta nfproto @blackout counter drop; }}
}}
table netdev {table} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "lo" priority 0; policy accept;
  ether type @blackout counter drop; }}
}}"""
    _run("/usr/sbin/nft", "-f", "-", input=rules.encode("ascii"))
    pins = {
        family: kernel.digest(kernel._static(kernel.read_table(family)["nftables"]))
        for family in kernel.KINDS
    }
    plan = {
        "schema_version": custody.PROFILE,
        "base_manifest_sha256": base_pin,
        "observer_sha256": startup.SOURCES["gateway_window_kernel.py"],
        **custody._identity(),
        "wan_interface": "lo",
        "collector": None,
        "static_rules_sha256": pins,
    }
    _write(custody.PLAN, (json.dumps(plan, sort_keys=True) + "\n").encode())
    holder = custody.RootSelectedWindowSnapshot(verifier())
    root = Path("/tmp/window-probe")
    root.mkdir(mode=0o700)
    journal = witness_module.WindowWitness(root, holder)
    try:
        result = activation.activate(holder, journal, duration_ms=DURATION_MS)
        archive = witness_module.replay(
            journal.expected, expected_sha256=witness_module.digest(journal.expected)
        )
        if (
            result["status"] != "local_blackout_transaction_observed_unqualified"
            or archive["observations"] != 1
            or archive["activation_prepared"] is not True
            or any(
                result[key] is not False
                for key in (
                    "activation_history_verified",
                    "source_authenticated",
                    "complete_caller_coverage_verified",
                    "network_admitted",
                )
            )
        ):
            raise ValueError("joint_probe_activation_unexpected_admission")
        for family in kernel.KINDS:
            sets = [row["set"] for row in kernel.read_table(family)["nftables"] if "set" in row]
            if next(row for row in sets if row["name"] == "permits").get("elem"):
                raise ValueError("joint_probe_permit_unexpectedly_populated")
        startup.select(base_pin)
        return {
            "status": "joint_protected_isolated_activation_unqualified",
            "startup_sha256": STARTUP_PIN,
            "selection_sha256": result["selection_sha256"],
            "archive_sha256": witness_module.digest(journal.expected),
            "observations": archive["observations"],
            "host_firewall_modified": False,
            "network_admitted": False,
        }
    finally:
        journal.close()
        holder.close()


def _outer(base_pin, joint_pin):
    startup = _startup()
    startup.select(base_pin)
    _manifest(JOINT_MANIFEST, joint_pin)
    original = {name: os.readlink("/proc/self/ns/" + name) for name in ("mnt", "net", "pid")}
    command = (
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
        ENTRY,
        "--inner",
        "--base-sha256",
        base_pin,
        "--joint-sha256",
        joint_pin,
    )
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=ENV,
        cwd="/",
        timeout=15,
        check=False,
    )
    if completed.returncode != 2 or len(completed.stdout) > 4096:
        raise ValueError("joint_probe_private_child_failed")
    report = json.loads(completed.stdout)
    if (
        report.get("status") != "joint_protected_isolated_activation_unqualified"
        or report.get("network_admitted") is not False
        or report.get("host_firewall_modified") is not False
        or {name: os.readlink("/proc/self/ns/" + name) for name in original} != original
    ):
        raise ValueError("joint_probe_private_report_invalid")
    startup.select(base_pin)
    return report


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if (
            len(args) != 5
            or args[0] not in {"--probe", "--inner"}
            or args[1] != "--base-sha256"
            or args[3] != "--joint-sha256"
            or re.fullmatch("[0-9a-f]{64}", args[2]) is None
            or re.fullmatch("[0-9a-f]{64}", args[4]) is None
        ):
            raise ValueError("joint_probe_fixed_selection_required")
        report = _outer(args[2], args[4]) if args[0] == "--probe" else _inner(args[2], args[4])
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        report = {"status": "joint_protected_isolated_probe_refused", "network_admitted": False}
    print(json.dumps(report, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

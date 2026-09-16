"""Read-only local binding preflight. No host mutation, network permit or helper API."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import stat
import time
from pathlib import Path

STORAGE_ROOT = Path("/var/lib/trader/egress")
PROFILE = "portfolio.egress_binding_snapshot.v1"
LIMIT = 32 * 1024 * 1024
NAMESPACES = ("net", "user", "mnt")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_bounded(path, limit=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("regular_file_required")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input_too_large")
    return raw


def process_identity(pid):
    """Observe process metadata only; never inspect argv, environment or credentials."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("invalid_pid")
    root = Path("/proc") / str(pid)

    def start():
        # comm may contain spaces and parentheses; field 22 follows the final ')'.
        fields = read_bounded(root / "stat").decode().rpartition(")")[2].split()
        if fields[0] in {"Z", "X"}:
            raise ValueError("process_not_running")
        return int(fields[19])

    before = start()
    status = dict(
        line.split(":", 1) for line in read_bounded(root / "status").decode().splitlines()
    )
    executable = (root / "exe").stat()
    result = {
        "pid": pid,
        "start_ticks": before,
        "uids": [int(item) for item in status["Uid"].split()],
        "gids": [int(item) for item in status["Gid"].split()],
        "groups": sorted(int(item) for item in status["Groups"].split()),
        "capabilities": {
            key: int(status[key].strip(), 16)
            for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        },
        "no_new_privileges": int(status["NoNewPrivs"].strip()),
        "namespaces": {key: os.readlink(root / "ns" / key) for key in NAMESPACES},
        "cgroup_sha256": hashlib.sha256(read_bounded(root / "cgroup")).hexdigest(),
        "executable": {
            "device": executable.st_dev,
            "inode": executable.st_ino,
            "size": executable.st_size,
            "mtime_ns": executable.st_mtime_ns,
        },
    }
    if start() != before:
        raise ValueError("process_changed_during_read")
    return result


def host_identity():
    return {
        "boot_id": read_bounded(Path("/proc/sys/kernel/random/boot_id")).decode().strip(),
        "namespaces": {key: os.readlink("/proc/self/ns/" + key) for key in NAMESPACES},
    }


def observe_identity(reader, *args):
    try:
        return {"status": "observed", "identity": reader(*args)}
    except (OSError, ValueError, KeyError, IndexError):
        return {"status": "unavailable_or_changed", "identity": None}


def fixed_storage(storage):
    rows = storage.get("components", [])
    expected = [str(path) for path in (*reversed(STORAGE_ROOT.parents), STORAGE_ROOT)]
    if [row["path"] for row in rows] != expected or storage["status"] == "non_directory_or_symlink":
        return False
    # Root authority requires every ancestor to resist unprivileged replacement.
    return (
        all(row["uid"] == 0 and not int(row["mode"], 8) & 0o022 for row in rows)
        and int(rows[-1]["mode"], 8) == 0o700
    )


def structural_network(parsed):
    """Ignore counters/lifetimes only in their known observational positions."""
    result = json.loads(canonical(parsed))
    for address in result.get("addresses", []):
        for item in address.get("addr_info", []):
            item.pop("valid_life_time", None)
            item.pop("preferred_life_time", None)
    for key in ("routes_v4", "routes_v6"):
        for route in result.get(key, []):
            route.pop("expires", None)
    if "nft" in result:
        rows = result["nft"]["nftables"]
        result["nft"]["nftables"] = [row for row in rows if "metainfo" not in row]
        for row in result["nft"]["nftables"]:
            counter = row.get("counter")
            if isinstance(counter, dict):
                counter.pop("packets", None)
                counter.pop("bytes", None)
            for expression in row.get("rule", {}).get("expr", []):
                counter = expression.get("counter")
                if isinstance(counter, dict):
                    counter.pop("packets", None)
                    counter.pop("bytes", None)
    return result


def collect(inspector, *, wan_interface, source_ipv4, collector_pid=None, nft_via_sudo=False):
    started = time.time_ns()
    host_before = observe_identity(host_identity)
    before = (
        observe_identity(process_identity, collector_pid)
        if collector_pid is not None
        else {"status": "not_selected", "identity": None}
    )
    snapshot = inspector.collect(nft_via_sudo=nft_via_sudo, storage_root=STORAGE_ROOT)
    after = (
        observe_identity(process_identity, collector_pid) if collector_pid is not None else before
    )
    host_after = observe_identity(host_identity)
    blockers = []
    parsed = {}
    for name in inspector.COMMANDS:
        row = snapshot["observations"][name]
        if row["status"] != "ok":
            blockers.append("local_read_incomplete:" + name)
        else:
            parsed[name] = json.loads(row["stdout"])
    if host_before["status"] != "observed" or host_before != host_after:
        blockers.append("host_identity_unavailable_or_changed")
    if snapshot["namespace_before"] != snapshot["namespace_after"] or snapshot[
        "namespace_before"
    ] != (host_before["identity"] or {}).get("namespaces", {}).get("net"):
        blockers.append("network_namespace_changed")
    if before["status"] != "observed" or before != after:
        blockers.append("collector_identity_unavailable_or_changed")
    else:
        caller = before["identity"]
        if (
            len(caller["uids"]) != 4
            or len(set(caller["uids"])) != 1
            or caller["uids"][0] == 0
            or any(caller["capabilities"].values())
            or caller["no_new_privileges"] != 1
        ):
            blockers.append("collector_privilege_boundary_missing")
        if caller["namespaces"]["net"] == (host_before["identity"] or {}).get("namespaces", {}).get(
            "net"
        ):
            blockers.append("collector_network_namespace_not_isolated")
    links = [row for row in parsed.get("links", []) if row.get("ifname") == wan_interface]
    if len(links) != 1 or type(links[0].get("ifindex")) is not int:
        blockers.append("selected_interface_missing_or_ambiguous")
    source_rows = [
        item
        for row in parsed.get("addresses", [])
        if row.get("ifname") == wan_interface
        for item in row.get("addr_info", [])
        if item.get("family") == "inet"
        and item.get("local") == source_ipv4
        and item.get("scope") == "global"
    ]
    if len(source_rows) != 1:
        blockers.append("selected_ipv4_not_assigned")
    if not any(
        row.get("dst") == "default" and row.get("dev") == wan_interface
        for row in parsed.get("routes_v4", [])
    ):
        blockers.append("selected_interface_default_route_missing")
    if not fixed_storage(snapshot["storage"]):
        blockers.append("fixed_root_owned_private_storage_missing")
    network = structural_network(parsed)
    binding = {
        "selection": {
            "wan_interface": wan_interface,
            "source_ipv4": source_ipv4,
            "storage_root": str(STORAGE_ROOT),
        },
        "host": host_before["identity"],
        "collector": before["identity"],
        "network": network,
        "storage": snapshot["storage"].get("components", []),
    }
    return {
        "schema_version": PROFILE,
        "status": "review_only_not_admitted",
        "started_ns": started,
        "finished_ns": time.time_ns(),
        "binding": binding,
        "binding_sha256": hashlib.sha256(canonical(binding)).hexdigest(),
        "local_binding_complete": not blockers,
        "local_blockers": blockers,
        "host_before": host_before,
        "host_after": host_after,
        "collector_before": before,
        "collector_after": after,
        "host_snapshot": snapshot,
        "remaining_requirements": [
            "authoritative_cloud_mapping_to_existing_public_ipv4",
            "collector_launch_and_authenticated_helper_channel",
            "complete_paths_tunnels_offload_and_proxy_acceptance",
            "fixed_storage_authority_crash_and_rollback_qualification",
            "privileged_helper_and_explicit_interruption_acceptance",
            "separate_bootstrap_policy_and_transport",
        ],
        "public_source_verified": False,
        "caller_authorized": False,
        "storage_qualified": False,
        "host_deployment_qualified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
    }


def selected_previous(raw, expected_sha256):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("previous_snapshot_hash_mismatch")
    previous = json.loads(raw)
    if (
        not isinstance(previous, dict)
        or previous.get("schema_version") != PROFILE
        or not isinstance(previous.get("binding"), dict)
        or set(previous["binding"]) != {"selection", "host", "collector", "network", "storage"}
        or type(previous.get("local_binding_complete")) is not bool
        or previous.get("binding_sha256")
        != hashlib.sha256(canonical(previous["binding"])).hexdigest()
    ):
        raise ValueError("invalid_previous_binding")
    return previous


def compare(report, raw, expected_sha256):
    previous = selected_previous(raw, expected_sha256)
    fields = set(report["binding"]) | set(previous["binding"])
    changed = sorted(
        key for key in fields if report["binding"].get(key) != previous["binding"].get(key)
    )
    return {
        "previous_snapshot_sha256": expected_sha256,
        "changed_fields": changed,
        "local_binding_matches": not changed
        and report["local_binding_complete"] is True
        and previous.get("local_binding_complete") is True,
        "comparison_is_authorization": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wan-interface", required=True)
    parser.add_argument("--source-ipv4", required=True)
    parser.add_argument("--collector-pid", type=int)
    parser.add_argument("--nft-via-sudo", action="store_true")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--compare-sha256")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ipaddress.IPv4Address(args.source_ipv4)
        if (
            not args.wan_interface
            or len(args.wan_interface.encode()) > 15
            or any(c.isspace() or c in "/\x00" for c in args.wan_interface)
        ):
            raise ValueError("invalid_interface")
        if args.collector_pid is not None and args.collector_pid <= 0:
            raise ValueError("invalid_pid")
        if (args.compare is None) != (args.compare_sha256 is None):
            raise ValueError("comparison_requires_path_and_hash")
        prior = read_bounded(args.compare, LIMIT) if args.compare else None
        # Validate the selected original before any local commands or output creation.
        if prior is not None:
            selected_previous(prior, args.compare_sha256)
        spec = importlib.util.spec_from_file_location(
            "egress_host_inspector", Path(__file__).with_name("inspect_host.py")
        )
        inspector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inspector)
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            report = collect(
                inspector,
                wan_interface=args.wan_interface,
                source_ipv4=args.source_ipv4,
                collector_pid=args.collector_pid,
                nft_via_sudo=args.nft_via_sudo,
            )
            report["comparison"] = (
                compare(report, prior, args.compare_sha256) if prior is not None else None
            )
            raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
            if len(raw) > LIMIT:
                raise ValueError("report_too_large")
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "binding_inspection_failed", "network_admitted": False}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "local_binding_complete": report["local_binding_complete"],
                "local_blockers": report["local_blockers"],
                "comparison": report["comparison"],
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # No admission-success exit code, even for an unchanged complete local binding.


if __name__ == "__main__":
    raise SystemExit(main())

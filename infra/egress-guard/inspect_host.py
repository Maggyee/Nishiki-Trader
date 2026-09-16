"""Retain a private, read-only host snapshot; never grant deployment or API access.

Run with system Python 3.10+. Only fixed local read commands are allowed. This
snapshot cannot identify a public source after cloud NAT or prove traffic history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path

IP = "/usr/sbin/ip"
NFT = "/usr/sbin/nft"
SUDO = "/usr/bin/sudo"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
LIMIT = 4 * 1024 * 1024
COMMANDS = {
    "links": (IP, "-j", "link", "show"),
    "addresses": (IP, "-j", "address", "show"),
    "routes_v4": (IP, "-4", "-j", "route", "show", "table", "all"),
    "routes_v6": (IP, "-6", "-j", "route", "show", "table", "all"),
    "rules_v4": (IP, "-4", "-j", "rule", "show"),
    "rules_v6": (IP, "-6", "-j", "rule", "show"),
    "nft": (NFT, "-j", "list", "ruleset"),
}


def capture(argv):
    """Keep original local output and failure state, with bounded retained bytes."""
    allowed = {*COMMANDS.values(), (SUDO, "-n", *COMMANDS["nft"])}
    if argv not in allowed:
        raise ValueError("command not in the read-only allowlist")
    result = {"argv": list(argv), "started_ns": time.time_ns(), "returncode": None}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=ENV,
                timeout=5,
                check=False,
            )
            result["returncode"] = process.returncode
            result["status"] = "ok" if process.returncode == 0 else "command_failed"
        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
        except OSError:
            result["status"] = "unavailable"
        for name, stream in (("stdout", out), ("stderr", err)):
            stream.seek(0)
            raw = stream.read(LIMIT + 1)
            if len(raw) > LIMIT:
                result["status"] = "output_limit"
                result[name] = None
                result[f"{name}_sha256"] = None
                continue
            # ip/nft emit UTF-8 JSON; reject invalid encoding rather than changing bytes.
            try:
                result[name] = raw.decode("utf-8")
                result[f"{name}_sha256"] = hashlib.sha256(raw).hexdigest()
            except UnicodeDecodeError:
                result["status"] = "invalid_encoding"
                result[name] = None
                result[f"{name}_sha256"] = None
    result["finished_ns"] = time.time_ns()
    return result


def storage_snapshot(path):
    """Inspect metadata only; do not create, open or claim an execution scope."""
    if path is None:
        return {"status": "not_selected", "qualified": False}
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("storage root must be an absolute path without parent traversal")
    rows = []
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except OSError:
            return {"status": "missing_or_unreadable", "components": rows, "qualified": False}
        rows.append(
            {
                "path": str(part),
                "uid": info.st_uid,
                "gid": info.st_gid,
                "mode": oct(stat.S_IMODE(info.st_mode)),
                "device": info.st_dev,
                "inode": info.st_ino,
            }
        )
        if not stat.S_ISDIR(info.st_mode):
            return {"status": "non_directory_or_symlink", "components": rows, "qualified": False}
    private = info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
    return {
        "status": "private_directory_observed" if private else "owner_or_mode_mismatch",
        "components": rows,
        "qualified": False,
    }


def collect(*, nft_via_sudo=False, storage_root=None):
    started = time.time_ns()
    namespace_before = os.readlink("/proc/self/ns/net")
    commands = dict(COMMANDS)
    if nft_via_sudo:
        commands["nft"] = (SUDO, "-n", *commands["nft"])
    observations = {name: capture(argv) for name, argv in commands.items()}
    parsed = {}
    for name, row in observations.items():
        if row["status"] != "ok":
            continue
        try:
            value = json.loads(row["stdout"])
            if name == "nft":
                valid = isinstance(value, dict) and isinstance(value.get("nftables"), list)
                items = value.get("nftables", []) if valid else []
            else:
                valid = isinstance(value, list)
                items = value if valid else []
            if not valid or not all(isinstance(item, dict) for item in items):
                raise ValueError("unexpected local JSON shape")
            parsed[name] = value
        except (ValueError, TypeError):
            row["status"] = "invalid_json"
    storage = storage_snapshot(storage_root)
    namespace_after = os.readlink("/proc/self/ns/net")
    blockers = [
        "cloud_public_to_private_mapping_missing",
        "dedicated_source_and_authorized_caller_binding_missing",
        "deployed_guard_and_continuous_ledger_unqualified",
        "fixed_storage_root_and_crash_behavior_unqualified",
        "bootstrap_contract_not_activated",
    ]
    blockers += [f"local_read_incomplete:{name}" for name in commands if name not in parsed]
    if namespace_after != namespace_before:
        blockers.append("network_namespace_changed_during_snapshot")
    if storage["status"] != "private_directory_observed":
        blockers.append(f"storage:{storage['status']}")
    nft = parsed.get("nft", {}).get("nftables", [])
    summary = {
        "interface_count": len(parsed["links"]) if "links" in parsed else None,
        "default_route_counts": {
            family: sum(row.get("dst") == "default" for row in parsed[key])
            if key in parsed
            else None
            for family, key in (("ipv4", "routes_v4"), ("ipv6", "routes_v6"))
        },
        "nft_base_chain_count": sum(
            isinstance(row.get("chain"), dict) and "hook" in row["chain"] for row in nft
        )
        if "nft" in parsed
        else None,
        "nft_flowtable_count": sum("flowtable" in row for row in nft) if "nft" in parsed else None,
        "storage_status": storage["status"],
    }
    return {
        "schema_version": "portfolio.egress_host_snapshot.v1",
        "status": "deployment_inputs_incomplete",
        "started_ns": started,
        "finished_ns": time.time_ns(),
        "uid": os.getuid(),
        "namespace_before": namespace_before,
        "namespace_after": namespace_after,
        "observations": observations,
        "storage": storage,
        "summary": summary,
        "blockers": blockers,
        "public_source_verified": False,
        "continuous_coverage_verified": False,
        "storage_qualified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument(
        "--nft-via-sudo",
        action="store_true",
        help="use only sudo -n /usr/sbin/nft -j list ruleset; never prompt or change rules",
    )
    args = parser.parse_args(argv)
    if args.storage_root is not None and (
        not args.storage_root.is_absolute() or ".." in args.storage_root.parts
    ):
        parser.error("storage root must be an absolute path without parent traversal")
    try:
        # Claim the output before collection so an existing file/symlink is never replaced.
        # On failure leave the partial file for inspection; a new report needs a new name.
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            report = collect(nft_via_sudo=args.nft_via_sudo, storage_root=args.storage_root)
            raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    except (OSError, ValueError):
        print(json.dumps({"status": "snapshot_failed", "network_admitted": False}))
        return 1
    # Host addresses, full rules and command stderr stay in the private local report.
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "blockers": report["blockers"],
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "network_admitted": False,
                "venue_requests_made": 0,
            },
            sort_keys=True,
        )
    )
    return 2  # Snapshot written; this tool has no admission-success exit code.


if __name__ == "__main__":
    raise SystemExit(main())

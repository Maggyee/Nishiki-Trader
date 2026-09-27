"""One-shot read-only census of current host, Docker and network namespaces.

The census cannot prove future callers, public source identity or continuous
exclusion. It does not activate nft rules, contact a venue or admit collection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

SUDO = "/usr/bin/sudo"
LSNS = "/usr/bin/lsns"
NSENTER = "/usr/bin/nsenter"
IP = "/usr/sbin/ip"
DOCKER = "/usr/bin/docker"
READLINK = "/usr/bin/readlink"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
LSNS_CMD = (SUDO, "-n", LSNS, "-J", "-t", "net", "-o", "NS,PID")
DOCKER_CMD = (SUDO, "-n", DOCKER, "ps", "--format", "{{json .ID}}", "--no-trunc")
LIMIT = 1024 * 1024
MAX_ROWS = 256
NS_PATTERN = re.compile(r"net:\[(\d+)\]\n?")
ID_PATTERN = re.compile(r"[0-9a-f]{64}")


def allowed(argv):
    if argv in (LSNS_CMD, DOCKER_CMD):
        return True
    if argv[:4] == (SUDO, "-n", DOCKER, "inspect"):
        return (
            argv[4:6] == ("--format", "{{json .State.Pid}}")
            and 0 < len(argv[6:]) <= MAX_ROWS
            and all(ID_PATTERN.fullmatch(value) for value in argv[6:])
        )
    if argv[:3] == (SUDO, "-n", READLINK) and len(argv) == 4:
        return re.fullmatch(r"/proc/[1-9][0-9]*/ns/net", argv[3]) is not None
    if argv[:4] == (SUDO, "-n", NSENTER, "--target") and len(argv) == 14:
        return (
            argv[4].isascii()
            and argv[4].isdecimal()
            and int(argv[4]) > 0
            and argv[5:8] == ("--net", "--", IP)
            and argv[8:]
            in (
                ("-4", "-j", "route", "show", "table", "all"),
                ("-6", "-j", "route", "show", "table", "all"),
            )
        )
    return False


def command(argv):
    argv = tuple(argv)
    if not allowed(argv):
        raise ValueError("namespace_inventory_command_not_read_only")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=ENV,
                timeout=5,
                check=False,
            )
            status = "ok" if result.returncode == 0 else "command_failed"
        except subprocess.TimeoutExpired:
            status = "timeout"
        except OSError:
            status = "unavailable"
        out.seek(0)
        raw = out.read(LIMIT + 1)
        if len(raw) > LIMIT:
            return {"status": "output_limit", "sha256": None, "raw": None}
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {"status": "invalid_encoding", "sha256": None, "raw": None}
        return {"status": status, "sha256": hashlib.sha256(raw).hexdigest(), "raw": decoded}


def read(argv, label, observations, blockers, parse):
    row = command(argv)
    observations.append({"name": label, "status": row["status"], "sha256": row["sha256"]})
    if row["status"] != "ok":
        blockers.append(f"read_failed:{label}:{row['status']}")
        return None
    try:
        return parse(row["raw"])
    except (ValueError, TypeError, KeyError):
        blockers.append(f"invalid_output:{label}")
        return None


def namespaces(raw):
    document = json.loads(raw)
    rows = document["namespaces"]
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS:
        raise ValueError("namespace_count")
    result = {}
    for row in rows:
        ns, pid = row["ns"], row["pid"]
        if type(ns) is not int or type(pid) is not int or ns <= 0 or pid <= 0 or ns in result:
            raise ValueError("namespace_identity")
        result[ns] = pid
    return result


def ids(raw):
    values = [json.loads(line) for line in raw.splitlines()]
    if (
        len(values) > MAX_ROWS
        or any(
            not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None for value in values
        )
        or len(set(values)) != len(values)
    ):
        raise ValueError("docker_id_list")
    return values


def pids(raw):
    values = [json.loads(line) for line in raw.splitlines()]
    if (
        not values
        or len(values) > MAX_ROWS
        or any(type(value) is not int or value <= 0 for value in values)
    ):
        raise ValueError("docker_pid_list")
    return values


def ns_link(raw):
    match = NS_PATTERN.fullmatch(raw)
    if match is None:
        raise ValueError("namespace_link")
    return int(match[1])


def routes(raw):
    document = json.loads(raw)
    if (
        not isinstance(document, list)
        or len(document) > MAX_ROWS
        or any(not isinstance(row, dict) for row in document)
    ):
        raise ValueError("route_list")
    return [
        {key: row[key] for key in ("dev", "gateway", "table") if key in row}
        for row in document
        if row.get("dst") == "default"
    ]


def inventory():
    started_ns = time.time_ns()
    current_ns = ns_link(os.readlink("/proc/self/ns/net"))
    observations, blockers, rows = [], [], []

    def observe(argv, label, parse):
        return read(argv, label, observations, blockers, parse)

    before = observe(LSNS_CMD, "lsns_before", namespaces)
    docker_before = observe(DOCKER_CMD, "docker_before", ids)
    if before is not None:
        if current_ns not in before:
            blockers.append("host_namespace_not_listed")
        for ns, pid in sorted(before.items()):
            link_cmd = (SUDO, "-n", READLINK, f"/proc/{pid}/ns/net")
            prior = observe(link_cmd, f"namespace_{ns}_before", ns_link)
            defaults = {}
            for family in (4, 6):
                cmd = (
                    SUDO,
                    "-n",
                    NSENTER,
                    "--target",
                    str(pid),
                    "--net",
                    "--",
                    IP,
                    f"-{family}",
                    "-j",
                    "route",
                    "show",
                    "table",
                    "all",
                )
                defaults[f"ipv{family}"] = observe(cmd, f"namespace_{ns}_ipv{family}", routes)
            after_link = observe(link_cmd, f"namespace_{ns}_after", ns_link)
            if prior != ns or after_link != ns:
                blockers.append(f"namespace_representative_changed:{ns}")
            rows.append({"ns": ns, "pid": pid, "host": ns == current_ns, "defaults": defaults})
    docker_rows = []
    if docker_before:
        cmd = (SUDO, "-n", DOCKER, "inspect", "--format", "{{json .State.Pid}}", *docker_before)
        docker_pids = observe(cmd, "docker_pids", pids)
        if docker_pids is not None:
            if len(docker_pids) != len(docker_before):
                blockers.append("docker_inspect_count_changed")
            else:
                for container, pid in zip(docker_before, docker_pids, strict=True):
                    ns = observe(
                        (SUDO, "-n", READLINK, f"/proc/{pid}/ns/net"),
                        f"docker_namespace_{container}",
                        ns_link,
                    )
                    if before is None or ns not in before:
                        blockers.append("docker_namespace_not_in_census")
                    docker_rows.append({"id": container, "pid": pid, "ns": ns})
    after = observe(LSNS_CMD, "lsns_after", namespaces)
    docker_after = observe(DOCKER_CMD, "docker_after", ids)
    if before is None or after is None or before != after:
        blockers.append("namespace_census_changed_or_missing")
    if docker_before is None or docker_after is None or docker_before != docker_after:
        blockers.append("docker_census_changed_or_missing")
    if ns_link(os.readlink("/proc/self/ns/net")) != current_ns:
        blockers.append("caller_namespace_changed")
    docker_complete = (
        docker_before is not None
        and docker_after is not None
        and docker_before == docker_after
        and len(docker_rows) == len(docker_before)
        and all(
            row["ns"] is not None and before is not None and row["ns"] in before
            for row in docker_rows
        )
    )

    def count_defaults(family):
        if before is None or any(row["defaults"][family] is None for row in rows):
            return None
        return sum(bool(row["defaults"][family]) for row in rows)

    blockers.extend(
        (
            "point_in_time_not_continuous_coverage",
            "provider_visible_source_unverified",
            "joint_host_exclusion_not_installed",
        )
    )
    return {
        "schema_version": "portfolio.host_namespace_inventory.v1",
        "status": "read_only_snapshot_unqualified",
        "started_ns": started_ns,
        "finished_ns": time.time_ns(),
        "host_ns": current_ns,
        "namespaces": rows,
        "docker": docker_rows,
        "observations": observations,
        "blockers": blockers,
        "summary": {
            "namespace_count": len(rows) if before is not None else None,
            "docker_count": len(docker_rows) if docker_complete else None,
            "ipv4_default_namespaces": count_defaults("ipv4"),
            "ipv6_default_namespaces": count_defaults("ipv6"),
            "read_failures_or_churn": len(blockers) - 3,
        },
        "complete_caller_coverage_verified": False,
        "network_admitted": False,
        "venue_requests_made": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the read-only wrapper as an ordinary user")
    try:
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            report = inventory()
            raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"status": "inventory_failed", "network_admitted": False}))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "network_admitted": False,
            },
            sort_keys=True,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

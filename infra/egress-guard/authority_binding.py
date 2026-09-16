"""Read-only local authority binding for the consumed bootstrap; no dispatch API.

Hold root-owned original/code descriptors and recheck identity, bytes, boot and
network structure. This binds local custody only, never provider-wide coverage.
Stage reviewed bytes under root ownership before invoking with isolated Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

CODE = Path("/usr/local/lib/trader-egress")
BOOTSTRAP_CODE = "/usr/local/lib/trader-egress-bootstrap-v1"
SCOPE = "/var/lib/trader/egress/rest-bootstrap-v1"
PLAN = "/etc/trader/egress-bootstrap-v1.json"
ENTRY_HASH = "2a91437ed9080ae481eae7496e43cfe35d29888e1e3a5a12b10605b6dc320c9b"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
COMMANDS = {
    "links": ("/usr/sbin/ip", "-j", "link", "show"),
    "addresses": ("/usr/sbin/ip", "-j", "address", "show"),
    "routes_v4": ("/usr/sbin/ip", "-4", "-j", "route", "show", "table", "all"),
    "routes_v6": ("/usr/sbin/ip", "-6", "-j", "route", "show", "table", "all"),
    "rules_v4": ("/usr/sbin/ip", "-4", "-j", "rule", "show"),
    "rules_v6": ("/usr/sbin/ip", "-6", "-j", "rule", "show"),
    "nft": ("/usr/sbin/nft", "-j", "list", "ruleset"),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(raw):
    scope = {"__name__": "verified_authority_dependency"}
    exec(compile(raw, "<verified-authority-source>", "exec"), scope)
    return scope


def installation():
    # Bootstrap only the independently pinned installed entry; the entry then
    # establishes root filesystem custody of its validator before loading it.
    for parent in (*reversed(CODE.parents), CODE):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("untrusted_installed_ancestor")
    fd = os.open(CODE / "helper_entry.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o444
            or info.st_size > 1024 * 1024
        ):
            raise ValueError("untrusted_installed_entry")
        raw = os.pread(fd, 1024 * 1024 + 1, 0)
        if digest(raw) != ENTRY_HASH:
            raise ValueError("entry_pin_changed")
    finally:
        os.close(fd)
    return load(raw)["load_verifier"]()()


def read_command(argv):
    result = subprocess.run(argv, capture_output=True, env=ENV, cwd="/", timeout=3, check=True)
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError("network_observation_limit")
    return json.loads(result.stdout)


def network(plan):
    rows = {name: read_command(command) for name, command in COMMANDS.items()}
    rows["selected_route"] = read_command(
        ("/usr/sbin/ip", "-4", "-j", "route", "get", plan["destination_ipv4"])
    )
    return rows


class AuthorityBinding:
    """An owned in-process check, invalidated permanently on any observed drift.

    Reports are observations, not serialized capabilities. No caller-supplied
    report, public key or signature can create this object's held descriptors.
    """

    def __init__(self, authority, *, plan_sha256, events_sha256, response_sha256):
        self.authority = authority
        self.closed = False
        self.files = []
        try:
            plan_raw = self.open_file(PLAN, 0o600, 65536, plan_sha256)
            self.plan = plan = json.loads(plan_raw)
            if (
                plan["schema_version"] != "portfolio.egress_bootstrap_execution.v1"
                or plan["scope"] != "portfolio.testnet_rest_bootstrap.v1"
                or plan["collector"] != authority.account
                or plan["installation_manifest_sha256"] != authority.manifest_sha256
                or plan["wan_interface"] != "enp0s6"
                or plan["private_ipv4"] != "10.0.0.136"
                or plan["public_ipv4"] != "149.118.158.46"
            ):
                raise ValueError("authority_plan_binding")
            # Literal endpoint is parsed before it is passed to a fixed read command.
            import ipaddress

            if str(ipaddress.IPv4Address(plan["destination_ipv4"])) != plan["destination_ipv4"]:
                raise ValueError("authority_destination")
            self.open_file(SCOPE + "/plan.json", 0o600, 65536, plan_sha256)
            self.open_file(SCOPE + "/events.jsonl", 0o600, 16 * 1024 * 1024, events_sha256)
            self.open_file(SCOPE + "/response.bin", 0o600, 16 * 1024 * 1024, response_sha256)
            for name, pin in [
                ("bootstrap_once.py", "helper_sha256"),
                ("http_parser.py", "parser_sha256"),
            ]:
                self.open_file(BOOTSTRAP_CODE + "/" + name, 0o444, 1024 * 1024, plan[pin])
            self.open_file(
                "/etc/ssl/certs/ca-certificates.crt", 0o644, 1024 * 1024, plan["ca_sha256"]
            )
            scope_fd = authority.open_directory(SCOPE)
            if stat.S_IMODE(os.fstat(scope_fd).st_mode) != 0o700:
                raise ValueError("authority_scope_mode")
            inspector = load(authority.source("inspect_binding.py"))
            self.host_reader = inspector["host_identity"]
            self.normalize = inspector["structural_network"]
            host = self.host_reader()
            if host["boot_id"] != plan["host_boot_id"]:
                raise ValueError("authority_host_restarted")
            observed_network = self.normalize(network(plan))
            self.validate_route(observed_network)
            self.binding = {
                "kind": "local_root_custody_of_consumed_bootstrap",
                "host": host,
                "collector": authority.account,
                "installation_manifest_sha256": authority.manifest_sha256,
                "installed_sources": {k: digest(v) for k, v in authority.sources.items()},
                "plan_sha256": plan_sha256,
                "source_commit": plan["source_commit"],
                "files": [
                    {"path": row["path"], "sha256": row["sha256"], "identity": row["identity"]}
                    for row in self.files
                ],
                "storage_identity": {
                    "device": os.fstat(scope_fd).st_dev,
                    "inode": os.fstat(scope_fd).st_ino,
                    "uid": os.fstat(scope_fd).st_uid,
                    "mode": stat.S_IMODE(os.fstat(scope_fd).st_mode),
                },
                "network_sha256": digest(canonical(observed_network)),
                "operator_mapping_sha256": plan["operator_mapping_sha256"],
                "public_mapping_basis": "operator_console_not_independent_provider_authority",
            }
            self.verify()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def identity(info):
        return {
            key: getattr(info, key)
            for key in (
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
        }

    def open_file(self, path, mode, limit, expected):
        parent = self.authority.open_directory(str(Path(path).parent))
        fd = os.open(
            Path(path).name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        self.authority.fds.append(fd)
        info = os.fstat(fd)
        # Authority.check_directory enforces the platform's selected root owner;
        # files must belong to that same authority, including in filesystem tests.
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.fstat(self.authority.root).st_uid
            or stat.S_IMODE(info.st_mode) != mode
            or info.st_nlink != 1
            or info.st_size > limit
        ):
            raise ValueError("authority_artifact_metadata")
        raw = os.pread(fd, limit + 1, 0)
        if (
            len(raw) != info.st_size
            or digest(raw) != expected
            or self.identity(os.fstat(fd)) != self.identity(info)
        ):
            raise ValueError("authority_artifact_bytes")
        self.files.append(
            {
                "path": path,
                "parent": parent,
                "name": Path(path).name,
                "fd": fd,
                "limit": limit,
                "sha256": expected,
                "identity": self.identity(info),
            }
        )
        return raw

    def validate_route(self, observed):
        plan = self.plan
        route = observed["selected_route"]
        links = [r for r in observed["links"] if r.get("ifname") == plan["wan_interface"]]
        if (
            len(route) != 1
            or route[0].get("dev") != plan["wan_interface"]
            or route[0].get("prefsrc") != plan["private_ipv4"]
            or len(links) != 1
            or links[0].get("address") != plan["vnic_mac"]
        ):
            raise ValueError("authority_source_route_or_vnic")

    def verify_files(self):
        for row in self.files:
            if (
                self.identity(os.fstat(row["fd"])) != row["identity"]
                or self.identity(os.stat(row["name"], dir_fd=row["parent"], follow_symlinks=False))
                != row["identity"]
            ):
                raise ValueError("authority_artifact_replaced")
            raw = os.pread(row["fd"], row["limit"] + 1, 0)
            if (
                digest(raw) != row["sha256"]
                or self.identity(os.fstat(row["fd"])) != row["identity"]
            ):
                raise ValueError("authority_artifact_changed")

    def verify(self):
        if self.closed:
            raise ValueError("authority_binding_closed")
        try:
            self.authority.verify()
            self.verify_files()
            observed = self.normalize(network(self.plan))
            self.validate_route(observed)
            if (
                self.host_reader() != self.binding["host"]
                or digest(canonical(observed)) != self.binding["network_sha256"]
            ):
                raise ValueError("authority_host_or_network_drift")
            self.authority.verify()
            self.verify_files()
            return {
                "schema_version": "portfolio.local_authority_binding.v1",
                "status": "local_custody_verified_no_dispatch",
                "binding": self.binding,
                "binding_sha256": digest(canonical(self.binding)),
                "local_root_custody_verified": True,
                "historical_source_reauthenticated": False,
                "source_signer_authority_qualified": False,
                "gateway_signer_authority_qualified": False,
                "complete_gateway_coverage_verified": False,
                "future_enforcement_verified": False,
                "network_admitted": False,
                "trading_admitted": False,
                "venue_requests_made": 0,
                "bootstrap_scope_consumed": True,
                "joint_scope_consumed": False,
            }
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.authority.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "events", "response"):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--expect-binding")
    args = parser.parse_args(argv)
    binding = None
    try:
        if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
            raise ValueError("isolated_root_required")
        started = time.time_ns()
        binding = AuthorityBinding(
            installation(),
            plan_sha256=args.plan_sha256,
            events_sha256=args.events_sha256,
            response_sha256=args.response_sha256,
        )
        report = binding.verify()
        if args.expect_binding and report["binding_sha256"] != args.expect_binding:
            raise ValueError("selected_authority_binding_changed")
        report.update(started_ns=started, finished_ns=time.time_ns())
        print(json.dumps(report, sort_keys=True))
        return 2
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "status": "local_authority_binding_blocked",
                    "error_type": type(exc).__name__,
                    "network_admitted": False,
                    "venue_requests_made": 0,
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        if binding is not None:
            binding.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only root-held selection for a joint nft snapshot; no activation API.

The installed base verifier must supply a held TrustedInstallation instance.
This module is not in the installed inventory and cannot certify its own code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

PLAN = "/etc/trader/joint-window-v1.json"
OBSERVER = "/usr/local/lib/trader-egress/gateway_window_kernel.py"
PROFILE = "portfolio.joint_window_kernel_selection.v1"
PLAN_FIELDS = {
    "schema_version",
    "base_manifest_sha256",
    "observer_sha256",
    "boot_id",
    "host_net_namespace",
    "host_user_namespace",
    "wan_interface",
    "collector",
    "static_rules_sha256",
}
MAX_PLAN = 65536
MAX_CODE = 1024 * 1024


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("joint_window_policy_duplicate_key")
        value[key] = item
    return value


def _read(authority, path, mode, limit):
    authority.verify()
    fd = authority.open_file(path, mode)
    before = os.fstat(fd)
    if before.st_size > limit:
        raise ValueError("joint_window_selected_file_oversized")
    raw = os.pread(fd, limit + 1, 0)
    if len(raw) != before.st_size or os.fstat(fd) != before:
        raise ValueError("joint_window_selected_file_changed")
    authority.verify()
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity():
    with open("/proc/sys/kernel/random/boot_id", "rb") as stream:
        boot_id = stream.read(128).decode("ascii").strip()
    return {
        "boot_id": boot_id,
        "host_net_namespace": os.readlink("/proc/self/ns/net"),
        "host_user_namespace": os.readlink("/proc/self/ns/user"),
    }


class RootSelectedWindowSnapshot:
    """Hold fixed plan/code descriptors; every observation rechecks their bytes."""

    def __init__(self, authority):
        self.authority = authority
        self.owner = os.getpid()
        self.closed = False
        try:
            if os.getuid() != 0 or os.geteuid() != 0 or not sys.flags.isolated:
                raise ValueError("joint_window_isolated_root_required")
            self.plan_raw = _read(authority, PLAN, 0o600, MAX_PLAN)
            plan = json.loads(self.plan_raw, object_pairs_hook=_pairs)
            if (
                not isinstance(plan, dict)
                or set(plan) != PLAN_FIELDS
                or plan["schema_version"] != PROFILE
                or plan["base_manifest_sha256"] != authority.manifest_sha256
                or not isinstance(plan["wan_interface"], str)
                or re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", plan["wan_interface"]) is None
                or not isinstance(plan["static_rules_sha256"], dict)
                or set(plan["static_rules_sha256"]) != {"inet", "netdev"}
                or any(
                    not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None
                    for value in (
                        plan["observer_sha256"],
                        *plan["static_rules_sha256"].values(),
                    )
                )
                or any(plan[key] != value for key, value in _identity().items())
            ):
                raise ValueError("joint_window_protected_selection_invalid")
            self.plan = plan
            self.source = _read(authority, OBSERVER, 0o444, MAX_CODE)
            if _sha(self.source) != plan["observer_sha256"]:
                raise ValueError("joint_window_observer_source_changed")
            scope = {"__name__": "root_selected_joint_window_observer"}
            exec(compile(self.source, OBSERVER, "exec"), scope)
            self.observe_kernel = scope["observe"]
            scope["_selected_collector"](plan["collector"], plan["wan_interface"])
        except BaseException:
            self.close()
            raise

    def observe(self):
        if self.closed or os.getpid() != self.owner:
            raise ValueError("joint_window_selection_closed_or_foreign_owner")
        try:
            if (
                _read(self.authority, PLAN, 0o600, MAX_PLAN) != self.plan_raw
                or _read(self.authority, OBSERVER, 0o444, MAX_CODE) != self.source
                or any(self.plan[key] != value for key, value in _identity().items())
            ):
                raise ValueError("joint_window_protected_selection_drift")
            snapshot = self.observe_kernel(
                expected_static_sha256=self.plan["static_rules_sha256"],
                wan_interface=self.plan["wan_interface"],
                collector=self.plan["collector"],
            )
            if (
                not isinstance(snapshot, dict)
                or snapshot.get("status") != "local_kernel_timers_observed_unqualified"
                or snapshot.get("static_rules_sha256") != self.plan["static_rules_sha256"]
                or any(
                    snapshot.get(field) is not False
                    for field in (
                        "source_authenticated",
                        "complete_caller_coverage_verified",
                        "network_admitted",
                    )
                )
            ):
                raise ValueError("joint_window_kernel_snapshot_invalid")
            if (
                _read(self.authority, PLAN, 0o600, MAX_PLAN) != self.plan_raw
                or _read(self.authority, OBSERVER, 0o444, MAX_CODE) != self.source
                or any(self.plan[key] != value for key, value in _identity().items())
            ):
                raise ValueError("joint_window_protected_selection_drift")
            return {
                "schema_version": "portfolio.root_selected_joint_window_snapshot.v1",
                "status": "root_selected_kernel_snapshot_unqualified",
                "selection_sha256": _sha(self.plan_raw),
                "kernel_snapshot": snapshot,
                "activation_history_verified": False,
                "source_authenticated": False,
                "complete_caller_coverage_verified": False,
                "network_admitted": False,
            }
        except BaseException:
            self.close()
            raise

    def close(self):
        if os.getpid() != self.owner:
            raise ValueError("joint_window_foreign_owner")
        if not self.closed:
            self.closed = True
            self.authority.close()

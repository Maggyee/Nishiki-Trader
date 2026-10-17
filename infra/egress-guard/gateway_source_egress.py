"""Offline consistency adapter for selected gateway source and egress evidence.

The installed gateway has no host-wide source/caller controller. This adapter
cannot turn injected observations, even ones supplied by a held installation,
into a dispatch permit or an authenticated provider-visible source.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus.portfolio_joint_admission import ENDPOINTS

SECOND = 1_000_000_000
LOOKBACK = 300 * SECOND
HORIZON = 125 * SECOND
ROLES = frozenset(ENDPOINTS)
SOURCE_FILE = "gateway_joint_ipc.py"
HEX = re.compile(r"[0-9a-f]{64}\Z")
IP = "/usr/sbin/ip"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
ROUTE_LIMIT = 65536
MARK = 0x6F720002


def _pin(value):
    if not isinstance(value, str) or HEX.fullmatch(value) is None:
        raise ValueError("source_egress_selected_pin_required")
    return value


def _binding(row, role, uid):
    if not isinstance(row, dict) or set(row) != {
        "endpoint",
        "destination_ip",
        "address_family",
        "local_source_ip",
        "public_source_ip",
        "collector_uid",
        "network_namespace",
    }:
        raise ValueError("source_egress_binding_fields")
    try:
        dest = ipaddress.ip_address(row["destination_ip"])
        local = ipaddress.ip_address(row["local_source_ip"])
        public = ipaddress.ip_address(row["public_source_ip"])
    except (ValueError, TypeError) as exc:
        raise ValueError("source_egress_address_invalid") from exc
    if (
        row["endpoint"] != ENDPOINTS[role]
        or type(row["address_family"]) is not int
        or row["address_family"] != dest.version
        or any(address.version != dest.version for address in (local, public))
        or any(
            str(address) != row[key]
            for key, address in (
                ("destination_ip", dest),
                ("local_source_ip", local),
                ("public_source_ip", public),
            )
        )
        or type(row["collector_uid"]) is not int
        or row["collector_uid"] != uid
        or not isinstance(row["network_namespace"], str)
        or re.fullmatch(r"net:\[[0-9]+\]", row["network_namespace"]) is None
    ):
        raise ValueError("source_egress_binding_changed")


def _unique_pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError("source_egress_duplicate_kernel_field")
        result[name] = value
    return result


def _read_ip(argv):
    result = subprocess.run(
        argv, stdin=subprocess.DEVNULL, capture_output=True,
        cwd="/", env=ENV, timeout=3, check=False,
    )
    if result.returncode or not 0 < len(result.stdout) <= ROUTE_LIMIT:
        raise ValueError("source_egress_local_route_unavailable")
    return json.loads(result.stdout, object_pairs_hook=_unique_pairs)


def observe_local_routes(bindings, uid):
    """Inspect hypothetical marked local OUTPUT routes; no packet is sent.

    This cannot inspect collector FORWARD/SNAT, a remote public source, or a
    different network namespace. Refuse when this process is not in the
    selected collector namespace; do not replace that check with nsenter.
    """
    if os.geteuid() != 0 or os.getuid() != 0:
        raise ValueError("source_egress_root_reader_required")
    namespace = os.readlink("/proc/self/ns/net")
    if any(row["network_namespace"] != namespace for row in bindings.values()):
        raise ValueError("source_egress_reader_namespace_mismatch")
    addresses = _read_ip((IP, "-j", "address", "show"))
    if not isinstance(addresses, list) or not all(isinstance(row, dict) for row in addresses):
        raise ValueError("source_egress_address_inventory_invalid")
    observed = {}
    for role in sorted(ROLES):
        binding = bindings[role]
        destination = binding["destination_ip"]
        route = _read_ip((
            IP, f"-{binding['address_family']}", "-j", "route", "get",
            destination, "mark", hex(MARK), "uid", str(uid),
        ))
        if not isinstance(route, list) or len(route) != 1 or not isinstance(route[0], dict):
            raise ValueError("source_egress_route_ambiguous")
        row = route[0]
        device, source = row.get("dev"), row.get("prefsrc", row.get("src"))
        if (
            row.get("dst") != destination
            or not isinstance(device, str)
            or not device
            or source != binding["local_source_ip"]
            or not any(
                interface.get("ifname") == device
                and isinstance(interface.get("addr_info"), list)
                and any(
                    isinstance(item, dict) and item.get("local") == source
                    for item in interface["addr_info"]
                )
                for interface in addresses
            )
        ):
            raise ValueError("source_egress_local_route_or_assigned_source_changed")
        observed[role] = (device, source)
    if os.readlink("/proc/self/ns/net") != namespace:
        raise ValueError("source_egress_reader_namespace_changed")
    return observed


class OfflineSourceEgress:
    """Hold one source selection; refuse drift and incomplete local history.

    ``sources`` must be the installed gateway's held source inventory and
    ``authority`` its held base verifier. Neither authenticates a host-wide
    caller bound, a public source at the provider, or a supplied observer.
    """

    def __init__(self, authority, sources, guard, *, collector_uid, bindings):
        self.owner = os.getpid()
        self.closed = False
        if type(collector_uid) is not int or collector_uid <= 0:
            raise ValueError("source_egress_dedicated_uid_required")
        self.authority, self.sources, self.guard = authority, sources, guard
        self.uid = collector_uid
        self.bindings = bindings
        self.selected = self._select()

    def _select(self):
        self.authority.verify()
        source = self.sources.source(SOURCE_FILE)
        if not isinstance(source, bytes) or not source:
            raise ValueError("source_egress_installed_gateway_source_required")
        base = _pin(self.authority.manifest_sha256)
        gateway = _pin(self.sources.manifest_sha256)
        if (
            not isinstance(self.authority.account, dict)
            or type(self.authority.account.get("uid")) is not int
            or self.authority.account["uid"] != self.uid
        ):
            raise ValueError("source_egress_installed_uid_mismatch")
        if not isinstance(self.bindings, dict) or set(self.bindings) != ROLES:
            raise ValueError("source_egress_three_roles_required")
        for role in ROLES:
            _binding(self.bindings[role], role, self.uid)
        if len({(b["public_source_ip"], b["address_family"]) for b in self.bindings.values()}) != 1:
            raise ValueError("source_egress_shared_public_source_missing")
        if len({b["network_namespace"] for b in self.bindings.values()}) != 1:
            raise ValueError("source_egress_collector_namespace_changed")
        return (
            base,
            gateway,
            hashlib.sha256(source).hexdigest(),
            {role: dict(row) for role, row in self.bindings.items()},
        )

    def review(self, *, ledger_raw, ledger_sha256, binding_sha256, now_ns):
        if self.closed or os.getpid() != self.owner:
            raise ValueError("source_egress_closed_or_foreign_owner")
        try:
            if self._select() != self.selected:
                raise ValueError("source_egress_selection_drift")
            observed = observe_local_routes(self.selected[3], self.uid)
            _pin(binding_sha256)
            _pin(ledger_sha256)
            report = attempts.replay(
                ledger_raw,
                expected_sha256=ledger_sha256,
                binding_sha256=binding_sha256,
                profile=attempts.JOINT_PROFILE,
            )
            if (
                report["status"] != "closed"
                or report["observed_gap"] is not None
                or report["pending_attempt"] is not None
                or any(row["unknown_charge_attempts"] for row in report["counts"])
            ):
                raise ValueError("source_egress_incomplete_or_unknown_attempt_history")
            window = self.guard.verify()
            if (
                not isinstance(window, dict)
                or set(window)
                != {
                    "binding_sha256",
                    "installation_manifest_sha256",
                    "boot_id",
                    "window_started_monotonic_ns",
                    "exclusive_through_monotonic_ns",
                    "all_other_callers_denied",
                    "collector_quarantined",
                }
                or window["binding_sha256"] != binding_sha256
                or window["installation_manifest_sha256"] != self.selected[0]
                or window["all_other_callers_denied"] is not True
                or window["collector_quarantined"] is not True
                or type(now_ns) is not int
                or type(window["window_started_monotonic_ns"]) is not int
                or type(window["exclusive_through_monotonic_ns"]) is not int
                or not 0
                < window["window_started_monotonic_ns"]
                <= report["interval_monotonic_ns"][0]
                or now_ns - window["window_started_monotonic_ns"] < LOOKBACK
                or report["interval_monotonic_ns"][1] > now_ns
                or now_ns + HORIZON > window["exclusive_through_monotonic_ns"]
            ):
                raise ValueError("source_egress_exclusion_gap_or_expiry")
            if (
                self._select() != self.selected
                or observe_local_routes(self.selected[3], self.uid) != observed
                or self.guard.verify() != window
            ):
                raise ValueError("source_egress_observation_drift")
            return {
                "status": "offline_local_consistency_only",
                "base_manifest_sha256": self.selected[0],
                "gateway_manifest_sha256": self.selected[1],
                "gateway_source_sha256": self.selected[2],
                "attempt_ledger_sha256": ledger_sha256,
                "counts": report["counts"],
                "local_marked_routes_observed": True,
                "source_authenticated": False,
                "complete_caller_coverage_verified": False,
                "provider_usage_qualified": False,
                "network_admitted": False,
                "trading_admitted": False,
            }
        except BaseException:
            self.closed = True
            raise

"""One-shot blackout transaction for isolated qualification, never admission.

The caller must supply protected, preinstalled empty rules and a fresh witness.
This module has no CLI, collector grant, transport, or guard.verify interface.
"""

from __future__ import annotations

import os
import re
import subprocess
from contextlib import suppress

NFT = "/usr/sbin/nft"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}
TABLE = "trader_joint_window_v1"
MAX_DURATION_MS = 3_725_000


def _fixed_inactive(row):
    if (
        not isinstance(row, dict)
        or row.get("schema_version") != "portfolio.root_selected_joint_window_inactive.v1"
        or row.get("status") != "selected_empty_blackout_and_permits_unqualified"
        or row.get("network_admitted") is not False
        or not isinstance(row.get("selection_sha256"), str)
        or re.fullmatch("[0-9a-f]{64}", row["selection_sha256"]) is None
        or not isinstance(row.get("static_rules_sha256"), dict)
        or set(row["static_rules_sha256"]) != {"inet", "netdev"}
        or any(
            not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None
            for value in row["static_rules_sha256"].values()
        )
    ):
        raise ValueError("joint_activation_protected_empty_selection_required")
    return row["selection_sha256"], row["static_rules_sha256"]


def _write_blackout(duration_ms, *, runner=subprocess.run):
    if type(duration_ms) is not int or not 1000 <= duration_ms <= MAX_DURATION_MS:
        raise ValueError("joint_activation_fixed_duration_required")
    # One nft -f transaction makes all four family timers visible together.
    script = (
        f"add element inet {TABLE} blackout {{ ipv4 timeout {duration_ms}ms, "
        f"ipv6 timeout {duration_ms}ms }}\n"
        f"add element netdev {TABLE} blackout {{ 0x0800 timeout {duration_ms}ms, "
        f"0x86dd timeout {duration_ms}ms }}\n"
    ).encode("ascii")
    result = runner(
        [NFT, "-f", "-"],
        input=script,
        capture_output=True,
        env=ENV,
        cwd="/",
        timeout=3,
        check=False,
    )
    if result.returncode:
        raise ValueError("joint_activation_kernel_transaction_failed")


def activate(held, witness, *, duration_ms, runner=subprocess.run):
    """Consume a prepared local scope, write blackout once, and recheck it."""
    try:
        if (
            os.getuid() != 0
            or os.geteuid() != 0
            or type(duration_ms) is not int
            or not 1000 <= duration_ms <= MAX_DURATION_MS
            or witness.snapshotter is not held
            or witness.seq != 1
            or witness.failed
            or witness.closed
        ):
            raise ValueError("joint_activation_root_fresh_scope_and_duration_required")
        selection, pins = _fixed_inactive(held.inspect_inactive())
        witness.prepare_activation(
            selection_sha256=selection, static_rules_sha256=pins, duration_ms=duration_ms
        )
        _write_blackout(duration_ms, runner=runner)
        report = witness.observe()
        if (
            report["activation_prepared"] is not True
            or report["observations"] != 1
            or report["first_selection_sha256"] != selection
            or report["minimum_observed_expiry_ns"] <= witness.last_time
            or report["network_admitted"] is not False
        ):
            raise ValueError("joint_activation_post_transaction_snapshot_required")
        return {
            "schema_version": "portfolio.joint_blackout_activation_probe.v1",
            "status": "local_blackout_transaction_observed_unqualified",
            "selection_sha256": selection,
            "minimum_observed_expiry_ns": report["minimum_observed_expiry_ns"],
            "activation_history_verified": False,
            "source_authenticated": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
        }
    except BaseException:
        witness.failed = True
        with suppress(BaseException):
            held.close()
        raise

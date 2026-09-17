"""Fixed multi-operation IPC custody acceptance, with no IP socket/dispatch API.

Loaded only from protected installed fixture sources. The root ledger records
prospective operation consumption; an IPC receipt never means venue execution.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import suppress

MAX_OPERATIONS = 20
MAX_DOCUMENTED_WEIGHT = 448
MAX_RAW_REQUESTS = 16
MAX_WS_CONNECTIONS = 2
DEADLINE_SECONDS = 30


def child_loop(fd, parent):
    """A fixed isolated UID requests tokens, receives accounting receipts and stops."""
    import socket

    channel = globals()["ControlChannel"](socket.socket(fileno=fd), parent, timeout=5)
    tokens = globals()["TOKENS"]
    try:
        channel.send("ready", 0)
        channel.receive({"start"}, 0)
        for index, token in enumerate(tokens, 1):
            channel.send(token, index)
            channel.receive({"prepared"}, index)
            channel.send("received", index)
        channel.send("finished", len(tokens) + 1)
        channel.receive({"close"}, len(tokens) + 1)
        channel.send("closed", len(tokens) + 1)
    finally:
        channel.close()


def launch(installation, sources, launcher, module):
    """Reuse the pinned launcher, credential parser, pidfd and namespace isolation."""
    installation.verify()
    reader = launcher["load_source"](installation.source("inspect_binding.py").decode())[
        "process_identity"
    ]

    def verified_identity(pid):
        installation.verify()
        return {**reader(pid), "installation_manifest_sha256": installation.manifest_sha256}

    base = installation.source("collector_launcher.py").decode()
    extension = sources.source("gateway_joint_ipc.py").decode()
    # Both sources are held and hashed by the installation; no caller code is accepted.
    source = (
        f"exec(compile({base!r},'<installed-launcher>','exec'))\n"
        f"exec(compile({extension!r},'<installed-joint-ipc>','exec'))\n"
        f"TOKENS={tuple(step[0] for step in module.IPC_STEPS)!r}\n"
    )
    return launcher["FixtureCollector"](
        source,
        verified_identity,
        collector_uid=installation.account["uid"],
        collector_gid=installation.account["gid"],
    )


def validate_budget(module, ledger):
    """Never accept a caller's weight, remaining budget or unknown-charge override."""
    steps = module.IPC_STEPS
    if len(steps) != MAX_OPERATIONS or ledger.state.profile != module.IPC_PROFILE:
        raise ValueError("joint_ipc_fixed_profile_required")
    index = len(ledger.state.attempts)
    if index >= MAX_OPERATIONS or ledger.state.pending is not None:
        raise ValueError("joint_ipc_sequence_consumed_or_pending")
    for n, attempt in enumerate(ledger.state.attempts):
        if attempt["operation"] != steps[n][1] or attempt["outcome"] != "succeeded":
            raise ValueError("joint_ipc_previous_receipt_required")
    consumed = [module.JOINT_OPERATIONS[a["operation"]] for a in ledger.state.attempts]
    remaining = [module.JOINT_OPERATIONS[op] for _, op in steps[index:]]
    units = consumed + remaining
    if (
        sum(r["documented_weight"] or 0 for r in units) != MAX_DOCUMENTED_WEIGHT
        or sum(r["raw_requests"] for r in units) != MAX_RAW_REQUESTS
        or sum(r["connections"] for r in units) != MAX_WS_CONNECTIONS
        or sum(r["documented_weight"] is None for r in units) != 1
    ):
        raise ValueError("joint_ipc_budget_changed")
    return index


def run_session(collector, ledger, module, *, on_prepared=None):
    """No grant, socket connect or payload forwarding follows an IPC request."""
    owner = os.getpid()
    deadline = time.monotonic() + DEADLINE_SECONDS

    def healthy():
        if os.getpid() != owner or time.monotonic() >= deadline:
            raise ValueError("joint_ipc_owner_or_deadline")
        collector.verify()
        ledger.checkpoint()

    try:
        healthy()
        collector.channel.send("start", 0)
        for token, operation in module.IPC_STEPS:
            index = validate_budget(module, ledger)
            healthy()
            collector.channel.receive({token}, index + 1)
            # recvmsg independently authenticated the exact PID, UID and GID.
            healthy()
            pin = module.digest(module.canonical(module.ipc_request(index)))
            result = ledger.prepare(caller="collector", operation=operation, request_sha256=pin)
            if result["index"] != index:
                raise ValueError("joint_ipc_index_changed")
            if on_prepared is not None:
                on_prepared(index)
            healthy()  # A drift or failed fsync cannot receive a success receipt.
            collector.channel.send("prepared", index + 1)
            collector.channel.receive({"received"}, index + 1)
            healthy()
            ledger.outcome(index=index, result="succeeded", request_sha256=pin)
        collector.channel.receive({"finished"}, MAX_OPERATIONS + 1)
        healthy()
        ledger.close()
        collector.channel.send("close", MAX_OPERATIONS + 1)
        collector.channel.receive({"closed"}, MAX_OPERATIONS + 1)
        collector.process.wait(timeout=1)
        return {
            "status": "joint_ipc_accounting_completed",
            "operations": MAX_OPERATIONS,
            "documented_weight_prepared": MAX_DOCUMENTED_WEIGHT,
            "unknown_charge_operations": 1,
            "transport_dispatch_verified": False,
            "kernel_permission_granted": False,
            "network_admitted": False,
        }
    except BaseException as exc:
        if not ledger.closed and not ledger.failed:
            ledger._abort(exc)
        raise
    finally:
        with suppress(Exception):
            ledger.close()
        collector.cleanup()


def run_installed(entry, authority, sources):
    collector = ledger = None
    try:
        entry["fixture_context"](authority)
        gateway = entry["load"](sources.source("ledger_gateway.py"))
        module = gateway["load_ledger"](
            {name: sources.source(name).decode() for name in entry["FILES"]}
        )
        launcher = entry["load"](authority.source("collector_launcher.py"))
        guards = entry["load"](sources.source("selftest.py"))
        collector = launch(authority, sources, launcher, module)
        binding = entry["InstalledBinding"](authority, sources, collector, guards)
        ledger = module.AttemptLedger(
            entry["STORAGE"],
            binding=binding,
            binding_sha256=binding.pin,
            profile=module.IPC_PROFILE,
        )
        print(
            json.dumps(
                {
                    "stage": "joint_ipc_ready",
                    "binding": binding.selected,
                    "binding_sha256": binding.pin,
                }
            ),
            flush=True,
        )
        if sys.stdin.readline() != "continue\n":
            raise ValueError("fixture_parent_release_required")

        def prepared(index):
            if index == 9:
                print(json.dumps({"stage": "joint_ipc_prepared", "index": index}), flush=True)
                if sys.stdin.readline() != "continue\n":
                    raise ValueError("fixture_parent_release_required")

        try:
            result = run_session(collector, ledger, module, on_prepared=prepared)
        except (ValueError, RuntimeError, OSError) as exc:
            result = {"status": "refused", "reason": type(exc).__name__, "network_admitted": False}
        print(json.dumps(result), flush=True)
    finally:
        if ledger is not None and not ledger.closed:
            with suppress(Exception):
                ledger.close()
        if collector is not None and not collector.closed:
            collector.cleanup()
        authority.close()

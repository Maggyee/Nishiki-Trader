"""Durable accounting for the existing local TLS joint collector, never admission.

This runs with the collector's ordinary process identity. It does not extend the
installed root gateway, authenticate a UID, mark sockets or qualify shared usage.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from contextlib import suppress
from functools import wraps
from pathlib import Path

from apps.strategies_nautilus import portfolio_egress_ledger as attempts
from apps.strategies_nautilus.portfolio_joint_observation import digest, replay_joint
from apps.strategies_nautilus.portfolio_joint_tls_evidence import TLSJointEvidence
from apps.strategies_nautilus.portfolio_market_depth import MAX_ARCHIVE, DepthError
from apps.strategies_nautilus.portfolio_stream import canonical

PROFILE = "portfolio.accounted_tls_joint_loopback.v1"


def binding_pin(manifest):
    return digest(canonical({"profile": PROFILE, "joint_manifest": manifest}))


def classify(operation):
    """Only documented fixed operation classes; selectors still come from the journal."""
    kind = operation.get("kind")
    if kind == "rest" and operation.get("method") == "GET":
        name = {
            "/api/v3/time": "time",
            "/api/v3/exchangeInfo": "exchange_info",
            "/api/v3/ticker/bookTicker": "book_ticker",
            "/api/v3/account": "account_read",
            "/api/v3/openOrders": "open_orders",
            "/api/v3/depth": "depth_100",
        }.get(operation.get("path"))
        if name == "depth_100" and operation.get("params", {}).get("limit") != "100":
            raise DepthError("joint_egress_depth_class")
    elif kind == "ws":
        name = {
            "ws_api_connection": "account_connect",
            "userDataStream.subscribe.signature": "account_subscribe",
            "userDataStream.unsubscribe": "account_unsubscribe",
        }.get(operation.get("operation"))
    elif kind == "market_connection":
        # The historical loopback budget's zero means no documented charge.
        # Keep the actual charge unknown in the durable ledger.
        name = "market_connect"
    else:
        name = None
    if (
        name is None
        or type(operation.get("weight")) is not int
        or operation["weight"] != (attempts.JOINT_OPERATIONS[name]["documented_weight"] or 0)
    ):
        raise DepthError("joint_egress_operation_class")
    return name


def selected_rows(raw):
    """Validate canonical chain bytes, retaining prefix positions for cross-file links."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE:
        raise DepthError("joint_egress_archive_bound")
    previous, rows, prefixes = "0" * 64, [], {}
    accumulated = hashlib.sha256()
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        row = json.loads(line)
        claimed = row.pop("sha256")
        if (
            canonical({**row, "sha256": claimed}) + b"\n" != line
            or row["seq"] != seq
            or type(row["seq"]) is not int
            or row["previous"] != previous
            or digest(canonical(row)) != claimed
        ):
            raise DepthError("joint_egress_archive_chain")
        rows.append(row)
        accumulated.update(line)
        prefixes[accumulated.hexdigest()] = seq
        previous = claimed
    return rows, prefixes, previous


def terminal_boundary(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        if os.getpid() != self.owner or self.ended:
            raise DepthError("joint_egress_owner_or_ended")
        if self.ledger.failed or self.ledger.state.terminal:
            raise DepthError("joint_egress_ended_no_retry")
        try:
            return method(self, *args, **kwargs)
        except BaseException as exc:
            if not self.ledger.failed:
                self.ledger._abort(exc)
            raise

    return guarded


class JointAccounting:
    """One local owner, one pending operation, no retry after any failed boundary."""

    def __init__(self, journal, root):
        if type(journal.state) is not TLSJointEvidence or journal.sequence != 2:
            raise DepthError("joint_egress_fresh_tls_journal_required")
        self.journal = journal
        self.manifest = canonical(journal.state.manifest)
        self.pin = binding_pin(journal.state.manifest)
        self.identity = os.fstat(journal.file.fileno())
        self.path = Path(os.readlink(f"/proc/self/fd/{journal.file.fileno()}"))
        self.reader = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        self.owner = os.getpid()
        self.pending = None
        self.stages = set()
        self.ended = False
        try:
            self.ledger = attempts.AttemptLedger(
                root,
                binding=self,
                binding_sha256=self.pin,
                clock=journal.clock,
                profile=attempts.JOINT_PROFILE,
            )
        except BaseException:
            os.close(self.reader)
            raise

    def verify(self):
        if os.getpid() != self.owner or self.ended or self.journal.failed:
            raise DepthError("joint_egress_owner_or_ended")
        info = self.path.stat(follow_symlinks=False)
        if (
            (info.st_dev, info.st_ino) != (self.identity.st_dev, self.identity.st_ino)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
            or canonical({**self.journal.state.manifest, "symbols": []}) != self.manifest
        ):
            raise DepthError("joint_egress_binding_changed")
        raw = os.pread(self.reader, MAX_ARCHIVE + 1, 0)
        rows, _, previous = selected_rows(raw)
        if (
            len(raw) != self.journal.size
            or len(rows) != self.journal.sequence
            or previous != self.journal.previous
            or canonical(rows[0]["manifest"]) != self.manifest
        ):
            raise DepthError("joint_egress_journal_changed")
        return {"binding_sha256": self.pin, "joint_prefix_sha256": digest(raw)}

    @terminal_boundary
    def prepare(self, operation, index):
        prepared = self.journal.state.prepared
        if (
            self.pending is not None
            or prepared is None
            or prepared["operation"] != operation
            or prepared["operation_id"] != index
            or index != len(self.ledger.state.attempts)
        ):
            raise DepthError("joint_egress_preparation_order")
        result = self.ledger.prepare(
            caller="collector",
            operation=classify(operation),
            joint_prefix_sha256=self.verify()["joint_prefix_sha256"],
        )
        if result["index"] != index:
            raise DepthError("joint_egress_index_changed")
        self.pending, self.stages = index, set()

    @terminal_boundary
    def before_wire(self, stage):
        """Called immediately before each connect or business write, never a permit."""
        self.ledger.checkpoint()
        state = self.journal.state
        now, _ = self.journal.clock()
        sample = state.manifest["budget_sample"]
        if (
            not 0 <= now - state.usage_ns <= 5_000_000_000
            or now // 60_000_000_000 != sample["observed_ns"] // 60_000_000_000
            or now // 300_000_000_000 != sample["observed_ns"] // 300_000_000_000
        ):
            raise DepthError("joint_egress_stale_dispatch_usage")
        prepared = self.journal.state.prepared
        if (
            self.pending is None
            or self.ledger.state.pending != self.pending
            or prepared is None
            or prepared["operation_id"] != self.pending
            or classify(prepared["operation"]) != self.ledger.state.attempts[-1]["operation"]
            or stage in self.stages
            or stage not in {"connect", "request"}
        ):
            raise DepthError("joint_egress_unprepared_or_repeated_wire")
        needs_connect = prepared["operation"]["kind"] != "ws" or (
            prepared["operation"].get("operation") == "ws_api_connection"
        )
        if (stage == "connect" and not needs_connect) or (
            stage == "request" and needs_connect and "connect" not in self.stages
        ):
            raise DepthError("joint_egress_wire_order")
        self.stages.add(stage)

    @terminal_boundary
    def control(self):
        # Pongs and closes keep the existing original-frame and per-second gates.
        # A checkpoint does not assign a zero provider cost to control traffic.
        self.ledger.checkpoint()

    @terminal_boundary
    def outcome(self):
        if (
            self.pending is None
            or self.journal.state.prepared is not None
            or "request" not in self.stages
        ):
            raise DepthError("joint_egress_response_required")
        self.ledger.outcome(
            index=self.pending,
            result="succeeded",
            joint_prefix_sha256=self.verify()["joint_prefix_sha256"],
        )
        self.pending = None

    def close(self, *, succeeded):
        if os.getpid() != self.owner:
            raise DepthError("joint_egress_foreign_owner")
        if not self.ended:
            try:
                if not succeeded and not self.ledger.failed:
                    self.ledger._abort(DepthError("joint_transport_failed"))
                self.ledger.close()
            finally:
                self.ended = True
                os.close(self.reader)


async def run_accounted_tls_loopback(
    journal, signer, *, ledger_root, trust_pem, observe_seconds=0.1
):
    from apps.strategies_nautilus.portfolio_joint_tls_transport import TLSBackend
    from apps.strategies_nautilus.portfolio_joint_transport import _run_loopback

    accounting = JointAccounting(journal, ledger_root)
    succeeded = False
    try:
        backend = TLSBackend(journal, trust_pem, accounting=accounting)
        result = await _run_loopback(
            journal,
            signer,
            observe_seconds=observe_seconds,
            transport=backend,
            accounting=accounting,
        )
        succeeded = result["status"] == "loopback_joint_completed"
        accounting.close(succeeded=succeeded)
        return {
            **result,
            "accounting_profile": PROFILE,
            "binding_sha256": accounting.pin,
            "installed_gateway_integrated": False,
            "network_admitted": False,
        }
    finally:
        with suppress(Exception):
            accounting.close(succeeded=False)


def replay_accounted(joint_raw, ledger_raw, *, joint_sha256, ledger_sha256):
    """Completed joint native replay plus both-direction original prefix linkage."""
    joint = replay_joint(joint_raw, expected_sha256=joint_sha256, evidence_type=TLSJointEvidence)
    rows, prefixes, _ = selected_rows(joint_raw)
    pin = binding_pin(rows[0]["manifest"])
    ledger = attempts.replay(
        ledger_raw,
        expected_sha256=ledger_sha256,
        binding_sha256=pin,
        profile=attempts.JOINT_PROFILE,
    )
    prepared = [r for r in rows if r["kind"] == "operation_prepared"]
    if (
        ledger["status"] != "closed"
        or ledger["pending_attempt"] is not None
        or (ledger["recorded_attempts"] != len(prepared))
    ):
        raise DepthError("joint_egress_incomplete_accounting")
    last_prefix = -1
    for line in ledger_raw.splitlines():
        event = json.loads(line)
        if event["kind"] not in {"prepared", "outcome"}:
            continue
        p = event["payload"]
        end = prefixes.get(p["joint_prefix_sha256"])
        index = p["index"]
        op = prepared[index]
        if (
            end is None
            or end < last_prefix
            or rows[end]["kind"] != "dispatch"
            or (
                rows[end]["received_ns"] > event["utc_ns"]
                or rows[end]["monotonic_ns"] > event["monotonic_ns"]
            )
        ):
            raise DepthError("joint_egress_prefix_order")
        if event["kind"] == "prepared":
            if (
                rows[end]["receipt_seq"] != op["seq"]
                or p["caller"] != "collector"
                or p["operation"] != classify(op["operation"])
            ):
                raise DepthError("joint_egress_preparation_link")
            # Next TLS opening (if any) must follow the durable ledger preparation.
            opened = next(
                (
                    r
                    for r in rows[end + 1 :]
                    if r["kind"] == "tls_opened" and r["connection_id"] == index
                ),
                None,
            )
            if opened is not None and (
                opened["received_ns"] < event["utc_ns"]
                or opened["monotonic_ns"] < event["monotonic_ns"]
            ):
                raise DepthError("joint_egress_transport_before_preparation")
        else:
            responses = [
                r
                for r in rows[op["seq"] + 1 : end]
                if (
                    r["kind"] in {"rest_response", "ws_operation", "market_connected"}
                    and r.get("operation_id") == index
                )
                or (
                    r["kind"] == "account_wire"
                    and json.loads(base64.b64decode(r["raw_b64"])).get("id") == op["request_id"]
                )
            ]
            if (
                p["result"] != "succeeded"
                or len(responses) != 1
                or not any(
                    r["kind"] == "dispatch" and r["receipt_seq"] == responses[0]["seq"]
                    for r in rows[responses[0]["seq"] + 1 : end + 1]
                )
                or (index + 1 < len(prepared) and end >= prepared[index + 1]["seq"])
            ):
                raise DepthError("joint_egress_outcome_link")
        last_prefix = end
    return {
        "schema_version": PROFILE,
        "status": "local_joint_accounting_replayed",
        "joint": joint,
        "attempts": ledger,
        "documented_weight": sum(c["documented_weight"] for c in ledger["counts"]),
        "unknown_charge_attempts": sum(c["unknown_charge_attempts"] for c in ledger["counts"]),
        "prepared_tcp_connections": len(joint["summary"]["tls_connections"]),
        "provider_connection_charge": None,
        "provider_control_charge": None,
        "installed_gateway_integrated": False,
        "complete_caller_coverage_verified": False,
        "used_upper_bound": None,
        "network_admitted": False,
        "trading_admitted": False,
        "restart_allowed": False,
        "venue_requests_made": 0,
    }

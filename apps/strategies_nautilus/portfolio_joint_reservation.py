"""Durable offline rehearsal of the draft's maximum documented request budget.

No transport consumes these records. Authorship, capacity arithmetic and local
durability are exercised without qualifying a gateway or granting network access.
Existing real one-shot scopes and the 448-weight loopback profile are untouched.
"""

from __future__ import annotations

import base64
import copy
import json
import os

from apps.strategies_nautilus import portfolio_joint_admission as admission
from apps.strategies_nautilus import portfolio_joint_attestation as attestation
from apps.strategies_nautilus.portfolio_rate_evidence import (
    _body,
    _integer,
    _invalid_constant,
    _unique,
)
from apps.strategies_nautilus.portfolio_stream import canonical

PROFILE = "portfolio.offline_joint_reservation.v1"
MAX_ARCHIVE = 64 * 1024 * 1024
INCIDENT_RESERVE = 4096
SECOND = admission.SECOND
UNQUALIFIED = {
    "authenticated_initial_source_adapter_unavailable",
    "authenticated_complete_egress_adapter_unavailable",
    "market_connection_charge_unresolved",
    "real_capture_profile_and_durable_activation_unimplemented",
    "selected_signer_authorities_not_independently_qualified",
    "gateway_traffic_completeness_and_future_enforcement_unverified",
}


class ReservationError(ValueError):
    """The local rehearsal cannot prepare another operation."""


def _decode_record(value, limit):
    if not isinstance(value, str) or len(value) > 4 * ((limit + 2) // 3):
        raise ReservationError("rehearsal_input_bound")
    raw = base64.b64decode(value, validate=True)
    if len(raw) > limit or base64.b64encode(raw).decode() != value:
        raise ReservationError("rehearsal_noncanonical_or_oversized_input")
    return raw


def maximum_operations():
    """Frozen maximum schedule; actual route selection is not simulated here."""
    budget = admission.contract()["maximum_three_symbol_budget"]
    result = []
    for index, row in enumerate(budget["rest_requests"]):
        if index == 2:
            result.extend({"kind": "account", **r} for r in budget["ws_api_operations"][:2])
        if index == 8:
            result.append(
                {"kind": "market", "operation": "market_connection", "charge_unresolved": True}
            )
        result.append({"kind": "rest", **row})
    result.append({"kind": "account", **budget["ws_api_operations"][2]})
    return result


def _units(operations, kind, role=None):
    if kind == "REQUEST_WEIGHT":
        # Missing market charge stays an explicit blocker; this sums documented costs only.
        return sum(r.get("weight", 0) for r in operations)
    if kind == "RAW_REQUESTS":
        return sum(r["kind"] == "rest" for r in operations)
    return sum(
        r.get("operation") in {"market_connection", "ws_api_connection"}
        and (role is None or r["kind"] == role)
        for r in operations
    )


def _bounds(candidate):
    return {
        (r["role"], r["rate_limit_type"], r["interval_seconds"]): r
        for r in candidate["ledger"]["usage_bounds"]
    }


def _remaining_review(signed, candidate, *, operations, index, previous):
    """Derive remaining requirements from the recorded prefix, never a supplied count."""
    capacity = signed["capacity_review"]
    bounds = _bounds(candidate)
    previous_capacity = previous["capacity"] if previous else None
    if previous:
        old_rates = previous_capacity["interval_reviews"]
        new_rates = capacity["interval_reviews"]
        fields = ("role", "rate_limit_type", "interval_seconds", "limit")
        if [tuple(r[k] for k in fields) for r in old_rates] != [
            tuple(r[k] for k in fields) for r in new_rates
        ] or bounds.keys() != previous["bounds"].keys():
            raise ReservationError("rehearsal_limit_dimensions_changed")
        for old, new in zip(old_rates, new_rates, strict=True):
            if old["count"] is not None and (new["count"] is None or new["count"] < old["count"]):
                raise ReservationError("rehearsal_server_counter_regressed")
            role = new["role"]
            before = previous_capacity["rate_sources"][role][-1]["review_server_time_ns"]
            after = capacity["rate_sources"][role][-1]["review_server_time_ns"]
            elapsed = signed["reviewed_at_ns"] - previous_capacity["reviewed_at_ns"]
            if (
                after[1] + 50_000_000 < before[0] + elapsed
                or after[0] - 50_000_000 > before[1] + elapsed
            ):
                raise ReservationError("rehearsal_server_clock_anchor_changed")
            if new["rate_limit_type"] != "CONNECTIONS":
                width = new["interval_seconds"] * SECOND
                if before[0] // width != after[1] // width:
                    raise ReservationError("rehearsal_bucket_changed_no_reset")
        for key, bound in bounds.items():
            role, kind, _ = key
            additional = _units(
                operations[index - 1 : index], kind, role if kind == "CONNECTIONS" else None
            )
            if bound["used_upper_bound"] < previous["bounds"][key]["used_upper_bound"] + additional:
                raise ReservationError("rehearsal_gateway_bound_below_prior_preparation")

    # Replace only the full-scope arithmetic with the remaining-scope arithmetic.
    # Every source, coverage, clock and unknown-cost blocker remains intact.
    blockers = {
        b
        for b in signed["blockers"]
        if not b.endswith(":remaining_scope_or_other_clients_exceed_limit")
        and b != "conservative_connection_union_exceeds_documented_limit"
    }
    rows = []
    for original in capacity["interval_reviews"]:
        row = copy.deepcopy(original)
        kind = row["rate_limit_type"]
        remaining = _units(operations[index:], kind)
        used, other = row["used_upper_bound"], row["other_clients_upper_bound"]
        row["remaining_scope_reservation"] = remaining
        row["headroom_after_documented_reservation"] = (
            None if used is None else row["limit"] - used - other - remaining
        )
        row["reasons"] = [
            r for r in row["reasons"] if r != "remaining_scope_or_other_clients_exceed_limit"
        ]
        if (
            row["headroom_after_documented_reservation"] is not None
            and row["headroom_after_documented_reservation"] < 0
        ):
            row["reasons"].append("remaining_scope_or_other_clients_exceed_limit")
            blockers.add(
                f"{row['role']}:{kind}:{row['interval_seconds']}:remaining_scope_or_other_clients_exceed_limit"
            )
        rows.append(row)
    connections = copy.deepcopy(capacity["connection_review"])
    connections["remaining_connections"] = _units(operations[index:], "CONNECTIONS")
    used, other = (
        connections["used_upper_bound_union"],
        connections["other_clients_upper_bound_union"],
    )
    connections["headroom"] = (
        None
        if used is None or other is None
        else 300 - used - other - connections["remaining_connections"]
    )
    if connections["headroom"] is not None and connections["headroom"] < 0:
        blockers.add("conservative_connection_union_exceeds_documented_limit")
    if blockers - UNQUALIFIED:
        raise ReservationError("rehearsal_remaining_capacity_or_evidence_blocked")
    return {
        "interval_reviews": rows,
        "connection_review": connections,
        "documented_weight_remaining": _units(operations[index:], "REQUEST_WEIGHT"),
        "rest_gets_remaining": _units(operations[index:], "RAW_REQUESTS"),
        "blockers": sorted(blockers),
        "full_scope_authorship_review": signed,
    }, {"capacity": capacity, "bounds": bounds}


class RehearsalEvidence:
    def __init__(self, *, policy_sha256, scope_id):
        self.policy_sha256, self.scope_id = policy_sha256, scope_id
        self.policy_raw = None
        self.operations = maximum_operations()
        self.index = 0
        self.pending = None
        self.previous = self.latest = None
        self.started = self.last = None
        self.ended = None

    def feed(self, row):
        if self.ended:
            raise ReservationError("rehearsal_already_ended")
        now, mono = (_integer(row[k], positive=True) for k in ("at_ns", "monotonic_ns"))
        if self.last and (
            now < self.last[0]
            or mono < self.last[1]
            or abs((now - self.started[0]) - (mono - self.started[1])) > 50_000_000
        ):
            raise ReservationError("rehearsal_clock_discontinuity")
        kind = row["kind"]
        payload = row["payload"]
        if self.policy_raw is None:
            admission.exact(payload, "scope_id policy_sha256 policy_b64")
            if (
                kind != "started"
                or payload["scope_id"] != self.scope_id
                or payload["policy_sha256"] != self.policy_sha256
            ):
                raise ReservationError("rehearsal_independent_selection_changed")
            self.policy_raw = _decode_record(payload["policy_b64"], attestation.MAX_PROOF)
            attestation._selected(self.policy_raw, self.policy_sha256, attestation.MAX_PROOF)
            self.started = (now, mono)
        elif kind == "prepared":
            admission.exact(
                payload, "index operation candidate_b64 candidate_sha256 bundle_b64 bundle_sha256"
            )
            if (
                self.pending is not None
                or self.index >= len(self.operations)
                or type(payload["index"]) is not int
                or payload["index"] != self.index
                or payload["operation"] != self.operations[self.index]
            ):
                raise ReservationError("rehearsal_duplicate_or_out_of_order_preparation")
            if max(now - self.started[0], mono - self.started[1]) > 120 * SECOND:
                raise ReservationError("rehearsal_capture_deadline")
            raw = _decode_record(payload["candidate_b64"], admission.MAX_INPUT)
            signed = attestation.review(
                raw,
                candidate_sha256=payload["candidate_sha256"],
                policy_raw=self.policy_raw,
                policy_sha256=self.policy_sha256,
                bundle_raw=_decode_record(payload["bundle_b64"], attestation.MAX_PROOF),
                bundle_sha256=payload["bundle_sha256"],
                scope_id=self.scope_id,
                at_ns=now,
                monotonic_ns=mono,
            )
            self.latest, self.previous = _remaining_review(
                signed,
                _body(raw),
                operations=self.operations,
                index=self.index,
                previous=self.previous,
            )
            self.pending = (now, mono)
            self.index += 1  # A preparation consumes the local attempt before any simulated result.
        elif kind == "outcome":
            admission.exact(payload, "index result")
            if (
                self.pending is None
                or type(payload["index"]) is not int
                or payload["index"] != self.index - 1
                or payload["result"] not in {"succeeded", "failed", "uncertain"}
            ):
                raise ReservationError("rehearsal_outcome_without_matching_preparation")
            if max(now - self.pending[0], mono - self.pending[1]) > 10 * SECOND:
                raise ReservationError("rehearsal_request_deadline")
            self.pending = None
            if payload["result"] != "succeeded":
                self.ended = payload["result"]
        elif kind == "completed":
            admission.exact(payload, "")
            if self.pending is not None or self.index != len(self.operations):
                raise ReservationError("rehearsal_incomplete_scope")
            self.ended = "completed"
        elif kind == "aborted":
            admission.exact(payload, "reason rejected_sha256")
            self.ended = "aborted"
        else:
            raise ReservationError("unknown_rehearsal_event")
        if max(now - self.started[0], mono - self.started[1]) > 125 * SECOND:
            raise ReservationError("rehearsal_shutdown_deadline")
        self.last = (now, mono)

    def summary(self):
        return {
            "profile": PROFILE,
            "scope_id": self.scope_id,
            "policy_sha256": self.policy_sha256,
            "status": self.ended or "incomplete_no_resume",
            "prepared_operations": self.index,
            "pending_operation_index": self.index - 1 if self.pending is not None else None,
            "documented_weight_consumed": _units(self.operations[: self.index], "REQUEST_WEIGHT"),
            "rest_gets_consumed": _units(self.operations[: self.index], "RAW_REQUESTS"),
            "connections_consumed": _units(self.operations[: self.index], "CONNECTIONS"),
            "last_remaining_review": self.latest,
            "source_authenticated": False,
            "shared_egress_verified": False,
            "network_admitted": False,
            "capacity_reserved": False,
            "scope_consumed": False,
            "venue_requests_made": 0,
            "qualification": admission.contract()["qualification"],
            **{
                k: v
                for k, v in admission.contract().items()
                if k.startswith("qualified_") or k == "common_account_market_revision"
            },
        }


class ReservationRehearsal:
    """One exclusively created local archive; no reopen/resume/transport API."""

    def __init__(self, path, *, policy_raw, policy_sha256, scope_id, clock):
        self.clock = clock
        self.state = RehearsalEvidence(policy_sha256=policy_sha256, scope_id=scope_id)
        self.sequence, self.previous, self.size = 0, "0" * 64, 0
        self.failed = False
        self.file = os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb"
        )
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self._append(
                "started",
                {
                    "scope_id": scope_id,
                    "policy_sha256": policy_sha256,
                    "policy_b64": base64.b64encode(policy_raw).decode(),
                },
            )
        except BaseException:
            self.file.close()
            raise

    def _persist(self, row, *, incident=False):
        row = {"profile": PROFILE, "seq": self.sequence, "previous": self.previous, **row}
        digest = admission.sha(canonical(row))
        raw = canonical({**row, "sha256": digest}) + b"\n"
        if self.size + len(raw) > MAX_ARCHIVE - (0 if incident else INCIDENT_RESERVE):
            raise ReservationError("rehearsal_archive_full")
        self.file.write(raw)
        self.file.flush()
        os.fsync(self.file.fileno())
        self.previous, self.size = digest, self.size + len(raw)
        self.sequence += 1

    def _append(self, kind, payload):
        if self.failed or self.file.closed or self.state.ended:
            raise ReservationError("rehearsal_closed_no_retry")
        now, mono = self.clock()
        row = {"kind": kind, "payload": payload, "at_ns": now, "monotonic_ns": mono}
        try:
            next_state = copy.deepcopy(self.state)
            next_state.feed(row)
            self._persist(row)
            self.state = next_state
        except Exception:
            self.failed = True
            aborted = {
                "kind": "aborted",
                "payload": {
                    "reason": "rehearsal_preparation_or_persistence_failed",
                    "rejected_sha256": admission.sha(canonical(row)),
                },
                "at_ns": now,
                "monotonic_ns": mono,
            }
            try:
                self._persist(aborted, incident=True)
                self.state.feed(aborted)
            except Exception:
                pass
            raise

    def prepare(
        self, *, index, operation, candidate_raw, candidate_sha256, bundle_raw, bundle_sha256
    ):
        if len(candidate_raw) > admission.MAX_INPUT or len(bundle_raw) > attestation.MAX_PROOF:
            self._append(
                "aborted",
                {
                    "reason": "rehearsal_input_bound",
                    "rejected_sha256": admission.sha(candidate_raw + bundle_raw),
                },
            )
            raise ReservationError("rehearsal_input_bound")
        self._append(
            "prepared",
            {
                "index": index,
                "operation": operation,
                "candidate_b64": base64.b64encode(candidate_raw).decode(),
                "candidate_sha256": candidate_sha256,
                "bundle_b64": base64.b64encode(bundle_raw).decode(),
                "bundle_sha256": bundle_sha256,
            },
        )
        return copy.deepcopy(self.state.latest)

    def outcome(self, *, index, result):
        self._append("outcome", {"index": index, "result": result})

    def complete(self):
        self._append("completed", {})

    def close(self):
        self.file.close()


def replay(raw, *, expected_sha256, policy_sha256, scope_id):
    if (
        not isinstance(raw, bytes)
        or not 0 < len(raw) <= MAX_ARCHIVE
        or admission.sha(raw) != expected_sha256
    ):
        raise ReservationError("selected_rehearsal_archive_changed")
    state = RehearsalEvidence(policy_sha256=policy_sha256, scope_id=scope_id)
    previous = "0" * 64
    for seq, line in enumerate(raw.splitlines(keepends=True)):
        if not line.endswith(b"\n"):
            raise ReservationError("truncated_rehearsal_archive")
        row = json.loads(line, object_pairs_hook=_unique, parse_constant=_invalid_constant)
        admission.exact(row, "profile seq previous kind payload at_ns monotonic_ns sha256")
        digest = row.pop("sha256")
        if (
            row["profile"] != PROFILE
            or type(row["seq"]) is not int
            or row["seq"] != seq
            or row["previous"] != previous
            or admission.sha(canonical(row)) != digest
        ):
            raise ReservationError("rehearsal_archive_integrity")
        state.feed(row)
        previous = digest
    if state.policy_raw is None:
        raise ReservationError("rehearsal_manifest_required")
    return {"archive_sha256": expected_sha256, **state.summary()}

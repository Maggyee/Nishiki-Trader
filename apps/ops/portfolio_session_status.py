"""Read-only operator summaries of fixed ADR-017 checkpoint records.

No credentials, network, execution objects, lease creation or state writes.
A local record is never current venue confirmation or permission to send.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from decimal import Decimal

from apps.strategies_nautilus.portfolio_session_ledger import TERMINAL, read_session
from apps.strategies_nautilus.portfolio_session_runtime import RUNTIME_PROFILE
from apps.strategies_nautilus.portfolio_session_transport import (
    HISTORY_NS,
    SCOPE,
    STATE_ROOT,
    private_read,
)
from apps.strategies_nautilus.portfolio_venue import _unique_object

RUNBOOK = "docs/runbook-testnet-session-recovery.md"


def unavailable_status():
    return {
        "schema_version": "portfolio.testnet_operator_status.v1",
        "evidence_basis": "local_checkpoint_unavailable",
        "outcome": "unknown_preserve_scope",
        "current_venue_state_verified": False,
        "new_orders_authorized": False,
        "cancel_retry_allowed": False,
        "recorded_owned_btc": None,
        "orders": None,
        "next_step": "review_private_files_without_reset",
        "runbook": RUNBOOK,
    }


def _checkpoint_status(raw, *, now_ns):
    """Summarize recorded facts only; callers retain source qualification separately."""
    state = read_session(raw)["state"]
    if (state.get("runtime_profile") != RUNTIME_PROFILE or type(now_ns) is not int
            or now_ns < state["updated_ns"]):
        raise ValueError("matching checkpoint and nonregressing observation time required")
    sid = state["session_id"]
    if not isinstance(sid, str) or not sid.isascii() or not sid.isalnum() or len(sid) != 20:
        raise ValueError("fixed session identity required")
    intents, view = state["intents"], state["view"]
    dispatches, cancels = state.get("dispatches", {}), state["cancel_intents"]
    if (len(intents) > 2 or set(view["statuses"]) != set(intents)
            or set(cancels) - set(intents)
            or set(dispatches) - {f"{kind}:{oid}" for oid in intents for kind in ("submit", "cancel")}):
        raise ValueError("incomplete original intent/dispatch coverage")
    orders = []
    for oid, intent in sorted(intents.items()):
        side = intent["side"]
        if side not in {"BUY", "SELL"} or oid != f"ts-{sid}-{'b' if side == 'BUY' else 's'}":
            raise ValueError("original bounded client order identity required")
        status = view["statuses"][oid]
        if status not in TERMINAL | {"PREPARED", "INITIALIZED", "SUBMITTED", "PENDING_CANCEL", "PENDING_UPDATE", "ACCEPTED", "PARTIALLY_FILLED"}:
            raise ValueError("unsupported recorded status")
        orders.append({
            "client_order_id": oid,
            "side": side,
            "recorded_status": status,
            "submit_intent_consumed": True,
            "submit_dispatch_recorded": f"submit:{oid}" in dispatches,
            "cancel_intent_consumed": oid in cancels,
            "cancel_dispatch_recorded": f"cancel:{oid}" in dispatches,
            "cancel_allowance_consumed": oid in cancels or f"cancel:{oid}" in dispatches,
        })
    active = [o for o in orders if o["recorded_status"] not in TERMINAL]
    if set(view["open_order_ids"]) != {o["client_order_id"] for o in active} or len(active) > 1:
        raise ValueError("recorded open order coverage differs")
    owned = Decimal(view["owned_btc"])
    if not owned.is_finite() or owned < 0:
        raise ValueError("finite recorded ownership required")
    buy_used = any(o["side"] == "BUY" for o in orders)
    sell_used = any(o["side"] == "SELL" for o in orders)
    if (view["buy_allowance_consumed"] is not buy_used
            or view["sell_allowance_consumed"] is not sell_used):
        raise ValueError("recorded allowances differ from prepared intents")
    if not orders:
        outcome = "activated_without_order_record"
    elif not active:
        outcome = "recorded_terminal_with_residual" if owned else "recorded_terminal_no_inventory"
    elif any(o["cancel_allowance_consumed"] or o["recorded_status"] == "PENDING_CANCEL" for o in active):
        outcome = "unresolved_cancellation_no_retry"
    elif any(o["recorded_status"] not in {"ACCEPTED", "PARTIALLY_FILLED"} for o in active):
        outcome = "unresolved_submission_no_resubmit"
    else:
        outcome = "recorded_active_requires_reconciliation"
    history_expired = now_ns - state["started_ns"] > HISTORY_NS
    return {
        "schema_version": "portfolio.testnet_operator_status.v1",
        "evidence_basis": "local_checkpoint_record",
        "outcome": outcome,
        "session_id": sid,
        "checkpoint_sha256": hashlib.sha256(raw).hexdigest(),
        "checkpoint_updated_ns": state["updated_ns"],
        "record_age_ns": now_ns - state["updated_ns"],
        "current_venue_state_verified": False,
        "new_orders_authorized": False,
        "cancel_retry_allowed": False,
        "new_order_deadline_expired": now_ns >= state["deadline_ns"],
        "collector_history_window_expired": history_expired,
        "buy_allowance_consumed": buy_used,
        "sell_allowance_consumed": sell_used,
        "dispatches_recorded": len(dispatches),
        "orders": orders,
        "recorded_owned_btc": str(owned),
        "halt_reasons": list(state["halt_reasons"]),
        "next_step": "review_archived_evidence_history_window_exceeded" if history_expired else "signed_get_reconciliation_before_any_action",
        "runbook": RUNBOOK,
    }


def checkpoint_status(raw, *, now_ns):
    """Reporting failures never change runtime admission or erase original errors."""
    try:
        return _checkpoint_status(raw, now_ns=now_ns)
    except Exception:
        return unavailable_status()


def local_status(*, now_ns, root=STATE_ROOT):
    """Best-effort fixed-file inspection. Missing/corrupt/unstable state stays unknown."""
    try:
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("private fixed directory required")
        paths = [root / name for name in ("scope.json", "activated.json", "native.json")]
        selected = [private_read(path) for path in paths]
        scope, activated = [json.loads(raw, object_pairs_hook=_unique_object) for raw in selected[:2]]
        state = read_session(selected[2])["state"]
        if (scope != activated or scope["scope"] != SCOPE
                or scope["source"] != state["source"] or scope["session_id"] != state["session_id"]):
            raise ValueError("fixed scope/activation/checkpoint mismatch")
        result = checkpoint_status(selected[2], now_ns=now_ns)
        if [private_read(path) for path in paths] != selected:
            raise ValueError("files changed during inspection")
        return result
    except Exception:
        # Do not print raw exceptions or malformed file contents (potential secrets).
        return unavailable_status()

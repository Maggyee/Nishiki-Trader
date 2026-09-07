"""Passive, fail-closed dashboard adapter for a saved portfolio monitor report."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from apps.ops.research_portfolio_monitor import CANDIDATE_SPECS, SCHEMA_VERSION


def read_portfolio_snapshot(path: Path | None, *, generated_at_ns: int) -> dict:
    result = {"attached": path is not None, "path": str(path) if path else None,
              "state": "not_attached", "issue_count": 0, "candidates": [], "errors": []}
    if path is None:
        return result
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
        if payload["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported portfolio schema")
        updated = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
        age = (datetime.fromtimestamp(generated_at_ns / 1e9, UTC) - updated).total_seconds()
        if not 0 <= age <= 4 * 86400:
            raise ValueError("portfolio status stale or future-dated")
        boundaries = payload["boundaries"]
        if any(boundaries.get(key) is not True for key in
               ("dry_run", "live_trading_blocked", "phase_6_gate_closed", "future_blind_sealed")):
            raise ValueError("portfolio boundary unverified")
        rows = payload["candidates"]
        specs = {s["protocol"]: s for s in CANDIDATE_SPECS}
        if not isinstance(rows, list) or len(rows) != len(specs) or {r["protocol"] for r in rows} != set(specs):
            raise ValueError("portfolio roster incomplete or duplicated")
        for row in rows:
            spec = specs[row["protocol"]]
            if any(row.get(k) != spec[k] for k in ("source", "model_version")):
                raise ValueError("portfolio candidate identity mismatch")
            if (type(row["qualified_days"]) is not int or row["qualified_days"] < 0 or
                    type(row["gate_days"]) is not int or row["gate_days"] <= 0 or
                    type(row["review_eligible"]) is not bool or
                    not isinstance(row["anomaly_blockers"], list) or
                    not all(isinstance(b, str) for b in row["anomaly_blockers"])):
                raise ValueError("invalid portfolio candidate state")
            # A cached row is never allowed to contradict its own blockers.
            if row["anomaly_blockers"]:
                row["review_eligible"] = False
        issues = sum(bool(r["anomaly_blockers"]) for r in rows)
        result.update(state="attention" if issues else "healthy", issue_count=issues,
                      candidates=rows, updated_at=payload["updated_at"],
                      sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result.update(state="attention", issue_count=1, candidates=[],
                      errors=[f"portfolio_input_invalid:{type(exc).__name__}:{exc}"])
    return result

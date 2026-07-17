"""Validate and fingerprint the fail-closed Research Protocol v4 provider recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.protocol.v4"
DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v4.json")
_SOURCE_RE = re.compile(r"^rule_[a-z0-9][a-z0-9_]*$")

IDENTITIES = {
    "broad_usd_weakness_impulse": (
        "rule_broad_usd_weakness_v1",
        "fred-dtwexbgs20obs-negative-1d-v1",
    ),
    "equity_vol_relief_fred": (
        "rule_equity_vol_relief_v2",
        "fred-vixcls5obs-negative-1d-v1",
    ),
}
PARAMETERS = {
    "broad_usd_weakness_impulse": {
        "usd_return_observations": 20,
        "maximum_usd_return": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
    "equity_vol_relief_fred": {
        "vix_change_observations": 5,
        "maximum_vix_change": 0.0,
        "ttl_seconds": 86_400,
        "confidence": 0.75,
    },
}
REQUIRED_FACTORS = {
    "broad_usd_weakness_impulse": ["broad_usd_index"],
    "equity_vol_relief_fred": ["vix_close"],
}

_EXPECTED_BOUNDARIES = {
    "opened_diagnostic_only": {
        "start": "2023-01-01",
        "end": "2025-12-31",
        "allowed_use": "data_pipeline_diagnostics_only",
        "pnl_selection_forbidden": True,
    },
    "historical_replication_reserve": {
        "start": "2020-01-01",
        "end": "2022-12-31",
        "access_status": "unconsumed",
        "max_openings": 1,
    },
    "forward_pipeline_qualification": {
        "start": "2026-07-01",
        "end": "2026-07-31",
        "allowed_use": "schema_lineage_freshness_only",
        "pnl_access_forbidden": True,
    },
    "final_future_blind": {
        "start": "2026-08-01",
        "end": "2026-12-31",
        "access_status": "not_started",
        "parameter_changes_after_open_forbidden": True,
    },
}
_EXPECTED_COSTS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}
_EXPECTED_EXECUTION = {
    "venue": "BINANCE",
    "instrument": "BTCUSDT",
    "account_type": "CASH",
    "oms_type": "NETTING",
    "starting_balance_usdt": 100000,
    "trade_size_btc": 0.001,
    "position_domain": ["long", "flat"],
    "fold_initial_state": "flat",
    "engine": "NautilusTrader",
}
_EXPECTED_GATES = {
    "historical_replication": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "positive_month_fraction_at_least": 0.5,
        "closed_positions_at_least": 30,
        "leave_best_position_base_net_pnl_gt": 0.0,
    },
    "final_future_blind": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_months_at_least": 4,
        "calendar_months_total": 5,
        "closed_positions_at_least": 30,
    },
    "hard_blockers": [
        "short_position",
        "non_point_in_time_input",
        "duplicate_or_missing_observation",
        "invalid_lineage",
        "unexplained_fill",
        "kill_switch",
        "non_reproducible_replay",
    ],
    "multiple_testing": {
        "candidate_count_locked": 2,
        "parameter_grid_search_forbidden": True,
        "pnl_selected_ensemble_forbidden": True,
        "failed_candidate_reparameterization_forbidden": True,
    },
}
_EXPECTED_DISCLOSURE = {
    "provider_choice_declared_before_documentation_search": True,
    "documentation_search_exposed_limited_current_rows": True,
    "direct_csv_accessed_before_lock": False,
    "returns_computed": False,
    "pnl_computed": False,
    "selection_effect": (
        "none; signs and lookbacks are inherited unchanged from Protocol v3"
    ),
}
_EXPECTED_IMPLEMENTATION = {
    "signal_generation_status": "not_implemented_until_provider_qualification",
    "writes_signal_store": False,
    "loads_credentials": False,
    "runs_nautilus": False,
    "mutates_source_policy": False,
    "resumes_testnet": False,
    "touches_live_path": False,
}


def _require_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _require_finite(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("status") != "provider_recovery_locked_before_direct_csv_access":
        raise ValueError("v4 must remain locked before direct CSV access")
    try:
        locked_at = datetime.fromisoformat(str(payload["locked_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("locked_at must be an ISO timestamp") from exc
    if locked_at.tzinfo is None:
        raise ValueError("locked_at must include a timezone")
    _require_finite(payload)

    if payload.get("data_access_disclosure") != _EXPECTED_DISCLOSURE:
        raise ValueError("data-access disclosure differs from the v4 lock")
    if payload.get("boundaries") != _EXPECTED_BOUNDARIES:
        raise ValueError("evidence partitions differ from the v4 lock")
    for boundary in _EXPECTED_BOUNDARIES.values():
        if date.fromisoformat(boundary["end"]) < date.fromisoformat(boundary["start"]):
            raise ValueError("evidence partition ends before it starts")
    if payload.get("cost_scenarios") != _EXPECTED_COSTS:
        raise ValueError("cost scenarios differ from the v4 lock")
    if payload.get("shared_execution") != _EXPECTED_EXECUTION:
        raise ValueError("shared execution differs from the v4 lock")
    if payload.get("gates") != _EXPECTED_GATES:
        raise ValueError("research gates differ from the v4 lock")
    if payload.get("implementation_boundary") != _EXPECTED_IMPLEMENTATION:
        raise ValueError("implementation boundary is missing or unsafe")

    relationship = payload.get("relationship_to_prior_work")
    if not isinstance(relationship, dict):
        raise ValueError("relationship_to_prior_work must be an object")
    if relationship.get("protocol_v3_hashrate") != "qualified_and_not_duplicated":
        raise ValueError("v4 must not duplicate the qualified v3 hashrate route")
    if "provider_change_under_v3_identity" not in relationship.get("forbidden_reuse", []):
        raise ValueError("v4 must forbid provider changes under v3 identities")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != len(IDENTITIES):
        raise ValueError("v4 must contain exactly two locked candidates")
    seen: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("every candidate must be an object")
        key = str(candidate.get("key", ""))
        if key not in IDENTITIES or key in seen:
            raise ValueError("candidate key is missing, duplicated, or unregistered")
        seen.add(key)
        source = str(candidate.get("source", ""))
        model = str(candidate.get("model_version", ""))
        if not _SOURCE_RE.fullmatch(source):
            raise ValueError(f"candidate {key} has an invalid source")
        if (source, model) != IDENTITIES[key]:
            raise ValueError(f"candidate {key} identity differs from the v4 lock")
        if (source, model) in identities:
            raise ValueError("candidate identities must be unique")
        identities.add((source, model))
        if candidate.get("parameters") != PARAMETERS[key]:
            raise ValueError(f"candidate {key} parameters differ from the v4 lock")
        if candidate.get("required_factors") != REQUIRED_FACTORS[key]:
            raise ValueError(f"candidate {key} factors differ from the v4 lock")
        if candidate.get("data_access_status") != "documentation_summary_rows_seen_no_returns":
            raise ValueError(f"candidate {key} must preserve the access disclosure")
        if candidate.get("promotion_ceiling") != "research_only":
            raise ValueError(f"candidate {key} must remain research-only")
        rule = str(candidate.get("signal_rule", ""))
        if "strictly negative" not in rule or "state change" not in rule:
            raise ValueError(f"candidate {key} signal rule differs from the sign lock")
    if seen != set(IDENTITIES):
        raise ValueError("v4 candidate set is incomplete")
    return payload


def validate_file(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(
        raw,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON numeric constant {value!r} is forbidden")
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError("protocol must be a JSON object")
    validate_protocol(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "locked_at": payload["locked_at"],
        "candidate_count": len(payload["candidates"]),
        "identities": [
            {"source": item["source"], "model_version": item["model_version"]}
            for item in payload["candidates"]
        ],
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "valid": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(validate_file(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

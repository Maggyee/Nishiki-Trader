"""Validate and fingerprint the fail-closed Research Protocol v3 pre-registration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from apps.strategies_freqtrade.research.macro_native_mechanism_signals import (
    PREREGISTERED_PARAMETERS,
    REQUIRED_FACTORS,
    STRATEGY_IDENTITIES,
)

SCHEMA_VERSION = "research.protocol.v3"
DEFAULT_PROTOCOL = Path("docs/progress/phase-2-research-protocol-v3.json")
_SOURCE_RE = re.compile(r"^rule_[a-z0-9][a-z0-9_]*$")


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _require_finite_numbers(value: Any, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_finite_numbers(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _require_finite_numbers(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def validate_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("status") != "preregistered_no_real_factor_data_access":
        raise ValueError("protocol must remain pre-registered before factor-data access")
    try:
        frozen_at = datetime.fromisoformat(str(payload["frozen_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("frozen_at must be an ISO timestamp") from exc
    if frozen_at.tzinfo is None:
        raise ValueError("frozen_at must include a timezone")

    _require_finite_numbers(payload)
    boundaries = payload.get("boundaries")
    if not isinstance(boundaries, dict):
        raise ValueError("boundaries must be an object")
    required_boundaries = {
        "opened_diagnostic_only",
        "historical_replication_reserve",
        "forward_pipeline_qualification",
        "final_future_blind",
    }
    if set(boundaries) != required_boundaries:
        raise ValueError(f"boundaries must contain exactly {sorted(required_boundaries)}")
    intervals: dict[str, tuple[date, date]] = {}
    expected_intervals = {
        "opened_diagnostic_only": (date(2023, 1, 1), date(2025, 12, 31)),
        "historical_replication_reserve": (date(2020, 1, 1), date(2022, 12, 31)),
        "forward_pipeline_qualification": (date(2026, 7, 1), date(2026, 7, 31)),
        "final_future_blind": (date(2026, 8, 1), date(2026, 12, 31)),
    }
    for name, boundary in boundaries.items():
        if not isinstance(boundary, dict):
            raise ValueError(f"boundary {name} must be an object")
        start = _parse_date(boundary.get("start"), f"{name}.start")
        end = _parse_date(boundary.get("end"), f"{name}.end")
        if end < start:
            raise ValueError(f"boundary {name} ends before it starts")
        intervals[name] = (start, end)
    if intervals != expected_intervals:
        raise ValueError("evidence partition dates differ from the pre-registration")
    names = sorted(intervals)
    for index, left_name in enumerate(names):
        left_start, left_end = intervals[left_name]
        for right_name in names[index + 1 :]:
            right_start, right_end = intervals[right_name]
            if max(left_start, right_start) <= min(left_end, right_end):
                raise ValueError(f"boundaries {left_name} and {right_name} overlap")
    if boundaries["opened_diagnostic_only"].get("pnl_selection_forbidden") is not True:
        raise ValueError("opened diagnostic partition must forbid PnL selection")
    if boundaries["historical_replication_reserve"].get("access_status") != "unconsumed":
        raise ValueError("historical reserve must remain unconsumed at pre-registration")
    if boundaries["historical_replication_reserve"].get("max_openings") != 1:
        raise ValueError("historical reserve allows exactly one opening")
    if boundaries["forward_pipeline_qualification"].get("pnl_access_forbidden") is not True:
        raise ValueError("July qualification must forbid PnL access")
    if boundaries["final_future_blind"].get("access_status") != "not_started":
        raise ValueError("final future blind must remain not_started at pre-registration")
    if boundaries["final_future_blind"].get("parameter_changes_after_open_forbidden") is not True:
        raise ValueError("future-blind parameter changes after open must be forbidden")

    costs = payload.get("cost_scenarios")
    expected_costs = {
        "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
        "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
        "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
    }
    if costs != expected_costs:
        raise ValueError("cost scenarios differ from the pre-registration")

    execution = payload.get("shared_execution")
    expected_execution = {
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
    if execution != expected_execution:
        raise ValueError("shared execution differs from the pre-registration")

    gates = payload.get("gates")
    expected_gates = {
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
            "candidate_count_locked": 3,
            "parameter_grid_search_forbidden": True,
            "pnl_selected_ensemble_forbidden": True,
            "failed_candidate_reparameterization_forbidden": True,
        },
    }
    if gates != expected_gates:
        raise ValueError("research gates differ from the pre-registration")
    multiple_testing = gates.get("multiple_testing")
    if not isinstance(multiple_testing, dict):
        raise ValueError("gates.multiple_testing must be an object")
    for flag in (
        "parameter_grid_search_forbidden",
        "pnl_selected_ensemble_forbidden",
        "failed_candidate_reparameterization_forbidden",
    ):
        if multiple_testing.get(flag) is not True:
            raise ValueError(f"multiple-testing guard {flag} must be true")

    relationship = payload.get("relationship_to_prior_work")
    expected_relationship = {
        "registry_v1": "frozen_at_16_rejects_empty_selected_set",
        "protocol_v2": (
            "remains_active_but_data_blocked; v3 does not reopen, retune, or ensemble "
            "v2 candidates"
        ),
        "forbidden_reuse": [
            "price_technical_thresholds",
            "ohlcv_breakout_and_mean_reversion_variants",
            "perpetual_funding_crowding",
            "spot_taker_flow_share",
            "cross_sectional_price_momentum_rotation",
            "failed_model_reparameterization",
            "pnl_selected_ensemble",
        ],
    }
    if relationship != expected_relationship:
        raise ValueError("relationship_to_prior_work differs from the pre-registration")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("the locked candidate pool must contain exactly three candidates")
    if multiple_testing.get("candidate_count_locked") != len(candidates):
        raise ValueError("candidate_count_locked does not match candidates")
    expected_identities = {
        key: {"source": source, "model_version": model}
        for key, (source, model) in STRATEGY_IDENTITIES.items()
    }
    seen_keys: set[str] = set()
    seen_identities: set[tuple[str, str]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("every candidate must be an object")
        key = candidate.get("key")
        source = candidate.get("source")
        model_version = candidate.get("model_version")
        if key not in expected_identities:
            raise ValueError(f"unexpected candidate key {key!r}")
        if key in seen_keys:
            raise ValueError(f"duplicate candidate key {key}")
        identity = (str(source), str(model_version))
        if identity in seen_identities:
            raise ValueError(f"duplicate source/model identity {identity}")
        if not isinstance(source, str) or not _SOURCE_RE.fullmatch(source):
            raise ValueError(f"candidate {key} has an invalid rule source")
        if {
            "source": source,
            "model_version": model_version,
        } != expected_identities[key]:
            raise ValueError(f"candidate {key} identity differs from implementation")
        if candidate.get("data_access_status") != "not_accessed":
            raise ValueError(f"candidate {key} must remain not_accessed at pre-registration")
        if candidate.get("promotion_ceiling") != "research_only":
            raise ValueError(f"candidate {key} must be capped at research_only")
        if not isinstance(candidate.get("parameters"), dict) or not candidate["parameters"]:
            raise ValueError(f"candidate {key} requires locked parameters")
        if candidate["parameters"] != PREREGISTERED_PARAMETERS[key]:
            raise ValueError(f"candidate {key} parameters differ from implementation")
        if not isinstance(candidate.get("required_factors"), list) or not candidate[
            "required_factors"
        ]:
            raise ValueError(f"candidate {key} requires a factor contract")
        if candidate["required_factors"] != REQUIRED_FACTORS[key]:
            raise ValueError(f"candidate {key} factor contract differs from implementation")
        seen_keys.add(str(key))
        seen_identities.add(identity)

    effects = payload.get("boundaries_effect")
    expected_effects = {
        "writes_signal_store_during_preregistration": False,
        "loads_credentials": False,
        "runs_nautilus": False,
        "mutates_source_policy": False,
        "resumes_testnet": False,
        "touches_live_path": False,
    }
    if effects != expected_effects:
        raise ValueError("all pre-registration trading effects must be false")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_sha256": f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}",
        "candidate_count": len(candidates),
        "candidate_identities": [
            {
                "key": candidate["key"],
                "source": candidate["source"],
                "model_version": candidate["model_version"],
            }
            for candidate in candidates
        ],
        "historical_replication_reserve": boundaries["historical_replication_reserve"],
        "final_future_blind": boundaries["final_future_blind"],
        "valid": True,
    }


def load_and_validate_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("protocol root must be an object")
    return validate_protocol(payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(load_and_validate_protocol(args.protocol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

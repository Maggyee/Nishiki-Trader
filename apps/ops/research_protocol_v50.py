"""Contract for Phase 2 Alpha Research Protocol v50 (BTC funding-rate positioning states).

Backlog B2 under ADR-014 (Gates v2). Family: ``crypto_derivatives_structure``
(open). The hypothesis is that the *settled* perpetual funding rate — a paid
positioning cost, not a quote — marks crowding states with next-day
directional content for BTC spot: crowded shorts (negative funding) precede
recoveries, and overheated longs (funding far above the structural baseline)
precede giveback.

Frozen before any funding VALUE is fetched or opened:

- the exact provider identity (Binance Vision USD-M monthly ``fundingRate``
  archives for BTCUSDT, CHECKSUM-verified, one GET per month file);
- the staged fetch boundary: development months 2019-12..2022-12 may be
  fetched at qualification; confirmation months 2023-01..2025-12 may be
  fetched only after development passes;
- three candidate rules with structural (non-tuned) thresholds, the trailing
  window, evaluation windows, cost scenarios, and Gates v2 thresholds.

Orthogonality / non-duplication declaration (ADR-014 §3.4, warning W2):

- vs the saturated ``external_index_relief`` family: the observable is a
  crypto-native settled payment, and none of the three rules is a
  short-window decline/relief/expansion shape — they are level states against
  fixed structural constants (0, the 0.01%/8h Binance interest component, and
  5x that baseline).
- vs sealed family members v45/v46 (premium-index 5-day delta relief) and
  v48 (basis vs its own moving average): different observable (funding
  settlements vs premium/basis quotes) and different state construction
  (level vs change/MA-cross); no 5-observation delta shape is reused.
- vs the legacy 16-candidate ``rule_funding_crowding_rotation_v1`` reject:
  that was a cross-alt rotation portfolio ranked by funding; this is a
  single-asset BTC regime rule set with fixed structural thresholds under the
  modern pre-registration ceremony.

Directional declaration: long/flat BTC spot only (paper-stage venue parity).
The candidates express the contrarian long side; the symmetric short side is
deferred to a ``two_sided_regime`` study (backlog B4). Because execution is
spot, no funding carry is earned or paid — the test is purely directional.

Weekend coverage: funding settles every 8h, 24/7, and is broadcast at
settlement, so there is no weekend vacuum and no vintage risk (immutable
exchange archive). The last settlement used for a day-D close decision is
16:00 UTC of day D — 8 hours before the decision, by construction.

Sealed protocols are unaffected. The 2026-09..2027-01 future blind stays
sealed. No SignalEvent writes, no SourcePolicy changes, no live-path impact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "research.protocol.v50.v1"
MECHANISM_FAMILY = "crypto_derivatives_structure"

IDENTITIES = {
    "fund_neg_3d": (
        "rule_crypto_funding_negative_v1",
        "crypto-btc-funding-sum72h-negative-v1",
    ),
    "fund_below_baseline_3d": (
        "rule_crypto_funding_below_baseline_v1",
        "crypto-btc-funding-mean72h-below-1bp8h-v1",
    ),
    "fund_overheat_flat_3d": (
        "rule_crypto_funding_overheat_flat_v1",
        "crypto-btc-funding-mean72h-overheat5bp8h-flat-v1",
    ),
}

SYMBOL = "BTCUSDT"
VENUE = "BINANCE"
TRADE_SIZE_BTC = 0.001

FUNDING_SOURCE = {
    "provider": "Binance Vision USD-M monthly fundingRate archives",
    "base_url": "https://data.binance.vision/data/futures/um/monthly/fundingRate",
    "symbol": SYMBOL,
    "development_months": ["2019-12", "2022-12"],
    "confirmation_months": ["2023-01", "2025-12"],
    "archive_dir": "data/research-v50/funding",
    "timestamp_columns": ["calc_time", "funding_time"],
    "rate_columns": ["last_funding_rate", "funding_rate"],
    "confirmation_fetch_requires_development_pass": True,
}

CLOSES_SOURCE = {
    "provider": "Binance Vision spot monthly 1d klines",
    "symbol": SYMBOL,
    "start_month": "2019-12",
    "end_month": "2025-12",
    "csv_path": "data/research-v50/closes/btcusdt-1d-closes-2019-12-2025-12.csv",
}

# Structural constants, not tuned numbers: 0 is the sign boundary of the paid
# rate; 0.0001 (0.01% per 8h) is Binance's fixed interest-rate component --
# the neutral funding level when the premium is zero; 0.0005 is five times
# that baseline, marking a plainly overheated long-crowding state.
PARAMETERS = {
    "trailing_window_hours": 72,
    "min_settlements_in_window": 6,
    "baseline_rate_per_8h": 0.0001,
    "overheat_rate_per_8h": 0.0005,
    "decision_cutoff": "settlements with timestamp < (D+1)T00:00:00Z decide day D's close",
    "position_rule": "state at day D close is held for day D+1; long/flat only",
    "fail_safe": "fewer than min settlements in the trailing window forces flat",
}

RULES = {
    "fund_neg_3d": "sum of settlement rates over trailing 72h < 0 -> long, else flat",
    "fund_below_baseline_3d": (
        "mean settlement rate over trailing 72h < baseline_rate_per_8h -> long, else flat"
    ),
    "fund_overheat_flat_3d": (
        "mean settlement rate over trailing 72h > overheat_rate_per_8h -> flat, else long"
    ),
}

DATA_QUALITY_GATES = {
    "rate_abs_sanity_max": 0.05,
    "max_settlement_gap_hours": 16.0,
    "min_development_settlements": 3300,
    "min_confirmation_settlements": 3200,
}

WINDOWS = {
    "development": ("2020-01-01", "2022-12-31"),
    "confirmation": ("2023-01-01", "2025-12-31"),
    "future_blind": ("2026-09-01", "2027-01-31"),
}

COST_SCENARIOS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}

GATES_V2 = {
    "development": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "positive_calendar_months_at_least": 18,
        "calendar_months_total": 36,
        "closed_positions_at_least": 60,
        "leave_best_position_base_net_pnl_gt": 0.0,
        "benchmark_relative": "base_net_pnl > time_in_market_fraction * window_buy_and_hold_pnl",
        "bootstrap_p_value_max": 0.10,
        "duplicate_replays_required": 2,
        "spot_long_flat_only": True,
    },
    "confirmation": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "positive_calendar_months_at_least": 18,
        "calendar_months_total": 36,
        "closed_positions_at_least": 60,
        "leave_best_position_base_net_pnl_gt": 0.0,
        "benchmark_relative": "base_net_pnl > time_in_market_fraction * window_buy_and_hold_pnl",
        "bootstrap_p_value_max": 0.10,
        "duplicate_replays_required": 2,
        "spot_long_flat_only": True,
    },
}

BOOTSTRAP_SPEC = {
    "n_trials": 20000,
    "seed": 20260827,
    "implementation": "apps.ops.research_meta_analysis.matched_random_timing_p_value",
}

ADVANCE_RULE = (
    "among development passers, only the candidate with the highest base net "
    "PnL opens confirmation (ties -> alphabetical key order); the others are "
    "recorded as development_passed_not_advanced"
)

BOUNDARIES = {
    "writes_signal_events": False,
    "mutates_source_policy": False,
    "opens_future_blind": False,
    "touches_live_path": False,
    "reopens_sealed_protocols": False,
    "confirmation_data_fetched_before_development_pass": False,
}


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mechanism_family": MECHANISM_FAMILY,
        "identities": {k: list(v) for k, v in sorted(IDENTITIES.items())},
        "symbol": SYMBOL,
        "venue": VENUE,
        "trade_size_btc": TRADE_SIZE_BTC,
        "funding_source": FUNDING_SOURCE,
        "closes_source": CLOSES_SOURCE,
        "parameters": PARAMETERS,
        "rules": RULES,
        "data_quality_gates": DATA_QUALITY_GATES,
        "windows": {k: list(v) if isinstance(v, tuple) else v for k, v in WINDOWS.items()},
        "cost_scenarios": COST_SCENARIOS,
        "gates_v2": GATES_V2,
        "bootstrap_spec": BOOTSTRAP_SPEC,
        "advance_rule": ADVANCE_RULE,
        "boundaries": BOUNDARIES,
    }


def contract_sha256() -> str:
    canonical = json.dumps(contract_payload(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def validate_contract() -> list[str]:
    errors: list[str] = []
    if set(IDENTITIES) != set(RULES):
        errors.append("IDENTITIES and RULES must cover the same candidate keys")
    if len(IDENTITIES) != 3:
        errors.append(f"expected 3 candidates, found {len(IDENTITIES)}")
    if WINDOWS["development"][1] >= WINDOWS["confirmation"][0]:
        errors.append("development window must end before confirmation begins")
    if PARAMETERS["baseline_rate_per_8h"] >= PARAMETERS["overheat_rate_per_8h"]:
        errors.append("overheat threshold must exceed the baseline rate")
    for stage, gates in GATES_V2.items():
        if gates["positive_calendar_months_at_least"] * 2 != gates["calendar_months_total"]:
            errors.append(f"{stage} month gate must be the 50% breadth rule")
    if FUNDING_SOURCE["development_months"][1] >= FUNDING_SOURCE["confirmation_months"][0]:
        errors.append("development fetch months must end before confirmation months")
    return errors

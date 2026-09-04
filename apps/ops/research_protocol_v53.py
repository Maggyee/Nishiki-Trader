"""Contract for Phase 2 Alpha Research Protocol v53 (cross-sectional momentum re-test).

First protocol frozen under the **accepted ADR-014 §11 class-adaptive breadth
gate** (operator acceptance 2026-08-28). Family: ``cross_sectional_relative``.
Single candidate: the UNCHANGED v52 30-day cross-sectional momentum rule under
a genuinely new identity, as §11 explicitly requires for any re-test of a
mechanism whose prior identity died on the fixed breadth floor.

**Conditional re-test disclosure (recorded before freezing):** protocol v52
already opened this rule's 2020-2022 development data. Its development
numbers (+426.71 USDT base, 429 legs, leave-best +226.36, permutation
p=0.0556, 17/36 positive months) are therefore KNOWN in advance and carry no
new evidentiary weight here. The only genuinely new development-stage
information is whether 17 positive months exceeds the null distribution's
median breadth — a quantity never computed before this freeze. The protocol's
real evidentiary weight rests on the 2023-2025 confirmation window, whose
archives were NEVER fetched by v52 (the staged fetch boundary held) and
remain a true out-of-sample test.

Everything except the identity and the breadth-gate rule is copied verbatim
from the sealed v52 contract: pool, mechanical universe and delisting rules,
construction (k=3, 100 USDT legs, weekly Monday-close rebalance), lookback
(30d, standard literature constant), costs, windows, staged fetch boundary,
and every other Gates v2 threshold. No lookback search, no k search, no
threshold change of any kind. The rejected v52 reversal and low-volatility
mechanisms are NOT re-registered: they failed on the merits, not on the
breadth gate.

Declarations (unchanged from v52): two-sided backtest only; no short-leg
funding/borrow drag modeled (recorded limitation); survivorship-biased
universe (recorded limitation); 24/7 official archives, Monday 00:00 UTC
rebalances, no weekend vacuum.

Sealed protocols are unaffected. The 2026-09..2027-01 future blind stays
sealed. No SignalEvent writes, no SourcePolicy changes, no live-path impact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "research.protocol.v53.v1"
MECHANISM_FAMILY = "cross_sectional_relative"

IDENTITIES = {
    "xs_mom_30d": (
        "rule_crypto_xs_momentum_ls_v2",
        "crypto-xs-mom30d-top3-bottom3-weekly-v2",
    ),
}

VENUE = "BINANCE"

# Identical to the sealed v52 pool (22 USDT spot pairs listed on Binance on or
# before 2019-10-01). Universe membership is resolved mechanically at
# qualification by archive coverage; exclusions are logged, never substituted.
SYMBOL_POOL = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "LTCUSDT",
    "EOSUSDT",
    "XLMUSDT",
    "TRXUSDT",
    "ETCUSDT",
    "LINKUSDT",
    "XMRUSDT",
    "DASHUSDT",
    "ZECUSDT",
    "NEOUSDT",
    "ATOMUSDT",
    "VETUSDT",
    "ONTUSDT",
    "IOTAUSDT",
    "QTUMUSDT",
    "MATICUSDT",
    "DOGEUSDT",
]

CLOSES_SOURCE = {
    "provider": "Binance Vision spot monthly 1d klines",
    "development_months": ["2019-10", "2022-12"],
    "confirmation_months": ["2023-01", "2025-12"],
    "closes_dir": "data/research-v53/closes",
    "confirmation_fetch_requires_development_pass": True,
}

PARAMETERS = {
    "legs_per_side": 3,
    "leg_notional_usdt": 100.0,
    "rebalance": "weekly, Monday 00:00 UTC close",
    "min_universe_size": 12,
    "lookbacks_days": {"xs_mom_30d": 30},
    "ranking": {
        "xs_mom_30d": "trailing 30d simple return; long top 3, short bottom 3",
    },
    "execution": "signals computed on rebalance close; positions carried until next rebalance",
    "warmup_rule": "first rebalance is the first Monday with full lookback for all universe "
    "members inside the evaluation window",
}

DATA_QUALITY_GATES = {
    "max_daily_gap_days": 1,
    "min_universe_size": 12,
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

# Gates v2 with the ADR-014 §11 class-adaptive breadth rule: the candidate's
# positive-month count must EXCEED the median positive-month count of its own
# rank-permutation null (identical calendar/universe/legs/costs). The fixed
# floor stays in the table as the reporting reference required by §11.
GATES_V2 = {
    "development": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "months_breadth_rule": "adaptive_null_median",
        "positive_calendar_months_at_least": 18,
        "calendar_months_total": 36,
        "closed_leg_positions_at_least": 60,
        "leave_best_leg_base_net_pnl_gt": 0.0,
        "benchmark_relative": "base_net_pnl > net_exposure_fraction * window_btc_buy_and_hold_pnl",
        "permutation_p_value_max": 0.10,
        "duplicate_replays_required": 2,
        "two_sided_backtest_only": True,
    },
    "confirmation": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "months_breadth_rule": "adaptive_null_median",
        "positive_calendar_months_at_least": 18,
        "calendar_months_total": 36,
        "closed_leg_positions_at_least": 60,
        "leave_best_leg_base_net_pnl_gt": 0.0,
        "benchmark_relative": "base_net_pnl > net_exposure_fraction * window_btc_buy_and_hold_pnl",
        "permutation_p_value_max": 0.10,
        "duplicate_replays_required": 2,
        "two_sided_backtest_only": True,
    },
}

PERMUTATION_SPEC = {
    "n_trials": 20000,
    "seed": 20260827,
    "null": (
        "identical rebalance calendar, universe evolution, leg counts, notionals, and "
        "costs; the ranking is replaced by an independent uniform random permutation at "
        "every rebalance; the same null supplies the §11 breadth median"
    ),
    "p_value": "(1 + #{null base PnL >= candidate base PnL}) / (n_trials + 1)",
}

ADVANCE_RULE = (
    "single candidate: it opens confirmation if and only if it passes every "
    "development gate; a development failure closes the identity permanently"
)

BOUNDARIES = {
    "writes_signal_events": False,
    "mutates_source_policy": False,
    "opens_future_blind": False,
    "touches_live_path": False,
    "reopens_sealed_protocols": False,
    "confirmation_data_fetched_before_development_pass": False,
    "conditional_retest_of_v52_development_window": True,
}


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mechanism_family": MECHANISM_FAMILY,
        "identities": {k: list(v) for k, v in sorted(IDENTITIES.items())},
        "venue": VENUE,
        "symbol_pool": SYMBOL_POOL,
        "closes_source": CLOSES_SOURCE,
        "parameters": PARAMETERS,
        "data_quality_gates": DATA_QUALITY_GATES,
        "windows": {k: list(v) if isinstance(v, tuple) else v for k, v in WINDOWS.items()},
        "cost_scenarios": COST_SCENARIOS,
        "gates_v2": GATES_V2,
        "permutation_spec": PERMUTATION_SPEC,
        "advance_rule": ADVANCE_RULE,
        "boundaries": BOUNDARIES,
    }


def contract_sha256() -> str:
    canonical = json.dumps(contract_payload(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def validate_contract() -> list[str]:
    errors: list[str] = []
    if len(IDENTITIES) != 1:
        errors.append(f"expected 1 candidate, found {len(IDENTITIES)}")
    if set(IDENTITIES) != set(PARAMETERS["lookbacks_days"]) or set(IDENTITIES) != set(
        PARAMETERS["ranking"]
    ):
        errors.append("IDENTITIES, lookbacks, and ranking specs must cover the same keys")
    if len(SYMBOL_POOL) != len(set(SYMBOL_POOL)):
        errors.append("symbol pool contains duplicates")
    if PARAMETERS["min_universe_size"] < 4 * PARAMETERS["legs_per_side"]:
        errors.append("minimum universe must be at least 4x legs per side")
    if WINDOWS["development"][1] >= WINDOWS["confirmation"][0]:
        errors.append("development window must end before confirmation begins")
    if CLOSES_SOURCE["development_months"][1] >= CLOSES_SOURCE["confirmation_months"][0]:
        errors.append("development fetch months must end before confirmation months")
    for stage, gates in GATES_V2.items():
        if gates.get("months_breadth_rule") != "adaptive_null_median":
            errors.append(f"{stage} must declare the ADR-014 §11 adaptive breadth rule")
        if gates["positive_calendar_months_at_least"] * 2 != gates["calendar_months_total"]:
            errors.append(f"{stage} fixed-floor reference must stay the 50% breadth rule")
    return errors

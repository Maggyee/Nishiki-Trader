"""Contract for Phase 2 Alpha Research Protocol v52 (cross-sectional long/short states).

Backlog B3 under ADR-014 (Gates v2). Family: ``cross_sectional_relative``
(open). First two-sided, multi-asset protocol in the program: dollar-neutral
long/short portfolios across long-listed liquid USDT pairs, so the tested
edge is *relative* selection skill with the shared long-BTC beta removed by
construction — orthogonal to every current ``paper_shadow`` survivor.

Frozen before any price VALUE is opened:

- the candidate symbol pool (22 USDT spot pairs listed on Binance on or
  before 2019-10-01, hand-listed below), the mechanical universe rule
  (pool members whose official monthly 1d kline archives fully cover the
  development fetch range; minimum 12 survivors else the protocol blocks),
  and the delisting rule for later windows;
- three candidate mechanisms with standard-literature lookbacks (30d
  momentum, 7d reversal, 30d low-volatility) — three different mechanisms,
  one shared construction, no per-mechanism parameter grids;
- portfolio construction (k=3 per side, equal weight, 100 USDT per leg,
  weekly Monday-close rebalance), costs, windows, and the Gates v2 mapping
  including the rank-permutation null.

Non-duplication declaration (ADR-014 §3.4, warning W2): the legacy
16-candidate era rejected four LONG-ONLY rotations (xs momentum, relative
value, diversified momentum, low-vol rotation). This protocol tests the
market-neutral long/short construction those rotations never had; a
long-only rotation is not among the candidates. No sealed identity's
condition, threshold, or fingerprint is reused.

Directional declaration: two-sided (short legs are modeled in the cash
replay). This is a research backtest only — every later venue stage keeps
its own constraints, and nothing here touches SourcePolicy, testnet, or live
paths. Funding costs of perpetual shorts are NOT modeled because the replay
uses spot closes; this is recorded as a known limitation for any later
review (spot-borrow/perp-funding drag would reduce short-leg PnL).

Weekend coverage: all inputs are 24/7 Binance official archives; rebalances
fall on Monday 00:00 UTC closes; no external-calendar vacuum exists.

Universe survivorship: requiring full development-range coverage biases the
universe toward survivors. This is mitigated (not eliminated) by the
long/short construction drawing both legs from the same surviving pool, and
by the mechanical mid-window delisting rule below. Recorded as a limitation.

Delisting rule (frozen): if a universe symbol's monthly archive is absent
for a month inside an evaluation window, the symbol exits the universe at
its last available daily close — any open leg is force-closed at that close
with standard costs — and is excluded from rankings thereafter. No
substitute symbol enters.

Sealed protocols are unaffected. The 2026-09..2027-01 future blind stays
sealed. No SignalEvent writes, no SourcePolicy changes, no live-path impact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "research.protocol.v52.v1"
MECHANISM_FAMILY = "cross_sectional_relative"

IDENTITIES = {
    "xs_mom_30d": (
        "rule_crypto_xs_momentum_ls_v1",
        "crypto-xs-mom30d-top3-bottom3-weekly-v1",
    ),
    "xs_rev_7d": (
        "rule_crypto_xs_reversal_ls_v1",
        "crypto-xs-rev7d-top3-bottom3-weekly-v1",
    ),
    "xs_lowvol_30d": (
        "rule_crypto_xs_lowvol_ls_v1",
        "crypto-xs-lowvol30d-top3-bottom3-weekly-v1",
    ),
}

VENUE = "BINANCE"

# Hand-listed candidate pool: USDT spot pairs listed on Binance on or before
# 2019-10-01. Membership in the tested universe is resolved mechanically at
# qualification by archive coverage; symbols failing coverage are excluded
# and logged, never substituted.
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
    "closes_dir": "data/research-v52/closes",
    "confirmation_fetch_requires_development_pass": True,
}

# Standard-literature lookbacks, not tuned grids: monthly momentum (30d),
# weekly reversal (7d), monthly realized volatility (30d).
PARAMETERS = {
    "legs_per_side": 3,
    "leg_notional_usdt": 100.0,
    "rebalance": "weekly, Monday 00:00 UTC close",
    "min_universe_size": 12,
    "lookbacks_days": {"xs_mom_30d": 30, "xs_rev_7d": 7, "xs_lowvol_30d": 30},
    "ranking": {
        "xs_mom_30d": "trailing 30d simple return; long top 3, short bottom 3",
        "xs_rev_7d": "trailing 7d simple return; long bottom 3, short top 3",
        "xs_lowvol_30d": "std of daily simple returns over 30d; long lowest 3, short highest 3",
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

# Gates v2 mapped to the dollar-neutral portfolio class:
# - closed_positions counts completed leg holdings (entry rebalance -> exit);
# - leave-best drops the single best completed leg holding;
# - benchmark_relative keeps the exposure formula; for a dollar-neutral book
#   net exposure ~ 0, so the floor degenerates to ~0 and the binding
#   statistical test is the rank-permutation null below;
# - the null replaces random *timing* with random *ranking*: identical
#   calendar, universe, construction, and costs, ranks drawn uniformly at
#   random each rebalance.
GATES_V2 = {
    "development": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
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
        "every rebalance"
    ),
    "p_value": "(1 + #{null base PnL >= candidate base PnL}) / (n_trials + 1)",
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
    if len(IDENTITIES) != 3:
        errors.append(f"expected 3 candidates, found {len(IDENTITIES)}")
    if set(IDENTITIES) != set(PARAMETERS["lookbacks_days"]) or set(IDENTITIES) != set(
        PARAMETERS["ranking"]
    ):
        errors.append("IDENTITIES, lookbacks, and ranking specs must cover the same keys")
    if len(SYMBOL_POOL) != len(set(SYMBOL_POOL)):
        errors.append("symbol pool contains duplicates")
    if len(SYMBOL_POOL) < 2 * PARAMETERS["min_universe_size"] // 2:
        errors.append("symbol pool smaller than the minimum universe")
    if PARAMETERS["min_universe_size"] < 4 * PARAMETERS["legs_per_side"]:
        errors.append("minimum universe must be at least 4x legs per side")
    if WINDOWS["development"][1] >= WINDOWS["confirmation"][0]:
        errors.append("development window must end before confirmation begins")
    if CLOSES_SOURCE["development_months"][1] >= CLOSES_SOURCE["confirmation_months"][0]:
        errors.append("development fetch months must end before confirmation months")
    for stage, gates in GATES_V2.items():
        if gates["positive_calendar_months_at_least"] * 2 != gates["calendar_months_total"]:
            errors.append(f"{stage} month gate must be the 50% breadth rule")
    return errors

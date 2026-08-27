"""Mechanism-family registry for the alpha research program (ADR-014 §3).

This module is the machine-readable source of truth for:

- which mechanism family every tested identity (protocols v2-v48 plus the
  original 16-candidate registry) belongs to;
- each family's status (``saturated`` families reject new members at
  pre-registration, before any data access);
- program totals used for multiple-testing corrections in
  ``apps/ops/research_meta_analysis.py`` and in confirmation reviews.

``--write`` regenerates ``docs/progress/research-mechanism-family-registry.json``.
``--check`` fails when a ``apps/ops/research_protocol_v*.py`` module has no
table entry (the ADR-014 §3.5 enforcement hook for v49+), when a table entry
drifts from a module's ``IDENTITIES``, or when the committed JSON is stale.

Outcome vocabulary (per candidate):

- ``provider_blocked``: closed at provider/data qualification before any PnL.
- ``not_opened``: identity frozen but development never opened under this
  protocol (superseded elsewhere).
- ``development_rejected``: opened development PnL and failed frozen gates.
- ``development_passed_not_advanced``: passed development gates but was not
  the candidate advanced to confirmation.
- ``superseded_by_later_protocol``: same identity re-registered by a later
  protocol which owns the final outcome.
- ``insufficient_evidence``: cost-positive but below the frozen activity floor.
- ``confirmation_rejected``: failed the independent confirmation holdout.
- ``confirmation_passed_paper_shadow``: confirmed and held at ``paper_shadow``.
- ``forward_data_candidate``: no historical PnL identity; forward-only contract.
- ``legacy_reject``: original 16-candidate registry reject (pre-protocol era).
- ``pre_registered``: contract frozen; development/confirmation not yet run.

The historical tables below describe sealed protocols and must not be edited
except to append new protocols or to correct a documented transcription error.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "research.mechanism_family_registry.v1"
AS_OF = "2026-08-27"
REGISTRY_RELPATH = Path("docs/progress/research-mechanism-family-registry.json")
LEGACY_REGISTRY_RELPATH = Path("docs/progress/phase-2-research-candidate-registry.json")

FAMILY_STATUSES = frozenset({"saturated", "open", "deprioritized", "blocked_provider", "planned"})

OUTCOMES = frozenset(
    {
        "provider_blocked",
        "not_opened",
        "development_rejected",
        "development_passed_not_advanced",
        "superseded_by_later_protocol",
        "insufficient_evidence",
        "confirmation_rejected",
        "confirmation_passed_paper_shadow",
        "forward_data_candidate",
        "legacy_reject",
        "pre_registered",
    }
)

# Outcomes that mean strategy PnL was actually opened for the identity.
PNL_OPENED_OUTCOMES = frozenset(
    {
        "development_rejected",
        "development_passed_not_advanced",
        "superseded_by_later_protocol",
        "insufficient_evidence",
        "confirmation_rejected",
        "confirmation_passed_paper_shadow",
        "legacy_reject",
    }
)

FAMILIES: dict[str, dict[str, str]] = {
    "external_index_relief": {
        "status": "saturated",
        "rationale": (
            "Short-window decline/relief/expansion conditions on non-crypto external "
            "index levels (implied vol, implied correlation, strategy/buywrite indices, "
            "Treasury yields and their volatility, financial-stress composites) mapped "
            "to long/flat BTC. Produced all ten paper_shadow survivors and dozens of "
            "rejects; marginal members add correlated beta, not new alpha (ADR-014 §3.3). "
            "Family-mining evidence: v35's primary VIX1Y failed confirmation while its "
            "dev-passed sibling VIX6M was re-registered by v42 and confirmed; VXN was "
            "confirmed twice under two near-identical rules (v18 OHLC, v40 diff5)."
        ),
    },
    "crypto_derivatives_structure": {
        "status": "open",
        "rationale": (
            "Perpetual/futures structure signals native to the traded venue: premium "
            "index, basis, funding, term structure. Only crypto-native family with "
            "confirmed survivors (v46 premium, v48 basis). 24/7 official archives; "
            "point-in-time by construction."
        ),
    },
    "microstructure_flow": {
        "status": "open",
        "rationale": (
            "Order-flow and positioning: book depth, taker imbalance, OI dynamics. "
            "v6 was provider-blocked and legacy flow rules were rejected, which leaves "
            "the mechanism under-tested rather than falsified."
        ),
    },
    "stablecoin_liquidity": {
        "status": "open",
        "rationale": (
            "Stablecoin supply expansion as crypto liquidity impulse. v11 flagged "
            "insufficient evidence (7 positions); v12 holds an active forward-only "
            "data contract. Do not re-propose as new (see backlog B8)."
        ),
    },
    "cross_sectional_relative": {
        "status": "open",
        "rationale": (
            "Cross-sectional long/short or rotation across liquid crypto assets. "
            "Legacy rotation rules (xs momentum, relative value, diversified momentum, "
            "low-vol rotation) were rejected as long-only rotations in the 16-candidate "
            "era; a market-neutral portfolio construction remains untested (backlog B3)."
        ),
    },
    "event_calendar": {
        "status": "open",
        "rationale": "Deterministic clock effects (funding settlement, session overlaps, "
        "month-end). No protocol has tested this axis (backlog B5).",
    },
    "two_sided_regime": {
        "status": "open",
        "rationale": "Short/two-sided expressions of regime states. Every tested rule to "
        "date is spot long/flat; the short half is unexplored (backlog B4).",
    },
    "multifactor_ml": {
        "status": "open",
        "rationale": "ADR-014 §7 ML restart: regularized multi-factor models over the "
        "archived point-in-time panel (backlog B1). Supersedes linear_ml. First member: "
        "protocol v49 panel ridge.",
    },
    "portfolio_overlay": {
        "status": "planned",
        "rationale": "Vol-targeted sizing and allocation overlays evaluated at shadow "
        "portfolio level (ADR-014 §6, backlog B7); not a tradable alpha identity.",
    },
    "crypto_price_ta": {
        "status": "deprioritized",
        "rationale": (
            "Single-rule technical conditions on BTC's own price/volume series "
            "(breakout, MACD, RSI pullback, OBV, realized-vol relief, Parkinson). "
            "Rejected across the legacy 16, v41, v43, v44, and v47; new members need a "
            "written statement of what is mechanically different."
        ),
    },
    "attention_sentiment": {
        "status": "deprioritized",
        "rationale": "Wikipedia pageviews (v23, v29) and Fear & Greed (v24) rejected in "
        "development three protocols in a row.",
    },
    "defi_activity": {
        "status": "deprioritized",
        "rationale": "DefiLlama TVL/DEX/fees/OI aggregates rejected or provider-blocked "
        "across v25-v28.",
    },
    "crypto_fundamentals_onchain": {
        "status": "deprioritized",
        "rationale": (
            "Coin Metrics network fundamentals: hashrate and fee demand rejected (v11), "
            "activity expansion rejected (v13), valuation batch provider-blocked (v14). "
            "MVRV-below-one remains an undersampled lead (7 positions) usable only via a "
            "new prospectively frozen identity."
        ),
    },
    "macro_liquidity_flows": {
        "status": "blocked_provider",
        "rationale": "US net-liquidity aggregates (WALCL et al.); v21 closed at provider "
        "qualification. Any retry needs a new frozen provider identity.",
    },
    "linear_ml": {
        "status": "deprioritized",
        "rationale": "Single-model linear momentum (freqai_linear_v1 lineage) demoted "
        "after 152-day paper evidence showed no post-cost edge; superseded by "
        "multifactor_ml (ADR-014 §7).",
    },
}

LEGACY_FAMILY_ALIASES: dict[str, str] = {
    "linear_ml": "linear_ml",
    "breakout": "crypto_price_ta",
    "trend_regime": "crypto_price_ta",
    "pullback_continuation": "crypto_price_ta",
    "mean_reversion": "crypto_price_ta",
    "volatility_breakout": "crypto_price_ta",
    "volume_breakout": "crypto_price_ta",
    "absolute_momentum": "crypto_price_ta",
    "market_breadth": "crypto_price_ta",
    "cross_sectional_momentum": "cross_sectional_relative",
    "relative_value": "cross_sectional_relative",
    "diversified_momentum": "cross_sectional_relative",
    "low_volatility_rotation": "cross_sectional_relative",
    "taker_flow": "microstructure_flow",
    "flow_exhaustion": "microstructure_flow",
    "funding_crowding": "microstructure_flow",
}


def _c(
    key: str,
    source: str,
    model_version: str,
    outcome: str,
    family: str | None = None,
) -> dict[str, str | None]:
    return {
        "key": key,
        "source": source,
        "model_version": model_version,
        "outcome": outcome,
        "family": family,
    }


# One entry per research protocol module. ``family`` is the protocol default;
# per-candidate ``family`` overrides it. Sealed history: append-only.
PROTOCOLS: tuple[dict[str, Any], ...] = (
    {
        "protocol": 2,
        "family": "crypto_derivatives_structure",
        "mechanism": "Binance option risk premium / futures basis curve / stablecoin transfer",
        "candidates": [
            _c(
                "option_risk_premium",
                "rule_option_risk_premium_v1",
                "structural-rn-excessret30d-sign-v1",
                "provider_blocked",
            ),
            _c(
                "futures_basis_curve",
                "rule_futures_basis_curve_v1",
                "front-next-contango-sign-1d-v1",
                "provider_blocked",
            ),
            _c(
                "stablecoin_liquidity",
                "rule_stablecoin_liquidity_v1",
                "supply30d-transfer7d-positive-1d-v1",
                "provider_blocked",
                family="stablecoin_liquidity",
            ),
        ],
    },
    {
        "protocol": 3,
        "family": "external_index_relief",
        "mechanism": "Macro/native relief: hashrate recovery, DXY weakness, VIX relief",
        "candidates": [
            _c(
                "miner_hashrate_recovery",
                "rule_miner_hashrate_recovery_v1",
                "hashrate7-30-positive-1d-v1",
                "not_opened",
                family="crypto_fundamentals_onchain",
            ),
            _c("usd_weakness", "rule_usd_weakness_v1", "dxy20d-negative-1d-v1", "provider_blocked"),
            _c(
                "equity_vol_relief",
                "rule_equity_vol_relief_v1",
                "vix5d-negative-1d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 4,
        "family": "external_index_relief",
        "mechanism": "FRED recovery of v3 DXY/VIX routes",
        "candidates": [
            _c(
                "broad_usd_weakness_impulse",
                "rule_broad_usd_weakness_v1",
                "fred-dtwexbgs20obs-negative-1d-v1",
                "provider_blocked",
            ),
            _c(
                "equity_vol_relief_fred",
                "rule_equity_vol_relief_v2",
                "fred-vixcls5obs-negative-1d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 5,
        "family": "crypto_derivatives_structure",
        "mechanism": "Binance-native curve carry and BVOL implied-vol relief (BTC+ETH)",
        "candidates": [
            _c(
                "binance_curve_carry",
                "rule_binance_curve_carry_v1",
                "btc-eth-front-next-positive-steep-daily-v1",
                "provider_blocked",
            ),
            _c(
                "binance_bvol_relief",
                "rule_binance_bvol_relief_v1",
                "btc-eth-bvol5d-negative-daily-lag2-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 6,
        "family": "microstructure_flow",
        "mechanism": "USD-M perpetual book-depth imbalance",
        "candidates": [
            _c(
                "book_depth_imbalance",
                "rule_binance_book_depth_imbalance_v1",
                "btc-eth-usdm-bidask1pct-daily-median-lag2-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 7,
        "family": "external_index_relief",
        "mechanism": "Cboe cross-asset vol relief (VIX, OVX, GVZ)",
        "candidates": [
            _c(
                "equity_vol_relief",
                "rule_equity_vol_relief_v3",
                "cboe-vix5obs-negative-1d-v1",
                "development_rejected",
            ),
            _c(
                "energy_vol_relief",
                "rule_energy_vol_relief_v1",
                "cboe-ovx5obs-negative-1d-v1",
                "development_rejected",
            ),
            _c(
                "gold_vol_relief",
                "rule_gold_vol_relief_v1",
                "cboe-gvz5obs-negative-1d-v1",
                "superseded_by_later_protocol",
            ),
        ],
    },
    {
        "protocol": 8,
        "family": "external_index_relief",
        "mechanism": "GVZ relief independent confirmation",
        "candidates": [
            _c(
                "gold_vol_relief",
                "rule_gold_vol_relief_v1",
                "cboe-gvz5obs-negative-1d-v1",
                "confirmation_passed_paper_shadow",
            ),
        ],
    },
    {
        "protocol": 9,
        "family": "external_index_relief",
        "mechanism": "Cboe option-risk curve (VIX9D<VIX) and VVIX relief",
        "candidates": [
            _c(
                "equity_vol_curve",
                "rule_equity_vol_curve_v1",
                "cboe-vix9d-below-vix-1d-v1",
                "development_rejected",
            ),
            _c(
                "vol_of_vol_relief",
                "rule_vol_of_vol_relief_v1",
                "cboe-vvix5obs-negative-1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 10,
        "family": "crypto_fundamentals_onchain",
        "mechanism": "Coin Metrics status-time fundamentals (route without vintage metadata)",
        "candidates": [
            _c(
                "miner_hashrate_recovery",
                "rule_miner_hashrate_recovery_v2",
                "coinmetrics-hashrate7-30-positive-1d-v1",
                "provider_blocked",
            ),
            _c(
                "btc_fee_demand",
                "rule_btc_fee_demand_v1",
                "coinmetrics-feetotntv7-30-positive-1d-v1",
                "provider_blocked",
            ),
            _c(
                "stablecoin_liquidity_expansion",
                "rule_stablecoin_liquidity_v1",
                "coinmetrics-usdt-usdc-splycur30d-positive-1d-v1",
                "provider_blocked",
                family="stablecoin_liquidity",
            ),
        ],
    },
    {
        "protocol": 11,
        "family": "crypto_fundamentals_onchain",
        "mechanism": "Coin Metrics fundamentals under D+2 finalized-ledger reconstruction",
        "candidates": [
            _c(
                "miner_hashrate_recovery",
                "rule_miner_hashrate_recovery_v3",
                "chainfinalized-hashrate7-30-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "btc_fee_demand",
                "rule_btc_fee_demand_v2",
                "chainfinalized-feetotntv7-30-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "stablecoin_liquidity_expansion",
                "rule_stablecoin_liquidity_v2",
                "chainfinalized-usdt-usdc-splycur30d-positive-lag2d-v1",
                "insufficient_evidence",
                family="stablecoin_liquidity",
            ),
        ],
    },
    {
        "protocol": 12,
        "family": "stablecoin_liquidity",
        "mechanism": "USDT+USDC 30-observation expansion, forward-only data contract",
        "candidates": [
            _c(
                "stablecoin_liquidity_forward",
                "rule_stablecoin_liquidity_v3",
                "forward-usdt-usdc-splycur30d-positive-d2-v1",
                "forward_data_candidate",
            ),
        ],
    },
    {
        "protocol": 13,
        "family": "crypto_fundamentals_onchain",
        "mechanism": "BTC network mechanisms: activity expansion, MVRV distress",
        "candidates": [
            _c(
                "active_address_expansion",
                "rule_btc_active_address_expansion_v1",
                "chainfinalized-adractcnt7-30-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "transfer_count_expansion",
                "rule_btc_transfer_expansion_v1",
                "chainfinalized-txtfrcnt7-30-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "mvrv_distress",
                "rule_btc_mvrv_distress_v1",
                "chainfinalized-mvrv-below1-lag2d-v1",
                "insufficient_evidence",
            ),
        ],
    },
    {
        "protocol": 14,
        "family": "crypto_fundamentals_onchain",
        "mechanism": "BTC valuation mechanisms (realized cap, NVT, SOPR)",
        "candidates": [
            _c(
                "realized_cap_expansion",
                "rule_btc_realized_cap_expansion_v1",
                "chainfinalized-caprealusd7-30-positive-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "nvt_compression",
                "rule_btc_nvt_compression_v1",
                "chainfinalized-nvtadj7-30-negative-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "sopr_capitulation",
                "rule_btc_sopr_capitulation_v1",
                "chainfinalized-sopr7-below1-lag2d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 15,
        "family": "external_index_relief",
        "mechanism": "US rate mechanisms via FRED (real yield, curve, yield volatility)",
        "candidates": [
            _c(
                "real_yield_relief",
                "rule_us_real_yield_relief_v1",
                "fred-dfii10-5-20-negative-lag4d-v1",
                "provider_blocked",
            ),
            _c(
                "yield_curve_steepening",
                "rule_us_yield_curve_steepening_v1",
                "fred-t10y2y-5-20-positive-lag4d-v1",
                "provider_blocked",
            ),
            _c(
                "treasury_volatility_relief",
                "rule_us_treasury_volatility_relief_v1",
                "fred-dgs10-absdiff5-20-negative-lag4d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 16,
        "family": "external_index_relief",
        "mechanism": "Treasury-direct rate mechanisms (recovery of v15 routes)",
        "candidates": [
            _c(
                "real_yield_relief",
                "rule_us_real_yield_relief_v2",
                "treasury-real10-5-20-negative-lag2d-v1",
                "insufficient_evidence",
            ),
            _c(
                "yield_curve_steepening",
                "rule_us_yield_curve_steepening_v2",
                "treasury-10y2y-5-20-positive-lag2d-v1",
                "insufficient_evidence",
            ),
            _c(
                "treasury_volatility_relief",
                "rule_us_treasury_volatility_relief_v2",
                "treasury-nominal10-absdiff5-20-negative-lag2d-v1",
                "confirmation_passed_paper_shadow",
            ),
        ],
    },
    {
        "protocol": 17,
        "family": "external_index_relief",
        "mechanism": "Cboe geographic vol relief (VXEEM/VXEFA/VXN close-only route)",
        "candidates": [
            _c(
                "em_vol_relief",
                "rule_em_vol_relief_v1",
                "cboe-vxeem5obs-negative-1d-v1",
                "provider_blocked",
            ),
            _c(
                "eafe_vol_relief",
                "rule_eafe_vol_relief_v1",
                "cboe-vxefa5obs-negative-1d-v1",
                "provider_blocked",
            ),
            _c(
                "nasdaq_vol_relief",
                "rule_nasdaq_vol_relief_v1",
                "cboe-vxn5obs-negative-1d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 18,
        "family": "external_index_relief",
        "mechanism": "OHLC recovery of v17 geographic vol relief",
        "candidates": [
            _c(
                "em_vol_relief",
                "rule_em_vol_relief_v2",
                "cboe-vxeem-ohlc5obs-negative-1d-v1",
                "development_rejected",
            ),
            _c(
                "eafe_vol_relief",
                "rule_eafe_vol_relief_v2",
                "cboe-vxefa-ohlc5obs-negative-1d-v1",
                "development_rejected",
            ),
            _c(
                "nasdaq_vol_relief",
                "rule_nasdaq_vol_relief_v2",
                "cboe-vxn-ohlc5obs-negative-1d-v1",
                "confirmation_passed_paper_shadow",
            ),
        ],
    },
    {
        "protocol": 19,
        "family": "external_index_relief",
        "mechanism": "Cboe size/style/China vol relief (RVX, VXD, VXFXI)",
        "candidates": [
            _c(
                "russell_vol_relief",
                "rule_russell_vol_relief_v1",
                "cboe-rvx-ohlc5obs-negative-1d-v1",
                "development_rejected",
            ),
            _c(
                "china_vol_relief",
                "rule_china_vol_relief_v1",
                "cboe-vxfxi-ohlc5obs-negative-1d-v1",
                "provider_blocked",
            ),
            _c(
                "dow_vol_relief",
                "rule_dow_vol_relief_v1",
                "cboe-vxd-ohlc5obs-negative-1d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 20,
        "family": "external_index_relief",
        "mechanism": "OFR financial-stress relief (total, credit, safe assets)",
        "candidates": [
            _c(
                "systemic_stress_relief",
                "rule_ofr_systemic_stress_relief_v1",
                "ofr-fsi-total-diff5-negative-lag5d-v1",
                "development_rejected",
            ),
            _c(
                "credit_stress_relief",
                "rule_ofr_credit_stress_relief_v1",
                "ofr-fsi-credit-diff5-negative-lag5d-v1",
                "development_rejected",
            ),
            _c(
                "safe_asset_stress_relief",
                "rule_ofr_safe_asset_stress_relief_v1",
                "ofr-fsi-safe-assets-diff5-negative-lag5d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 21,
        "family": "macro_liquidity_flows",
        "mechanism": "US net liquidity expansion (WALCL - TGA - RRP)",
        "candidates": [
            _c(
                "net_usd_liquidity_expansion",
                "rule_us_net_liquidity_expansion_v1",
                "fred-walcl-wdtgal-rrpontsyd-diff4w-positive-lag7d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 22,
        "family": "external_index_relief",
        "mechanism": "Cboe option surface (COR1M, DSPX, SKEW)",
        "candidates": [
            _c(
                "implied_dispersion_expansion",
                "rule_cboe_implied_dispersion_expansion_v1",
                "cboe-dspx-diff5-positive-lag1d-v1",
                "provider_blocked",
            ),
            _c(
                "tail_skew_relief",
                "rule_cboe_tail_skew_relief_v1",
                "cboe-skew-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "implied_correlation_relief",
                "rule_cboe_implied_correlation_relief_v1",
                "cboe-cor1m-diff5-negative-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
        ],
    },
    {
        "protocol": 23,
        "family": "attention_sentiment",
        "mechanism": "Wikipedia crypto-article attention expansion",
        "candidates": [
            _c(
                "bitcoin_attention_expansion",
                "rule_wikipedia_bitcoin_attention_expansion_v1",
                "wikimedia-enwiki-bitcoin-pageviews-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "ethereum_attention_expansion",
                "rule_wikipedia_ethereum_attention_expansion_v1",
                "wikimedia-enwiki-ethereum-pageviews-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "cryptocurrency_attention_expansion",
                "rule_wikipedia_cryptocurrency_attention_expansion_v1",
                "wikimedia-enwiki-cryptocurrency-pageviews-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 24,
        "family": "attention_sentiment",
        "mechanism": "Crypto Fear & Greed classification holds",
        "candidates": [
            _c(
                "extreme_fear_hold",
                "rule_alternative_extreme_fear_hold_v1",
                "alternative-fng-extreme-fear-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "fear_hold",
                "rule_alternative_fear_hold_v1",
                "alternative-fng-fear-or-extreme-fear-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "non_greed_hold",
                "rule_alternative_non_greed_hold_v1",
                "alternative-fng-not-greed-or-extreme-greed-lag2d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 25,
        "family": "defi_activity",
        "mechanism": "DefiLlama TVL expansion",
        "candidates": [
            _c(
                "bitcoin_tvl_expansion",
                "rule_defillama_bitcoin_tvl_expansion_v1",
                "defillama-bitcoin-tvl-diff5-positive-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "ethereum_tvl_expansion",
                "rule_defillama_ethereum_tvl_expansion_v1",
                "defillama-ethereum-tvl-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "all_chains_tvl_expansion",
                "rule_defillama_all_chains_tvl_expansion_v1",
                "defillama-all-chains-tvl-diff5-positive-lag2d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 26,
        "family": "defi_activity",
        "mechanism": "DefiLlama DEX volume expansion",
        "candidates": [
            _c(
                "solana_dex_volume_expansion",
                "rule_defillama_solana_dex_volume_expansion_v1",
                "defillama-solana-dex-vol-diff5-positive-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "all_dex_volume_expansion",
                "rule_defillama_all_dex_volume_expansion_v1",
                "defillama-all-dexs-vol-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "ethereum_dex_volume_expansion",
                "rule_defillama_ethereum_dex_volume_expansion_v1",
                "defillama-ethereum-dex-vol-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 27,
        "family": "defi_activity",
        "mechanism": "DefiLlama protocol fee/revenue expansion",
        "candidates": [
            _c(
                "all_fees_expansion",
                "rule_defillama_all_fees_expansion_v1",
                "defillama-all-fees-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "all_revenue_expansion",
                "rule_defillama_all_revenue_expansion_v1",
                "defillama-all-revenue-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "all_holders_revenue_expansion",
                "rule_defillama_all_holders_revenue_expansion_v1",
                "defillama-all-holders-revenue-diff5-positive-lag2d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 28,
        "family": "defi_activity",
        "mechanism": "DefiLlama options notional/premium and perp OI expansion",
        "candidates": [
            _c(
                "options_notional_expansion",
                "rule_defillama_options_notional_expansion_v1",
                "defillama-options-notional-diff5-positive-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "options_premium_expansion",
                "rule_defillama_options_premium_expansion_v1",
                "defillama-options-premium-diff5-positive-lag2d-v1",
                "provider_blocked",
            ),
            _c(
                "open_interest_expansion",
                "rule_defillama_open_interest_expansion_v1",
                "defillama-open-interest-diff5-positive-lag2d-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 29,
        "family": "attention_sentiment",
        "mechanism": "Wikipedia macro-article attention relief",
        "candidates": [
            _c(
                "fed_attention_relief",
                "rule_wikipedia_fed_attention_relief_v1",
                "wikimedia-enwiki-federal-reserve-pageviews-diff5-negative-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "inflation_attention_relief",
                "rule_wikipedia_inflation_attention_relief_v1",
                "wikimedia-enwiki-inflation-pageviews-diff5-negative-lag2d-v1",
                "development_rejected",
            ),
            _c(
                "recession_attention_relief",
                "rule_wikipedia_recession_attention_relief_v1",
                "wikimedia-enwiki-recession-pageviews-diff5-negative-lag2d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 30,
        "family": "external_index_relief",
        "mechanism": "Cboe single-name vol relief (VXAPL, VXAZN, VXGOG)",
        "candidates": [
            _c(
                "apple_vol_relief",
                "rule_cboe_apple_vol_relief_v1",
                "cboe-vxapl-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "amazon_vol_relief",
                "rule_cboe_amazon_vol_relief_v1",
                "cboe-vxazn-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "google_vol_relief",
                "rule_cboe_google_vol_relief_v1",
                "cboe-vxgog-diff5-negative-lag1d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 31,
        "family": "external_index_relief",
        "mechanism": "Cboe commodity/sector/duration vol relief (VXSLV, VXXLE, VXTLT)",
        "candidates": [
            _c(
                "silver_vol_relief",
                "rule_cboe_silver_vol_relief_v1",
                "cboe-vxslv-diff5-negative-lag1d-v1",
                "provider_blocked",
            ),
            _c(
                "energy_sector_vol_relief",
                "rule_cboe_energy_sector_vol_relief_v1",
                "cboe-vxxle-diff5-negative-lag1d-v1",
                "provider_blocked",
            ),
            _c(
                "long_treasury_etf_vol_relief",
                "rule_cboe_long_treasury_etf_vol_relief_v1",
                "cboe-vxtlt-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 32,
        "family": "external_index_relief",
        "mechanism": "Cboe FX vol relief (EUVIX, BPVIX, JYVIX)",
        "candidates": [
            _c(
                "euro_fx_vol_relief",
                "rule_cboe_euro_fx_vol_relief_v1",
                "cboe-euvix-diff5-negative-lag1d-v1",
                "provider_blocked",
            ),
            _c(
                "yen_fx_vol_relief",
                "rule_cboe_yen_fx_vol_relief_v1",
                "cboe-jyvix-diff5-negative-lag1d-v1",
                "provider_blocked",
            ),
            _c(
                "pound_fx_vol_relief",
                "rule_cboe_pound_fx_vol_relief_v1",
                "cboe-bpvix-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 33,
        "family": "external_index_relief",
        "mechanism": "Cboe implied-correlation term structure (COR3M, COR6M, COR1Y)",
        "candidates": [
            _c(
                "cor3m_relief",
                "rule_cboe_cor3m_relief_v1",
                "cboe-cor3m-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "cor6m_relief",
                "rule_cboe_cor6m_relief_v1",
                "cboe-cor6m-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "cor1y_relief",
                "rule_cboe_cor1y_relief_v1",
                "cboe-cor1y-diff5-negative-lag1d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 34,
        "family": "external_index_relief",
        "mechanism": "Cboe benchmark Treasury yield relief (FVX, TNX, TYX)",
        "candidates": [
            _c(
                "fvx_relief",
                "rule_cboe_fvx_relief_v1",
                "cboe-fvx-diff5-negative-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
            _c(
                "tnx_relief",
                "rule_cboe_tnx_relief_v1",
                "cboe-tnx-diff5-negative-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "tyx_relief",
                "rule_cboe_tyx_relief_v1",
                "cboe-tyx-diff5-negative-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
    {
        "protocol": 35,
        "family": "external_index_relief",
        "mechanism": "Cboe long vol & money market relief (IRX, VIX1Y, VIX6M)",
        "candidates": [
            _c(
                "irx_relief",
                "rule_cboe_irx_relief_v1",
                "cboe-irx-diff5-negative-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "vix1y_relief",
                "rule_cboe_vix1y_relief_v1",
                "cboe-vix1y-diff5-negative-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "vix6m_relief",
                "rule_cboe_vix6m_relief_v1",
                "cboe-vix6m-diff5-negative-lag1d-v1",
                "superseded_by_later_protocol",
            ),
        ],
    },
    {
        "protocol": 36,
        "family": "external_index_relief",
        "mechanism": "Cboe option strategy & variance premium expansion (VPN, PUT, BXM)",
        "candidates": [
            _c(
                "vpn_expansion",
                "rule_cboe_vpn_expansion_v1",
                "cboe-vpn-diff5-positive-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
            _c(
                "put_expansion",
                "rule_cboe_put_expansion_v1",
                "cboe-put-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "bxm_expansion",
                "rule_cboe_bxm_expansion_v1",
                "cboe-bxm-diff5-positive-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
    {
        "protocol": 37,
        "family": "external_index_relief",
        "mechanism": "Cboe buywrite & tech overwrite expansion (BXN, BXY, BXR)",
        "candidates": [
            _c(
                "bxn_expansion",
                "rule_cboe_bxn_expansion_v1",
                "cboe-bxn-diff5-positive-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "bxy_expansion",
                "rule_cboe_bxy_expansion_v1",
                "cboe-bxy-diff5-positive-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "bxr_expansion",
                "rule_cboe_bxr_expansion_v1",
                "cboe-bxr-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 38,
        "family": "external_index_relief",
        "mechanism": "Cboe hedged equity & daily VRP expansion (VPD, PPUT, CLL)",
        "candidates": [
            _c(
                "cll_expansion",
                "rule_cboe_cll_expansion_v1",
                "cboe-cll-diff5-positive-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "pput_expansion",
                "rule_cboe_pput_expansion_v1",
                "cboe-pput-diff5-positive-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "vpd_expansion",
                "rule_cboe_vpd_expansion_v1",
                "cboe-vpd-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 39,
        "family": "external_index_relief",
        "mechanism": "Cboe low-vol & non-directional harvest expansion (LOVOL, PUTD, CNDR)",
        "candidates": [
            _c(
                "lovol_expansion",
                "rule_cboe_lovol_expansion_v1",
                "cboe-lovol-diff5-positive-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "putd_expansion",
                "rule_cboe_putd_expansion_v1",
                "cboe-putd-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "cndr_expansion",
                "rule_cboe_cndr_expansion_v1",
                "cboe-cndr-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 40,
        "family": "external_index_relief",
        "mechanism": "Cboe cross-asset equity vol relief expansion (VXN, RVX, VXD diff5 route)",
        "candidates": [
            _c(
                "vxn_relief",
                "rule_cboe_vxn_relief_v1",
                "cboe-vxn-diff5-negative-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
            _c(
                "vxd_relief",
                "rule_cboe_vxd_relief_v1",
                "cboe-vxd-diff5-negative-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "rvx_relief",
                "rule_cboe_rvx_relief_v1",
                "cboe-rvx-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 41,
        "family": "crypto_price_ta",
        "mechanism": "BTC/ETH crypto-native TA (ETH/BTC RS, Parkinson vol relief, OBV)",
        "candidates": [
            _c(
                "eth_btc_rs_expansion",
                "rule_crypto_eth_btc_rs_v1",
                "crypto-eth-btc-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_parkinson_vol_relief",
                "rule_crypto_btc_parkinson_v1",
                "crypto-btc-parkinson-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_obv_expansion",
                "rule_crypto_btc_obv_v1",
                "crypto-btc-obv-diff5-positive-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 42,
        "family": "external_index_relief",
        "mechanism": "Cboe vol term-structure relief (VIX9D, VIX3M, VIX6M)",
        "candidates": [
            _c(
                "vix9d_relief",
                "rule_cboe_vix9d_relief_v1",
                "cboe-vix9d-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "vix3m_relief",
                "rule_cboe_vix3m_relief_v1",
                "cboe-vix3m-diff5-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "vix6m_relief",
                "rule_cboe_vix6m_relief_v1",
                "cboe-vix6m-diff5-negative-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
        ],
    },
    {
        "protocol": 43,
        "family": "crypto_price_ta",
        "mechanism": "BTC volume-confirmed MACD trend regimes",
        "candidates": [
            _c(
                "btc_macd_vol_confirmed",
                "rule_crypto_btc_macd_vol_v1",
                "crypto-btc-macd12-26-9-vol080-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "btc_macd_rsi_vol_confirmed",
                "rule_crypto_btc_macd_rsi_vol_v1",
                "crypto-btc-macd12-26-9-rsi45-vol080-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "btc_macd_vol_tight",
                "rule_crypto_btc_macd_vol_tight_v1",
                "crypto-btc-macd12-26-9-vol085-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
    {
        "protocol": 44,
        "family": "crypto_price_ta",
        "mechanism": "BTC trend-following OR 2-day RSI oversold pullbacks",
        "candidates": [
            _c(
                "btc_trend_pullback_rsi10",
                "rule_crypto_trend_pullback_rsi10_v1",
                "crypto-btc-macd12-26-9-or-rsi2-lt10-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_trend_pullback_rsi15",
                "rule_crypto_trend_pullback_rsi15_v1",
                "crypto-btc-macd12-26-9-or-rsi2-lt15-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_trend_pullback_rsi20",
                "rule_crypto_trend_pullback_v1",
                "crypto-btc-macd12-26-9-or-rsi2-lt20-lag1d-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 45,
        "family": "crypto_derivatives_structure",
        "mechanism": "Binance perpetual premium-index delta relief (first batch)",
        "candidates": [
            _c(
                "btc_prem_diff4_negative",
                "rule_crypto_prem_relief_diff4_v1",
                "crypto-btc-prem-diff4-negative-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_prem_diff5_negative",
                "rule_crypto_prem_relief_v1",
                "crypto-btc-prem-diff5-negative-lag1d-v1",
                "superseded_by_later_protocol",
            ),
            _c(
                "btc_prem_diff5_tight",
                "rule_crypto_prem_relief_tight_v1",
                "crypto-btc-prem-diff5-tight-lag1d-v1",
                "confirmation_rejected",
            ),
        ],
    },
    {
        "protocol": 46,
        "family": "crypto_derivatives_structure",
        "mechanism": "Binance perpetual premium-index standard relief (confirmation of v45 sibling)",
        "candidates": [
            _c(
                "btc_prem_diff5_negative",
                "rule_crypto_prem_relief_v1",
                "crypto-btc-prem-diff5-negative-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
            _c(
                "btc_prem_diff5_loose",
                "rule_crypto_prem_relief_loose_v1",
                "crypto-btc-prem-diff5-loose-lag1d-v1",
                "development_rejected",
            ),
            _c(
                "btc_prem_diff5_minhold2",
                "rule_crypto_prem_relief_minhold2_v1",
                "crypto-btc-prem-diff5-minhold2-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
    {
        "protocol": 47,
        "family": "crypto_price_ta",
        "mechanism": "BTC realized-volatility relief",
        "candidates": [
            _c(
                "btc_rvol_relief_5_20",
                "rule_crypto_rvol_relief_v1",
                "crypto-btc-rvol-relief-5-20-lag1d-v1",
                "confirmation_rejected",
            ),
            _c(
                "btc_rvol_relief_5_20_loose",
                "rule_crypto_rvol_relief_loose_v1",
                "crypto-btc-rvol-relief-loose-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "btc_rvol_relief_5_20_minhold2",
                "rule_crypto_rvol_relief_minhold2_v1",
                "crypto-btc-rvol-relief-minhold2-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
    {
        "protocol": 51,
        "family": "crypto_derivatives_structure",
        "mechanism": "BTC settled funding-rate positioning states — provider-corrected "
        "recovery of v50 with 2020-01 archive start (ADR-014 B2, v17->v18 pattern)",
        "candidates": [
            _c(
                "fund_neg_3d",
                "rule_crypto_funding_negative_v2",
                "crypto-btc-funding-sum72h-negative-v2",
                "pre_registered",
            ),
            _c(
                "fund_below_baseline_3d",
                "rule_crypto_funding_below_baseline_v2",
                "crypto-btc-funding-mean72h-below-1bp8h-v2",
                "pre_registered",
            ),
            _c(
                "fund_overheat_flat_3d",
                "rule_crypto_funding_overheat_flat_v2",
                "crypto-btc-funding-mean72h-overheat5bp8h-flat-v2",
                "pre_registered",
            ),
        ],
    },
    {
        "protocol": 50,
        "family": "crypto_derivatives_structure",
        "mechanism": "BTC settled funding-rate positioning states (contrarian short-crowding, "
        "below-baseline, overheat-flat) with structural thresholds (ADR-014 B2)",
        "candidates": [
            _c(
                "fund_neg_3d",
                "rule_crypto_funding_negative_v1",
                "crypto-btc-funding-sum72h-negative-v1",
                "provider_blocked",
            ),
            _c(
                "fund_below_baseline_3d",
                "rule_crypto_funding_below_baseline_v1",
                "crypto-btc-funding-mean72h-below-1bp8h-v1",
                "provider_blocked",
            ),
            _c(
                "fund_overheat_flat_3d",
                "rule_crypto_funding_overheat_flat_v1",
                "crypto-btc-funding-mean72h-overheat5bp8h-flat-v1",
                "provider_blocked",
            ),
        ],
    },
    {
        "protocol": 49,
        "family": "multifactor_ml",
        "mechanism": "Ridge regression over the archived 17-factor point-in-time panel "
        "plus two BTC-native features; monthly-refit expanding walk-forward (ADR-014 §7 / B1)",
        "candidates": [
            _c(
                "panel_ridge",
                "freqai_panel_ridge_v1",
                "panel17-ridge-mwf-oos2020h2-v1",
                "development_rejected",
            ),
        ],
    },
    {
        "protocol": 48,
        "family": "crypto_derivatives_structure",
        "mechanism": "Binance perpetual basis moving-average relief",
        "candidates": [
            _c(
                "btc_basis_below_ma10",
                "rule_crypto_basis_relief_v1",
                "crypto-btc-basis-below-ma10-lag1d-v1",
                "confirmation_passed_paper_shadow",
            ),
            _c(
                "btc_basis_below_ma14",
                "rule_crypto_basis_relief_ma14_v1",
                "crypto-btc-basis-below-ma14-lag1d-v1",
                "development_passed_not_advanced",
            ),
            _c(
                "btc_basis_below_ma10_minhold2",
                "rule_crypto_basis_relief_minhold2_v1",
                "crypto-btc-basis-below-ma10-minhold2-lag1d-v1",
                "development_passed_not_advanced",
            ),
        ],
    },
)

_PROTOCOL_MODULE_RE = re.compile(r"^research_protocol_v(\d+)\.py$")

# Protocol modules whose identities cannot be read from a module-level
# IDENTITIES dict (older heterogeneous shapes); table stands alone for these.
_MODULES_WITHOUT_IDENTITIES = frozenset({2, 3, 5, 6, 7, 8, 12})


def _discover_protocol_versions(repo_root: Path) -> list[int]:
    ops_dir = repo_root / "apps" / "ops"
    versions = []
    for path in ops_dir.iterdir():
        match = _PROTOCOL_MODULE_RE.match(path.name)
        if match:
            versions.append(int(match.group(1)))
    return sorted(versions)


def _module_identities(version: int) -> dict[str, tuple[str, str]] | None:
    if version in _MODULES_WITHOUT_IDENTITIES:
        return None
    module = importlib.import_module(f"apps.ops.research_protocol_v{version}")
    identities = getattr(module, "IDENTITIES", None)
    if not isinstance(identities, dict):
        return None
    result: dict[str, tuple[str, str]] = {}
    for key, value in identities.items():
        if isinstance(value, (tuple, list)) and len(value) == 2:
            result[str(key)] = (str(value[0]), str(value[1]))
    return result or None


def _load_legacy_candidates(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / LEGACY_REGISTRY_RELPATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for candidate in payload["candidates"]:
        family = LEGACY_FAMILY_ALIASES[candidate["family"]]
        rows.append(
            {
                "key": candidate["family"],
                "source": candidate["source"],
                "model_version": candidate["model_version"],
                "outcome": "legacy_reject",
                "family": family,
                "legacy_classification": candidate["classification"],
            }
        )
    return rows


def build_registry(repo_root: Path) -> dict[str, Any]:
    protocols_block = []
    identity_outcomes: dict[tuple[str, str], str] = {}
    stage_rank = {
        "provider_blocked": 0,
        "not_opened": 0,
        "forward_data_candidate": 0,
        "pre_registered": 0,
        "legacy_reject": 1,
        "development_rejected": 1,
        "development_passed_not_advanced": 1,
        "superseded_by_later_protocol": 1,
        "insufficient_evidence": 1,
        "confirmation_rejected": 2,
        "confirmation_passed_paper_shadow": 3,
    }
    for entry in PROTOCOLS:
        candidates = []
        for cand in entry["candidates"]:
            family = cand["family"] or entry["family"]
            if family not in FAMILIES:
                raise ValueError(f"unknown family {family!r} in protocol v{entry['protocol']}")
            if cand["outcome"] not in OUTCOMES:
                raise ValueError(
                    f"unknown outcome {cand['outcome']!r} in protocol v{entry['protocol']}"
                )
            row = {
                "key": cand["key"],
                "source": cand["source"],
                "model_version": cand["model_version"],
                "family": family,
                "outcome": cand["outcome"],
            }
            candidates.append(row)
            ident = (cand["source"], cand["model_version"])
            prev = identity_outcomes.get(ident)
            if prev is None or stage_rank[cand["outcome"]] >= stage_rank[prev]:
                identity_outcomes[ident] = cand["outcome"]
        protocols_block.append(
            {
                "protocol": entry["protocol"],
                "default_family": entry["family"],
                "mechanism": entry["mechanism"],
                "candidates": sorted(candidates, key=lambda c: c["key"]),
            }
        )
    legacy_rows = _load_legacy_candidates(repo_root)
    for row in legacy_rows:
        ident = (row["source"], row["model_version"])
        identity_outcomes.setdefault(ident, row["outcome"])

    unique_outcomes = list(identity_outcomes.values())
    totals = {
        "protocol_count": len(PROTOCOLS),
        "legacy_candidate_count": len(legacy_rows),
        "candidate_rows": sum(len(p["candidates"]) for p in protocols_block) + len(legacy_rows),
        "unique_identities": len(identity_outcomes),
        "unique_identities_pnl_opened": sum(
            1 for outcome in unique_outcomes if outcome in PNL_OPENED_OUTCOMES
        ),
        "unique_identities_provider_blocked": sum(
            1 for outcome in unique_outcomes if outcome == "provider_blocked"
        ),
        "survivors_paper_shadow": sum(
            1 for outcome in unique_outcomes if outcome == "confirmation_passed_paper_shadow"
        ),
        "confirmation_opened": sum(
            1
            for outcome in unique_outcomes
            if outcome in {"confirmation_rejected", "confirmation_passed_paper_shadow"}
        ),
    }
    families_block = {
        family_id: dict(sorted(meta.items())) for family_id, meta in sorted(FAMILIES.items())
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": AS_OF,
        "adr": "docs/decisions/014-research-program-v2.md",
        "families": families_block,
        "protocols": sorted(protocols_block, key=lambda p: p["protocol"]),
        "legacy_candidates": sorted(legacy_rows, key=lambda r: r["source"]),
        "totals": totals,
    }


def check_registry(repo_root: Path) -> list[str]:
    errors: list[str] = []
    table_versions = {entry["protocol"] for entry in PROTOCOLS}
    module_versions = set(_discover_protocol_versions(repo_root))
    for missing in sorted(module_versions - table_versions):
        errors.append(
            f"apps/ops/research_protocol_v{missing}.py has no PROTOCOLS entry; "
            "register its mechanism family per ADR-014 §3.4 before data access"
        )
    for stale in sorted(table_versions - module_versions):
        errors.append(f"PROTOCOLS entry v{stale} has no matching protocol module")
    for entry in PROTOCOLS:
        version = entry["protocol"]
        if version not in module_versions:
            continue
        identities = _module_identities(version)
        if identities is None:
            continue
        table_idents = {(c["source"], c["model_version"]) for c in entry["candidates"]}
        module_idents = set(identities.values())
        if table_idents != module_idents:
            errors.append(
                f"protocol v{version}: registry identities drifted from module IDENTITIES "
                f"(table-only={sorted(table_idents - module_idents)}, "
                f"module-only={sorted(module_idents - table_idents)})"
            )
    registry_path = repo_root / REGISTRY_RELPATH
    if not registry_path.exists():
        errors.append(f"{REGISTRY_RELPATH.as_posix()} is missing; run --write")
    else:
        committed = json.loads(registry_path.read_text(encoding="utf-8"))
        if committed != build_registry(repo_root):
            errors.append(f"{REGISTRY_RELPATH.as_posix()} is stale; run --write and commit")
    return errors


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root with pyproject.toml not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the registry JSON")
    group.add_argument("--check", action="store_true", help="validate table, modules, and JSON")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = args.repo_root or _find_repo_root()
    if args.write:
        registry = build_registry(repo_root)
        path = repo_root / REGISTRY_RELPATH
        path.write_text(json.dumps(registry, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"wrote {path.as_posix()}")
        return 0
    errors = check_registry(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("registry check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

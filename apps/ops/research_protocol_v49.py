"""Contract for Phase 2 Alpha Research Protocol v49 (multi-factor panel ridge).

First protocol pre-registered under ADR-014 (Gates v2, mechanism-family
orthogonality). Family: ``multifactor_ml`` (backlog B1). The hypothesis is that
the *combination* of the program's already-snapshotted point-in-time factors
carries conditional information about next-day BTC returns that no single
factor carried on its own (single-factor timing failed across v2-v48).

Frozen before any factor VALUE is opened:

- the exact 17 archived factor files (dev + confirmation snapshots, SHA256
  pinned below; file hashes and header/coverage metadata were the only reads
  performed before this freeze);
- the official Binance Vision spot 1d closes source used for labels,
  execution, and benchmarks;
- feature construction, model class, hyperparameter grid, walk-forward
  scheme, evaluation windows, cost scenarios, and Gates v2 thresholds.

Orthogonality declaration (ADR-014 §3.4): every sealed single-factor rule
mapped ONE series through a fixed short-window condition. This candidate
learns a cross-factor conditional expectation with signed output; it profits
only when factor combinations predict next-day returns, a state no member of
the saturated ``external_index_relief`` family expresses. It reuses archived
inputs but not any sealed rule's condition, threshold, or identity.

Directional declaration: the model emits signed scores; execution in this
protocol is spot long/flat only (paper-stage venue parity). The short half is
deferred to a separate ``two_sided_regime`` study (backlog B4).

Weekend coverage: external factors publish on their source calendars and are
forward-filled (max 7 calendar days) after their point-in-time
``available_at`` stamps; BTC-native features update 24/7. Weekend positions
therefore carry Friday-aged external information by construction.

Sealed protocols are unaffected. The 2026-09..2027-01 future blind stays
sealed. No SignalEvent writes, no SourcePolicy changes, no live-path impact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "research.protocol.v49.v1"
MECHANISM_FAMILY = "multifactor_ml"

IDENTITIES = {
    "panel_ridge": (
        "freqai_panel_ridge_v1",
        "panel17-ridge-mwf-oos2020h2-v1",
    ),
}

SYMBOL = "BTCUSDT"
VENUE = "BINANCE"
TRADE_SIZE_BTC = 0.001

# Archived point-in-time factor snapshots (paths relative to the repo root on
# the research host). SHA256 values pinned at freeze; the qualify step fails
# closed on any mismatch. ``value_column`` is the factor value; ``available_at``
# in each file is the point-in-time availability stamp written by the sealed
# source protocol and already encodes that source's publication lag.
FACTOR_SOURCES: dict[str, dict[str, str]] = {
    "gvz": {
        "dev_path": "data/research-v7/factors/gvz.csv",
        "dev_sha256": "0cbe771bf77b486035ce13374a51597ac6e20bb576f81ddb3f765a717dc9b9f1",
        "conf_path": "data/research-v8/factors/gvz.csv",
        "conf_sha256": "9a15a24f8ae10f0c05f4ce72249dfe50e927dd3e3d60e38e536c699c963eb055",
        "value_column": "vol_close",
    },
    "vxn": {
        "dev_path": "data/research-v40/factors/vxn_development.csv",
        "dev_sha256": "7799ae0cf6640bcc9a74f837b9793fd6495703dfc4025af5b87d25e568b8400a",
        "conf_path": "data/research-v40/factors/vxn_confirmation.csv",
        "conf_sha256": "ad0926340f51f3d25116fd8ab1d626fce5bca7ed312663eaf1489651343e69f1",
        "value_column": "index_value",
    },
    "vxd": {
        "dev_path": "data/research-v19/factors/vxd.csv",
        "dev_sha256": "cdd61441e040aba9a0dd4fdd03b9f04ba490b7fca292e6ad2a9a8af49a16296e",
        "conf_path": "data/research-v19/confirmation/factors/vxd.csv",
        "conf_sha256": "a8a12efafb7454c7125f7b59d2ca110695fe15179be7caf6b1de801922b414e6",
        "value_column": "vol_close",
    },
    "vxgog": {
        "dev_path": "data/research-v30/factors/vxgog.csv",
        "dev_sha256": "a7ffaaf312285f5bc80d230993cafbb16dedaf702939991c2381fe189b06cca7",
        "conf_path": "data/research-v30/confirmation/factors/vxgog.csv",
        "conf_sha256": "ac94a8e2e38af5a5d7044ed0dd018b878418598109ecef6bb5e4abaec0f0e487",
        "value_column": "index_value",
    },
    "vix6m": {
        "dev_path": "data/research-v35/factors/vix6m_development.csv",
        "dev_sha256": "7287fe5949a11eed1d970a794c4a5e8d260fedaa0eaf23e38b443f604c0d5096",
        "conf_path": "data/research-v42/factors/vix6m_confirmation.csv",
        "conf_sha256": "4b58a73f78cd19f09ebdb7ae457fb533eab949a0cbf243bf4c0278e0a7dd3c20",
        "value_column": "index_value",
    },
    "vix1y": {
        "dev_path": "data/research-v35/factors/vix1y_development.csv",
        "dev_sha256": "effd501235910644a76ab350520451d676783483c5db4da40a01b5358866ad70",
        "conf_path": "data/research-v35/factors/vix1y_confirmation.csv",
        "conf_sha256": "ba7d92f721abe7251e40829ffdda407097e551274c5ba7214abb4e677964edc6",
        "value_column": "index_value",
    },
    "cor1m": {
        "dev_path": "data/research-v22/factors/cor1m.csv",
        "dev_sha256": "2c37e73c2e9659d238283623047f4507e0ace1da197c747832b9938c06fec71c",
        "conf_path": "data/research-v22/confirmation/factors/cor1m.csv",
        "conf_sha256": "17fc14e0ddd4616aa7e6ae60b22fb0fa4fdda78ef67d786de27d119e847f4708",
        "value_column": "index_value",
    },
    "cor1y": {
        "dev_path": "data/research-v33/factors/cor1y-development-factors.csv",
        "dev_sha256": "341cb294d0de08e1bd0e38bbf9414aea961ee804564665883db531cb3923c92b",
        "conf_path": "data/research-v33/confirmation/factors/cor1y.csv",
        "conf_sha256": "874e33b13a959a0e932fb566221f844e53508df938cf9e4015d1fa3b535815d0",
        "value_column": "index_value",
    },
    "fvx": {
        "dev_path": "data/research-v34/factors/fvx-development-factors.csv",
        "dev_sha256": "434e73a54e103149d6e2d7f64bd17fd66e6c5c68ddf806afe599cf980025574d",
        "conf_path": "data/research-v34/factors/fvx-confirmation-factors.csv",
        "conf_sha256": "b715f9f9ca835619f1d303a312c21a0fd3b86bc7155c4c34b4662cd613ae925b",
        "value_column": "index_value",
    },
    "ofr_safe_asset": {
        "dev_path": "data/research-v20/factors/fsi.csv",
        "dev_sha256": "f0f112171d8f442a24da106db80320a9856f4f5f285289f4009d73de62828c72",
        "conf_path": "data/research-v20/confirmation/factors/safe_asset.csv",
        "conf_sha256": "0c258762f65fa62dc579c12d8294f2b1b244e1dc4ccb935859490aedba826a2e",
        "value_column": "safe_asset_stress",
    },
    "vpn": {
        "dev_path": "data/research-v36/factors/vpn_development.csv",
        "dev_sha256": "66f5ee4f7fa748ade197aa5238b1db2009538644fb3f34a3aa091f915a29bbdc",
        "conf_path": "data/research-v36/factors/vpn_confirmation.csv",
        "conf_sha256": "5099f4a8fb7d4142954fa2fb31ea12011737acbb7dd3ce43499e4f844196272e",
        "value_column": "index_value",
    },
    "lovol": {
        "dev_path": "data/research-v39/factors/lovol_development.csv",
        "dev_sha256": "5bf0999059132c10fa5220b0e19b3d9ab0b4e2352d394567be3185bd40ef70f4",
        "conf_path": "data/research-v39/factors/lovol_confirmation.csv",
        "conf_sha256": "c0f1ec35d4788c7967e462ec802b68c835e7f1e53a48af0370ddd08c1e718b43",
        "value_column": "index_value",
    },
    "bxn": {
        "dev_path": "data/research-v37/factors/bxn_development.csv",
        "dev_sha256": "a303103c6463b8f588d95b53c5f07a81fc52ac7f8aad4fdfd11c4964291bc7e4",
        "conf_path": "data/research-v37/factors/bxn_confirmation.csv",
        "conf_sha256": "7ca08aab6c058b56de937ea3dc4750b519e8c904f4f70c414298a276982ef75e",
        "value_column": "index_value",
    },
    "cll": {
        "dev_path": "data/research-v38/factors/cll_development.csv",
        "dev_sha256": "d16dfc6a4cc43a35495e92be6757d23aca01538b9dc03c184b4fdc9deb588519",
        "conf_path": "data/research-v38/factors/cll_confirmation.csv",
        "conf_sha256": "d25e3bfcf8ccc0a41e73f166f5c36f0254160c8321d8c9610a2e158dd7188899",
        "value_column": "index_value",
    },
    "tvl_all_chains": {
        "dev_path": "data/research-v25/factors/all_chains.csv",
        "dev_sha256": "33c4433621c9205f278df1537ccf602906db87e10d23ff5305a3aee64be16067",
        "conf_path": "data/research-v25/confirmation/factors/all_chains.csv",
        "conf_sha256": "32aa36e6e3fce0ea5742611b68554307fa7389909f3c81ef8e4a98b7829d34e7",
        "value_column": "tvl",
    },
    "btc_premium": {
        "dev_path": "data/research-v46/factors/btc_prem_diff5_negative_development.csv",
        "dev_sha256": "ed1aea09fedf95d7710d5058e5383847fabc3a2747ba10f47e41ac4c274ef186",
        "conf_path": "data/research-v46/factors/btc_prem_diff5_negative_confirmation.csv",
        "conf_sha256": "1c322dc5a7076b5f360f6e2ec2d8d49d868d987de730bab37b21d9094df96bc9",
        "value_column": "index_value",
    },
    "btc_basis": {
        "dev_path": "data/research-v48/factors/btc_basis_below_ma10_development.csv",
        "dev_sha256": "aa1dc7871e9751278e35f78794fb9f61156adfde6dc100ce2950ee066b68c069",
        "conf_path": "data/research-v48/factors/btc_basis_below_ma10_confirmation.csv",
        "conf_sha256": "4b3161271f1230a7abd77212c524441c07837d09ef1c14d47fb621ada76c241d",
        "value_column": "index_value",
    },
}

# Labels, execution prices, benchmarks, and the two BTC-native features come
# from the Binance Vision official spot 1d kline archives (CHECKSUM-verified,
# one GET per month file) via apps.ops.research_meta_analysis.fetch_closes.
CLOSES_SOURCE = {
    "provider": "Binance Vision spot monthly 1d klines",
    "symbol": SYMBOL,
    "start_month": "2019-12",
    "end_month": "2025-12",
    "csv_path": "data/research-v49/closes/btcusdt-1d-closes-2019-12-2025-12.csv",
}

FEATURE_SPEC = {
    "panel_calendar": "BTC UTC daily dates from the closes CSV",
    "availability_rule": (
        "panel date D uses the last factor row with available_at <= end of day D "
        "(D+1T00:00:00Z), forward-filled at most 7 calendar days, else NaN"
    ),
    "external_transform": "5-panel-day difference, then expanding z-score (min 60 obs)",
    "native_features": {
        "btc_mom20": "20-day log return of close, expanding z-score (min 60 obs)",
        "btc_rvol20": "std of daily log returns over 20 days, expanding z-score (min 60 obs)",
    },
    "prediction_row_nan_policy": "NaN features are imputed to 0 (z-neutral) at prediction",
    "training_row_policy": "training rows require label and at least 10 non-NaN features",
}

MODEL_SPEC = {
    "model": "ridge regression, closed form, intercept unpenalized",
    "label": "next-day log return of BTCUSDT spot close",
    "alpha_grid": [1.0, 10.0, 100.0, 1000.0, 10000.0],
    "refit_schedule": "calendar-monthly, expanding training window starting 2020-01-01",
    "min_train_months": 6,
    "alpha_selection": (
        "nested inside development only: run the identical walk-forward for every "
        "alpha in the grid over the development OOS window; select the alpha with "
        "the highest base net PnL (ties -> larger alpha); the selected alpha is "
        "frozen for confirmation with no further tuning"
    ),
    "signal_rule": "predicted next-day return > 0 -> long next day, else flat",
}

WINDOWS = {
    "training_start": "2020-01-01",
    "development_oos": ("2020-07-01", "2022-12-31"),
    "confirmation": ("2023-01-01", "2025-12-31"),
    "future_blind": ("2026-09-01", "2027-01-31"),
}

COST_SCENARIOS = {
    "gross": {"fee_bps_per_fill": 0.0, "slippage_bps_per_fill": 0.0},
    "base": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 2.0},
    "stress": {"fee_bps_per_fill": 10.0, "slippage_bps_per_fill": 5.0},
}

# ADR-014 §4 Gates v2. Months thresholds are the 50% breadth rule applied to
# each window's month count (30 OOS months in development, 36 in confirmation).
GATES_V2 = {
    "development": {
        "base_net_pnl_gt": 0.0,
        "stress_net_pnl_gt": 0.0,
        "positive_calendar_years_at_least": 2,
        "calendar_years_total": 3,
        "positive_calendar_months_at_least": 15,
        "calendar_months_total": 30,
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
    "null": (
        "random Markov long/flat daily timing on the same window and costs; "
        "exposure fraction ~ U(clip(f-0.15), clip(f+0.15)) and mean hold ~ "
        "logU(max(1.5, h/2), 2h) where f/h are the candidate's realized "
        "time-in-market fraction and mean holding days"
    ),
    "p_value": "(1 + #{null base PnL >= candidate base PnL}) / (n_trials + 1)",
}

BOUNDARIES = {
    "writes_signal_events": False,
    "mutates_source_policy": False,
    "opens_future_blind": False,
    "touches_live_path": False,
    "reopens_sealed_protocols": False,
}


def contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mechanism_family": MECHANISM_FAMILY,
        "identities": {k: list(v) for k, v in sorted(IDENTITIES.items())},
        "symbol": SYMBOL,
        "venue": VENUE,
        "trade_size_btc": TRADE_SIZE_BTC,
        "factor_sources": FACTOR_SOURCES,
        "closes_source": CLOSES_SOURCE,
        "feature_spec": FEATURE_SPEC,
        "model_spec": MODEL_SPEC,
        "windows": {k: list(v) if isinstance(v, tuple) else v for k, v in WINDOWS.items()},
        "cost_scenarios": COST_SCENARIOS,
        "gates_v2": GATES_V2,
        "bootstrap_spec": BOOTSTRAP_SPEC,
        "boundaries": BOUNDARIES,
    }


def contract_sha256() -> str:
    canonical = json.dumps(contract_payload(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def validate_contract() -> list[str]:
    errors: list[str] = []
    for key, spec in FACTOR_SOURCES.items():
        for field in ("dev_path", "dev_sha256", "conf_path", "conf_sha256", "value_column"):
            if not spec.get(field):
                errors.append(f"{key}: missing {field}")
        for field in ("dev_sha256", "conf_sha256"):
            value = spec.get(field, "")
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                errors.append(f"{key}: {field} is not a lowercase sha256 hex digest")
    if len(FACTOR_SOURCES) != 17:
        errors.append(f"expected 17 factor sources, found {len(FACTOR_SOURCES)}")
    dev = WINDOWS["development_oos"]
    conf = WINDOWS["confirmation"]
    if not dev[1] < conf[0]:
        errors.append("development window must end before confirmation begins")
    if (
        GATES_V2["development"]["positive_calendar_months_at_least"] * 2
        != GATES_V2["development"]["calendar_months_total"]
    ):
        errors.append("development month gate must be the 50% breadth rule")
    if (
        GATES_V2["confirmation"]["positive_calendar_months_at_least"] * 2
        != GATES_V2["confirmation"]["calendar_months_total"]
    ):
        errors.append("confirmation month gate must be the 50% breadth rule")
    return errors

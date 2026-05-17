# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T05:34:51Z
- **Operator**: nishiki
- **Decision**: PROMOTE
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `freqai_linear_v1`
- model_version: `linear-mom-train20240105`

## 2. Current vs target policy

- current_stage: `paper_shadow`
- target_stage: `paper_simulated`
- current_policy: dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None
- target_policy: dry_run=False, position_pct_multiplier=0.2, min_confidence_override=None
- policy_diff:
  - dry_run: True -> False
- bundle_policy_matches_current: True
- bundle_policy_mismatches:
- (bundle policy matches current_policy)

## 3. Bundle path / manifest fingerprint

- bundle_dir: `data/paper/20260517-052512Z-36feef84`
- run_id: `20260517-052512Z-36feef84`
- manifest_sha256: `9d813db2a77adf39cb974f5e6b7b3e04b2f701f930757edf132d97fd3ddb13c0`
- git_commit: `35a35c26da81049302af2edcf904ac47a8c286ba`
- git_dirty: False
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 4. Signals & lineage

- signal_rows: 595
- session_days_inclusive: 60
- accepted: 595
- skipped: 0
- dry_run: 595
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 436, "target_short": 159}`
- lineage reason counts: `{"dry_run": 595}`

## 5. Execution outcome

- totals: `{"events": 595, "fills": 0, "iterations": 86400, "orders": 0, "positions": 0}`
- PnL by currency: `{"USDT": 0.0}`
- max_drawdown_pct: `{"USDT": 0.0}`
- max_drawdown_abs: `{"USDT": 0.0}`
- kill_switch_fired: False
- missing_metrics: none

## 6. Runtime hygiene

- heartbeat_count: 86400
- restart_sequence: 0
- previous_run_id: none
- runtime_data_gaps: 0

## 7. Conclusion

- review_blockers: none
- promotion_gate_blockers: none
- decision: **PROMOTE**
- decision_allowed: **yes**
- decision_reasons:
- promote_gates_passed

### Rationale

First deliberate promote of freqai_linear_v1 / linear-mom-train20240105 from paper_shadow (SourcePolicy(dry_run=True, position_pct_multiplier=0.2)) to paper_simulated (SourcePolicy(dry_run=False, position_pct_multiplier=0.2)). Evidence bundle: v8 paper-shadow bundle data/paper/20260517-052512Z-36feef84 (manifest 9d813db2…). ADR-007 §2.5 paper_shadow → paper_simulated gate review: (a) sample size: 595 signals over 60 inclusive days — far past the >=50 OR >=7 threshold; (b) bundle is clean: git_dirty=false, runtime heartbeat_count=86400, poll_count=86400, restart_sequence=0, data_gap_count=0, no kill-switch / signal_lag / unauthorized / expired / data_gap rejections; (c) signal-side hold-out evidence: Jan-vs-Feb distributional comparison shows near-identical density (9.94 vs 9.90 / day), long-share (0.7305 vs 0.7352), score quantiles, and confidence quantiles — see docs/progress/phase-2-signal-source-baselines.md v8 for the table; (d) policy_diff is explicit (only dry_run flips, multiplier stays at 0.2 which is the paper_simulated stage cap); (e) reproducibility chain v3/v6/v7/v8 preserves the same model_version, features_hash (sha256:885207ac…), train_rows (7181), and train_until (2024-01-05T23:59). Multiplier is held at the cap (0.2) and not raised; min_confidence_override stays None (cannot loosen strategy default). What is NOT yet evidenced and is exactly what this promote unlocks: return-side numbers (Win Rate / expectancy / max drawdown) — paper_simulated is the stage that produces them. Risk if promote is wrong: the daily 5% kill-switch is intact, max position is 5% × 0.2 = 1% of starting balance per signal, and trade size is 0.001 BTC; the simulated execution account does not touch any real exchange. After this retro is applied, the next paper bundle (v9) for this source must be generated with --policy-position-pct-multiplier 0.2 and WITHOUT --policy-dry-run. paper_simulated → testnet_canary is Phase 3 territory and is hard-blocked by the promotion_review tool, so this retro is the highest stage this source can reach in Phase 2.

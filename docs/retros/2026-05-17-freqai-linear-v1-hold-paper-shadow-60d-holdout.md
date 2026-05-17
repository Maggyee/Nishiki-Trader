# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T05:26:26Z
- **Operator**: nishiki
- **Decision**: HOLD
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `freqai_linear_v1`
- model_version: `linear-mom-train20240105`

## 2. Current vs target policy

- current_stage: `paper_shadow`
- target_stage: `paper_shadow`
- current_policy: dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None
- target_policy: dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None
- policy_diff:
  - (no fields differ — policies are identical)
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
- decision: **HOLD**
- decision_allowed: **yes**
- decision_reasons:
- hold_gates_passed

### Rationale

freqai_linear_v1 / linear-mom-train20240105 now has 595 SignalEvents over 60 inclusive catalog-polling days (2024-01-01..2024-02-29): 308 in January (in-sample month, train_until=2024-01-05T23:59) and 287 in February (fully held-out month, never seen by the trainer). Both halves of the ADR-007 §2.5 OR-gate are far past threshold: 595 >= 50 signals AND 60 >= 7 days. Bundle is clean: git_dirty=false, no review blockers, runtime heartbeat_count=86400, poll_count=86400, restart_sequence=0, data_gap_count=0, no kill-switch / signal_lag / unauthorized / expired rejections. Hold-out distributional comparison Jan vs Feb (ad-hoc analysis from signal_lineage joined to signals.db — see docs/progress/phase-2-signal-source-baselines.md v8 for full table): signal density 9.94/day vs 9.90/day; long_share 0.7305 vs 0.7352; score p50 buy +0.2342 / +0.2342, sell -0.2438 / -0.2332; score abs_mean buy 0.2817 / 0.2785, sell 0.2967 / 0.2736; confidence mean buy 0.5647 / 0.5627, sell 0.5737 / 0.5597. Signal-side distributions are stable across the train month and the held-out month — no evidence of systematic regime breakage. What is still missing for a promote-to-paper-simulated decision is *return-side* evidence (Win Rate, expectancy, Sharpe, max drawdown), which dry-run paper-shadow cannot produce: ADR-007 §2.5 paper_simulated is the stage that produces fills/PnL precisely so the next review has return-side numbers. Decision: hold at paper_shadow this session — the source meets every signal-side and runtime gate the §2.6 review can check from a dry-run bundle, and the next deliberate human action is to flip dry_run=False under SourcePolicy(position_pct_multiplier=0.2) and run a paper_simulated bundle for at least the same 60-day window. That promote should be its own retro.

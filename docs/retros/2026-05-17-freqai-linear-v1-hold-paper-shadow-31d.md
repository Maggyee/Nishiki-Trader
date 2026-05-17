# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T05:14:46Z
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

- bundle_dir: `data/paper/20260517-051417Z-9afb2cd1`
- run_id: `20260517-051417Z-9afb2cd1`
- manifest_sha256: `218e3b0c75db85b5c6a90f692ee270d9d1de5b1aed58bab0e2fbc8015b541035`
- git_commit: `52a01ba1413e2735b5a4eaafa9739e7d429bda48`
- git_dirty: False
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 4. Signals & lineage

- signal_rows: 308
- session_days_inclusive: 31
- accepted: 308
- skipped: 0
- dry_run: 308
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 225, "target_short": 83}`
- lineage reason counts: `{"dry_run": 308}`

## 5. Execution outcome

- totals: `{"events": 308, "fills": 0, "iterations": 44640, "orders": 0, "positions": 0}`
- PnL by currency: `{"USDT": 0.0}`
- max_drawdown_pct: `{"USDT": 0.0}`
- max_drawdown_abs: `{"USDT": 0.0}`
- kill_switch_fired: False
- missing_metrics: none

## 6. Runtime hygiene

- heartbeat_count: 44640
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

freqai_linear_v1 / linear-mom-train20240105 now emits 308 SignalEvents over 31 inclusive catalog-polling days (2024-01-01..2024-01-31). Both halves of the ADR-007 §2.5 OR-gate are satisfied: 308 >= 50 signals AND 31 >= 7 days. Bundle is clean: git_dirty=false, no review blockers, runtime heartbeat_count=44640, poll_count=44640, restart_sequence=0, data_gap_count=0, no kill-switch / signal_lag / unauthorized / expired rejections. Despite that, ADR-007 §2.6 still requires explicit human review before disabling dry_run, and the source has not yet been benchmarked on a sample-out-of-sample window (e.g., 2024-02 forward). The 308-signal bundle is the right base for a future promote review, but on its own it is in-sample model fit on January 2024; we do not have hold-out evidence that the model continues to predict above noise on different market regimes. Decision: hold at paper_shadow with the same SourcePolicy(dry_run=True, position_pct_multiplier=0.2). Plan to next review: backfill at least one more month (2024-02 or later) using the same train_until=2024-01-05T23:59 boundary, run paper_runner over the truly held-out window, and only consider promote if Win Rate / PnL on the hold-out month is consistent with January and review blockers stay at zero.

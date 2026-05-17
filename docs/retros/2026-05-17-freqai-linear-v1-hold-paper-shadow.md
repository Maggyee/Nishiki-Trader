# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T05:03:50Z
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

- bundle_dir: `data/paper/20260517-050320Z-f5e13cda`
- run_id: `20260517-050320Z-f5e13cda`
- manifest_sha256: `88164be1024d96f706f27d53e22933a7cbab6eedd576bb0a7274307ccc95eebe`
- git_commit: `3ee958c0878843053b7294346b968df616043fd6`
- git_dirty: False
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 4. Signals & lineage

- signal_rows: 7
- session_days_inclusive: 7
- accepted: 7
- skipped: 0
- dry_run: 7
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 7}`
- lineage reason counts: `{"dry_run": 7}`

## 5. Execution outcome

- totals: `{"events": 7, "fills": 0, "iterations": 10080, "orders": 0, "positions": 0}`
- PnL by currency: `{"USDT": 0.0}`
- max_drawdown_pct: `{"USDT": 0.0}`
- max_drawdown_abs: `{"USDT": 0.0}`
- kill_switch_fired: False
- missing_metrics: none

## 6. Runtime hygiene

- heartbeat_count: 10080
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

freqai_linear_v1 emitted 7 SignalEvents over 7 catalog-polling days. ADR-007 §2.5 paper_shadow → paper_simulated requires ≥7 days OR ≥50 signals; this run satisfies the days half but the absolute sample size (7) is far below the signal half. The shadow bundle itself is clean: no review blockers, runtime data_gaps=0, restart_sequence=0, no kill-switch, no expired/unauthorized/lagging signals. ADR-007 §2.6 still requires explicit human review before disabling dry_run, and 7 dry-run lineage rows over 1 week is too thin a base to justify simulated orders. Decision: hold at paper_shadow. Plan to next review: extend the catalog window to ≥30 days or shorten the model horizon so the source accumulates ≥50 shadow signals; rerun this review once the sample size threshold is also met. Until then freqai_linear_v1 stays SourcePolicy(dry_run=True, position_pct_multiplier=0.2).

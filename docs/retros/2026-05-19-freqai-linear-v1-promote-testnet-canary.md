# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-19T01:21:25Z
- **Operator**: nishiki
- **Decision**: PROMOTE
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `freqai_linear_v1`
- model_version: `linear-mom-train20240105`

## 2. Current vs target policy

- current_stage: `paper_simulated`
- target_stage: `testnet_canary`
- current_policy: dry_run=False, position_pct_multiplier=0.2, min_confidence_override=None
- target_policy: dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None
- policy_diff:
  - position_pct_multiplier: 0.2 -> 0.1
- bundle_policy_matches_current: True
- bundle_policy_mismatches:
- (bundle policy matches current_policy)

## 3. Bundle path / manifest fingerprint

- bundle_dir: `data/paper/20260517-053502Z-37b99b3f`
- run_id: `20260517-053502Z-37b99b3f`
- manifest_sha256: `fa344a5534c220a0a0547f58f069394921399fd21def505faaf3c978d04e6efb`
- git_commit: `a9a35d46251b5452e83e6ed9a175f143a63b9bc0`
- git_dirty: False
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 3a. Phase 3 evidence paths

- paper_simulated_retro_path: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md`
- testnet_runbook_signoff_path: `docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md`

## 4. Signals & lineage

- signal_rows: 595
- session_days_inclusive: 60
- accepted: 595
- skipped: 0
- dry_run: 0
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 436, "target_short": 159}`
- lineage reason counts: `{"": 273, "already_target_long": 299, "already_target_short": 23}`

## 5. Execution outcome

- totals: `{"events": 595, "fills": 545, "iterations": 86400, "orders": 545, "positions": 273}`
- PnL by currency: `{"USDT": 5.007578000004287}`
- max_drawdown_pct: `{"USDT": -1.0034972341445869e-05}`
- max_drawdown_abs: `{"USDT": -1.003526000014972}`
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

First testnet_canary promote for freqai_linear_v1 / linear-mom-train20240105. paper_simulated evidence: v9 bundle 20260517-053502Z-37b99b3f, 60d BTCUSDT 1m, 545 fills/545 orders 1:1 with signal_id traceability, 273 positions, kill_switch=0, data_gap=0, manifest git_dirty=false. Testnet runbook signoff: docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md (ADR-008 §6.6 6h soak, shutdown_reason=max_duration, all 9 §5.4 alert paths silent, watchdog 714 healthy ticks 0 flatten_invoked, Nautilus ERROR=0). target_policy halves position_pct_multiplier from 0.2 to 0.1 for first canary; dry_run stays False; min_confidence_override unchanged.

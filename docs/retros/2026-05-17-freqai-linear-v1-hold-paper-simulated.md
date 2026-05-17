# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T05:35:56Z
- **Operator**: nishiki
- **Decision**: HOLD
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `freqai_linear_v1`
- model_version: `linear-mom-train20240105`

## 2. Current vs target policy

- current_stage: `paper_simulated`
- target_stage: `paper_simulated`
- current_policy: dry_run=False, position_pct_multiplier=0.2, min_confidence_override=None
- target_policy: dry_run=False, position_pct_multiplier=0.2, min_confidence_override=None
- policy_diff:
  - (no fields differ — policies are identical)
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
- decision: **HOLD**
- decision_allowed: **yes**
- decision_reasons:
- hold_gates_passed

### Rationale

First record of freqai_linear_v1 / linear-mom-train20240105 at paper_simulated stage, immediately after the promote retro authorized SourcePolicy(dry_run=False, position_pct_multiplier=0.2). Evidence bundle: v9 simulated paper bundle data/paper/20260517-053502Z-37b99b3f (manifest fa344a55…). Sanity checks ALL pass: orders=545, fills=545 (perfect 1:1 mapping, no orphan orders), positions=273, signal_lineage=595 (all 595 signals accounted for), account_balances=86400 (one per bar). ADR-002 §4.1 traceability: every order and every fill carries a non-empty signal_id (0 missing on each); positions has signal_ids list. Runtime hygiene: heartbeat_count=86400, poll_count=86400, processed_until_ns=1709251140000000000, restart_sequence=0, data_gap_count=0, git_dirty=false. Risk: no kill-switch fires, no signal_lag / unauthorized / expired / data_gap rejections. Lineage decisions: target_long×436 + target_short×159 = 595; reasons split as 273 first-position openings (empty reason), 299 already_target_long, 23 already_target_short — strategy correctly skips flipping when already in the desired side. First return-side numbers ever recorded for this source on paper_simulated: PnL (total) = +5.0076 USDT (+0.005% on 100000 USDT starting balance over 60 inclusive catalog-polling days); Win Rate = 0.5551 (55.5%); Expectancy = +0.0186 USDT/trade; Max Drawdown (Pct) = -1.00e-5 (0.001% peak-to-trough); Max Drawdown (Abs) = -.003. Decision: hold at paper_simulated. The next stage paper_simulated → testnet_canary is hard-blocked by the promotion_review tool because Phase 3 has not yet delivered the prerequisite ADRs (testnet runtime, real-exchange-credentials management, emergency flatten / kill workflow, restart recovery, alerting). Even setting that aside, ADR-007 §2.5 requires paper_simulated stable for ≥ 7 days plus an explicit Phase 3 testnet runbook before testnet_canary; 60 days of stable simulated runtime exceeds the days half but the runbook half is missing entirely. The +0.0186 USDT/trade expectancy with 55.5% win rate is barely above coin-flip noise and could easily be noise on this fixture; until Phase 3 is in place this is monitored evidence, not promotion evidence. Plan: keep this source running on paper_simulated for accumulated catalog windows; gate the next promote on the Phase 3 risk/runbook ADR (referenced as future work in ADR-007 §4).

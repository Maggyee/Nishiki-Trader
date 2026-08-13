# Promotion review — rule_nasdaq_vol_relief_v2 / cboe-vxn-ohlc5obs-negative-1d-v1

- **Date (UTC)**: 2026-08-13T02:59:57Z
- **Operator**: nishiki
- **Decision**: HOLD
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `rule_nasdaq_vol_relief_v2`
- model_version: `cboe-vxn-ohlc5obs-negative-1d-v1`

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

- bundle_dir: `data/research-v18/paper/20260813-025939Z-ea651f8d`
- run_id: `20260813-025939Z-ea651f8d`
- bundle_kind: `paper`
- manifest_sha256: `507fe79b3f23fc6f0293cddf165d1a1d5790ecdcafd06bdfda10c6decaecfa08`
- git_commit: `4f2c8a48748a49c8a0fba03449f16f603b3f335b`
- git_dirty: False
- policy_evidence_path: `data/research-v18/paper/20260813-025939Z-ea651f8d/run_manifest.json`
- policy_evidence_sha256: `507fe79b3f23fc6f0293cddf165d1a1d5790ecdcafd06bdfda10c6decaecfa08`
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 3a. Phase 3 evidence paths

- paper_simulated_retro_path: `none`
- testnet_runbook_signoff_path: `none`

## 4. Signals & lineage

- signal_rows: 129
- session_days_inclusive: 1014
- accepted: 129
- skipped: 0
- dry_run: 129
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_flat": 65, "target_long": 64}`
- lineage reason counts: `{"dry_run": 129}`

## 5. Execution outcome

- totals: `{"events": 129, "fills": 0, "iterations": 24322, "orders": 0, "positions": 0}`
- PnL by currency: `{"USDT": 0.0}`
- max_drawdown_pct: `{"USDT": 0.0}`
- max_drawdown_abs: `{"USDT": 0.0}`
- kill_switch_fired: False
- missing_metrics: none

## 6. Runtime hygiene

- heartbeat_count: 24322
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

The exact VXN-relief identity passed prospectively frozen 2023-2025 confirmation. The longest contiguous catalog suffix after the separately audited Binance exchange-unavailable hour verifies 129 of 129 SignalEvent v1 rows under the identity-specific dry-run policy with zero orders, fills, schema, authorization, freshness, lag, kill-switch, or data-gap blockers. Historical replay is stage-entry plumbing evidence only; a separate review remains mandatory before paper_simulated.

The formal policy bundle begins at 2023-03-24 14:00 UTC, immediately after
the single exchange-unavailable hour already preserved by the v8 execution
audit. The full-window confirmation bundles retain that discontinuity and
show no order or fill event in it; no bar was synthesized or hidden.

This HOLD authorizes only the exact identity-specific consumer policy
`SourcePolicy(dry_run=True, position_pct_multiplier=0.2,
min_confidence_override=None)` at `paper_shadow`. It does not authorize a
collector schedule, `paper_simulated`, credentials, testnet/live trading, or
future-blind access.

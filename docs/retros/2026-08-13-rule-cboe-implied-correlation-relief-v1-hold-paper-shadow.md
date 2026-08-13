# Promotion review — rule_cboe_implied_correlation_relief_v1 / cboe-cor1m-diff5-negative-lag1d-v1

- **Date (UTC)**: 2026-08-13T04:59:26Z
- **Operator**: nishiki
- **Decision**: HOLD
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `rule_cboe_implied_correlation_relief_v1`
- model_version: `cboe-cor1m-diff5-negative-lag1d-v1`

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

- bundle_dir: `data/research-v22/paper/20260813-045912Z-903c37c0`
- run_id: `20260813-045912Z-903c37c0`
- bundle_kind: `paper`
- manifest_sha256: `a25ce1307533597ced01b1a9d70e7f2ab6133d7740adbda637014bf767c032d2`
- git_commit: `757c191c265d12e160e9b2bd47e9f0ca1666771e`
- git_dirty: False
- policy_evidence_path: `data/research-v22/paper/20260813-045912Z-903c37c0/run_manifest.json`
- policy_evidence_sha256: `a25ce1307533597ced01b1a9d70e7f2ab6133d7740adbda637014bf767c032d2`
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 3a. Phase 3 evidence paths

- paper_simulated_retro_path: `none`
- testnet_runbook_signoff_path: `none`

## 4. Signals & lineage

- signal_rows: 141
- session_days_inclusive: 1014
- accepted: 141
- skipped: 0
- dry_run: 141
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_flat": 70, "target_long": 71}`
- lineage reason counts: `{"dry_run": 141}`

## 5. Execution outcome

- totals: `{"events": 141, "fills": 0, "iterations": 24322, "orders": 0, "positions": 0}`
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

The exact COR1M-relief identity passed its independently frozen 2023-2025 confirmation, but 2025 base PnL was slightly negative and monthly breadth passed exactly at 18/36, so it enters only the strict identity-specific dry-run stage. The longest contiguous catalog suffix after the separately audited Binance exchange-unavailable hour verifies 141 of 141 SignalEvent v1 rows with zero orders, fills, schema, authorization, freshness, lag, kill-switch, or data-gap blockers. Historical replay is stage-entry plumbing evidence only; genuinely forward observations remain zero and a separate ADR-007 review is mandatory before paper_simulated.

The formal policy bundle starts at 2023-03-24 14:00 UTC, immediately after
the single exchange-unavailable hour already preserved by the v8 execution
audit. The full-window confirmation bundles retain that discontinuity and
show no strategy event, order, or fill in it; no bar was synthesized or
hidden.

Zero PnL and drawdown in this review are expected shadow semantics, not return
evidence: `dry_run=True` deliberately prevents every order and fill.

This HOLD authorizes only the exact identity-specific consumer policy
`SourcePolicy(dry_run=True, position_pct_multiplier=0.2,
min_confidence_override=None)` at `paper_shadow`. It does not authorize a
collector schedule, `paper_simulated`, credentials, testnet/live trading, or
future-blind access.

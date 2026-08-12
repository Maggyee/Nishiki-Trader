# Promotion review — rule_us_treasury_volatility_relief_v2 / treasury-nominal10-absdiff5-20-negative-lag2d-v1

- **Date (UTC)**: 2026-08-12T09:37:17Z
- **Operator**: nishiki
- **Decision**: HOLD
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `rule_us_treasury_volatility_relief_v2`
- model_version: `treasury-nominal10-absdiff5-20-negative-lag2d-v1`

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

- bundle_dir: `data/research-v16/paper/20260812-093622Z-bbe531b6`
- run_id: `20260812-093622Z-bbe531b6`
- bundle_kind: `paper`
- manifest_sha256: `87ccdca45dc7fc9410e3e5b58bcaa1ade2f2d14614d5a76c8e4e886a2f81e4c7`
- git_commit: `ca9c731f097c742582a9393c9c48e9ad5ce2e685`
- git_dirty: False
- policy_evidence_path: `data/research-v16/paper/20260812-093622Z-bbe531b6/run_manifest.json`
- policy_evidence_sha256: `87ccdca45dc7fc9410e3e5b58bcaa1ade2f2d14614d5a76c8e4e886a2f81e4c7`
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

The companion full-window bundle is
`data/research-v16/paper/20260812-093438Z-e67c961f` with manifest SHA-256
`6ec96b88948e6e7911fcd79f4ccb8e148af6756025f50c693515bc82bfe80bcb`.
It retains all 159 confirmation signals and the single 2023-03-24 13:00 UTC
catalog discontinuity. That hour exactly matches the previously archived
official-file plus empty-REST response audit, is classified
`exchange_unavailable_not_missing_market_data`, and contains no strategy
event. It was not filled or hidden. The formal policy bundle starts at the
next available hour and uses the longest remaining contiguous suffix so the
generic ADR-007 checker needs no manual gap waiver.

## 3a. Phase 3 evidence paths

- paper_simulated_retro_path: `none`
- testnet_runbook_signoff_path: `none`

## 4. Signals & lineage

- signal_rows: 147
- session_days_inclusive: 1014
- accepted: 147
- skipped: 0
- dry_run: 147
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_flat": 73, "target_long": 74}`
- lineage reason counts: `{"dry_run": 147}`

## 5. Execution outcome

- totals: `{"events": 147, "fills": 0, "iterations": 24322, "orders": 0, "positions": 0}`
- PnL by currency: `{"USDT": 0.0}`
- max_drawdown_pct: `{"USDT": 0.0}`
- max_drawdown_abs: `{"USDT": 0.0}`
- kill_switch_fired: False
- missing_metrics: none

Zero PnL and drawdown are expected shadow semantics, not return evidence:
`dry_run=True` deliberately prevents every order and fill.

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

The exact Treasury-volatility identity passed independently frozen 2023-2025 confirmation. This longest contiguous catalog suffix after the single separately audited Binance exchange-unavailable hour verifies 147/147 SignalEvent v1 rows under the identity-specific dry-run policy with zero orders, fills, schema/auth/freshness/lag/kill-switch/data-gap blockers. Historical replay is stage-entry plumbing evidence only; genuinely forward observations remain 0 and a separate review is required before paper_simulated.

This decision authorizes only the identity-specific consumer policy
`SourcePolicy(dry_run=True, position_pct_multiplier=0.2,
min_confidence_override=None)` at `paper_shadow`. It does not authorize a
collector schedule, `paper_simulated`, testnet, credentials, or live orders.
The 2026-09 through 2027-01 future blind remains sealed.

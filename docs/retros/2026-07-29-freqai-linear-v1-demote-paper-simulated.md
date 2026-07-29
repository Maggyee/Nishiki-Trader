# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-07-29T12:25:40Z
- **Operator**: nishiki
- **Decision**: DEMOTE
- **Decision allowed by gates**: yes

## 1. Source / model

- source: `freqai_linear_v1`
- model_version: `linear-mom-train20240105`

## 2. Current vs target policy

- current_stage: `testnet_canary`
- target_stage: `paper_simulated`
- current_policy: dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None
- target_policy: dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None
- policy_diff:
  - (no fields differ — policies are identical)
- bundle_policy_matches_current: True
- bundle_policy_mismatches:
- (bundle policy matches current_policy)

## 3. Bundle path / manifest fingerprint

- bundle_dir: `data/testnet/20260530-141037Z-6e860b4f`
- run_id: `20260530-141037Z-6e860b4f`
- bundle_kind: `testnet`
- manifest_sha256: `40c1a86106f3af1f9d02da6525db33d0958053135ef9739c1fd179cc45c347ad`
- git_commit: `348ca5b3f79d0ba82dd3e7f732075571a01e7515`
- git_dirty: False
- policy_evidence_path: `docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`
- policy_evidence_sha256: `bd86754b62bc1a7d2eedc9da30482360f4bb73709307a89b5622191fe15bccc3`
- runtime: mode=testnet, data_mode=exchange_ws, order_mode=exchange_testnet

## 3a. Phase 3 evidence paths

- paper_simulated_retro_path: `none`
- testnet_runbook_signoff_path: `none`

## 4. Signals & lineage

- signal_rows: 896
- session_days_inclusive: 1
- accepted: 896
- skipped: 0
- dry_run: 0
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 896}`
- lineage reason counts: `{"": 895, "suppressed_after_same_bar_order_submission": 1}`

## 5. Execution outcome

- totals: `{"account_balances": 451, "events": 896, "fills": 2, "orders": 2, "positions": 1}`
- PnL by currency: `{"USDT": -0.01055}`
- max_drawdown_pct: `{"USDT": null}`
- max_drawdown_abs: `{"USDT": null}`
- kill_switch_fired: False
- missing_metrics: ['max_drawdown_pct', 'max_drawdown_abs']

## 6. Runtime hygiene

- heartbeat_count: 719
- restart_sequence: 0
- previous_run_id: none
- runtime_data_gaps: 0

## 7. Conclusion

- review_blockers: none
- promotion_gate_blockers: none
- decision: **DEMOTE**
- decision_allowed: **yes**
- decision_reasons:
- demote_gates_passed

### Rationale

Human-approved demotion after the 2026-07-10 cost-sensitive alpha review. The frozen 152-day paper evidence is gross +4.873394 USDT but base/stress -24.218490/-31.491462 USDT and contains historical SHORT positions incompatible with the Spot-only/no-margin scope. The locked 2024-08..12 current-reference blind is base/stress -0.522843/-0.580555 USDT with 0/5 base-positive months. The linked signed policy is testnet_canary at dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None. The selected testnet bundle is clean operational evidence (719 heartbeats, no alerts or review blockers, 2 orders/fills, final FLAT, realized PnL -0.01055 USDT), not alpha evidence. Demote to paper_simulated with the same 0.1 multiplier; do not resume testnet, authorize live trading, tune this frozen identity, or reinterpret historical shorts. Any renewed research requires a new source/model identity and fresh pre-registration.

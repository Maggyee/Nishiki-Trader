# Promotion review — freqai_linear_v1 / linear-mom-train20240105

- **Date (UTC)**: 2026-05-17T09:03:02Z
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

- bundle_dir: `data/paper/20260517-090217Z-c1214e6d`
- run_id: `20260517-090217Z-c1214e6d`
- manifest_sha256: `966fc8ac6010592b4f2af5b10d6deb3c63109083f2cfa7e70c83b175b26763a3`
- git_commit: `bfbb7e6cf6bd0bc24863041122ca8494d969e8aa`
- git_dirty: False
- runtime: mode=paper, data_mode=catalog_polling, order_mode=simulated

## 4. Signals & lineage

- signal_rows: 1750
- session_days_inclusive: 121
- accepted: 1750
- skipped: 0
- dry_run: 0
- expired: 0
- unauthorized: 0
- signal_lag: 0
- kill_switch: 0
- data_gap_signals: 0
- lineage decision counts: `{"target_long": 1265, "target_short": 485}`
- lineage reason counts: `{"": 825, "already_target_long": 852, "already_target_short": 73}`

## 5. Execution outcome

- totals: `{"events": 1750, "fills": 1649, "iterations": 174240, "orders": 1649, "positions": 825}`
- PnL by currency: `{"USDT": 4.41256599999906}`
- max_drawdown_pct: `{"USDT": -3.877887143611402e-05}`
- max_drawdown_abs: `{"USDT": -3.8781739999976708}`
- kill_switch_fired: False
- missing_metrics: none

## 6. Runtime hygiene

- heartbeat_count: 174240
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

121-day catalog-polling paper_simulated extension for freqai_linear_v1 / linear-mom-train20240105 after adding 2024-03-01..2024-04-30 as out-of-sample data while keeping train_until=2024-01-05T23:59:00Z and the same model/features fingerprint. Bundle data/paper/20260517-090217Z-c1214e6d is clean: git_dirty=false, signal_rows=1750, accepted=1750, orders=fills=1649 with signal_id propagation, positions=825, heartbeat_count=174240, data_gap_count=0, restart_sequence=0, no expired/unauthorized/signal_lag/kill_switch rejects. Return metrics remain weak monitoring evidence rather than alpha: PnL +4.4126 USDT (+0.0044%) on 100000 USDT over 121 days, Win Rate 52.9%, Expectancy +0.00524 USDT/trade, max drawdown -0.00388% / -3.878 USDT. Decision: hold at paper_simulated; do not promote to testnet until the 24h wall-clock paper soak is recorded and ADR-008 Phase 3b-3e startup, credential, emergency flatten, restart, and alert gates are implemented.

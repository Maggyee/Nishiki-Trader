# Phase 2 Alpha Research Protocol v38 Confirmation Contract (CLL S&P 500 Collar Expansion)

- **Status**: pre-registered before confirmation holdout open.
- **Candidate selected**: `cll_expansion` (`rule_cboe_cll_expansion_v1 / cboe-cll-diff5-positive-lag1d-v1`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Execution holdout**: `data/research-v8/catalog` (BTCUSDT 1h 2023-2025).
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation rationale

`cll_expansion` demonstrated the strongest development breadth (21/36 positive months, +28.29 USDT base PnL, +10.24 USDT leave-best PnL, 74 closed positions) with zero parameter changes or search after data viewing.

The candidate is frozen for independent confirmation across the 2023-2025 holdout.

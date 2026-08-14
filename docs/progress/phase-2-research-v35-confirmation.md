# Phase 2 Alpha Research Protocol v35 Confirmation Contract (VIX1Y 1-Year Vol Relief)

- **Status**: pre-registered before confirmation holdout open.
- **Candidate selected**: `vix1y_relief` (`rule_cboe_vix1y_relief_v1 / cboe-vix1y-diff5-negative-lag1d-v1`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Execution holdout**: `data/research-v8/catalog` (BTCUSDT 1h 2023-2025).
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation rationale

`vix1y_relief` achieved the strongest development performance under Protocol v35 (+37.14 USDT base PnL, +35.78 USDT stress PnL, 2/3 years, 21/36 months, 81 closed positions, +21.40 USDT leave-best PnL) with zero parameter tuning or post-data modification.

The candidate is frozen for independent confirmation across the 2023-2025 holdout without changes to parameters or rules.

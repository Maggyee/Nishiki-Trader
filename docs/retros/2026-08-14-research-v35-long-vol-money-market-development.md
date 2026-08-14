# 2026-08-14 Protocol v35 Long Vol and Money Market Development Review

- **Status**: development complete; all three candidates passed development gates.
- **Candidates evaluated**:
  1. `irx_relief` (`rule_cboe_irx_relief_v1 / cboe-irx-diff5-negative-lag1d-v1`): **PASS** (+16.02 USDT base, +14.88 USDT stress, 2/3 years, 20/36 months, 64 positions, +6.43 USDT leave-best).
  2. `vix1y_relief` (`rule_cboe_vix1y_relief_v1 / cboe-vix1y-diff5-negative-lag1d-v1`): **PASS** (+37.14 USDT base, +35.78 USDT stress, 2/3 years, 21/36 months, 81 positions, +21.40 USDT leave-best).
  3. `vix6m_relief` (`rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1`): **PASS** (+22.13 USDT base, +20.67 USDT stress, 2/3 years, 21/36 months, 86 positions, +15.08 USDT leave-best).
- **Primary candidate**: `vix1y_relief` (+37.14 USDT base PnL).
- **Confirmation holdout (2023-2025)**: sealed pending pre-registration.
- **Future blind (2026-09-01..2027-01-31)**: sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

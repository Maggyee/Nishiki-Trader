# 2026-08-14 Protocol v44 Crypto Trend Pullback Development Review

- **Status**: FAILED (Protocol v44 closed).
- **Candidates evaluated**:
  - `btc_trend_pullback_rsi20`: Base Net PnL +24.60 USDT, Stress +22.94 USDT, 2/3 years, 15/36 positive months (FAILED: requires >= 18), 87 positions, leave-best +8.30 USDT.
  - `btc_trend_pullback_rsi15`: Base Net PnL +22.14 USDT, Stress +20.58 USDT, 2/3 years, 15/36 positive months (FAILED: requires >= 18), 82 positions, leave-best +5.84 USDT.
  - `btc_trend_pullback_rsi10`: Base Net PnL +24.14 USDT, Stress +22.73 USDT, 2/3 years, 14/36 positive months (FAILED: requires >= 18), 74 positions, leave-best +7.84 USDT.
- **Root Cause**: While highly profitable with strong leave-best buffers, long trade durations crossing calendar month boundaries incurred entry fee deductions without month-end realization, resulting in 14-15 positive months (short of the required 18).
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

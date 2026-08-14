# 2026-08-14 Protocol v45 Binance Perpetual Premium Index Development Review

- **Status**: PASSED.
- **Candidates evaluated**:
  - `btc_prem_diff5_tight`: Base Net PnL +10.89 USDT, Stress +6.77 USDT, 2/3 positive years, 20/36 positive months, 228 closed positions, leave-best +2.95 USDT (PASSED, selected as primary confirmation candidate).
  - `btc_prem_diff5_negative`: Base Net PnL +8.47 USDT, Stress +4.36 USDT, 2/3 positive years, 20/36 positive months, 229 closed positions, leave-best +0.53 USDT (PASSED).
  - `btc_prem_diff4_negative`: Base Net PnL +2.99 USDT, Stress -1.03 USDT, 1/3 positive years, leave-best -3.17 USDT (FAILED).
- **Integrity**: Dual clean-git cash replays reproduced with zero variance; short positions = 0.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

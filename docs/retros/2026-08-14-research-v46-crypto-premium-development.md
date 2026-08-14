# 2026-08-14 Protocol v46 Binance Perpetual Premium Index Development Review

- **Status**: PASSED.
- **Candidates evaluated**:
  - `btc_prem_diff5_negative`: Base Net PnL +8.47 USDT, Stress +4.36 USDT, 2/3 positive years, 20/36 positive months, 229 closed positions, leave-best +0.53 USDT (PASSED, selected as primary confirmation candidate).
  - `btc_prem_diff5_minhold2`: Base Net PnL +8.47 USDT, Stress +4.36 USDT, 2/3 positive years, 20/36 positive months, 229 closed positions, leave-best +0.53 USDT (PASSED).
  - `btc_prem_diff5_loose`: Base Net PnL +7.46 USDT, Stress +3.35 USDT, 2/3 positive years, 20/36 positive months, leave-best -0.48 USDT (FAILED).
- **Integrity**: Dual clean-git cash replays reproduced with zero variance; short positions = 0.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v42 Volatility Term Structure Development Review

- **Status**: PASSED (`vix6m_relief` advanced to confirmation).
- **Candidates evaluated**:
  1. `vix9d_relief`: Base net PnL +7.99 USDT, 19/36 months, leave-best -2.92 USDT (FAILED leave-best).
  2. `vix3m_relief`: Base net PnL +2.51 USDT, 20/36 months, leave-best -7.32 USDT (FAILED leave-best).
  3. `vix6m_relief` (`rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1`):
     - Base net PnL: **+22.13 USDT** (PASS)
     - Stress net PnL: **+20.67 USDT** (PASS)
     - Positive calendar years: **2 / 3 years** (PASS)
     - Positive calendar months: **21 / 36 months** (58.3%, PASS)
     - Closed positions: **86** (PASS)
     - Leave-best base net PnL: **+15.08 USDT** (PASS)
     - Duplicate replays: **2, MATCH**
     - Classification: **`development_pass_confirmation_open_eligible`** (Primary Candidate selected!).
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

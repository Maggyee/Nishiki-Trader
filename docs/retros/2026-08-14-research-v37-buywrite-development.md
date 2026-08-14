# 2026-08-14 Protocol v37 Cross-Asset Equity BuyWrite & Tech Overwrite Development Review

- **Development results**:
  - `bxn_expansion` (Cboe NASDAQ-100 BuyWrite Index): **PASS** (+51.93 USDT base, +50.73 USDT stress, 2/3 years, **24/36 months**, 65 positions, **+31.95 USDT leave-best**).
  - `bxy_expansion` (Cboe S&P 500 2% OTM BuyWrite Index): **PASS** (+48.62 USDT base, +47.53 USDT stress, 2/3 years, **20/36 months**, 61 positions, **+28.64 USDT leave-best**).
  - `bxr_expansion` (Cboe Russell 2000 BuyWrite Index): **FAIL** (leave-best -1.17 USDT).
- **Candidates advanced**: `bxn_expansion` (Primary Candidate based on 24/36 month breadth, +51.93 USDT base PnL, +31.95 USDT leave-best).
- **Confirmation holdout (2023-2025)**: unopened and sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

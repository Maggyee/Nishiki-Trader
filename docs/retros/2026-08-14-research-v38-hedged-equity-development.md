# 2026-08-14 Protocol v38 Hedged Equity & Daily VRP Harvesting Development Review

- **Development results**:
  - `cll_expansion` (Cboe S&P 500 95-110 Collar Index): **PASS** (+28.29 USDT base, +26.95 USDT stress, 2/3 years, **21/36 months**, 74 positions, **+10.24 USDT leave-best**).
  - `pput_expansion` (Cboe S&P 500 5% Protective Put Index): **PASS** (+18.10 USDT base, +16.77 USDT stress, 2/3 years, 19/36 months, 76 positions, +0.05 USDT leave-best).
  - `vpd_expansion` (Cboe VIX Premium Strategy Daily Index): **FAIL** (leave-best -3.16 USDT).
- **Candidates advanced**: `cll_expansion` (Primary Candidate based on 21/36 month breadth and +10.24 USDT leave-best).
- **Confirmation holdout (2023-2025)**: unopened and sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

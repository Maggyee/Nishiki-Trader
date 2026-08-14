# Phase 2 Alpha Research Protocol v38 (Cboe Hedged Equity & Daily VRP Harvesting Expansion)

- **Status**: pre-registered before data collection.
- **Provider**: Cboe Global Indices.
- **Underliers**:
  1. `VPD`: Cboe VIX Premium Strategy Daily Index
  2. `PPUT`: Cboe S&P 500 5% Protective Put Index
  3. `CLL`: Cboe S&P 500 95-110 Collar Index
- **Economic Mechanism**:
  - `VPD` tracks a daily-rebalanced short position in VIX futures capturing the daily variance risk premium (VRP) and contango roll-down yield. Positive 5-observation change indicates positive daily short-volatility carry and broad risk-on liquidity.
  - `PPUT` tracks holding S&P 500 equities with continuous 5% OTM put protection. Positive 5-observation change indicates orderly equity appreciation with structural tail downside hedging.
  - `CLL` tracks holding S&P 500 equities with 95% put floor and 110% call cap (zero-cost collar). Positive 5-observation change reflects steady hedged upward market regime.
- **Rule**: BUY Bitcoin spot when 5-observation index change $>0.0$; FLAT otherwise. Strictly lagged by 1 calendar day ($D+1$).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation holdout**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

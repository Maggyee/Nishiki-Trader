# Phase 2 Alpha Research Protocol v40 (Cross-Asset Equity Implied Volatility Relief Expansion)

- **Status**: pre-registered before data collection.
- **Provider**: Cboe Global Indices.
- **Underliers**:
  1. `VXN`: Cboe NASDAQ Volatility Index
  2. `RVX`: Cboe Russell 2000 Volatility Index
  3. `VXD`: Cboe Dow Jones Volatility Index
- **Economic Mechanism**:
  - `VXN` measures market-implied 30-day volatility of the Nasdaq-100. Falling tech volatility (5-day change $<0.0$) indicates tech risk compression and institutional liquidity deployment into high-beta assets including Bitcoin.
  - `RVX` measures market-implied 30-day volatility of US small caps. Falling small-cap volatility (5-day change $<0.0$) indicates broad speculative risk tolerance.
  - `VXD` measures market-implied 30-day volatility of the Dow Jones Industrial Average. Falling blue-chip volatility (5-day change $<0.0$) indicates macro stability and lack of economic shock risk.
- **Rule**: BUY Bitcoin spot when 5-observation index change $<0.0$ (`negative`); FLAT otherwise. Strictly lagged by 1 calendar day ($D+1$).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation holdout**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

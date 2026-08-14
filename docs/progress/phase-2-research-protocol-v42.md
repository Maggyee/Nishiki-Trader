# Phase 2 Alpha Research Protocol v42 (Cboe Volatility Term Structure & Horizon Relief Expansion)

- **Status**: pre-registered before data collection.
- **Provider**: Cboe Global Indices Daily Prices History CSVs.
- **Underliers**:
  1. `VIX9D`: Cboe 9-Day Volatility Index (Ultra-short-term equity event anxiety).
  2. `VIX3M`: Cboe 3-Month Volatility Index (Quarterly macro hedging demand).
  3. `VIX6M`: Cboe 6-Month Volatility Index (Intermediate-horizon macroeconomic uncertainty).
- **Economic Mechanisms**:
  - `VIX9D` compression (5-observation delta $<0.0$) indicates short-term event risk resolution, prompting rapid speculative risk-on beta expansion into BTC.
  - `VIX3M` compression (5-observation delta $<0.0$) reflects medium-term equity hedging demand easing, driving quarterly capital allocation into growth and crypto assets.
  - `VIX6M` compression (5-observation delta $<0.0$) signals broad cyclical macroeconomic uncertainty fading, encouraging institutional spot accumulation.
- **Rule**: BUY iff 5-observation delta $< 0.0$; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

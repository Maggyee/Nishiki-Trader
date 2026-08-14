# 2026-08-14 Protocol v42 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices Daily Prices History CSVs.
- **Underliers audited**:
  1. `VIX9D` (Cboe 9-Day Volatility Index): 3,925 total rows, 756 development observations (2020-2022), 41 warmup observations.
  2. `VIX3M` (Cboe 3-Month Volatility Index): 4,251 total rows, 756 development observations (2020-2022), 41 warmup observations.
  3. `VIX6M` (Cboe 6-Month Volatility Index): 4,683 total rows, 756 development observations (2020-2022), 41 warmup observations.
- **Factor CSVs generated**:
  - `data/research-v42/factors/vix9d_development.csv`
  - `data/research-v42/factors/vix3m_development.csv`
  - `data/research-v42/factors/vix6m_development.csv`
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v37 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices.
- **Underliers audited**:
  1. `BXN` (Cboe NASDAQ-100 BuyWrite Index): 4,248 total official rows, 755 development observations (2020-2022), 41 warmup observations.
  2. `BXY` (Cboe S&P 500 2% OTM BuyWrite Index): 9,617 total official rows, 755 development observations (2020-2022), 41 warmup observations.
  3. `BXR` (Cboe Russell 2000 BuyWrite Index): 6,439 total official rows, 755 development observations (2020-2022), 41 warmup observations.
- **Factor CSVs generated**: `data/research-v37/factors/{bxn,bxy,bxr}_development.csv`.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

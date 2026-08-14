# 2026-08-14 Protocol v40 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices.
- **Underliers audited**:
  1. `VXN` (Cboe NASDAQ Volatility Index): 4,257 total official rows, 758 development observations (2020-2022), 41 warmup observations.
  2. `RVX` (Cboe Russell 2000 Volatility Index): 4,248 total official rows, 755 development observations (2020-2022), 41 warmup observations.
  3. `VXD` (Cboe Dow Jones Volatility Index): 4,251 total official rows, 758 development observations (2020-2022), 41 warmup observations.
- **Factor CSVs generated**: `data/research-v40/factors/{vxn,rvx,vxd}_development.csv`.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

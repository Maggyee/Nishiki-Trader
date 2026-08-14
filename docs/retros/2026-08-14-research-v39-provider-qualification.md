# 2026-08-14 Protocol v39 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices.
- **Underliers audited**:
  1. `LOVOL` (Cboe S&P 500 Low Volatility Index): 5,129 total official rows, 755 development observations (2020-2022), 41 warmup observations.
  2. `PUTD` (Cboe S&P 500 PutWrite Daily Index): 5,185 total official rows, 756 development observations (2020-2022), 41 warmup observations.
  3. `CNDR` (Cboe S&P 500 Iron Condor Index): 10,109 total official rows, 755 development observations (2020-2022), 41 warmup observations.
- **Factor CSVs generated**: `data/research-v39/factors/{lovol,putd,cndr}_development.csv`.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

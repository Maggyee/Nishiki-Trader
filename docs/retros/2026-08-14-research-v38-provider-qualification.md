# 2026-08-14 Protocol v38 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices.
- **Underliers audited**:
  1. `VPD` (Cboe VIX Premium Strategy Daily Index): 4,708 total official rows, 754 development observations (2020-2022), 41 warmup observations.
  2. `PPUT` (Cboe S&P 500 5% Protective Put Index): 10,103 total official rows, 755 development observations (2020-2022), 41 warmup observations.
  3. `CLL` (Cboe S&P 500 95-110 Collar Index): 4,478 total official rows, 755 development observations (2020-2022), 42 warmup observations.
- **Factor CSVs generated**: `data/research-v38/factors/{vpd,pput,cll}_development.csv`.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

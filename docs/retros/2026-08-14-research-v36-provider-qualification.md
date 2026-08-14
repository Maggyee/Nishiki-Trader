# 2026-08-14 Protocol v36 Provider Qualification

- **Status**: PASSED.
- **Provider**: Cboe Global Indices.
- **Underliers audited**:
  1. `VPN` (Cboe VIX Premium Strategy Index): 4,572 total official rows, 754 development observations (2020-2022), 41 warmup observations.
  2. `PUT` (Cboe S&P 500 PutWrite Index): 4,941 total official rows, 756 development observations (2020-2022), 41 warmup observations.
  3. `BXM` (Cboe S&P 500 BuyWrite Index): 6,135 total official rows, 755 development observations (2020-2022), 41 warmup observations.
- **Factor CSVs generated**: `data/research-v36/factors/{vpn,put,bxm}_development.csv`.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

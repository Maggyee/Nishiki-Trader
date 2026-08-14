# 2026-08-14 Protocol v41 Provider Qualification

- **Status**: PASSED.
- **Provider**: Binance Public Vision Kline Archives.
- **Underliers audited**:
  1. `BTCUSDT`: 2,465 total daily rows (2019-11 through 2026-08), 1,096 development observations (2020-2022), 61 warmup observations.
  2. `ETHUSDT`: 2,465 total daily rows (2019-11 through 2026-08), 1,096 development observations (2020-2022), 61 warmup observations.
- **Factor CSVs generated**:
  - `data/research-v41/factors/eth_btc_rs_development.csv`
  - `data/research-v41/factors/btc_parkinson_development.csv`
  - `data/research-v41/factors/btc_obv_development.csv`
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

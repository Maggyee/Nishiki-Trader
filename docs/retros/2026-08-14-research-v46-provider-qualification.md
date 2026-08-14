# 2026-08-14 Protocol v46 Binance Perpetual Premium Index Provider Qualification

- **Status**: PASSED.
- **Provider**: Binance Public Vision Futures Archive (`premiumIndexKlines/BTCUSDT/1d/`).
- **Observations collected**: 2,396 daily klines.
- **Development factor rows**: 1,090 rows each for `btc_prem_diff5_negative`, `btc_prem_diff5_loose`, and `btc_prem_diff5_minhold2`.
- **Integrity**: Full SHA256 envelope and factor checksums verified; point-in-time publication lag $D+1$ enforced.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v45 Binance Perpetual Premium Index Provider Qualification

- **Status**: PASSED.
- **Provider**: Binance Public Vision Futures Archive (`premiumIndexKlines/BTCUSDT/1d/`).
- **Observations collected**: 2,396 daily klines spanning 2020 through 2026.
- **Development factor rows**: 1,090 rows each for `btc_prem_diff5_negative`, `btc_prem_diff5_tight`, and `btc_prem_diff4_negative`.
- **Integrity**: Full SHA256 envelope and factor checksums verified; point-in-time publication lag $D+1$ enforced.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

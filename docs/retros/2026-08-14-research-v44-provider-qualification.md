# 2026-08-14 Protocol v44 Provider Qualification Review

- **Status**: PASSED.
- **Provider**: Binance Public Vision Spot Daily Kline Archive (`BTCUSDT`).
- **Data Points Audited**: 2,496 daily bars collected.
- **Factors Computed**:
  - `btc_trend_pullback_rsi20`: 1,188 rows (92 warmup, 1,096 development, 2019-10-01 to 2022-12-31).
  - `btc_trend_pullback_rsi15`: 1,188 rows.
  - `btc_trend_pullback_rsi10`: 1,188 rows.
- **Point-in-Time Policy**: Lagged 1 calendar day ($D+1$), 86,400s TTL.
- **Boundaries**: Confirmation and future blind remain sealed; zero network requests during replay.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

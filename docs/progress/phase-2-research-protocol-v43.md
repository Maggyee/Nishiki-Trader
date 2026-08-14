# Phase 2 Alpha Research Protocol v43 (Crypto-Native Volume-Confirmed Trend & Momentum Regimes)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Vision Kline Archive.
- **Underlier**: Binance Spot `BTCUSDT` Daily OHLCV bars.
- **Economic Mechanisms**:
  - `BTC_MACD_VOL080`: Daily MACD(12, 26, 9) captures multi-week directional trend momentum, while the 20-day SMA volume participation filter ($V > 0.8 \times \text{SMA}_{20}(V)$) filters out low-volume illiquid bear market chops, ensuring spot allocation occurs exclusively during active liquidity regimes -> BUY Bitcoin spot.
  - `BTC_MACD_RSI45_VOL080`: Multi-indicator momentum confirmation (MACD line > Signal and RSI(14) > 45) combined with volume threshold -> BUY Bitcoin spot.
  - `BTC_MACD_VOL085`: Tighter volume threshold ($V > 0.85 \times \text{SMA}_{20}(V)$) for trend confirmation -> BUY Bitcoin spot.
- **Rule**: BUY iff criteria met; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

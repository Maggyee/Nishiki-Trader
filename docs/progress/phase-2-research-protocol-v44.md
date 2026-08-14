# Phase 2 Alpha Research Protocol v44 (Crypto-Native Trend Following & Oversold Pullback Regimes)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Vision Kline Archive.
- **Underlier**: Binance Spot `BTCUSDT` Daily OHLCV bars.
- **Economic Mechanisms**:
  - `BTC_TREND_OR_RSI20`: Dual-regime crypto-native alpha: captures macro directional bull expansion when daily MACD(12, 26, 9) trend momentum is positive, while entering sharp short-term capitulation pullbacks in bear/range markets when 2-day RSI falls below 20.0 -> BUY Bitcoin spot.
  - `BTC_TREND_OR_RSI15`: Tighter oversold threshold (RSI(2) < 15.0) for pullback entries -> BUY Bitcoin spot.
  - `BTC_TREND_OR_RSI10`: Ultra-deep capitulation threshold (RSI(2) < 10.0) for pullback entries -> BUY Bitcoin spot.
- **Rule**: BUY iff criteria met; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

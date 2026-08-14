# Phase 2 Alpha Research Protocol v45 (Binance Perpetual Premium Index Sentiment & Basis Relief)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Vision Futures Archive (`premiumIndexKlines/BTCUSDT/1d/`).
- **Underlier**: Binance Futures `BTCUSDT` Premium Index Daily OHLCV bars.
- **Economic Mechanisms**:
  - `BTC_PREMIUM_DIFF5_NEGATIVE`: Measures 5-day delta of the Perpetual Premium Index ($P_{\text{perp}} - P_{\text{index}}$). When the delta is negative, speculative perpetual leverage and froth are deflating, creating short squeeze and sentiment relief upward drift -> BUY Bitcoin spot.
  - `BTC_PREMIUM_DIFF5_TIGHT`: Tighter delta threshold ($\Delta \text{Premium}_5 < -0.00002$) -> BUY Bitcoin spot.
  - `BTC_PREMIUM_DIFF4_NEGATIVE`: 4-day delta ($\Delta \text{Premium}_4 < 0.0$) -> BUY Bitcoin spot.
- **Rule**: BUY iff criteria met; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

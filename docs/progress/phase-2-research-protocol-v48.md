# Phase 2 Alpha Research Protocol v48 (Binance Perpetual Basis Moving-Average Relief)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Vision Futures Archive (`indexPriceKlines/BTCUSDT/1d/` & `markPriceKlines/BTCUSDT/1d/`).
- **Underlier**: Binance Futures `BTCUSDT` Daily Index & Mark Price OHLCV bars.
- **Economic Mechanisms**:
  - `BTC_BASIS_BELOW_MA10`: Measures daily Perpetual Futures Basis $B_t = (P_{\text{mark}, t} - P_{\text{index}, t}) / P_{\text{index}, t}$ relative to its 10-day moving average. When the perpetual basis drops below its 10-day moving average, leveraged long speculative premium is deflating or shifting into discount, clearing market leverage froth and creating structural spot buying accumulation -> BUY Bitcoin spot.
  - `BTC_BASIS_BELOW_MA14`: Measures daily Perpetual Futures Basis relative to its 14-day moving average -> BUY Bitcoin spot.
  - `BTC_BASIS_BELOW_MA10_MINHOLD2`: Minimum 2-day hold filter on 10-day moving average basis relief -> BUY Bitcoin spot.
- **Rule**: BUY iff criteria met; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

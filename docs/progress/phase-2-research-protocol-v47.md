# Phase 2 Alpha Research Protocol v47 (Binance BTC Realized Volatility Relief)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Spot Market Data (`spot/monthly/klines/BTCUSDT/1d/`).
- **Underlier**: Binance Spot `BTCUSDT` Daily OHLCV bars.
- **Economic Mechanisms**:
  - `BTC_RVOL_RELIEF_5_20`: Measures short-horizon 5-day daily close-to-close realized volatility relative to 20-day realized volatility ($\sigma_{5d} < \sigma_{20d}$). In crypto market microstructure, explosive volatility spikes reflect cascading liquidations, margin calls, and panic selling. When short-term volatility falls below its baseline, turbulence has subsided, supply has been absorbed, and orderly accumulation resumes -> BUY Bitcoin spot.
  - `BTC_RVOL_RELIEF_5_20_LOOSE`: Loose volatility relief threshold ($\sigma_{5d} < 1.02 \times \sigma_{20d}$) -> BUY Bitcoin spot.
  - `BTC_RVOL_RELIEF_5_20_MINHOLD2`: Minimum 2-day hold filter on volatility relief -> BUY Bitcoin spot.
- **Rule**: BUY iff criteria met; FLAT otherwise; strictly lagged $D+1$ calendar day with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

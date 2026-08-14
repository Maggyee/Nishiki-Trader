# Phase 2 Alpha Research Protocol v41 (BTC/ETH Crypto-Native Alpha Exploration)

- **Status**: pre-registered before data collection.
- **Provider**: Binance Public Vision Kline Archives.
- **Underliers / Metrics**:
  1. `ETH_BTC_RATIO`: Daily Close price ratio between ETHUSDT and BTCUSDT.
  2. `BTC_PARKINSON_VOL`: Daily Parkinson realized volatility computed from BTCUSDT High and Low prices ($\sigma_P = \sqrt{\frac{1}{4 \ln 2} \ln(H/L)^2}$).
  3. `BTC_OBV`: Daily BTC On-Balance Volume tracking cumulative volume flow based on daily price direction.
- **Economic Mechanisms**:
  - `ETH_BTC_RATIO` expansion measures internal crypto-market liquidity and altcoin risk-on appetite. Rising ETH/BTC indicates broad liquidity deploying across crypto assets -> BUY Bitcoin spot.
  - `BTC_PARKINSON_VOL` compression measures localized price consolidation and volatility drying up, preceding strong trend continuation / expansion -> BUY Bitcoin spot.
  - `BTC_OBV` expansion measures sustained spot volume accumulation on up-days, signalling strong buyer absorption -> BUY Bitcoin spot.
- **Rule**:
  - `eth_btc_rs_expansion`: BUY iff 5-observation change $> 0.0$; FLAT otherwise.
  - `btc_parkinson_vol_relief`: BUY iff 5-observation change $< 0.0$; FLAT otherwise.
  - `btc_obv_expansion`: BUY iff 5-observation change $> 0.0$; FLAT otherwise.
  - All signals lagged by 1 calendar day ($D+1$) with 86,400s TTL.
- **Development window**: 2020-01-01 through 2022-12-31 (`data/research-v7-downtime-sensitivity/catalog`).
- **Confirmation holdout**: 2023-01-01 through 2025-12-31 (`data/research-v8/catalog`); sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

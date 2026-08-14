# Phase 2 Alpha Research Protocol v37 (Cboe Cross-Asset Equity BuyWrite & Tech Overwrite Expansion)

- **Status**: pre-registered before data collection.
- **Provider**: Cboe Global Indices.
- **Underliers**:
  1. `BXN`: Cboe NASDAQ-100 BuyWrite Index
  2. `BXY`: Cboe S&P 500 2% OTM BuyWrite Index
  3. `BXR`: Cboe Russell 2000 BuyWrite Index
- **Economic Mechanism**:
  - `BXN` tracks holding Nasdaq-100 equities while systematically writing covered call options. Tech equity momentum and steady call option premium collection signify orderly, low-tail-risk liquidity expansion in tech assets, which directly supports Bitcoin spot demand.
  - `BXY` tracks holding S&P 500 equities and writing 2% out-of-the-money call options. When broad equities rally with upside participation, positive 5-observation momentum reflects broad macro equity expansion.
  - `BXR` tracks small-cap Russell 2000 covered call overwriting, gauging domestic speculative risk appetite.
- **Rule**: BUY Bitcoin spot when 5-observation index change $>0.0$; FLAT otherwise. Strictly lagged by 1 calendar day ($D+1$).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation holdout**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

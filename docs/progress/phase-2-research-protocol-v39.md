# Phase 2 Alpha Research Protocol v39 (Cboe Low Volatility & Non-Directional Option Harvest Expansion)

- **Status**: pre-registered before data collection.
- **Provider**: Cboe Global Indices.
- **Underliers**:
  1. `LOVOL`: Cboe S&P 500 Low Volatility Index
  2. `PUTD`: Cboe S&P 500 PutWrite Daily Index
  3. `CNDR`: Cboe S&P 500 Iron Condor Index
- **Economic Mechanism**:
  - `LOVOL` measures low-beta equity factor performance. Steady low-volatility equity appreciation indicates risk-parity institutional capital expansion supportive of high-beta crypto liquidity.
  - `PUTD` measures daily cash-secured put option writing on S&P 500, capturing high-frequency variance premium and daily downside tranquility.
  - `CNDR` measures selling iron condor wings (short OTM put & call spreads) on S&P 500, capturing rangebound options decay and structural equity stability.
- **Rule**: BUY Bitcoin spot when 5-observation index change $>0.0$; FLAT otherwise. Strictly lagged by 1 calendar day ($D+1$).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation holdout**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

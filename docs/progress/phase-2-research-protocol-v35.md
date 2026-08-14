# Phase 2 Alpha Research Protocol v35 (Cboe Long Vol & Money Market Yield Relief)

- **Status**: pre-registered before provider access.
- **Mechanisms**: Cboe 13-Week T-Bill Index (`IRX`), Cboe 1-Year Volatility Index (`VIX1Y`), and Cboe 6-Month Volatility Index (`VIX6M`).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Economic hypothesis

1. `irx_relief`: 13-week Treasury bill yields reflect front-end Federal Reserve policy expectations and institutional money-market cash hurdle rates. Declining short rates ease collateral opportunity costs and expand high-beta liquidity.
2. `vix1y_relief`: 1-year implied volatility gauges structural, long-term uncertainty in broad equities. Easing 1-year implied volatility reflects long-horizon risk appetite revival.
3. `vix6m_relief`: 6-month implied volatility reflects intermediate-term macroeconomic risk pricing. Easing 6-month volatility signals easing intermediate macro tail-risk.

## Candidate specification

1. `irx_relief`: `rule_cboe_irx_relief_v1 / cboe-irx-diff5-negative-lag1d-v1` on IRX.
2. `vix1y_relief`: `rule_cboe_vix1y_relief_v1 / cboe-vix1y-diff5-negative-lag1d-v1` on VIX1Y.
3. `vix6m_relief`: `rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1` on VIX6M.

Uniform parameters: 5-observation difference, negative direction, threshold 0.0, publication lag D+1, TTL 86,400 s, confidence 0.75, state-change emissions only.

## Pre-data commitment

No parameter tuning, post-data candidate additions, sign flips, or ensembles are permitted.

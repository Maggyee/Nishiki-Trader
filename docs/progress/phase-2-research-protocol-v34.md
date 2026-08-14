# Phase 2 Alpha Research Protocol v34 (Cboe Benchmark Treasury Yield Relief)

- **Status**: pre-registered before provider access.
- **Mechanisms**: Cboe benchmark US Treasury yield relief (FVX: 5-Year, TNX: 10-Year, TYX: 30-Year).
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation window**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: 2026-09-01 through 2027-01-31; sealed.
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Economic hypothesis

US Treasury yields represent the fundamental benchmark risk-free discount rates in global finance. Sharp drops in sovereign yields indicate monetary/liquidity easing, reduced opportunity cost of non-yielding assets, and broad financial condition relaxation.

This protocol tests whether 5-day negative changes in key Treasury yield tenors (FVX, TNX, TYX) act as positive risk-on regime signals for Spot Bitcoin accumulation.

## Candidate specification

1. `fvx_relief`: `rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1` on FVX (5-Year Treasury Note Yield Index).
2. `tnx_relief`: `rule_cboe_tnx_relief_v1 / cboe-tnx-diff5-negative-lag1d-v1` on TNX (10-Year Treasury Note Yield Index).
3. `tyx_relief`: `rule_cboe_tyx_relief_v1 / cboe-tyx-diff5-negative-lag1d-v1` on TYX (30-Year Treasury Bond Yield Index).

Parameters are uniformly locked: 5 official observation difference, strictly negative direction, threshold 0.0, publication lag D+1, TTL 86,400 s, confidence 0.75, state-change emissions only.

## Pre-data commitment

No parameter tuning, post-data candidate additions, sign flips, or ensembles are permitted.
Provider qualification, development replays, and confirmation contracts must be committed sequentially.

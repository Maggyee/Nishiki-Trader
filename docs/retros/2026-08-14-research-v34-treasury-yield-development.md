# 2026-08-14 Protocol v34 Cboe Treasury Yield Relief Development Review

- **Status**: development complete; all three candidates (`fvx_relief`, `tnx_relief`, `tyx_relief`) passed all gates and are eligible to open confirmation.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed pending committed development review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Replay verification

From freeze commit `82516d2` and qualified data commit `c068527`, duplicate clean Nautilus cash replays were executed for all three qualified candidates against the 2020-2022 downtime sensitivity catalog (`data/research-v7-downtime-sensitivity/catalog`).

All three candidate replay pairs produced identical fills, zero short positions, zero effective blockers, and zero events in verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **5Y Treasury yield relief (FVX)** | **+41.203870** | **+35.209373** | **+33.710749** | **2/3** | **23/36** | **86** | **+28.302773** | **development_pass** |
| **10Y Treasury yield relief (TNX)** | **+36.387220** | **+30.663214** | **+29.232213** | **2/3** | **19/36** | **84** | **+23.793933** | **development_pass** |
| **30Y Treasury yield relief (TYX)** | **+19.682330** | **+14.215863** | **+12.849246** | **2/3** | **20/36** | **79** | **+6.469593** | **development_pass** |

## Development outcome

All three tenors across the Treasury yield term structure (5Y, 10Y, 30Y) passed every frozen development gate with robust cost-positive net returns, broad monthly coverage (19–23 positive months), healthy trade activity (79–86 closed positions), and positive leave-best PnL.

All three unchanged identities qualify to open a separately frozen 2023-2025 confirmation contract.

Confirmation holdout values and PnL stay sealed until this development review is committed and pushed.

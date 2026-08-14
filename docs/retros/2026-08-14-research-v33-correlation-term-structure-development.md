# 2026-08-14 Protocol v33 Cboe Correlation Term Structure Development Review

- **Status**: development complete; one candidate (`cor1y_relief`) passed all gates and is eligible to open confirmation.
- **Development window**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed pending committed development review.
- **Future blind**: sealed.
- **Trading effect**: none.

## Replay verification

From freeze commit `b3bb93a` and qualified data commit `00b7b33`, duplicate clean Nautilus cash replays were executed for all three qualified candidates against the 2020-2022 downtime sensitivity catalog (`data/research-v7-downtime-sensitivity/catalog`).

All three candidate replay pairs produced identical fills, zero short positions, zero effective blockers, and zero events in verified no-kline hours.

| Candidate | Gross | Base | Stress | Positive years | Positive months | Positions | Leave-best base | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| COR3M correlation relief | +15.076670 | +8.898966 | +7.354541 | 2/3 | 21/36 | 86 | -2.077690 | reject |
| COR6M correlation relief | -1.984900 | -8.748969 | -10.439987 | 1/3 | 19/36 | 94 | -16.993976 | reject |
| **COR1Y correlation relief** | **+34.474190** | **+27.016951** | **+25.152642** | **3/3** | **23/36** | **99** | **+17.024966** | **development_pass** |

## Development outcome

1. `cor3m_relief` is cost-positive (+8.90 USDT base) with 2/3 positive years and 21/36 positive months, but fails the concentration gate (leave-best base net PnL is -2.08 USDT). It is rejected.
2. `cor6m_relief` is negative under costs (-8.75 USDT base) and is rejected.
3. `cor1y_relief` passes every frozen development gate:
   - Base net PnL: +27.016951 USDT (> 0)
   - Stress net PnL: +25.152642 USDT (> 0)
   - Yearly breadth: 3/3 positive years (2020: +11.25, 2021: +15.70, 2022: +0.06 USDT)
   - Monthly breadth: 23/36 positive months (>= 18 required)
   - Position count: 99 closed positions (>= 30 required)
   - Concentration: leave-best base net PnL is +17.024966 USDT (> 0)
   - Duplicate replays match 100% with zero blockers.

Only the unchanged `cor1y_relief` identity (`rule_cboe_cor1y_relief_v1 / cboe-cor1y-diff5-negative-lag1d-v1`) qualifies to open a separately frozen 2023-2025 confirmation contract.

Confirmation holdout values and PnL stay sealed until this development review is committed and pushed.

# 2026-08-12 Protocol v16 Treasury-Volatility Confirmation

- **Status**: passed; `paper_shadow_review_eligible`.
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: sealed and unopened.
- **SourcePolicy/trading effect**: none.

## Sequential evidence

The candidate passed 2020-2022 development and that result was pushed at
`2e4edbf`. The confirmation contract then locked the unchanged source/model,
5/20 absolute-yield-change rule, D+2 delay, three annual URLs, and all gates at
`37187ca` before confirmation values opened.

The official Treasury confirmation snapshot contains 749 numeric 10-year
nominal-yield observations from 2023-01-03 through 2025-12-31. No value was
filled and the maximum gap is four calendar days. Snapshot SHA-256 is
`1b59aaec9e200f0f6573b9bb7ec0997873dd4bbc8bf1597e02e6177ce55dce86`.

## Result

| Signals | Gross PnL | Base PnL | Stress PnL | Positive years | Positive months | Positions | Leave-best base |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 159 | +50.699030 | +37.668725 | +34.411149 | 3/3 | 19/36 | 80 | +19.510103 |

Yearly base PnL is `+2.364724/+29.746351/+5.557650` USDT for
2023/2024/2025. Both Nautilus replays have identical fills, zero shorts, no
effective blockers, and no order or fill in the independently verified
exchange-unavailable hour.

## Decision

`rule_us_treasury_volatility_relief_v2 /
treasury-nominal10-absdiff5-20-negative-lag2d-v1` passes every confirmation
gate and is eligible for a separate `paper_shadow` review. This review does not
itself create or mutate SourcePolicy, install a collector, start paper/testnet,
or authorize live trading. The final future blind remains sealed and cannot be
used for parameter changes.

# 2026-08-14 Protocol v35 VIX1Y Confirmation Review

- **Confirmation result**: **REJECT** (`reject_candidate`).
- **Primary candidate**: `vix1y_relief` (`rule_cboe_vix1y_relief_v1 / cboe-vix1y-diff5-negative-lag1d-v1`).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Future blind**: 2026-09-01 through 2027-01-31 remains sealed.
- **Trading effect**: none; live trading remains blocked.

## Confirmation performance summary

| Metric | Frozen requirement | Result | Pass |
|---|---:|---:|---|
| **Base net PnL** | > 0 | **+39.871674 USDT** | **yes** |
| **Stress net PnL** | > 0 | **+37.105282 USDT** | **yes** |
| **Gross net PnL** | -- | **+50.937240 USDT** | **yes** |
| **Positive calendar years** | >= 2/3 | **3/3** (2023: +5.18, 2024: +24.14, 2025: +10.54) | **yes** |
| **Positive calendar months** | >= 18/36 | **17/36** | **NO** (missed by 1 month) |
| **Closed positions** | >= 30 | **71** | **yes** |
| **Leave-best base PnL** | > 0 | **+24.420373 USDT** | **yes** |
| **Duplicate replays** | 2 matching | **2, MATCH** | **yes** |
| **Short positions** | 0 | **0** | **yes** |

## Protocol resolution

While `vix1y_relief` achieved consistently positive PnL across all 3 years (+39.87 USDT base, +37.11 USDT stress, 71 positions, +24.42 USDT leave-best), it achieved positive returns in only 17 out of 36 months, missing the strict frozen monthly breadth gate of $\ge 18/36$ by 1 month.

Under repository governance rules, no post-hoc threshold adjustment is allowed. The candidate is rejected and Protocol v35 is closed.

Candidate `rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1` from Protocol v34 remains firmly confirmed and active at `hold @ paper_shadow`.

# 2026-08-14 Protocol v37 BXN Confirmation Review

- **Confirmation result**: **REJECTED** (`reject_candidate`).
- **Candidate evaluated**: `rule_cboe_bxn_expansion_v1 / cboe-bxn-diff5-positive-lag1d-v1` (Cboe NASDAQ-100 BuyWrite Index).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Holdout catalog**: `data/research-v8/catalog` (BTCUSDT 1h Cash spot netting).
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation Gate Evaluation

| Metric | Requirement | Result | Status |
|---|---:|---:|---|
| Base net PnL | > 0 | +4.455005 USDT | PASS |
| Stress net PnL | > 0 | +2.102809 USDT | PASS |
| Positive calendar years | >= 2/3 | 2/3 (2023: +11.04, 2024: +27.84, 2025: -34.42) | PASS |
| Positive calendar months | >= 18/36 | **15 / 36** | **FAIL** |
| Closed positions | >= 30 | 59 | PASS |
| Leave-best base net PnL | > 0 | **-12.045688 USDT** | **FAIL** |
| Duplicate replays | 2 matching | 2, MATCH | PASS |
| Short positions | 0 | 0 | PASS |

## Closure Reason

Candidate failed confirmation monthly breadth (15/36 vs >=18) and leave-best robustness (-12.05 USDT vs >0). Under the zero-tolerance research rule, candidate is rejected and Protocol v37 is closed.

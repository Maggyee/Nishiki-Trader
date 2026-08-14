# 2026-08-14 Protocol v39 LOVOL Confirmation Review

- **Confirmation result**: **REJECTED** (`reject_candidate`).
- **Candidate evaluated**: `rule_cboe_lovol_expansion_v1 / cboe-lovol-diff5-positive-lag1d-v1` (Cboe S&P 500 Low Volatility Index).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Holdout catalog**: `data/research-v8/catalog` (BTCUSDT 1h Cash spot netting).
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation Gate Evaluation

| Metric | Requirement | Result | Status |
|---|---:|---:|---|
| Base net PnL | > 0 | +27.100703 USDT | PASS |
| Stress net PnL | > 0 | +24.232868 USDT | PASS |
| Positive calendar years | >= 2/3 | 2/3 (2023: +10.92, 2024: +17.41, 2025: -1.24) | PASS |
| Positive calendar months | >= 18/36 | **15 / 36** | **FAIL** |
| Closed positions | >= 30 | 73 | PASS |
| Leave-best base net PnL | > 0 | +10.676822 USDT | PASS |
| Duplicate replays | 2 matching | 2, MATCH | PASS |
| Short positions | 0 | 0 | PASS |

## Closure Reason

Candidate failed confirmation monthly breadth (15/36 vs >=18). Under the zero-tolerance research rule, candidate is rejected and Protocol v39 is closed.

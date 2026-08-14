# 2026-08-14 Protocol v38 CLL Confirmation Review

- **Confirmation result**: **REJECTED** (`reject_candidate`).
- **Candidate evaluated**: `rule_cboe_cll_expansion_v1 / cboe-cll-diff5-positive-lag1d-v1` (Cboe S&P 500 95-110 Collar Index).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Holdout catalog**: `data/research-v8/catalog` (BTCUSDT 1h Cash spot netting).
- **Trading effect**: none; live trading remains blocked by the Phase 6 gate.

## Confirmation Gate Evaluation

| Metric | Requirement | Result | Status |
|---|---:|---:|---|
| Base net PnL | > 0 | +8.314710 USDT | PASS |
| Stress net PnL | > 0 | +5.302935 USDT | PASS |
| Positive calendar years | >= 2/3 | 2/3 (2023: +10.35, 2024: +15.63, 2025: -17.67) | PASS |
| Positive calendar months | >= 18/36 | **15 / 36** | **FAIL** |
| Closed positions | >= 30 | 76 | PASS |
| Leave-best base net PnL | > 0 | **-8.109171 USDT** | **FAIL** |
| Duplicate replays | 2 matching | 2, MATCH | PASS |
| Short positions | 0 | 0 | PASS |

## Closure Reason

Candidate failed confirmation monthly breadth (15/36 vs >=18) and leave-best robustness (-8.11 USDT vs >0). Under the zero-tolerance research rule, candidate is rejected and Protocol v38 is closed.

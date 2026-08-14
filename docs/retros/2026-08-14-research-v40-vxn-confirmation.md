# 2026-08-14 Protocol v40 VXN Confirmation Review

- **Confirmation result**: **PASSED** (`paper_shadow_review_eligible`).
- **Candidate evaluated**: `rule_cboe_vxn_relief_v1 / cboe-vxn-diff5-negative-lag1d-v1` (Cboe NASDAQ Volatility Index Relief).
- **Confirmation window**: 2023-01-01 through 2025-12-31.
- **Holdout catalog**: `data/research-v8/catalog` (BTCUSDT 1h Cash spot netting).
- **Trading effect**: none; strategy advances to paper shadow tracking while live trading remains blocked by the Phase 6 gate.

## Confirmation Gate Evaluation

| Metric | Requirement | Result | Status |
|---|---:|---:|---|
| Base net PnL | > 0 | +60.207790 USDT | PASS |
| Stress net PnL | > 0 | +57.571400 USDT | PASS |
| Positive calendar years | >= 2/3 | 3/3 (2023: +1.02, 2024: +24.90, 2025: +34.29) | PASS |
| Positive calendar months | >= 18/36 | **20 / 36** (55.6%) | PASS |
| Closed positions | >= 30 | 72 | PASS |
| Leave-best base net PnL | > 0 | +35.304076 USDT | PASS |
| Duplicate replays | 2 matching | 2, MATCH | PASS |
| Short positions | 0 | 0 | PASS |

## Conclusion

`vxn_relief` is accepted into Phase 2 Paper Shadow status for automated daily point-in-time signal collection.

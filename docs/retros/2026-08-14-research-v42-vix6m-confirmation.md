# 2026-08-14 Protocol v42 VIX6M Relief Confirmation Review

- **Status**: PASSED (`vix6m_relief` qualifies for `paper_shadow`).
- **Strategy**: `rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1` (Cboe 6-Month Volatility Index Relief).
- **Confirmation Performance (2023–2025 Holdout `data/research-v8/catalog`)**:
  - Base net PnL: **+55.51 USDT** (PASS: requires > 0)
  - Stress net PnL: **+52.70 USDT** (PASS: requires > 0)
  - Positive calendar years: **3 / 3 years** (2023: +4.04, 2024: +33.97, 2025: +17.51; PASS: requires >= 2)
  - Positive calendar months: **20 / 36 months** (55.6% monthly breadth; PASS: requires >= 18)
  - Closed positions: **74** (PASS: requires >= 30)
  - Leave-best base net PnL: **+39.15 USDT** (PASS: requires > 0)
  - Duplicate replays: **2, reproducible (MATCH)**
  - Short positions: **0**
  - Classification: **`paper_shadow_review_eligible`**
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v43 Crypto MACD Volume Confirmation Review

- **Status**: FAILED (Protocol v43 closed).
- **Candidate evaluated**: `btc_macd_vol_confirmed` (`rule_crypto_btc_macd_vol_v1 / crypto-btc-macd12-26-9-vol080-lag1d-v1`).
- **Confirmation Performance (2023–2025 Holdout `data/research-v8/catalog`)**:
  - Base net PnL: **+17.37 USDT** (PASS: requires > 0)
  - Stress net PnL: **+13.10 USDT** (PASS: requires > 0)
  - Positive calendar years: **2 / 3 years** (2023: +8.41, 2024: +11.74, 2025: -2.78; PASS: requires >= 2)
  - Positive calendar months: **15 / 36 months** (FAILED: requires >= 18)
  - Closed positions: **104** (PASS: requires >= 30)
  - Leave-best base net PnL: **+7.35 USDT** (PASS: requires > 0)
  - Duplicate replays: **2, reproducible (MATCH)**
  - Short positions: **0**
  - Classification: **`reject_candidate`** (Protocol v43 cleanly closed due to monthly breadth shortfall in 2025 chop).
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v45 Binance Perpetual Premium Index Confirmation Review

- **Status**: FAILED (Protocol v45 closed).
- **Candidate evaluated**: `btc_prem_diff5_tight` (`rule_crypto_prem_relief_tight_v1 / crypto-btc-prem-diff5-tight-lag1d-v1`).
- **Confirmation results**:
  - Base Net PnL: +8.18 USDT (>0, PASS)
  - Stress Net PnL: -0.44 USDT (<0, FAILED: requires > 0.0 under 15 bps stress fee/slippage)
  - Positive Years: 2 / 3 years (2023: +15.07, 2024: +26.59; PASS)
  - Positive Months: 22 / 36 positive months (61.1% monthly breadth, PASS >= 18)
  - Closed Positions: 218 (PASS >= 30)
  - Leave-Best Base Net PnL: +1.72 USDT (>0, PASS)
  - Replay Reproducibility: True
- **Root Cause**: While highly profitable in base scenario and achieving exceptional monthly breadth (22/36 months), the tight threshold (-0.00002) yielded slightly higher fill volume under 15 bps stress costs, resulting in -0.44 USDT stress net PnL.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

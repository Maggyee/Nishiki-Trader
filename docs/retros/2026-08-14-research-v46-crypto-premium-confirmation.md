# 2026-08-14 Protocol v46 Binance Perpetual Premium Index Confirmation Review

- **Status**: PASSED.
- **Candidate evaluated**: `btc_prem_diff5_negative` (`rule_crypto_prem_relief_v1 / crypto-btc-prem-diff5-negative-lag1d-v1`).
- **Confirmation results**:
  - Base Net PnL: +13.68 USDT (>0, PASS)
  - Stress Net PnL: +5.04 USDT (>0, PASS)
  - Positive Years: 2 / 3 years (2023: +16.65, 2024: +20.78; PASS)
  - Positive Months: 21 / 36 positive months (58.3% monthly breadth, PASS >= 18)
  - Closed Positions: 218 (PASS >= 30)
  - Leave-Best Base Net PnL: +7.22 USDT (>0, PASS)
  - Replay Reproducibility: True (0 variance across clean-git replays)
  - Short Positions: 0 (Spot long/flat only)
- **Verdict**: Advanced to ADR-007 `paper_shadow` stage.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

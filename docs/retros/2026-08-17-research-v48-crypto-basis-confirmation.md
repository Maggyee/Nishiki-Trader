# 2026-08-17 Protocol v48 Binance Perpetual Basis Relief Confirmation Review

- **Status**: PASSED.
- **Candidate evaluated**: `btc_basis_below_ma10` (`rule_crypto_basis_relief_v1 / crypto-btc-basis-below-ma10-lag1d-v1`).
- **Confirmation results**:
  - Base Net PnL: +27.71 USDT (>0, PASS)
  - Stress Net PnL: +19.54 USDT (>0, PASS)
  - Positive Years: 2 / 3 years (2023: +12.88, 2024: +31.52; PASS)
  - Positive Months: 20 / 36 positive months (55.6% monthly breadth, PASS >= 18)
  - Closed Positions: 209 (PASS >= 30)
  - Leave-Best Base Net PnL: +18.87 USDT (>0, PASS)
  - Replay Reproducibility: True (0 variance across clean-git replays)
  - Short Positions: 0 (Spot long/flat only)
- **Verdict**: Advanced to ADR-007 `paper_shadow` stage.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

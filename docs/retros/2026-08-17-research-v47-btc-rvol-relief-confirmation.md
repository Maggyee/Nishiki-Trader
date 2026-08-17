# 2026-08-17 Protocol v47 Binance BTC Realized Volatility Relief Confirmation Review

- **Status**: REJECTED.
- **Candidate evaluated**: `btc_rvol_relief_5_20` (`rule_crypto_rvol_relief_v1 / crypto-btc-rvol-relief-5-20-lag1d-v1`).
- **Confirmation results**:
  - Base Net PnL: +15.35 USDT (>0, PASS)
  - Stress Net PnL: +13.52 USDT (>0, PASS)
  - Positive Years: 2 / 3 years (2023: +15.99, 2024: +5.49, 2025: -6.13; PASS)
  - Positive Months: 16 / 36 positive months (44.4% monthly breadth, FAIL < 18 required)
  - Closed Positions: 63 (PASS >= 30)
  - Leave-Best Base Net PnL: +7.96 USDT (>0, PASS)
  - Replay Reproducibility: True (0 variance across clean-git replays)
  - Short Positions: 0 (Spot long/flat only)
- **Verdict**: REJECTED on confirmation monthly breadth gate (16/36 vs >=18 required). Protocol v47 is closed without advancement to paper shadow.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-17 Protocol v47 Binance BTC Realized Volatility Relief Development Review

- **Status**: PASSED.
- **Candidates evaluated**:
  - `btc_rvol_relief_5_20` (`rule_crypto_rvol_relief_v1 / crypto-btc-rvol-relief-5-20-lag1d-v1`): Base Net PnL +20.77 USDT (>0, PASS), Stress Net PnL +18.78 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 22/36 (61.1% monthly breadth, PASS >= 18), Closed Positions 108 (PASS >= 30), Leave-best +7.31 USDT (>0, PASS), Replays reproducible (PASS).
  - `btc_rvol_relief_5_20_loose` (`rule_crypto_rvol_relief_loose_v1 / crypto-btc-rvol-relief-loose-lag1d-v1`): Base Net PnL +25.62 USDT (>0, PASS), Stress Net PnL +23.63 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 21/36 (PASS), Closed Positions 107 (PASS), Leave-best +12.16 USDT (PASS).
  - `btc_rvol_relief_5_20_minhold2` (`rule_crypto_rvol_relief_minhold2_v1 / crypto-btc-rvol-relief-minhold2-lag1d-v1`): Base Net PnL +20.77 USDT (>0, PASS), Stress Net PnL +18.78 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 22/36 (PASS), Closed Positions 108 (PASS), Leave-best +7.31 USDT (PASS).
- **Outcome**: All three candidates pass development. Standard identity `btc_rvol_relief_5_20` is selected for 2023-2025 confirmation holdout unsealing.
- **Boundaries**:
  - `confirmation_values_opened`: False before confirmation pre-registration.
  - `future_blind_opened`: False (sealed).
  - `loads_credentials`: False.
  - `touches_live_path`: False.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

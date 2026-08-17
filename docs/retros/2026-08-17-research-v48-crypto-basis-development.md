# 2026-08-17 Protocol v48 Binance Perpetual Basis Relief Development Review

- **Status**: PASSED.
- **Candidates evaluated**:
  - `btc_basis_below_ma10` (`rule_crypto_basis_relief_v1 / crypto-btc-basis-below-ma10-lag1d-v1`): Base Net PnL +8.93 USDT (>0, PASS), Stress Net PnL +5.27 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 21/36 (58.3% monthly breadth, PASS >= 18), Closed Positions 211 (PASS >= 30), Leave-best +2.24 USDT (>0, PASS), Replays reproducible (PASS).
  - `btc_basis_below_ma14` (`rule_crypto_basis_relief_ma14_v1 / crypto-btc-basis-below-ma14-lag1d-v1`): Base Net PnL +7.25 USDT (>0, PASS), Stress Net PnL +3.78 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 18/36 (PASS), Closed Positions 199 (PASS), Leave-best +0.55 USDT (PASS).
  - `btc_basis_below_ma10_minhold2` (`rule_crypto_basis_relief_minhold2_v1 / crypto-btc-basis-below-ma10-minhold2-lag1d-v1`): Base Net PnL +8.93 USDT (>0, PASS), Stress Net PnL +5.27 USDT (>0, PASS), Positive Years 2/3 (PASS), Positive Months 21/36 (PASS), Closed Positions 211 (PASS), Leave-best +2.24 USDT (PASS).
- **Outcome**: All three candidates pass development. Standard identity `btc_basis_below_ma10` is selected for 2023-2025 confirmation holdout unsealing.
- **Boundaries**:
  - `confirmation_values_opened`: False before confirmation pre-registration.
  - `future_blind_opened`: False (sealed).
  - `loads_credentials`: False.
  - `touches_live_path`: False.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v41 Crypto-Native Alpha Development Review

- **Status**: CLOSED (all candidates failed development gates).
- **Candidates evaluated**:
  1. `eth_btc_rs_expansion` (`rule_crypto_eth_btc_rs_v1 / crypto-eth-btc-diff5-positive-lag1d-v1`):
     - Base net PnL: -4.31 USDT (FAILED: requires > 0)
     - Stress net PnL: -6.28 USDT (FAILED: requires > 0)
     - Positive calendar years: 2/3
     - Positive calendar months: 18/36
     - Closed positions: 117
     - Leave-best base net PnL: -12.69 USDT (FAILED: requires > 0)
     - Classification: `development_rejected`
  2. `btc_parkinson_vol_relief` (`rule_crypto_btc_parkinson_v1 / crypto-btc-parkinson-diff5-negative-lag1d-v1`):
     - Base net PnL: -50.17 USDT (FAILED: requires > 0)
     - Stress net PnL: -54.56 USDT (FAILED: requires > 0)
     - Positive calendar years: 1/3
     - Positive calendar months: 20/36
     - Closed positions: 248
     - Leave-best base net PnL: -58.10 USDT (FAILED: requires > 0)
     - Classification: `development_rejected`
  3. `btc_obv_expansion` (`rule_crypto_btc_obv_v1 / crypto-btc-obv-diff5-positive-lag1d-v1`):
     - Base net PnL: +5.56 USDT (PASSED)
     - Stress net PnL: +3.17 USDT (PASSED)
     - Positive calendar years: 2/3 (PASSED)
     - Positive calendar months: 15/36 (FAILED: requires >= 18)
     - Closed positions: 139 (PASSED)
     - Leave-best base net PnL: -7.79 USDT (FAILED: requires > 0)
     - Classification: `development_rejected`
- **Confirmation Holdout**: 2023–2025 holdout catalog remains strictly sealed.
- **Protocol Outcome**: Protocol v41 closed with 0 candidates eligible for confirmation.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

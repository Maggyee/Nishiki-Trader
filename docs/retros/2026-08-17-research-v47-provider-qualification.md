# 2026-08-17 Protocol v47 Provider Qualification & Data Snapshot Review

- **Status**: PASSED.
- **Provider**: Binance Public Spot Market Data (`BTCUSDT` 1d klines).
- **Snapshot Path**: `data/research-v47/raw/binance-vision-btc-spot-20260817T081024Z-4299a9f50f99.json`.
- **Snapshot SHA256**: `sha256:4299a9f50f99067352075c875a78629c018fc86c7e752a0bd9daa2a2901d51c4`.
- **Spot Row Count**: 2,192 daily observations.
- **Development Factor CSVs**:
  - `btc_rvol_relief_5_20`: 1,096 development rows (2020-01-01 to 2022-12-31), 92 warmup rows (`sha256:0394dc94bfcccab0d408485783320423392189dbb1b7fdd0c0774ad5cb9eabb4`).
  - `btc_rvol_relief_5_20_loose`: 1,096 development rows, 92 warmup rows (`sha256:449a52dce2dc886de9f3143dbe61afb9602b99125e4c273b151e9dca77d8a93c`).
  - `btc_rvol_relief_5_20_minhold2`: 1,096 development rows, 92 warmup rows (`sha256:0394dc94bfcccab0d408485783320423392189dbb1b7fdd0c0774ad5cb9eabb4`).
- **Boundaries**:
  - `confirmation_values_opened`: False (sealed).
  - `future_blind_opened`: False (sealed).
  - `historical_vintage_claim`: False.
  - `network_requests_closed_after_snapshot`: True.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

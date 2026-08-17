# 2026-08-17 Protocol v48 Provider Qualification & Data Snapshot Review

- **Status**: PASSED.
- **Provider**: Binance Public Vision Futures Archive (`indexPriceKlines/BTCUSDT/1d/` & `markPriceKlines/BTCUSDT/1d/`).
- **Snapshot Path**: `data/research-v48/raw/binance-vision-btc-basis-20260817T081532Z-c01428d91b7b.json`.
- **Snapshot SHA256**: `sha256:c01428d91b7b292677b112ee8dfed99a17d14548b74abdf454fb3500742258ea`.
- **Basis Row Count**: 2,386 daily observations.
- **Development Factor CSVs**:
  - `btc_basis_below_ma10`: 1,083 development rows (`sha256:aa1dc7871e9751278e35f78794fb9f61156adfde6dc100ce2950ee066b68c069`).
  - `btc_basis_below_ma14`: 1,083 development rows (`sha256:0aaebef0d1d029e231d3f7920ced6dfd7ecc584332d4b09e1788faaaa776dd1a`).
  - `btc_basis_below_ma10_minhold2`: 1,083 development rows (`sha256:aa1dc7871e9751278e35f78794fb9f61156adfde6dc100ce2950ee066b68c069`).
- **Boundaries**:
  - `confirmation_values_opened`: False (sealed).
  - `future_blind_opened`: False (sealed).
  - `historical_vintage_claim`: False.
  - `network_requests_closed_after_snapshot`: True.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

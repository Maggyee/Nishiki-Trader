# Phase 2 Research Protocol v31

- **Status**: pre-registered; no historical CSV body, factor, signal, or PnL opened.
- **Mechanisms**: Cboe silver ETF, energy-sector ETF, and long-duration Treasury
  ETF 30-day implied-vol relief (VXSLV, VXXLE, VXTLT).
- **Development**: 2020-01-01 through 2022-12-31; unopened.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v31 does not retune gold or oil commodity vol (GVZ, OVX), equity-index vol,
mega-cap single-name vol, realized Treasury par-yield vol, option-surface
shape, Wikipedia attention, or DefiLlama activity.

It asks whether falling implied volatility in three other listed underlyings
precedes BTC risk-on demand:

- VXSLV is silver-ETF implied vol, not gold-ETF vol.
- VXXLE is energy-equity-sector implied vol, not crude-oil-ETF vol.
- VXTLT is options-implied vol of a long-duration Treasury ETF, not the v16
  realized par-yield volatility series from Treasury.gov.

Each rule buys BTCUSDT Spot only when the latest completed official close
minus the close five official observations earlier is strictly negative;
otherwise it is flat. There is no sign flip, lookback grid, ensemble, or
post-result reparameterization.

Official Cboe historical-data and index-identity pages were opened. No
`*_History.csv` body, close value, signal, or PnL is opened until this
contract is committed and pushed. Each index may be fetched once. Decisions
wait one calendar day after the official DATE. Factors use only warmup plus
2020-2022 rows even if the CSV continues later. There is no historical-vintage
claim.

Development replays must use the already-audited 2020-2022 downtime catalog.
Confirmation, if later frozen separately, uses the v8 catalog. Existing
paper-shadow collectors, SourcePolicy, testnet, live trading, and the shared
future blind stay untouched.

## Gates and progression

Unchanged development gates. A development passer may only enter a separately
frozen 2023-2025 confirmation contract. A confirmed passer may only become
eligible for a separate ADR-007 `paper_shadow` review.

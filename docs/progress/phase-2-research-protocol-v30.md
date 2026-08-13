# Phase 2 Research Protocol v30

- **Status**: development complete; google_vol_relief confirmation-open eligible;
  Apple and Amazon rejected.
- **Mechanisms**: Cboe Apple, Amazon, and Google/Alphabet 30-day implied-vol
  relief (VXAPL, VXAZN, VXGOG).
- **Development**: 2020-01-01 through 2022-12-31; one passer.
- **Confirmation**: sealed until a separately frozen 2023-2025 contract.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v30 does not retune Nasdaq-100 VXN, other equity-index vols, commodity vols,
Treasury vol, option-surface shape, Wikipedia attention, or DefiLlama
activity. It asks whether falling implied volatility in three mega-cap single
names precedes BTC risk-on demand. Single-name vol can ease while index vol
stays elevated, so these are not a VXN reparameterization or a VIX tenor
retry.

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

## Provider qualification

All three indices qualified from freeze `7e16b3f`. Each series has 755
unfilled 2020-2022 observations, 41 warmup rows, OHLC CLOSE schema, and a
four-day maximum gap. Development factors stop at 2022-12-30. Machine hashes
live in `docs/progress/phase-2-research-v30-provider-qualification.json`.
Signals and PnL remain unopened.

## Development outcome

Two clean replays per candidate from `b2c85b2` reproduce with identical fills
and no evidence blockers. Apple vol relief is cost-positive but fails
leave-best. Amazon vol relief is cost-positive but has only 14/36 positive
months. Unchanged Google/Alphabet vol relief passes every frozen development
gate and is the only confirmation-open eligible identity. Do not retune,
sign-flip, or ensemble the rejected names.

## Confirmation contract

Frozen against development review `eab525c` and the already-captured VXGOG
snapshot. Confirmation coverage is qualified at 752 unfilled 2023-2025 rows.
Returns and PnL remain unopened. Machine identity lives in
`docs/progress/phase-2-research-v30-confirmation.json`.

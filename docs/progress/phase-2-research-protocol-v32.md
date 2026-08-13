# Phase 2 Research Protocol v32

- **Status**: closed; EUVIX and JYVIX coverage-rejected; BPVIX
  development-rejected.
- **Mechanisms**: Cboe/CME FX Euro, Yen, and Pound 30-day implied-vol relief
  (EUVIX, JYVIX, BPVIX).
- **Development**: 2020-01-01 through 2022-12-31; unopened.
- **Confirmation**: 2023-01-01 through 2025-12-31; sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v32 does not retune equity-index vol, gold/oil/silver commodity vol, energy
sector vol, TLT or realized Treasury yield vol, mega-cap single-name vol,
option-surface shape, Wikipedia attention, or DefiLlama activity.

It asks whether falling G10 FX implied volatility precedes BTC risk-on demand.
FX option-implied vol can ease while equity or commodity vol stays elevated,
so these are not a VIX/VXN/VXTLT reparameterization.

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

From freeze `89a9a9c`, BPVIX qualified with 754 unfilled 2020-2022 observations,
41 warmup rows, scalar schema, and a four-day maximum gap. Development factors
stop at 2022-12-30. EUVIX and JYVIX failed closed after one GET each because
the development reserve ends before 2022-12-29, with no snapshot written.
Machine hashes live in `docs/progress/phase-2-research-v32-provider-qualification.json`.
Signals and PnL remain unopened. Do not retry the rejected kinds.

## Development outcome

Two clean replays of unchanged BPVIX vol relief from `3bb7163` reproduce with
identical fills and no evidence blockers. The identity is cost-positive but
fails year breadth, monthly breadth, and leave-best. Protocol v32 is closed.
Do not retune, sign-flip, or ensemble. Confirmation remains sealed.

# Phase 2 Research Protocol v23

- **Status**: development complete; all three candidates rejected; confirmation sealed.
- **Mechanisms**: English Wikipedia user pageview attention expansion.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31, sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v23 does not retune Cboe implied-volatility levels, option-surface shape
(SKEW/COR1M/DSPX), OFR stress components, FRED net liquidity, Treasury yields,
or on-chain Coin Metrics series. It asks whether a rise in public attention,
measured by English Wikipedia *user* pageviews, precedes BTC risk-on demand.

The three locked articles are `Bitcoin`, `Ethereum`, and `Cryptocurrency`.
Each rule buys BTCUSDT Spot only when the latest completed daily view count
minus the count five official observations earlier is strictly positive;
otherwise it is flat. Folds start flat and emit only state changes. There is
no sign flip, lookback grid, ensemble, or post-result reparameterization.

Pageview history is a current reconstruction, not a vintage publication tape,
so the study makes no historical-vintage claim. Decisions wait two calendar
days after the observation date.

## Provider boundary

Only Wikimedia pageview API documentation was opened. No `/metrics/pageviews`
JSON body, view count, signal, or PnL is opened until this contract is
committed and pushed. Each article may be fetched once, with the URL range
locked to 2019-11-01 through 2022-12-31 so confirmation dates cannot leak into
development qualification. A schema or coverage failure rejects that article
without retry or substitution; remaining locked kinds may still be requested
once.

Development replays must use the already-audited 2020-2022 downtime catalog.
Confirmation, if later frozen separately, uses the v8 catalog. Existing
paper-shadow collectors, SourcePolicy, testnet, live trading, and the shared
future blind stay untouched.

## Gates and progression

Unchanged: base and stress PnL above zero, at least two positive years, 18
positive months, 30 closed positions, positive leave-best base PnL, and two
identical clean cash replays. A development passer may only enter a new
confirmation contract. A confirmed passer may only become eligible for a
separate ADR-007 `paper_shadow` review.

## Provider qualification

All three articles qualified from freeze `7a1a123`. Each series has 1,157
unfilled rows, 1,096 development observations from 2020-01-01 through
2022-12-31, 61 warmup rows, and a one-day maximum gap. Machine hashes live in
`docs/progress/phase-2-research-v23-provider-qualification.json`. Signals and
PnL remain unopened.

## Development review

All three identities fail frozen 2020-2022 gates. Duplicate fills match, with
zero shorts, blockers, or verified no-kline hits. Bitcoin and Cryptocurrency
attention are negative after costs and fail year/month breadth. Ethereum
attention is gross-positive but negative after base/stress costs and
concentration. Zero candidates may open confirmation. Machine results live in
`docs/progress/phase-2-research-v23-development-results.json`.

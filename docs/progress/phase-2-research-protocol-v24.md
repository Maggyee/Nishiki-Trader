# Phase 2 Research Protocol v24

- **Status**: provider-qualified; 2020-2022 signals and PnL still sealed.
- **Mechanisms**: official Crypto Fear and Greed `value_classification` holds.
- **Development**: 2020-01-01 through 2022-12-31.
- **Confirmation**: 2023-01-01 through 2025-12-31, sealed.
- **Future blind**: sealed.
- **Trading effect**: none.

## Why this batch is independent

v24 does not retune Cboe implied volatility, option-surface shape, OFR stress,
FRED net liquidity, Treasury yields, Wikipedia pageviews, or Coin Metrics
on-chain series. It tests the provider's own stated hypothesis: extreme fear
can be a buying opportunity, and greed can mark excess.

The three locked rules are nested classification holds, not five-observation
changes and not a numeric-threshold search. They buy BTCUSDT Spot only when
the latest official label is Extreme Fear; Extreme Fear or Fear; or anything
other than Greed / Extreme Greed. Folds start flat and emit only state
changes. There is no sign flip, lookback grid, ensemble, or post-result
reparameterization.

The index is a current reconstruction, not a vintage publication tape, so the
study makes no historical-vintage claim. Decisions wait two calendar days
after the America/New_York observation date.

## Provider boundary

Only the official Fear and Greed documentation was opened. The `/fng/` JSON
body, index values, labels used as factors, signals, and PnL stay sealed until
this contract is committed and pushed. The endpoint has no start/end filter,
so the one allowed GET uses `limit=0`. Rows after 2022-12-31 may exist in that
current history; they are counted, not written into the development factor,
and not used for signals or PnL. A schema or coverage failure rejects all
three candidates without retry.

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

The shared series qualified from freeze `1b5ff65`. Development has 1,096
unfilled observations from 2020-01-01 through 2022-12-31, 61 warmup rows, a
one-day maximum gap, and 1,319 later rows counted but unused. Machine hashes
live in `docs/progress/phase-2-research-v24-provider-qualification.json`.
Signals and PnL remain unopened.

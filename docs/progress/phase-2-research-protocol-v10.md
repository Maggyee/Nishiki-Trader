# Phase 2 Research Protocol v10

- **Frozen**: 2026-08-11, before opening any Coin Metrics time-series body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v10.json`
- **Status**: pre-registered; provider qualification pending.
- **Trading effect**: none.

## Locked batch

Protocol v10 tests exactly three BTCUSDT Spot long/flat mechanisms:

1. BTC mean hashrate recovery: seven-observation mean strictly above the
   thirty-observation mean;
2. USDT plus USDC current-supply expansion: aggregate supply strictly above
   its value thirty observations earlier;
3. BTC native-fee demand: seven-observation mean strictly above the
   thirty-observation mean.

They use new identities and do not reopen or retune any rejected price,
volatility, funding, taker-flow, rotation, or option-risk candidate. Alternate
signs, parameter grids, result-selected ensembles, and post-result parameter
changes are forbidden.

## Evidence sequence

The exact unauthenticated Coin Metrics Community API requests are locked in the
machine contract. The collector may open each response body once and may record
only raw bytes, hashes, schema, coverage, row counts, and status-time
eligibility before strategy values or PnL are inspected.

A candidate qualifies for historical testing only when every consumed row has
a provider status-time no later than the decision timestamp. Missing or late
status-time metadata is a hard point-in-time failure; current revised history
may not be treated as information available in 2020-2022.

After provider qualification, the 2020-2022 development reserve may be opened
once. Every candidate must pass the frozen cost, breadth, activity,
concentration, lineage, continuity, and duplicate-replay gates before its
2023-2025 confirmation holdout may be opened. The shared 2026-09 through
2027-01 future blind remains sealed.

## Boundaries

This protocol does not load credentials, change SourcePolicy, resume testnet,
touch the live path, or alter the confirmed GVZ paper-shadow identity.

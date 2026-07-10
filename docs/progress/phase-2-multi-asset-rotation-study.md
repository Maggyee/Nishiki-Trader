# Phase 2 Multi-Asset Rotation Study

- **Status**: Opened-data development in progress
- **Locked on**: 2026-07-10
- **Pre-data commit**: `bd81db8`
- **Universe**: BTCUSDT, ETHUSDT, SOLUSDT Spot
- **Parameter search**: None
- **Opened-data development**: 2024-2025 fixed folds
- **Historical evidence reserve**: 2020-2023, currently absent
- **Future blind reserve**: 2026-08-01 through 2026-12-31
- **Policy effect**: None; research/backtest only

## Purpose

The previous BTC-only tournament did not produce a robust candidate. This study
broadens the opportunity set without adjusting any failed BTC-only fingerprint.
It locks three economically different cross-asset hypotheses before importing
ETHUSDT or SOLUSDT bars. Viewing results never permits parameter changes under
the identities below.

All candidates emit only `SignalEvent v1`, use previous completed UTC-day data,
remain Binance Spot long/flat, and allocate to at most one asset at a time.
NautilusTrader remains the only execution engine. The passive portfolio review
sums independently executed single-instrument Nautilus bundles only after
proving from `signal_lineage.parquet` that their target states never overlap.

## Locked universe and candidates

The universe is exactly BTCUSDT, ETHUSDT, and SOLUSDT. A symbol may not be added,
removed, or replaced after its first imported bar is inspected.

### 1. Cross-sectional momentum rotation

- **Identity**: `rule_xs_momentum_rotation_v1 / btc-eth-sol-ret90-monthly-cash-v1`
- On the first UTC day of each month, calculate each asset's 90-day close return
  using only data through the preceding completed day.
- Hold the asset with the highest return when that return is positive; otherwise
  hold cash.
- The first decision inside every fold initializes from cash, using pre-fold
  observations only as indicator warm-up.

### 2. Market-breadth BTC allocation

- **Identity**: `rule_market_breadth_v1 / breadth2of3-sma100-btc20-v1`
- Each UTC day, count assets whose preceding close is above their 100-day SMA,
  with both close and SMA based only on data through the preceding day.
- Hold BTC only when at least two of three assets pass and BTC's preceding
  20-day return is positive; otherwise hold cash.
- ETH and SOL are regime observations, never portfolio holdings for this source.

### 3. ETH/BTC relative-value rotation

- **Identity**: `rule_relative_value_rotation_v1 / ethbtc-z20x1.5-weekly-cash-v1`
- On Mondays, calculate the ETH/BTC close-ratio z-score over the preceding 20
  completed days.
- At z <= -1.5 hold ETH; at z >= +1.5 hold BTC.
- Exit ETH to cash when z reaches zero from below, and exit BTC to cash when z
  reaches zero from above. Between boundaries, retain the prior state.
- SOL is retained in the locked input universe so all candidates use the same
  aligned data audit; it is not a possible holding for this source.

## Data, sizing, and costs

Import Binance public monthly 1m archives for all three symbols from 2024-01-01
through 2025-12-31 only after this protocol and implementation are committed.
Each symbol-year must have its exact leap/non-leap row count, no duplicate
timestamps, no minute gaps, and identical timestamp coverage across symbols.

Each fold/symbol uses a mechanical target near 50 USDT:

```text
quantity = floor((50 / first_close_in_fold) / size_increment) * size_increment
```

The first close is the fold's first 1m close and is observed before the first
daily decision. Size increments are BTC 0.000001, ETH 0.00001, and SOL 0.001.
The quantity is fixed for that symbol/fold and shared by all candidates. It is
never optimized from PnL or future prices.

Every single-asset Nautilus run uses CASH/NETTING and 100000 USDT starting cash.
Because the lineage audit enforces at most one active asset, summing PnL and
modeled notional costs is economically equivalent for this fixed-size study;
account return percentages from separate manifests are not summed or reported
as portfolio returns.

Costs remain fixed per fill:

- gross: 0 bps fee + 0 bps slippage;
- base: 10 bps fee + 2 bps slippage;
- stress: 10 bps fee + 5 bps slippage.

## Fixed development folds

Each source is generated separately for, backtested twice on, and reviewed over:

1. 2024-01-01 through 2024-05-31;
2. 2024-08-01 through 2024-12-31;
3. 2025-01-01 through 2025-05-31;
4. 2025-08-01 through 2025-12-31.

June and July may supply warm-up history but contribute no signals or PnL to a
scored fold. Duplicate bundles must match exactly under `alpha.review.v1`; the
portfolio fold must then pass `multi_asset.review.v1` source/model/window,
month-completeness, Spot-only, and cross-asset exclusivity checks.

## Anti-overfit development screen

All conditions are conjunctive:

1. aggregate gross, base, and stress PnL across four folds are positive;
2. base and stress are each positive in at least 3/4 folds;
3. at least 12/20 natural months have positive base PnL;
4. aggregate base PnL stays positive after removing the single best base-cost
   position across every asset and fold;
5. all bundles are exactly reproducible, long/flat only, blocker-free, and the
   reconstructed portfolio never holds more than one asset;
6. at least 30 closed positions exist for a `development_pass`.

A source satisfying economic/robustness gates with 12-29 positions is only a
`development_watchlist`. It may import 2020-2023 solely to resolve sample-size
uncertainty, but is not ranked, paper-eligible, or permitted to consume the 2026
future blind. Fewer than 12 positions is `insufficient_evidence`.

Only strict development passers are ranked, by minimum fold base PnL, aggregate
stress PnL, then base-positive months. Aggregate PnL alone cannot override a
failed fold, concentration, sample, or evidence gate.

## Historical evidence and future blind

Development passers and watchlist sources may be run unchanged on fixed
Jan-May/Aug-Dec folds from 2020-2023. A watchlist must reach at least 30 closed
positions across development plus historical validation and still pass the same
economic, concentration, and evidence rules before it can be ranked.

Only a fully ranked historical-validation passer may consume 2026-08..12. The
future blind must pass base/stress profitability, at least four of five positive
base months, at least 30 cumulative closed positions, leave-best positivity,
Spot-only, exclusivity, and reproducibility before paper-shadow review is even
considered.

No tool may call `promotion_review.py`, change SourcePolicy, resume testnet,
load credentials, start a live runner, or authorize real trading.

## Opened-data execution note

After commit `bd81db8`, 2024 and 2025 audits passed for all three symbols: exact
527040/525600 rows, zero duplicate timestamps, zero missing or irregular minute
steps, and exact cross-asset timestamp alignment. The first single-instrument
bundle batch was invalidated before tournament scoring because the runner fed
every same-source event from the shared store to each instrument strategy. For
example, an ETH runner executed a SOL `buy` lineage row.

This is execution plumbing, not a candidate result. The strategy wrapper now
fail-closes an event whose `symbol.venue` differs from its configured
`InstrumentId`, records `decision=skip` plus `instrument_mismatch`, and submits
no order. No candidate parameter, fold, sizing rule, gate, or holdout changed.
The invalid bundles remain excluded; development must be rerun from the safety
fix's clean commit.

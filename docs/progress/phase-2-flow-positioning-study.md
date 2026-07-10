# Phase 2 Flow and Positioning Study

- **Status**: Opened-data development complete; no candidate progressed
- **Locked on**: 2026-07-10
- **Universe**: BTCUSDT, ETHUSDT, SOLUSDT Spot holdings
- **New inputs**: Spot taker-buy quote volume and USD-M perpetual funding rate
- **Parameter search**: None
- **Opened-data folds**: 2024-2025 fixed development
- **Historical reserve**: 2020-2023 remains absent
- **Future blind reserve**: 2026-08-01 through 2026-12-31
- **Policy effect**: None; research/backtest only

## Why this is a new study

The closed BTC-only and multi-asset tournaments used price, OHLCV, trend,
volatility, or ordinary aggregate volume. This study does not tune those failed
fingerprints. It introduces two previously uninspected data drivers:

1. aggressive buyer share from Binance Spot kline
   `taker_buy_quote_asset_volume / quote_asset_volume`;
2. Binance USD-M perpetual funding as a positioning/crowding proxy while all
   actual holdings remain unlevered Spot long/cash.

The existing 2024-2025 raw Spot ZIPs physically contain taker-flow columns, but
no feature value, aggregate, distribution, signal, or result may be computed or
viewed until this protocol, loaders, synthetic tests, and gates are committed.
Only a funding archive URL HEAD check was made. No funding file was downloaded.

Binance's official public-data repository documents the Spot kline quote-volume
and taker-buy quote-volume columns and daily/monthly archive process:
<https://github.com/binance/binance-public-data>. Funding archives use the
official checksum-paired path
`data/futures/um/monthly/fundingRate/<SYMBOL>/`.

## Locked candidates

### 1. Weekly taker-flow continuation rotation

- **Identity**: `rule_taker_flow_rotation_v1 / buyshare7d-ret20-weekly-cash-v1`
- On Monday, aggregate quote volume and taker-buy quote volume over the previous
  seven completed UTC days.
- Compute each asset's previous-completed-day 20-day close return.
- An asset is eligible only when its seven-day taker-buy share is greater than
  the neutral 0.50 boundary and its 20-day return is positive.
- Hold the eligible asset with the highest taker-buy share; otherwise hold cash.
- Thesis: persistent aggressive buying confirmed by positive price direction is
  more informative than ordinary volume or return rank alone.

### 2. Four-hour flow-exhaustion reversal

- **Identity**:
  `rule_flow_exhaustion_v1 / retq10-180-buyshare0.40-vol2x-exit12h-4h-v1`
- Aggregate raw 1m rows into completed UTC-aligned 4h bars.
- From cash, an asset is eligible when the completed bar return is at or below
  the 10th percentile of the preceding 180 completed 4h returns, taker-buy share
  is at or below 0.40, and quote volume is at least 2x the preceding 42-bar
  median.
- If multiple assets qualify, hold only the asset with the most negative bar
  return.
- Exit after three subsequent 4h bars (12h maximum) or at the first completed
  bar whose taker-buy share recovers to at least 0.50.
- Thesis: an unusually forceful, high-volume seller-initiated flush can exhaust
  short-horizon supply and mean-revert. The adaptive return quantile avoids a
  price-level-specific bps threshold.

### 3. Weekly funding-crowding rotation

- **Identity**:
  `rule_funding_crowding_rotation_v1 / ret90-funding7d-z30lt1.5-weekly-cash-v1`
- Aggregate each asset's USD-M funding observations to completed UTC-day means.
- On Monday, compute previous-completed-day 90-day Spot return, preceding 7-day
  average funding, and its z-score against the preceding 30 daily funding means.
- An asset is eligible only when its 90-day return is positive and funding
  z-score is no greater than +1.5.
- Hold the eligible asset with the highest 90-day return; otherwise hold cash.
- Thesis: positive medium-term demand can persist, but unusually crowded
  positive funding is an adverse selection warning rather than extra alpha.
- The strategy never trades a future, earns funding, uses leverage, or shorts.

All three sources emit state-changing `SignalEvent v1` rows only. Every fold
initializes from cash at its first eligible decision. Signals use current
completed-bar information and execute no earlier than that bar's event time.

## Data contract and fail-closed audit

The locked source period is 2024-01-01 through 2025-12-31:

- reuse the existing Binance Spot monthly 1m ZIPs only for their documented raw
  flow columns;
- download exactly 24 monthly USD-M funding ZIPs per symbol with their official
  `.CHECKSUM` files and verify SHA-256 before parsing;
- reject missing/duplicate/non-finite timestamps or feature values;
- require exact, aligned daily Spot coverage across the three symbols;
- require at least one funding observation on every UTC day and no semantic
  funding gap above eight hours; permit at most 60 seconds of archive timestamp
  publication jitter around the scheduled interval. Exact cross-symbol funding
  timestamps are reported but not required because intervals can change by symbol;
- require taker-buy share in [0, 1] and absolute funding rate no greater than
  the defensive 0.10 sanity ceiling;
- record deterministic Spot-flow and funding fingerprints before signals run.

No 2020-2023 or 2026 archive may be downloaded for this development screen.

## Folds, sizing, and execution

Use the same four fixed five-month folds:

1. 2024-01-01 through 2024-05-31;
2. 2024-08-01 through 2024-12-31;
3. 2025-01-01 through 2025-05-31;
4. 2025-08-01 through 2025-12-31.

June/July may provide feature warm-up but produce no scored signals. Quantities
remain the previously locked approximately 50 USDT per symbol/fold values from
the multi-asset study; they are not recalculated from feature results.

Each source/fold/asset runs twice through NautilusTrader CASH/NETTING with
100000 USDT starting balance. The shared SignalStore is safe only with the
committed `instrument_mismatch` guard. `multi_asset.review.v1` must reconstruct
at most one concurrent target asset from raw lineage.

Costs remain gross 0/0, base 10/2, and stress 10/5 bps fee/slippage per fill.

## Anti-overfit gate

Every condition is required:

1. aggregate gross, base, and stress PnL are positive;
2. base and stress are each positive in at least 3/4 folds;
3. at least 12/20 natural months have positive base PnL;
4. aggregate base PnL remains positive after removing the single best
   base-cost position across every asset/fold;
5. every duplicate run reproduces exactly and has zero shorts, data gaps,
   invalid lineage, kill-switches, unexplained fills, or portfolio overlap;
6. at least 30 closed positions are required for `development_pass`.

An economic passer with 12-29 positions is only
`development_watchlist`: it may add fixed 2020-2023 historical evidence solely
to resolve sample size, cannot be ranked, and cannot consume 2026. Fewer than 12
positions is `insufficient_evidence`. Only strict passers are ranked by minimum
fold base PnL, aggregate stress PnL, then positive base months.

No parameter, sign, ranking field, or threshold may change after the first real
feature value is viewed. A change requires a new model version and a new
untouched holdout. No tool may mutate SourcePolicy, call promotion review,
resume testnet, load credentials, or authorize live trading.

## Opened-data audit note

After pre-data commit `6336585`, all 72 locked 2024-2025 funding archives and
official checksums downloaded successfully. The first 2024 audit found exact
366-day Spot/funding coverage, 1098 funding rows per asset, no duplicates, and
identical funding timestamps. It initially failed only because archive funding
timestamps carry roughly 13 milliseconds of publication jitter, producing a
measured 8.0000036-hour maximum interval. The audit now permits at most 60
seconds of timestamp jitter around the locked eight-hour semantic interval while
still requiring complete daily coverage. No signal formula or model parameter
changed, and no signal was generated before this audit correction was committed.

## Recorded outcome

The clean tournament completed 72 Nautilus bundles covering 36
source/fold/asset pairs twice. Every duplicate reproduced, all 12 portfolio
folds were exclusive and blocker-free, and no short exposure occurred.

Taker-flow rotation was aggregate-positive under base/stress costs but won only
2/4 folds and 7/20 months, had 23 positions, and is therefore rejected despite
remaining +2.476147 USDT after removing its best position. Flow exhaustion and
funding crowding were aggregate-negative. Ranking is empty and recommendation
is `no_candidate_progresses`; 2020-2023 and 2026 remain untouched.

Full evidence:
[`2026-07-10-flow-positioning-development-review.md`](../retros/2026-07-10-flow-positioning-development-review.md).

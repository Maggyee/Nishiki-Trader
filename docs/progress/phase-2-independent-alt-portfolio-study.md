# Phase 2 Independent Alt Portfolio Replication Study

- **Status**: Pre-registered; BNB/XRP/ADA price data not viewed
- **Locked on**: 2026-07-10
- **Universe**: BNBUSDT, XRPUSDT, ADAUSDT Spot
- **Candidate count**: Two
- **Parameter search**: None
- **Warm-up**: 2023 daily bars only, never scored
- **Development**: 2024-2025 fixed folds
- **Historical validation reserve**: 2020-2022, currently absent
- **Future blind reserve**: 2026-08-01 through 2026-12-31
- **Policy effect**: None; research/backtest only

## Purpose and multiple-testing boundary

Repeated experiments on the opened BTC/ETH/SOL 2024-2025 sample would turn the
research process into result mining. This study therefore moves to a fully
independent, previously unopened opportunity set and limits the family to two
classical portfolio hypotheses. It is a cross-universe replication test, not a
search for a threshold that fixes prior failures.

BNB, XRP, and ADA are fixed before any archive is downloaded. HEAD requests
confirmed that the official Binance January 2024 monthly 1m archives and January
2023 monthly 1d warm-up archives exist; no response body or price was read.

## Locked candidates

### 1. Diversified absolute-momentum basket

- **Identity**:
  `rule_alt_diversified_momentum_v1 / bnb-xrp-ada-ret90-weekly-equal16-v1`
- Every Monday, independently compute each asset's return from the close 90 days
  earlier to the previous completed UTC-day close.
- Hold each asset whose return is positive; otherwise hold that asset flat.
- The portfolio may hold zero to three assets simultaneously.
- Each active asset has an approximately 16 USDT fixed target, so maximum
  planned total notional is 48 USDT rather than increasing risk with breadth.
- Thesis: independent time-series momentum diversified across mature altcoin
  return paths should be less concentrated than selecting the single winner.

### 2. Positive-momentum low-volatility rotation

- **Identity**:
  `rule_alt_low_vol_rotation_v1 / bnb-xrp-ada-ret90-lowvol30-weekly-cash-v1`
- Every Monday, require positive previous-day 90-day return.
- Among eligible assets, hold the one with the lowest standard deviation of the
  preceding 30 completed daily returns; if none qualify, hold cash.
- Maximum one active asset and approximately 50 USDT target notional.
- Thesis: within a positive-trend set, the least volatile asset may preserve
  trend exposure while reducing crash and turnover concentration.

All features use only previous completed days. The first valid decision in each
fold initializes from cash. Both sources emit only state-changing long/flat
`SignalEvent v1` rows and never encode quantity, leverage, future orders, or
short exposure.

## Data and warm-up contract

Only after the pre-data commit:

- download Binance Spot monthly 1d archives for 2023-01-01 through 2025-12-31;
- use 2023 exclusively for 90-day/30-day warm-up and never include it in PnL;
- download/import monthly 1m archives for 2024-01-01 through 2025-12-31 into the
  Nautilus catalog;
- require 1096 exact aligned daily rows across 2023-2025, finite OHLC/volume,
  zero duplicate days, and deterministic fingerprints;
- require exact 527040/525600 per-asset 1m rows in 2024/2025, zero duplicate or
  missing minutes, and exact cross-asset timestamp alignment.

Do not download 2020-2022 or 2026 unless a later gate explicitly authorizes it.

## Folds, sizing, and execution

The four development folds remain:

1. 2024-01-01 through 2024-05-31;
2. 2024-08-01 through 2024-12-31;
3. 2025-01-01 through 2025-05-31;
4. 2025-08-01 through 2025-12-31.

June/July provide only warm-up. Quantities are fixed per symbol/fold from the
first observed 1m close:

```text
rotation_quantity = floor((50 / first_close) / size_increment) * size_increment
basket_quantity   = floor((16 / first_close) / size_increment) * size_increment
```

BNB size increment is 0.001; XRP and ADA increments are 0.1. The formula is
applied mechanically before any PnL is inspected.

Every source/fold/asset runs twice in NautilusTrader CASH/NETTING with 100000
USDT starting balance. `multi_asset.review.v1` reconstructs raw lineage and
requires maximum concurrency one for low-vol rotation and three for diversified
momentum. A concurrency breach, cross-symbol execution, unexplained fill, or
dirty/non-reproducible bundle blocks the portfolio.

Costs remain gross 0/0, base 10/2, and stress 10/5 bps fee/slippage per fill.

## Conservative gate

Each candidate must satisfy all conditions:

1. aggregate gross, base, and stress PnL are positive;
2. base and stress are each positive in at least 3/4 folds;
3. at least 12/20 natural months have positive base PnL;
4. aggregate base stays positive after removing the best base-cost position;
5. every duplicate run reproduces exactly with zero shorts/blockers and within
   its pre-registered portfolio concurrency limit;
6. at least 30 closed positions for `development_pass`.

An otherwise economic passer with 12-29 positions is only
`development_watchlist`, cannot be ranked, and may use 2020-2022 only to resolve
sample size. Fewer than 12 is `insufficient_evidence`. Strict passers rank by
minimum fold base PnL, aggregate stress PnL, then positive base months.

Only a full historical-validation passer may consume the 2026 future blind or
enter paper-shadow review. No observed result permits changing the universe,
return sign, 90/30-day windows, weekly cadence, concurrency, or risk budget.

No tool may modify SourcePolicy, call promotion review, resume testnet, load
credentials, trade futures, or authorize live trading.

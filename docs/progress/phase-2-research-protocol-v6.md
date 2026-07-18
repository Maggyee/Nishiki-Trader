# Phase 2 Research Protocol v6 — Binance-native availability discovery

- **Opened**: 2026-07-18 as an independent discovery protocol.
- **Machine inventory**:
  `docs/progress/phase-2-research-v6-binance-availability.json`.
- **Status**: availability screen only; no candidate selected or registered.
- **Historical bodies/PnL**: unopened / not computed.
- **Trading effect**: none.

## Separation from Protocol v5

Protocol v6 is not a parameter-search continuation of v5. Curve carry and BVOL
relief remain rejected and frozen. Their data, rules, parameters, blind window,
signals and results cannot be reused to select a v6 rule.

This first step inspects only public interface descriptions, archive object-key
metadata and HTTP HEAD status. It does not open an archive or checksum body.
It does not derive a factor, inspect returns, generate a signal, run Nautilus,
or compute PnL.

## Official-source contract

Only Binance's current developer documentation, official public-data repository
and official data bucket were inspected. Binance documents daily/monthly public
archives, next-day daily publication, checksum siblings, and the possibility of
later archive replacements in its
[official public-data repository](https://github.com/binance/binance-public-data).
Current REST semantics come from the
[official USD-M market-data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).
Archive coverage observations come from the
[official Binance Data Collection bucket](https://data.binance.vision/).

An observed first and recent key is not a continuity claim. A future
pre-registration must define exact completeness gates before any body is
opened.

## Availability and independence inventory

| Route | Metadata coverage observed | Independence screen | Decision |
|---|---|---|---|
| USD-M `bookDepth`, BTC/ETH | 2023-01-01 through a HEAD-200 2026-07-17 daily key | Provisionally new order-book liquidity mechanism | Eligible for identity review |
| USD-M `metrics`, BTC/ETH | BTC from 2020-09-01; ETH from 2021-12-01; both HEAD-200 on 2026-07-17 | Open-interest may be distinct, but bundled positioning/taker fields can overlap rejected funding-crowding and taker-flow families | Hold for identity-overlap review |
| COIN-M `liquidationSnapshot`, BTC/ETH perpetuals | 2023-06-25 through 2024-10-14; 2026-07-17 is 404; no matching USD-M BTC prefix | Forced liquidation would be provisionally distinct | Reject: archive discontinued |
| USD-M `bookTicker`, BTC/ETH | 2023-05-16 through 2024-03-30; 2026-07-17 is 404 | Provisionally distinct spread/top-of-book mechanism | Reject: archive discontinued |
| USD-M ADL risk / insurance balance REST | Current public snapshot endpoints; standard archive-prefix probes returned zero keys | Provisionally distinct exchange-loss-absorption mechanism | Hold: forward-only, no historical archive |
| Option `EOHSummary`, BTC/ETH | 2023-05-18 through 2023-10-23; 2026-07-17 is 404 | Overlaps Protocol v2 option risk premium | Exclude: overlap and discontinued archive |
| Funding / premium / basis | Historical interfaces exist | Reopens rejected funding and curve families | Exclude: identity overlap |
| Spot/futures klines, trades, aggTrades | Official historical interfaces exist | Reopens rejected price, volume and taker-flow families | Exclude: identity overlap |
| v5 delivery curve / BVOL | Collector operational | Frozen rejected v5 identities | Exclude: v5 freeze |

The REST documentation also limits open-interest statistics to the latest one
month and global long/short and taker buy/sell histories to the latest 30 days.
The longer `metrics` archive namespace therefore needs a schema-only
qualification after, and only after, a non-overlapping identity is registered;
its body was not opened here.

## Current outcome

`usdm_book_depth_liquidity` is the only route that survives both the first
availability and independence screens. It is not yet a selected candidate.
No source name, model version, sign, aggregation, lookback, threshold, holding
rule, data window or review gate has been registered.

The next research decision is deliberately small: accept or reject order-book
liquidity as the v6 mechanism. If accepted, a separate pre-data commit must
freeze all of the following before any archive body is opened:

1. a new source/model identity unrelated to every v2-v5 and original-registry
   identity;
2. exact archive fields and a point-in-time aggregation rule;
3. BTC and ETH sleeve behavior, missing-data state and long/flat transition
   semantics;
4. immutable qualification, development, replication and future-blind windows;
5. checksum, continuity, publication-lag, cost, reproducibility, per-asset and
   concentration gates; and
6. the same Nautilus-only execution and `SignalEvent v1` bridge boundaries.

Until that pre-registration is committed and pushed, v6 remains metadata-only.
No historical body may be opened and no outcome may be viewed.

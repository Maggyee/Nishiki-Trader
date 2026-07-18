# 2026-07-18 Protocol v6 bookDepth mechanism identity review

- **Decision**: `accept_for_preregistration_only`.
- **Candidate**: `book_depth_imbalance`.
- **Economic identity**: resting limit-order liquidity-supply asymmetry.
- **Archive body/PnL**: unopened / not computed.
- **Trading-state effect**: none.

## Finding

USD-M `bookDepth` passes the economic-identity screen. The proposed factor
measures the imbalance of resting quote notional available on the bid and ask
sides of the futures limit order book. Resting liquidity is an offered supply
state before execution; it is not executed volume or taker direction, and the
candidate does not condition on price return, volatility, funding, open
interest, curve shape or any prior candidate result.

This decision authorizes one pre-data identity only. It does not assert that
the archive implements the presumed side/percentage semantics, that historical
rows are correct, or that the mechanism predicts Spot returns.

## Independence matrix

| Frozen family | Why v6 is not that family | Forbidden bridge back into it |
|---|---|---|
| Price technicals, trend, breakout, pullback, mean reversion, momentum | Factor contains no return, OHLC, moving average, breakout or volatility feature | No price direction/filter or parameter confirmation |
| Volume breakout and taker/flow studies | Resting limit orders are unexecuted liquidity; prior studies used executed volume and buyer-maker/taker fields | No trade, aggTrade, volume, OBV or taker-share field |
| Funding, positioning and open interest | Factor uses only cross-sectional bid/ask depth at a timestamp | No funding/OI/long-short filter or ensemble |
| Option premium, VIX and BVOL | Factor is quoted liquidity supply, not implied or realized volatility | No volatility state or relief overlay |
| Fixed-expiry basis and v5 delivery curve | Factor uses the perpetual order book, not expiry or index/futures basis | No basis, mark-index spread or contract roll field |
| Hashrate, USD and stablecoin macro/native factors | Factor is exchange microstructure, not network or macro activity | No macro confirmation or candidate weighting |

The original 16-candidate registry and Protocols v2-v5 remain frozen. The
shared BTC/ETH universe, Spot execution path, cost scenarios and evidence
calendar are governance controls, not reuse of a rejected signal mechanism.

## Locked economic rule

For each asset and complete order-book timestamp, use only quote `notional` at
the nearest archived percentage bands: negative one percent as bid and positive
one percent as ask. Compute:

`imbalance = (bid_notional - ask_notional) / (bid_notional + ask_notional)`

Take the median of all valid complete timestamp groups in the completed UTC
day. After the fixed two-day historical publication lag, the asset is `buy`
only when the daily median is strictly positive; otherwise it is `flat`.
Missing or invalid data is flat and is never forward-filled. BTC and ETH are
independent sleeves, and signals are emitted only on state changes.

The one-percent band is the nearest offered-liquidity band in the disclosed
archive grid, zero is the natural bid/ask symmetry point, and median is a
pre-data robust aggregation. No alternate band, threshold, mean/last snapshot,
lookback, sign or ensemble may be selected after access under this identity.

## Official evidence and disclosed uncertainty

Binance's current USD-M REST documentation defines `/fapi/v1/depth` as the
symbol order book and returns bid/ask `[price, quantity]` levels. It also notes
that RPI orders are excluded. Binance's public-data repository documents daily
archive timing, checksums and possible later replacements, but does not define
the `bookDepth` CSV or state that it is a direct `/fapi/v1/depth` replay.

An unresolved public issue in Binance's official repository displays the CSV
header `timestamp,percentage,depth,notional` and reports possible 2025 price
misalignment. Documentation search exposed example rows in that issue. No
displayed value, date or outcome was used to choose the band, sign, aggregation,
threshold, window or gate. The disclosure instead creates a hard requirement
to prove archive semantics and mark-price consistency during qualification.

References:

- <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data>
- <https://github.com/binance/binance-public-data>
- <https://github.com/binance/binance-public-data/issues/431>

## Acceptance conditions and stop rule

The machine protocol, provider contract and fingerprint file freeze identity,
fields, formula, parameters, windows, costs and gates. The exact 2026-07-17
qualification body may be opened only after this pre-registration commit is
pushed. Both BTC and ETH must prove the exact schema/grid, full timestamp-group
structure, side mapping and mark-price band consistency with immutable
checksum/vintage lineage.

Any ambiguity or failure returns `blocked_provider_qualification` before a
factor, signal, return, Nautilus run or PnL. It cannot be repaired within v6 by
changing the percentage band, relaxing the 1% audit tolerance, deleting rows,
interpolating data or substituting another order-book feed.

## Boundaries

This review opened no Binance archive or checksum body, generated no factor or
SignalEvent, computed no return/PnL, ran no Nautilus backtest, loaded no
credential, changed no SourcePolicy, and did not resume testnet or live work.

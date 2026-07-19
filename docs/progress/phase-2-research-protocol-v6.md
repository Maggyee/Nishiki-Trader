# Phase 2 Research Protocol v6 — Binance book-depth imbalance

- **Opened**: 2026-07-18 as an independent discovery protocol.
- **Machine inventory**:
  `docs/progress/phase-2-research-v6-binance-availability.json`.
- **Machine protocol**: `docs/progress/phase-2-research-protocol-v6.json`.
- **Provider contract**:
  `docs/progress/phase-2-research-v6-data-sources.json`.
- **Candidate fingerprints**:
  `docs/progress/phase-2-research-v6-candidate-fingerprints.json`.
- **Status**: one mechanism identity accepted and pre-registered; the immutable
  one-day qualification collector and synthetic audit suite are implemented,
  while provider-body access has not started.
- **Historical bodies/PnL**: unopened / not computed.
- **Trading effect**: none.

## Separation from Protocol v5

Protocol v6 is not a parameter-search continuation of v5. Curve carry and BVOL
relief remain rejected and frozen. Their data, rules, parameters, blind window,
signals and results cannot be reused to select a v6 rule.

The availability step inspected only public interface descriptions, archive
object-key metadata and HTTP HEAD status. The later identity review and
pre-registration used documentation only. Neither step opened an archive or
checksum body, derived a factor value, inspected returns, generated a signal,
ran Nautilus, or computed PnL.

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

An observed first and recent key is not a continuity claim. The current
pre-registration therefore freezes exact completeness gates before any body is
opened. The machine inventory remains the timestamped discovery snapshot; its
empty-selection fields describe the state before this identity review.

## Availability and independence inventory

| Route | Metadata coverage observed | Independence screen | Decision |
|---|---|---|---|
| USD-M `bookDepth`, BTC/ETH | 2023-01-01 through a HEAD-200 2026-07-17 daily key | Independent resting-liquidity mechanism, subject to archive-semantics qualification | Selected and pre-registered after identity review |
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

## Mechanism identity decision

The dated identity review is
`docs/retros/2026-07-18-research-v6-book-depth-identity-review.md`. It accepts
resting limit-order liquidity-supply asymmetry as economically independent of
the frozen price, OHLCV, trade/taker-flow, funding/positioning, option/BVOL,
and fixed-expiry curve families. Acceptance means only that one fixed identity
may be pre-registered. It is not evidence that the archive is correct or that
the candidate has alpha.

The locked identity is:

- candidate: `book_depth_imbalance`;
- source: `rule_binance_book_depth_imbalance_v1`;
- model version:
  `btc-eth-usdm-bidask1pct-daily-median-lag2-v1`;
- universe: independent BTCUSDT and ETHUSDT Spot sleeves, each using its
  corresponding USD-M perpetual `bookDepth` archive as a factor only;
- factor fields: `timestamp`, `percentage`, `depth`, `notional` with an exact
  percentage grid of `-5..-1,+1..+5`;
- snapshot factor: quote-notional imbalance at the nearest one-percent bands,
  `(bid[-1] - ask[+1]) / (bid[-1] + ask[+1])`;
- daily factor: median across every valid complete timestamp group in the
  completed UTC day;
- availability: fixed two-day historical lag; forward data no earlier than
  the first UTC boundary after actual retrieval;
- signal: `buy` only when the eligible daily factor is strictly positive;
  zero, invalid, or missing data is `flat`; and
- output: `SignalEvent v1` on state changes only, with no execution fields.

The one-percent band is the nearest archived band and the zero threshold is
the mechanism's natural symmetry point. The daily median is fixed before body
access to prevent a small number of intraday depth snapshots from selecting
the state. There is no lookback grid, percentile fit, sign reversal, price
filter, taker-flow confirmation, or cross-asset netting.

## Provider qualification blocker

Binance's current USD-M REST specification confirms that an order book is
resting bid/ask price and quantity, but its official public-data README does
not document how the derived `bookDepth` CSV maps to that endpoint. A public
issue in Binance's own repository discloses the header
`timestamp,percentage,depth,notional` and reports historical rows whose implied
prices may be misaligned. That issue is a risk disclosure, not a schema or
quality guarantee, and none of its displayed values selected the v6 rule.

The pre-registered provider qualification therefore fails closed unless both
BTC and ETH pass all of these checks on data date 2026-07-17:

- exact official ZIP and checksum, locked columns and percentage grid;
- complete timestamp groups, at most a 15-minute intraday gap, and near-full
  UTC-day span;
- negative/positive percentages proven to map to bid/ask sides;
- `notional / depth` side and percentage-band sanity against the same-minute
  official 1m mark-price archive with the locked 1% tolerance; and
- immutable raw bytes, HTTP metadata, retrieval time, hashes, Parquet and
  conflict behavior.

Mark price is qualification audit data only and can never enter the candidate
factor. Any unproven archive semantics, schema drift or mark-price consistency
failure produces `blocked_provider_qualification` before factors, signals,
returns or PnL. It cannot be repaired by interpolation, row deletion, a wider
tolerance or an alternate interpretation under this identity.

## Frozen evidence windows and gates

- 2026-07-17: schema/semantics/lineage/coverage qualification only; no signal
  or PnL.
- Six fixed five-month development folds: Jan-May and Aug-Dec of 2023, 2024
  and 2025. At least five must be base/stress positive; at least 18/30 months,
  both asset sleeves, aggregate gross/base/stress, 30 total positions, 15 per
  asset and leave-best base PnL must pass. Each asset/fold needs at least 95%
  valid days.
- 2026-08..12: sealed final future blind. Passing requires positive base and
  stress in aggregate and in each sleeve, 4/5 positive months, 30 positions,
  positive leave-best PnL and stronger drawdown efficiency than the same-size
  equal-weight buy-and-hold benchmark.
- 2027 Jan-May: mandatory second future confirmation after any 2026 pass,
  because no 2020-2022 `bookDepth` archive reserve exists.

Every backtest must run twice through NautilusTrader with exact sidecar and
lineage reproduction. Costs remain gross `0/0`, base `10/2`, and stress `10/5`
fee/slippage bps per fill. BTC and ETH cannot mask one another: each sleeve
must pass its own cost gate.

## Qualification collector implementation

`apps/ops/research_v6_book_depth.py` is a separate, credential-free v6-only
entrypoint for the exact 2026-07-17 BTC/ETH qualification. It exposes only the
fixed `--download`, offline `--dry-run`, and offline `--verify` actions. Each
asset envelope retains the bookDepth and mark-price ZIP/checksum bytes, HTTP
metadata, retrieval timestamps, content hashes, strict audit summary and one
single-row audit Parquet. It does not calculate or store the registered factor,
daily aggregation, state, signal, return, or PnL.

Successful HTTP 200 response bytes are published atomically before later
requests or validation. Reruns consume saved responses first; timeout/5xx may
only fill missing responses. A saved 4xx blocker, checksum/schema/semantic
failure, tamper, or different-content conflict cannot be retried into a new
interpretation. The isolated `infra/research-v6/` image carries a commit label
and internal SHA marker and has separate writable-download and network-none,
read-only offline services. It deliberately has no systemd timer.

## Next entrypoint

Push the exact clean collector/image commit, deploy that SHA to an isolated
detached cloud checkout, and run the network-disabled dry-run against an empty
data root. Then open the exact 2026-07-17 bookDepth and mark-price qualification
bodies once. Historical development, factors, signals and PnL remain closed
until both assets pass and a qualification retro is committed and pushed.

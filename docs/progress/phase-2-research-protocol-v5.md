# Phase 2 Research Protocol v5 — Binance-native mechanism restart

- **Frozen**: 2026-07-17, before any curve-carry or BVOL historical archive body was opened.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v5.json`
- **Provider contract**: `docs/progress/phase-2-research-v5-data-sources.json`
- **Candidate fingerprints**: `docs/progress/phase-2-research-v5-candidate-fingerprints.json`
- **Status**: pre-registered implementation and synthetic validation only.
- **Trading effect**: none.

## Scope and separation from prior research

Protocol v5 starts exactly two new Binance-native candidates for BTCUSDT and
ETHUSDT Spot. The prior 16-candidate registry and Protocols v2/v3/v4 stay
frozen. v5 does not reuse their identities, retune a rejected rule, substitute
a provider under an old identity, or construct a PnL-selected ensemble.

Both assets are independent sleeves. Each fold targets approximately 50 USDT
per asset using the first Spot close and the instrument size increment. At most
two sleeves may be long simultaneously and their combined initial target
notional may not exceed 100 USDT. The only allowed state is long or flat;
NautilusTrader remains the sole backtest/execution engine.

## Locked candidates

### Binance delivery-curve carry

Identity:

- `rule_binance_curve_carry_v1`
- `btc-eth-front-next-positive-steep-daily-v1`

For each asset and UTC data day, select the nearest two USDⓈ-M quarterly
delivery contracts whose suffix-derived 08:00 UTC expiry is still after the
decision boundary. Using only the previous complete UTC day's contract and
index closes, compute:

`annualized_basis = (futures_close / index_close - 1) * 365 / days_to_expiry`

Emit `buy` only when front and next annualized bases are both strictly positive
and the next basis is not below the front. Zero is flat. This is a new v5
reconstruction and does not replace the frozen Protocol v2 basis identity.

### Binance BVOL relief

Identity:

- `rule_binance_bvol_relief_v1`
- `btc-eth-bvol5d-negative-daily-lag2-v1`

For BTCBVOLUSDT and ETHBVOLUSDT, retain the last valid index observation of
each UTC day. Historical replay uses a fixed two-day publication lag. Forward
rows cannot become eligible before the first UTC boundary after actual
`retrieved_at`. Emit `buy` only when the current value minus the value five
valid observations earlier is strictly negative. Zero is flat.

Missing days, duplicates, and non-finite observations are never forward-filled.
A missing day prevents entry and changes an existing long state to `flat`.

Both generators emit `SignalEvent v1` only on state changes. Metadata includes
the data day, availability and retrieval times, vintage and snapshot hashes,
raw-file hashes, contract/expiry lineage where applicable, factor values,
parameters, and the locked `features_hash`. Signals contain no size, leverage,
order type, stop, target, or other execution field.

## Immutable Binance collection

The only data sources are unauthenticated Binance public REST and official
`data.binance.vision` archives. Each archive requires its official checksum.
The collector preserves exact ZIP/checksum bytes, HTTP metadata,
`retrieved_at`, content hashes, an audit report, and normalized Parquet.

Identical content is idempotent. Changed upstream content creates a separate
vintage and a comparison-blocking marker; old bytes are never overwritten.
Dry-run mode performs no network request and writes no file. Collection never
generates a signal or PnL.

Spot execution data is BTCUSDT/ETHUSDT official 1m archive data imported into
the existing Nautilus catalog. No Binance key, testnet credential, live
credential, or third-party/paid dataset is allowed.

## Evidence partitions and review gates

Curve carry fast-track reconstruction uses 2021-06 through 2022-12 data and
scores three five-month folds: 2021 Aug-Dec, 2022 Jan-May, and 2022 Aug-Dec.
Aggregate gross/base/stress, every fold's base/stress, both sleeves' aggregate
base/stress, at least 9/15 base-positive months, at least 30 closed positions,
and leave-best-position base PnL must all be positive.

BVOL fast-track is diagnostic only. It uses 2023-06 through 2025-12 data and
scores 2023 Aug-Dec plus the Jan-May and Aug-Dec folds of 2024 and 2025. At
least 4/5 folds must have positive base and stress, at least 15/25 months must
be base-positive, and the same asset, sample, concentration, lineage, and
reproducibility gates apply. A diagnostic pass cannot promote the candidate.

July 2026 is schema, lineage, publication-lag, and cloud-collection
qualification only; PnL is forbidden. August-December 2026 is the common final
future blind and cannot be opened before it finishes. A future candidate must
have positive base/stress, at least 4/5 base-positive months, positive
base/stress in each sleeve, at least 30 closed positions, positive base PnL
after removing the best position, lower maximum drawdown than equal-weight
same-size buy-and-hold, and a better return/drawdown ratio when the benchmark is
profitable. BVOL additionally needs a locked 2027 Jan-May confirmation before
paper-shadow review because no 2020-2022 BVOL history exists.

Every asset/fold backtest runs twice. Orders, fills, positions, lineage, monthly
metrics, and gates must reproduce exactly. Commission is added back once before
deducting the frozen gross/base/stress modeled costs.

## Fixed workflow and boundaries

1. Commit and push this protocol, contracts, implementation, fingerprints, and
   synthetic tests before opening historical bodies.
2. From that clean commit, run one-day July schema/lineage qualification and
   record a retro in a second commit.
3. Only after qualification passes may historical bodies be opened for the
   fast tracks.
4. After fast-track reports are committed, deploy a separate idempotent daily
   read-only collector. Do not open blind PnL before 2026-12-31.

The tools can only recommend the locked outcomes. They do not call
`promotion_review.py`, mutate SourcePolicy, restore testnet continuity, load
credentials, start a live runner, or place an order. The current project-level
`stop_before_testnet_resume` remains in force.

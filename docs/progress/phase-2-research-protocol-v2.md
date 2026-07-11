# Phase 2 Research Protocol v2

- **Frozen**: 2026-07-11, before accessing any real option-surface, fixed-expiry
  basis, or point-in-time stablecoin factor body.
- **Machine contract**: `docs/progress/phase-2-research-protocol-v2.json`
- **Status**: pre-registered; implementation and synthetic validation only.
- **Trading effect**: none.
- **Provider contract**: `docs/progress/phase-2-research-v2-data-sources.json`.

## Why research may resume

The 16-candidate program stop rule remains valid for price/volume/funding
variants tested on opened 2024-2025 samples. Protocol v2 does not reopen those
families. It fixes three new data-generating mechanisms before data access:

1. option-implied risk compensation from a structural risk-neutral return model;
2. fixed-expiry futures term structure, not perpetual funding;
3. point-in-time stablecoin supply and transfer activity.

The option candidate follows external evidence that variance alone is
insufficient and higher risk-neutral moments add information. The implementation
therefore consumes only a fully attributed structural replication output; a
plain historical-volatility or ATM-IV threshold is invalid. The Deribit public
historical-volatility endpoint is not an acceptable substitute for an archived
option surface.

References:

- Atanasova et al., *What Do Crypto Options Tell Us? Risk Premia Implied by BTC
  Option Prices*: <https://ssrn.com/abstract=6410838>
- Deribit public historical-volatility interface:
  <https://docs.deribit.com/api-reference/market-data/public-get_historical_volatility>

## Evidence partitions

- 2023-2025 is opened and diagnostic-only. No PnL-based selection is allowed.
- 2020-2022 is a one-opening historical replication reserve.
- July 2026 may qualify schemas, publication lag, lineage, and freshness only;
  PnL access is forbidden.
- August-December 2026 is the final future blind. Opening it freezes every
  candidate forever; any parameter change requires a new identity and a new
  future sample.

No candidate may use an opened interval to choose a sign, threshold, lookback,
universe, or ensemble weight. The locked pool contains exactly three candidates.

## Point-in-time input contract

Every observation must carry:

- a unique, strictly increasing UTC `ts_event` at daily frequency;
- `available_at <= ts_event`;
- a non-empty provider `vintage_id`;
- an immutable `sha256:<64 lowercase hex>` snapshot fingerprint;
- finite required numeric factors;
- no forward-filled missing day.

An option row additionally carries a `replication_spec_hash` and decomposes its
expected excess return into intercept, variance, higher-moment, and
volatility-of-volatility contributions. The decomposition must add back exactly
within numerical tolerance. This makes an unexplained vendor score fail closed.

Stablecoin history must be genuine point-in-time vintages. A present-day API
response that rewrites historical classifications is invalid even if its rows
look complete.

The provider contract deliberately separates forward qualification from
historical eligibility. Current Deribit summaries, Binance's latest-30-day
basis API, and a present-day Coin Metrics history may be snapshotted from July
2026 onward, but none is allowed to stand in for the 2020-2022 point-in-time
replication reserve.

## Candidate rules

All candidates target BTCUSDT Spot and emit only `buy`/`flat` `SignalEvent v1`
rows on state changes. Every replication fold starts flat; an eligible first
in-fold observation must therefore emit `buy` rather than inheriting an
unobservable pre-fold position.

- **Option risk premium**: buy only when the locked structural replication's
  30-day expected BTC excess return is strictly positive.
- **Futures basis curve**: annualize front and next fixed-expiry bases using
  actual days to expiry; buy only when both are positive and the next annualized
  basis is not below the front.
- **Stablecoin liquidity**: buy only when aggregate supply grew over 30 days and
  the current seven-day transfer-volume sum exceeds the preceding seven days.

Zero is always flat. No threshold grid, percentile fitting, sign reversal,
symbol substitution, or PnL-selected combination is allowed.

## Gates and stop decisions

The exact gates live in the machine contract. In addition to positive base and
stress results, candidates need cross-year/month breadth, at least 30 closed
positions, positive leave-best-position PnL, clean long/flat lineage, and exact
rerun reproducibility.

After the one allowed historical opening:

- passing candidates become `replication_pass_pending_future_blind`;
- profitable but undersampled candidates become `insufficient_evidence`;
- every other candidate becomes permanently `reject`;
- no result-driven parameter or ensemble change is permitted.

Only a candidate that subsequently passes the locked five-month future blind
may be considered for `paper_shadow`. This protocol does not change
`SourcePolicy`, run promotion review, restart testnet, load credentials, or
authorize live trading.

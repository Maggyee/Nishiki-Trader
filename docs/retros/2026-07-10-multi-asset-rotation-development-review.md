# Multi-Asset Rotation Development Review

- **Date**: 2026-07-10
- **Pre-data protocol commit**: `bd81db8`
- **Cross-symbol execution guard commit**: `938d006`
- **Zero-activity review fix commit**: `b7c29d3`
- **Universe**: BTCUSDT, ETHUSDT, SOLUSDT Spot
- **Development folds**: 2024 Jan-May, 2024 Aug-Dec, 2025 Jan-May, 2025 Aug-Dec
- **Result**: No candidate progresses
- **Recommendation**: `no_candidate_progresses`
- **Policy/testnet effect**: None

## Executive conclusion

None of the three pre-registered multi-asset candidates is robust enough to
progress. Cross-sectional momentum and market breadth lose money before and
after modeled costs. ETH/BTC relative value has positive aggregate gross, base,
and stress PnL, but succeeds in only two of four folds, has only 7/20 positive
base months, and becomes negative after removing its best base-cost position.

The ranking is empty. No candidate qualifies even for the low-frequency
historical-evidence watchlist because all fail economic/robustness conditions,
not merely sample size. Per protocol, 2020-2023 is not imported and the
2026-08..12 future blind remains untouched.

## Data evidence

The ETHUSDT and SOLUSDT 2024-2025 monthly public archives were first opened only
after the protocol was committed. `catalog.audit.v1` passed both years for all
three assets.

| Year | Expected/actual rows per asset | Duplicates | Missing/irregular minutes | Cross-asset timestamps |
|---|---:|---:|---:|---|
| 2024 | 527040 / 527040 | 0 | 0 / 0 | exact match |
| 2025 | 525600 / 525600 | 0 | 0 / 0 | exact match |

OHLCV fingerprints:

| Asset | 2024 SHA-256 | 2025 SHA-256 |
|---|---|---|
| BTCUSDT | `f0453b9785900cbb0e5e129f4af2fa15bd42a89f586381a59de49e0fad32849b` | `d5740ad7dfd792644e700f6c8ccec9f1c063aa5a587ec12ea91da3e495514c0c` |
| ETHUSDT | `8af65ff4ed2e191cc10b405fb763b3b2574751d746e30d0a2796f4bbcba33cb5` | `e6260e06a24aa2443750449f42c7773a0fa98939325e39e1f5e77ba84a36bff8` |
| SOLUSDT | `94d001577d0c52367515895e130a7fcc232b836fe4f7fa237e3de4cfb2620f34` | `d96354c352947e2306c7db9e000d441a348d1da00ee76fe9fad6b5ccf8a3e1cf` |

## Fixed sizing

The pre-registered formula produced the following approximately 50 USDT target
quantities. These were shared by every source for the same asset/fold.

| Fold | BTC | ETH | SOL |
|---|---:|---:|---:|
| 2024 Jan-May | 0.001182 | 0.02190 | 0.491 |
| 2024 Aug-Dec | 0.000773 | 0.01547 | 0.291 |
| 2025 Jan-May | 0.000534 | 0.01497 | 0.263 |
| 2025 Aug-Dec | 0.000432 | 0.01352 | 0.290 |

## Evidence correction before scoring

The first 48-bundle batch was invalidated before tournament scoring. A shared
SignalStore was filtered by source/model but not instrument, so every
single-instrument strategy consumed other symbols' events. Raw ETH lineage, for
example, contained and executed a SOL `buy`. No PnL from that batch is used.

The execution wrapper was corrected to reject a SignalEvent when its
`symbol.venue` differs from the configured Nautilus InstrumentId. The event is
retained as `decision=skip`, reason `instrument_mismatch`, and cannot submit an
order. An end-to-end regression test covers the order-path boundary. No strategy
parameter, signal, fold, size, cost, gate, or holdout changed.

The post-guard evidence consists of 48 clean bundles: 24 fixed
source/fold/asset combinations run twice. All 24 duplicate pairs are exactly
reproducible under `alpha.review.v1`. Twelve `multi_asset.review.v1` folds have
zero short positions, no evidence blockers, and exact portfolio exclusivity.

## Fold results under base costs

| Candidate | 2024 Jan-May | 2024 Aug-Dec | 2025 Jan-May | 2025 Aug-Dec |
|---|---:|---:|---:|---:|
| Cross-sectional momentum | -17.807884 | +2.591848 | -4.669321 | -12.325562 |
| Market breadth | -5.120306 | +7.480318 | -1.354797 | -11.032312 |
| ETH/BTC relative value | +15.115372 | +24.444505 | -18.411243 | -5.159393 |

All values are USDT and include 10 bps modeled fee plus 2 bps modeled slippage
per fill, after adding back recorded commission as specified by
`alpha.review.v1`.

## Tournament result

| Candidate | Gross | Base | Stress | Base/stress winning folds | Positive base months | Positions | Base without best | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Cross-sectional momentum | -31.096937 | -32.210919 | -32.489414 | 1/4, 1/4 | 2/20 | 8 | -60.185643 | reject |
| Market breadth | -7.091201 | -10.027097 | -10.761071 | 1/4, 1/4 | 3/20 | 21 | -31.371933 | reject |
| ETH/BTC relative value | +18.423159 | +15.989241 | +15.380761 | 2/4, 2/4 | 7/20 | 18 | -3.309221 | reject |

The relative-value aggregate is not treated as a near-pass. It fails the 3/4
fold rule, the 12/20 month rule, the 30-position rule, and the leave-best
concentration rule. Its positive aggregate is therefore regime- and
trade-concentrated rather than sufficiently repeatable evidence.

## Decision and next research boundary

- Close all three model versions; do not tune their lookbacks, thresholds, or
  rebalance cadence on these results.
- Do not import 2020-2023 for these rejected fingerprints.
- Preserve 2026-08..12 as unseen future data.
- Do not call `promotion_review.py`, change SourcePolicy, resume testnet, or
  connect to an exchange.
- Before another candidate round, define a new economic hypothesis and a new
  model version. Prefer a small number of hypotheses that add a genuinely new
  return driver or opportunity set; do not mine more thresholds from the same
  three rules and opened folds.

The practical conclusion is to stop this branch, not to select the least-bad
strategy. Current evidence supports `stop_before_testnet_resume`.

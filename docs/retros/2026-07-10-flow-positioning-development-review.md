# Flow and Positioning Development Review

- **Date**: 2026-07-10
- **Pre-feature commit**: `6336585`
- **Funding-jitter audit fix**: `ffa7001`
- **Universe**: BTCUSDT, ETHUSDT, SOLUSDT Spot holdings
- **New inputs**: Spot taker-buy quote share and USD-M funding
- **Evidence**: 72 clean Nautilus bundles, 36 duplicate pairs, 12 portfolio folds
- **Result**: No candidate progresses
- **Recommendation**: `no_candidate_progresses`
- **Policy/testnet effect**: None

## Executive conclusion

None of the three new data-driver candidates passes the pre-registered
development screen. Funding-crowding rotation and four-hour flow exhaustion are
aggregate-negative. Weekly taker-flow rotation is aggregate-positive and stays
positive after removing its best position, but wins only two of four folds,
only 7/20 months are positive, and it closes 23 positions. Those are robustness
failures, not permission to relax the gate.

The ranking is empty. No source reaches `development_watchlist`, because the
taker-flow source fails economic consistency conditions in addition to having
fewer than 30 positions. 2020-2023 and 2026 remain unconsumed.

## Feature data audit

All 72 fixed monthly funding archives passed their official Binance SHA-256
checksum. `feature.audit.v1` passed both years with exact aligned Spot-day and
funding timestamp coverage.

| Year | Spot days/asset | Funding rows/asset | Funding days | Maximum observed gap | Blockers |
|---|---:|---:|---:|---:|---:|
| 2024 | 366 | 1098 | 366 | 8.0000036h | 0 |
| 2025 | 365 | 1095 | 365 | 8.0000044h | 0 |

The sub-second excess over eight hours is archive publication timestamp jitter.
The audit permits at most 60 seconds while retaining exact daily completeness,
duplicate, finite-value, and sanity-range checks.

Feature fingerprints:

| Asset | 2024 Spot flow | 2024 funding | 2025 Spot flow | 2025 funding |
|---|---|---|---|---|
| BTCUSDT | `5ffe409d75c51518...9764cecd` | `df58ead317f8ec4f...3cd17865` | `c5552651b846cc2c...58d1bcc` | `e9dc81d523b8459b...5613fd2` |
| ETHUSDT | `1f0283d035d4a44d...821dd00f` | `198c3c755f14d50e...5dce323a` | `474abf36ade5c4d3...2b5a08f` | `12c7a11ae9980cdf...60c911f` |
| SOLUSDT | `755ecbb2e24637fb...d82735f` | `6ffd24963e9a6e6f...d42c8d40` | `57b2b2b7d26b7bb...6c5b0aa` | `b1edf6507ba918cb...2d8469d7` |

## Signal and evidence volume

| Candidate | Fold event counts | Closed positions | Evidence outcome |
|---|---|---:|---|
| Taker-flow rotation | 13, 14, 9, 8 | 23 | exact duplicate reproduction |
| Flow exhaustion | 0, 2, 4, 8 | 7 | exact duplicate reproduction; sparse by design |
| Funding crowding | 5, 9, 9, 4 | 15 | exact duplicate reproduction |

Every asset/fold pair was run twice, including zero-activity assets. All 36
duplicate pairs reproduced, every portfolio fold was Spot long/flat with zero
blockers, and raw lineage proved at most one concurrent target asset.

## Base-cost fold results

| Candidate | 2024 Jan-May | 2024 Aug-Dec | 2025 Jan-May | 2025 Aug-Dec |
|---|---:|---:|---:|---:|
| Taker-flow rotation | -2.260185 | +17.331678 | +10.015342 | -1.581767 |
| Flow exhaustion | 0.000000 | +0.200868 | -0.578446 | -1.054019 |
| Funding crowding | -21.835863 | +14.028539 | -12.327501 | -1.456354 |

All values are USDT under 10 bps fee plus 2 bps slippage per fill.

## Tournament result

| Candidate | Gross | Base | Stress | Base/stress winning folds | Positive months | Positions | Base without best | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Taker-flow rotation | +26.812539 | +23.505068 | +22.678201 | 2/4, 2/4 | 7/20 | 23 | +2.476147 | reject |
| Flow exhaustion | -0.662289 | -1.431597 | -1.623924 | 1/4, 1/4 | 2/20 | 7 | -1.890541 | reject |
| Funding crowding | -19.456390 | -21.591179 | -22.124877 | 1/4, 1/4 | 3/20 | 15 | -37.888539 | reject |

Taker-flow rotation is not labeled insufficient evidence because it fails the
3/4 fold and 12/20 month economic gates. Its positive aggregate and leave-best
result are useful diagnostic evidence, not a promotable strategy.

## Decision

- Close all three source/model versions without tuning their flow thresholds,
  quantiles, funding windows, holding period, or rebalance cadence.
- Do not import 2020-2023 for these rejected fingerprints.
- Preserve 2026-08..12 as unseen future data.
- Keep SourcePolicy unchanged and testnet/live paths stopped.
- Do not construct a weighted ensemble by selecting the best opened candidates;
  that would convert observed performance into an unregistered optimizer.

The appropriate outcome is an empty ranking and continued
`stop_before_testnet_resume`, not selection of the least-bad strategy.

# Independent Alt Portfolio Development Review

- **Date**: 2026-07-10
- **Pre-data commit**: `1856236`
- **Universe**: BNBUSDT, XRPUSDT, ADAUSDT Spot
- **Warm-up**: 2023 daily bars only
- **Development folds**: 2024/2025 Jan-May and Aug-Dec
- **Evidence**: 48 clean Nautilus bundles, 24 duplicate pairs, 8 portfolio folds
- **Result**: No candidate progresses
- **Recommendation**: `no_candidate_progresses`
- **Policy/testnet effect**: None

## Executive conclusion

The independent-universe replication does not produce a robust candidate.
Diversified absolute momentum is aggregate-positive and remains positive after
removing its best position, but both 2025 folds lose money. It wins only 2/4
folds, has only 4/20 positive base months, and closes 27 positions. Low-volatility
rotation is aggregate-negative and also wins only 2/4 folds.

This result confirms that broadening the opportunity set does not remove the
observed regime concentration: the tested long/cash rules profit mainly in the
2024 altcoin advance and fail to retain that evidence in 2025. Ranking is empty;
2020-2022 and 2026 remain unconsumed.

## Data audit

The data was first downloaded after pre-data commit `1856236`.

- 2023-2025 daily archives: 1096 exact aligned rows per asset, zero blockers.
- 2024 1m catalog: 527040 exact rows per asset, zero duplicates/gaps.
- 2025 1m catalog: 525600 exact rows per asset, zero duplicates/gaps.
- Minute timestamps align exactly across BNB/XRP/ADA in both years.

Daily fingerprints:

| Asset | 2023-2025 daily SHA-256 |
|---|---|
| BNBUSDT | `07c3802d4e60a9d93c0f097e4df172806982816a9ffd4590c9d1da8a011f63c0` |
| XRPUSDT | `fa2a1e1b180d289b5c241ba38b1295ce0c4c5a2c4959d86ce704eb2fd99c2677` |
| ADAUSDT | `aabe5ece53a4ee5e3e0924ad23df5737c1f3ba6248b529ec5bf0a4675540731c` |

Minute fingerprints:

| Asset | 2024 SHA-256 | 2025 SHA-256 |
|---|---|---|
| BNBUSDT | `608b14699325999573fb2ec6180a5db2e35669ffe529dc6201a31e463363f7ed` | `1fe279af08fcf0bb7550ea6dbedec2f7fef9f5a467d19ffafdd4d2f5322efdbf` |
| XRPUSDT | `69821c5dc4f6b2e27abac29ff16b833ca26c0eb5bdcd04a594f993f57fe3ee92` | `50f9e13e18397ffb5c11888ca4dd3ada9d4f414dd04c925390d2ffdcd96d155e` |
| ADAUSDT | `0ac5a5101345082ef9443c1ec271474fed619881230c7ad12bab5fe45f04de0f` | `39f23db7f43f6fde19d9eaf56d7965005db471bfdaab6eadc87a5c9a3fdae663` |

## Fixed sizing

Diversified-momentum positions use approximately 16 USDT per active asset and
never exceed three assets. Low-vol rotation uses approximately 50 USDT and one
asset. Every quantity was floored to the pre-registered instrument increment
from the first 1m close in its fold before PnL was viewed.

Observed lineage concurrency was exactly within the locked limits: maximum
three for diversified momentum and one for low-vol rotation in every fold.

## Fold results under base costs

| Candidate | 2024 Jan-May | 2024 Aug-Dec | 2025 Jan-May | 2025 Aug-Dec |
|---|---:|---:|---:|---:|
| Diversified absolute momentum | +4.443742 | +62.878114 | -19.275644 | -3.981579 |
| Positive-momentum low-vol rotation | +20.761588 | +9.233956 | -38.346823 | -17.374337 |

All values are USDT after 10 bps fee plus 2 bps slippage per fill.

## Tournament result

| Candidate | Gross | Base | Stress | Winning folds | Positive months | Positions | Base without best | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Diversified absolute momentum | +45.142960 | +44.064632 | +43.795051 | 2/4 | 4/20 | 27 | +3.667917 | reject |
| Positive-momentum low-vol rotation | -23.513980 | -25.725617 | -26.278526 | 2/4 | 5/20 | 17 | -65.938660 | reject |

Diversified momentum is not a watchlist candidate: although its aggregate and
leave-best results are positive and it is near the 30-position threshold, it
fails the required 3/4 folds and 12/20 positive months. Treating 27 positions as
the only missing evidence would misstate the result.

## Decision

- Close both source/model versions without changing return windows, universe,
  weekly cadence, low-vol ranking, or concurrency budget.
- Do not consume 2020-2022 historical validation for rejected fingerprints.
- Preserve 2026 as future blind data.
- Do not create a fitted ensemble from the best opened strategies.
- Keep SourcePolicy/testnet/live state unchanged.

The correct screened set remains empty. Further candidate generation on the
same opened periods should stop until an independently justified data source or
new future sample exists.

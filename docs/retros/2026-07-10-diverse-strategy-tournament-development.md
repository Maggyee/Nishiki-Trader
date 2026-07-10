# Diverse Strategy Tournament — Opened-Data Development

- **Date**: 2026-07-10
- **Pre-registration commit**: `bcee304`
- **Scope**: Four distinct BTCUSDT Spot long/flat hypotheses, four fixed five-month folds
- **Decision**: No candidate progresses to historical validation
- **Tournament recommendation**: `no_candidate_progresses`
- **Policy effect**: None

## Decision

None of the four pre-registered candidates met the shared cost, regime,
month, sample, and concentration gates. Do not import the reserved 2020-2023
historical validation or consume 2026 data for these model versions.

The volatility-squeeze and volume-confirmed breakout sources are informative
watchlist references because their aggregate base/stress PnL stayed positive.
They are not selected strategies: both won only 2/4 folds, had too few
positions, and became negative after removing the single best trade.

## Tournament result

| strategy | gross total | base total | stress total | base-positive folds | base-positive months | positions | base without best | classification |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| oversold mean reversion | +5.302140 | -12.031668 | -16.365120 | 2/4 | 8/20 | 88 | -16.636277 | reject |
| volatility squeeze | +20.974140 | +15.666855 | +14.340034 | 2/4 | 8/20 | 26 | -1.037924 | reject |
| volume/OBV breakout | +20.651260 | +13.266385 | +11.420167 | 2/4 | 8/20 | 37 | -8.082295 | reject |
| dual momentum | +3.468760 | -0.773624 | -1.834220 | 2/4 | 2/20 | 21 | -29.682380 | reject |

The ranking is empty because ranking applies only after every development gate
passes. Aggregate PnL alone is not a selection rule.

## Fold details

| strategy/fold | gross | base | stress | positions | base-positive months |
|---|---:|---:|---:|---:|---:|
| mean reversion 2024 Jan-May | +3.953510 | +0.835716 | +0.056267 | 22 | 3/5 |
| mean reversion 2024 Aug-Dec | +4.856290 | +0.743490 | -0.284710 | 23 | 2/5 |
| mean reversion 2025 Jan-May | +0.759290 | -3.607801 | -4.699573 | 20 | 2/5 |
| mean reversion 2025 Aug-Dec | -4.266950 | -10.003073 | -11.437104 | 23 | 1/5 |
| volatility squeeze 2024 Jan-May | +5.423060 | +4.730034 | +4.556777 | 5 | 1/5 |
| volatility squeeze 2024 Aug-Dec | +17.305050 | +15.932218 | +15.589010 | 7 | 2/5 |
| volatility squeeze 2025 Jan-May | -2.087830 | -3.863123 | -4.306946 | 8 | 2/5 |
| volatility squeeze 2025 Aug-Dec | +0.333860 | -1.132274 | -1.498807 | 6 | 3/5 |
| volume breakout 2024 Jan-May | +4.858250 | +3.411529 | +3.049848 | 10 | 2/5 |
| volume breakout 2024 Aug-Dec | +28.283710 | +26.680081 | +26.279174 | 9 | 4/5 |
| volume breakout 2025 Jan-May | -8.707390 | -10.976860 | -11.544227 | 10 | 1/5 |
| volume breakout 2025 Aug-Dec | -3.783310 | -5.848365 | -6.364629 | 8 | 1/5 |
| dual momentum 2024 Jan-May | -10.615970 | -11.897591 | -12.217996 | 8 | 0/5 |
| dual momentum 2024 Aug-Dec | +19.216950 | +18.341555 | +18.122706 | 5 | 1/5 |
| dual momentum 2025 Jan-May | +2.984650 | +2.018533 | +1.777004 | 4 | 1/5 |
| dual momentum 2025 Aug-Dec | -8.116870 | -9.236121 | -9.515934 | 4 | 0/5 |

## Interpretation

- **Mean reversion** had a small pre-cost edge but deteriorated through 2025;
  realistic costs and the weak second year reject it.
- **Volatility squeeze** captured a few large 2024 expansions. Its 26-position
  sample and negative leave-best result show that the aggregate gain is too
  concentrated to treat as alpha.
- **Volume/OBV breakout** was strongest in the 2024 bull fold and negative in
  both 2025 folds. Volume confirmation did not remove regime dependence.
- **Dual momentum** behaved as expected for a slow allocation rule but had only
  21 positions, two positive months, and negative cost-adjusted aggregate PnL.

The common finding is not that every technical signal has zero information.
It is that BTC-only long/flat returns are concentrated in a few favorable
directional episodes and do not yet provide stable, cost-adjusted evidence
across regimes.

## Reproducibility and evidence

All 16 strategy/fold pairs were run twice. `compare_backtests` returned `MATCH`
for fills, orders, positions, and signal lineage in every pair. Every strict
review reports zero shorts, clean blockers, and reproducibility.

Primary evidence bundle identities (each has a matching duplicate run):

| strategy/fold | run id | manifest sha256 prefix | fills sha256 prefix |
|---|---|---|---|
| mean reversion 2024a | `20260710-113244Z-f118c9fb` | `7b0978574a3151e5…` | `9e4d202250095802…` |
| mean reversion 2024b | `20260710-113244Z-05fa0ed7` | `16f94463a55cd55a…` | `4fffb82d620eed7f…` |
| mean reversion 2025a | `20260710-113252Z-f6f5f2a4` | `4937e4c443ed5126…` | `67b722d8cd6974ac…` |
| mean reversion 2025b | `20260710-113252Z-20d4323a` | `b134c32a56508e89…` | `9556c8ba06b482d8…` |
| vol squeeze 2024a | `20260710-113259Z-ec411869` | `28b27058eec1056c…` | `83f56e729af80627…` |
| vol squeeze 2024b | `20260710-113259Z-0e91a69e` | `7bfaee751675352b…` | `303c6ee0f717ca13…` |
| vol squeeze 2025a | `20260710-113306Z-688b3e35` | `ec994bf75970d491…` | `bdf691d3f0a1a437…` |
| vol squeeze 2025b | `20260710-113306Z-d679dce5` | `9c7c50cb5b63d660…` | `fd7662720f4b2be3…` |
| volume breakout 2024a | `20260710-113314Z-66610634` | `27dd885193c6d596…` | `8f36087a74feb5a4…` |
| volume breakout 2024b | `20260710-113313Z-f80aebaf` | `8e6e738993a34115…` | `769cbead6dfde9f0…` |
| volume breakout 2025a | `20260710-113321Z-162d918c` | `0f719408df1cd94e…` | `a93b6de382b985ca…` |
| volume breakout 2025b | `20260710-113321Z-8ed2126b` | `55da14c6783d58bd…` | `7407eed3fbafc3de…` |
| dual momentum 2024a | `20260710-113329Z-82276474` | `13babf9523233e78…` | `237100711db4c707…` |
| dual momentum 2024b | `20260710-113329Z-0f3728ed` | `7828b341db529984…` | `2086e92d9421cf30…` |
| dual momentum 2025a | `20260710-113337Z-58091af8` | `648b11eb37253d65…` | `0ce92b31e0b227b5…` |
| dual momentum 2025b | `20260710-113337Z-4347b1bc` | `935632b86cf8a248…` | `bb4d64bb783f15b0…` |

Machine-readable artifacts remain gitignored under `data/tournament/`, with
`result.json` using `strategy.tournament.v1`.

## Next research boundary

Do not tune any of these four model versions and do not import the reserved
2020-2023 data for them. The next research round should expand the economic
opportunity set rather than add another BTC-only threshold: for example a
pre-registered multi-asset relative-strength/rotation study with independent
BTC, ETH, and one liquid alternative asset histories, while retaining cash as
an explicit allocation choice.

Until a genuinely robust candidate passes historical validation and future
blind review, keep `stop_before_testnet_resume`.

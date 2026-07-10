# 2024-2025 Market-Regime and Failure-Attribution Report

- **Date**: 2026-07-10
- **Scope**: BTCUSDT Binance Spot, 2024-01-01 through 2025-12-31 UTC
- **Primary source reviewed**: `rule_trend_regime_v1 / ema24-96-1h-mom24-atr14x0.5-v1`
- **Evidence**: 1052640 complete 1m bars plus the clean 2024 development and 2025 blind bundles
- **Purpose**: Diagnostic research on already-opened data; not a new blind test
- **Policy effect**: None

## Executive conclusion

The trend-regime candidate failed for three linked reasons:

1. **The gross signal edge did not survive the market-regime change.** The
   2024-08..12 development market rose 44.79%, while the 2025-08..12 blind
   market fell 24.29%. Strategy gross PnL changed from +16.19 to -13.63 USDT.
   The blind loss therefore exists before fees and slippage.
2. **The development pass was concentrated rather than robust.** One
   2024-11 position earned +18.91 USDT gross, or 117% of the entire
   development gross result. Removing it leaves development gross PnL at
   -2.72 and base PnL at -7.87 USDT. The prior 3/5 positive months and 29
   positions were genuine warnings, not merely conservative gate failures.
3. **The exit design surrendered transient edge.** All 25 gross-losing blind
   positions first achieved positive MFE; 20 of them moved far enough to cover
   the modeled base round-trip cost before ultimately closing at a loss. All
   31 blind exits were caused by the slow-EMA price buffer, not an EMA cross.
   The strategy repeatedly entered countertrend rallies and waited for the
   broad stop condition to invalidate them.

Costs remain material but are not the root cause. Modeled base costs added
7.60 USDT to a pre-cost blind loss of 13.63 USDT, producing -21.24 USDT base
PnL. The correct response is not fee optimization or a small EMA/ATR threshold
change. The current fingerprint should stay closed.

## Method and reproducibility

The passive script
[`notebooks/market_regime_failure_attribution.py`](../../notebooks/market_regime_failure_attribution.py)
reads:

- the complete local 2024-2025 BTCUSDT 1m catalog;
- development bundle `20260710-053017Z-8c63508d`;
- blind bundle `20260710-053944Z-1a2d2376`.

It calculates:

- monthly return from first 1m open to last 1m close;
- annualized volatility from daily log returns using `sqrt(365)`;
- trend efficiency as absolute cumulative daily log return divided by the sum
  of absolute daily log returns;
- position gross/base/stress PnL directly from entry and exit fills;
- intratrade MFE/MAE from 1m highs and lows;
- entry-time EMA/momentum/ATR state and the actual exit-condition branch.

The `directional_up/down` label is descriptive only: absolute monthly return
at least 5% and trend efficiency at least 0.30. It is not a proposed strategy
parameter or a claim of an optimal regime threshold.

Reproduce from the repository root:

```bash
TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m notebooks.market_regime_failure_attribution
```

The strict JSON artifact is written to
`data/market-regime-failure-attribution-2024-2025.json` and remains gitignored.
The script does not load credentials, start NautilusTrader, write signals,
change policy, or connect to an exchange.

## Market-state comparison

| period | BTC return | mean annualized realized vol | mean trend efficiency | up/down months |
|---|---:|---:|---:|---:|
| 2024 full year | +121.31% | 51.22% | 0.208 | 8 / 4 |
| 2025 full year | -6.33% | 40.22% | 0.188 | 6 / 6 |
| 2024-08..12 development | +44.79% | 50.65% | 0.199 | 3 / 2 |
| 2025-08..12 blind | -24.29% | 37.23% | 0.162 | 1 / 4 |

The development and blind windows were not comparable directional regimes.
The development window contained November 2024's +37.15% directional advance;
the blind window contained November 2025's -17.56% directional decline and no
diagnostic directional-up month.

| month | BTC return | annualized vol | trend efficiency | diagnostic state |
|---|---:|---:|---:|---|
| 2024-08 | -8.75% | 68.54% | 0.117 | mixed |
| 2024-09 | +7.38% | 42.46% | 0.133 | mixed |
| 2024-10 | +11.00% | 38.70% | 0.220 | mixed |
| 2024-11 | +37.15% | 59.78% | 0.469 | directional up |
| 2024-12 | -2.94% | 43.75% | 0.056 | mixed |
| 2025-08 | -6.49% | 35.84% | 0.147 | mixed |
| 2025-09 | +5.36% | 24.47% | 0.187 | mixed |
| 2025-10 | -3.89% | 44.00% | 0.072 | mixed |
| 2025-11 | -17.56% | 44.56% | 0.336 | directional down |
| 2025-12 | -3.00% | 37.30% | 0.071 | mixed |

## Strategy attribution

| metric | 2024 development | 2025 blind | interpretation |
|---|---:|---:|---|
| positions | 29 | 31 | sample counts are comparable |
| gross PnL | +16.191970 | -13.634510 | edge changes sign before costs |
| base PnL | +10.844598 | -21.238820 | costs amplify, not create, failure |
| modeled base cost | 5.347372 | 7.604310 | higher BTC notional raises absolute cost |
| gross win rate | 34.48% | 19.35% | fewer successful trend captures |
| median gross position PnL | -0.790000 | -1.080900 | typical trade was negative in both windows |
| mean holding time | 66.66 h | 43.39 h | blind trends invalidated sooner |
| exposure | 1933 h / 52.6% | 1345 h / 36.6% | less time long did not avoid repeated losses |
| mean 24h return after entry | +0.179% | -0.212% | immediate continuation flips sign |
| mean 48h return after entry | +0.806% | -0.366% | multi-day continuation flips sign |
| mean entry 24h momentum | +2.310% | +1.608% | blind entries had weaker impulse |
| mean entry distance above slow EMA | 2.166 ATR | 1.905 ATR | entries still chased already-extended price |
| mean MFE | +3.104 USDT | +2.176 USDT | transient favorable movement remained |
| mean giveback from MFE | 2.545 USDT | 2.616 USDT | giveback exceeded blind mean MFE |

### Development concentration

The best development position opened on 2024-11-05 and closed on 2024-11-17:

- gross PnL: +18.907990 USDT;
- base PnL: +18.716748 USDT;
- duration: 291 hours.

Without that one position, the development screen is negative before and after
costs. Aggregate-positive continuation was therefore too permissive. Future
development screens should apply the final distribution gates before consuming
a scarce holdout and should remain base-positive after removing the single best
position.

### Blind loss anatomy

- December 2025 closed 11 positions and contributed -11.586490 USDT gross,
  approximately 85% of the full blind gross loss.
- The blind set had 6 gross winners and 25 gross losers.
- All 25 losers had some positive intratrade excursion.
- 20/25 losers exceeded their modeled base cost while open and then finished
  negative.
- Only 5/31 positions never moved far enough to cover base costs. Purely
  immediate false entry is therefore not the dominant pattern.
- Every blind exit was `price_buffer`; `fast EMA < slow EMA` never independently
  caused an exit.

This is consistent with a long-only extension rule entering temporary rallies
inside a broader weak market, then returning too much open profit before its
slow regime invalidation becomes true.

## Cross-candidate evidence

The other cost-review candidates reinforce the same boundaries:

| candidate | observed failure | implication |
|---|---|---|
| frozen `freqai_linear_v1` | small gross paper gain becomes base/stress negative; historical shorts conflict with Spot-only scope | do not restore or tune it |
| ridge walk-forward | one closed position and negative result | thresholded linear forecast provides too little evidence |
| 15m Donchian breakout | -6.06 gross, -39.31 base over 184 positions | high turnover magnifies a missing gross edge |
| 1h trend-regime | positive but concentrated development; negative future gross | low turnover alone does not solve regime dependence |

The next hypothesis must therefore avoid both extremes: it cannot depend on
high turnover, and it cannot treat every short-term upside extension as a valid
long regime.

## Recommended next hypothesis

The strongest next research direction is a **causal higher-timeframe risk-on
pullback-continuation** hypothesis:

> BTC continuation is more likely when a multi-week risk-on state already
> exists and price recovers from a controlled pullback. Buying an extension
> immediately after positive short-horizon momentum is more vulnerable to
> countertrend rallies and late entries.

This is materially different from adjusting EMA(24/96) or ATR × 0.5:

- state permission comes from a slower causal regime, not the same entry
  timeframe;
- entry seeks recovery after a pullback rather than price extension;
- exit must explicitly bound giveback or time in a failed continuation, rather
  than relying solely on the slow-EMA price buffer;
- output remains deterministic Spot long/flat `SignalEvent v1` with low
  turnover.

No indicator periods or thresholds are selected in this report. Selecting and
locking them is the next pre-registration task, using 2024-2025 only as opened
development data.

## Research protocol changes

Before a new future window is consumed, require all of the following on the
development/validation evidence:

1. gross, base, and stress aggregate PnL are positive;
2. base PnL is positive in at least 4/5 validation months;
3. at least 30 positions close;
4. base aggregate PnL remains positive after removing the single best
   position;
5. zero shorts, blockers, invalid lineage, or unexplained fills;
6. byte-reproducible fills, orders, positions, lineage, and review result.

Use 2024-2025 only for development and diagnosis. The local catalog currently
ends on 2025-12-31. A new source/model fingerprint should be committed before
importing an unseen validation period. The final future blind window should be
locked separately; `2026-08-01..2026-12-31` is the natural five-month choice
as of this report date and cannot be completed until that market period exists.

Until a new fingerprint passes these gates, keep the recommendation
`stop_before_testnet_resume`.

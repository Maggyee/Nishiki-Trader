# Phase 2 Diverse Strategy Tournament

- **Status**: Locked before running any candidate on real catalog data
- **Locked on**: 2026-07-10
- **Scope**: Four economically distinct BTCUSDT Spot long/flat candidates
- **Parameter search**: None
- **Historical validation reserve**: 2020-01-01 through 2023-12-31, currently absent from the catalog
- **Future blind reserve**: 2026-08-01 through 2026-12-31
- **Policy effect**: None; research/backtest only

## Purpose

Prior candidates explored nearby momentum, breakout, and trend thresholds one
at a time. This tournament instead locks four different return hypotheses at
once, applies identical cost and robustness evidence, and preserves failures.
No candidate may be tuned after its first real-data result.

All sources emit deterministic `SignalEvent v1` state transitions, use
NautilusTrader as the only backtest engine, remain Spot long/flat, and never
write an order instruction into signal metadata.

## Locked candidates

### 1. Oversold mean reversion

- **Identity**: `rule_mean_reversion_v1 / z20-rsi2-exitmean-time24h-4h-v1`
- Deterministically resample to 4h.
- Calculate close SMA/std over 20 bars and simple rolling RSI(2).
- Enter when close z-score ≤ -2.0 and RSI(2) ≤ 10.
- Exit at the first of: close reaches SMA(20), RSI(2) ≥ 70, or six 4h bars
  elapse.
- Thesis: short, extreme selloffs partially mean-revert within one day.

### 2. Volatility-squeeze breakout

- **Identity**: `rule_vol_squeeze_v1 / bb20-kc20x1.5-breakout20-chandelier3-4h-v1`
- Deterministically resample to 4h.
- Bollinger(20, 2 std) inside Keltner(EMA20, 1.5 × ATR20) arms a squeeze for
  six bars.
- Enter while armed when close exceeds the previous 20-bar high.
- Exit when close falls three current ATR below peak high, or after 60 bars.
- Thesis: volatility contraction followed by directional range expansion can
  pay for a lower-frequency breakout.

### 3. Volume/OBV-confirmed breakout

- **Identity**: `rule_volume_breakout_v1 / price20-obv20-volume2x-exit10-4h-v1`
- Deterministically resample to 4h.
- Enter only when close exceeds the previous 20-bar high, OBV exceeds its
  previous 20-bar high, and volume is at least 2 × the prior 20-bar median.
- Exit when close falls below the previous 10-bar low.
- Thesis: price breakouts accompanied by exceptional signed volume should be
  less prone to false continuation than price-only breakouts.

### 4. Slow dual absolute momentum

- **Identity**: `rule_dual_momentum_v1 / ret20-60-positive-1d-v1`
- Deterministically resample to completed UTC daily bars.
- Enter when both 20-day and 60-day close returns are positive.
- Exit when either return is non-positive.
- Thesis: remain exposed only when medium and slow absolute momentum agree.
- This low-frequency source may end as `insufficient_evidence`; the sample gate
  is not relaxed to make it pass.

All numeric choices above are fixed from conventional horizon semantics. No
grid, random search, Bayesian search, or manual result-driven alternative is
allowed under these model versions.

## Opened-data development folds

After this document, implementations, synthetic tests, and review protocol are
committed and pushed, each source is generated once from the already-opened
2024-2025 catalog. Each source is backtested twice on four fixed folds:

1. 2024-01-01 through 2024-05-31.
2. 2024-08-01 through 2024-12-31.
3. 2025-01-01 through 2025-05-31.
4. 2025-08-01 through 2025-12-31.

June/July are excluded from scored folds rather than shifted per candidate.
They may provide indicator warm-up through the full catalog, but their PnL is
not counted.

Every fold uses CASH/NETTING, 100000 USDT, 0.001 BTC, the existing risk rules,
and gross/base/stress costs of 0/0, 10/2, and 10/5 bps per fill.

## Tournament gate

`apps.ops.strategy_tournament` consumes four strict `alpha.review.v1` files per
source and applies one shared development gate:

1. aggregate gross, base, and stress PnL across all four folds are positive;
2. base and stress are each positive in at least 3/4 folds;
3. at least 12/20 natural months have positive base PnL;
4. at least 120 positions close across the four folds;
5. aggregate base PnL remains positive after removing the single best
   base-scenario position across all folds;
6. every fold has zero shorts/blockers and exact duplicate-run reproducibility.

An economically passing source with fewer than 120 positions is labeled
`insufficient_evidence`, not promoted. Sources passing all gates are ranked by:

1. highest minimum fold base PnL;
2. highest aggregate stress PnL;
3. highest count of base-positive months.

Ranking is only among passers. A large aggregate return cannot outrank a
strategy that fails a robustness gate.

## Historical validation and future blind

Only development passers may cause the currently absent 2020-2023 data to be
imported. Those parameters remain unchanged and are evaluated on eight fixed
Jan-May/Aug-Dec folds. Historical validation is intended to add bull, bear,
and high-volatility regimes; it is not a substitute for the future blind.

Only historical-validation passers remain candidates for the locked
2026-08..12 future blind and later `paper_shadow` review. Viewing any result
never permits changing its model version. A change creates a new candidate and
requires a new untouched holdout.

No tool may automatically call `promotion_review.py`, modify SourcePolicy,
resume testnet continuity, load credentials, or authorize live trading.

# Phase 2 Pullback-Regime Hypothesis

- **Status**: Locked before reading any 2026 market data
- **Locked on**: 2026-07-10
- **Source/model**: `rule_pullback_regime_v1 / daily50-200-1h24-pullback-giveback1.25-v1`
- **Unseen validation window**: 2026-01-01 through 2026-05-31 UTC
- **Future blind window**: 2026-08-01 through 2026-12-31 UTC
- **Policy effect**: None; research and backtest only

## Economic hypothesis

BTC long continuation should be more reliable when a causal multi-week risk-on
state already exists and price recovers from a short pullback. Entering an
already-extended short-horizon move is vulnerable to countertrend rallies;
waiting for a pullback and recovery should reduce late entries. A successful
continuation should make measurable progress within three days, and open profit
should not be surrendered without a bounded volatility-scaled exit.

This is a new economic structure, not an EMA/ATR retune of the rejected
`rule_trend_regime_v1` extension rule.

## Fixed fingerprint

All calculations use deterministic BTCUSDT 1m OHLCV resampling. Signals are
evaluated only on completed 1h bars.

### Causal daily permission

- Resample to completed UTC daily bars.
- Calculate EMA(50) and EMA(200) from daily closes.
- A day is `risk_on` only when the **previous completed day's** close is above
  its EMA(200) and EMA(50) is above EMA(200).
- At least 200 completed daily observations are required before permission can
  become true.
- Current-day partial data is never used for the daily state.

The 50/200-day pair represents roughly quarterly versus annual trend state and
is fixed from common horizon semantics, not selected by a repository search.

### Pullback and recovery entry

- Resample deterministically to 1h bars.
- Calculate EMA(24) and ATR(14).
- While flat and daily `risk_on`, a close below EMA(24) arms a pullback for 24
  hourly bars. Further closes below EMA(24) refresh the 24h arm.
- Enter long only while armed, when close is above EMA(24), above the previous
  completed hour's high, and no more than 0.75 × ATR above EMA(24).
- The 0.75 ATR cap prevents an extension entry; there is no parameter sweep.

### Exit and giveback control

After entry, record entry price, entry ATR, peak hourly close, and bars held.
Exit to flat using the first condition in this priority order:

1. `daily_risk_off_exit`: previous-day daily permission becomes false.
2. `structural_failure_exit`: close falls below EMA(24) − 1.0 × current ATR.
3. `bounded_giveback_exit`: after peak close first reaches entry + 1.0 × entry
   ATR, close falls to peak close − 1.25 × current ATR.
4. `failure_timeout_exit`: after 72 hourly bars, peak close has never reached
   entry + 1.0 × entry ATR.

The three-day timeout expresses the continuation thesis directly: a move that
cannot make one-ATR progress within 72 hours is invalidated instead of waiting
for a slow trend cross.

### Signal contract

- State transitions only: `buy` from flat to long and `flat` from long to flat.
- Never emit `sell` and never target a Spot short.
- Horizon `1h`, TTL 3600 seconds, fixed confidence 0.75.
- Entry score is `1 - abs(distance_from_hourly_ema_in_atr)`, clipped to [0, 1].
- Metadata records every parameter, previous-day regime values, entry EMA/ATR,
  entry state, peak close, bars held, progress state, and trigger.
- No forced terminal flat is generated from knowledge of a review boundary.

## Opened-data development protocol

No 2026 market bar or result was read while choosing or implementing this
fingerprint. Synthetic tests are allowed before the pre-registration commit.

After the fingerprint commit is pushed, generate one signal stream from the
already-opened 2024-2025 catalog and run two clean CASH/NETTING backtests for
each development fold:

- Fold A: 2024-08-01 through 2024-12-31.
- Fold B: 2025-08-01 through 2025-12-31.

Each fold must independently satisfy all of these conditions before any 2026
data is imported:

1. gross, base, and stress aggregate PnL are all greater than zero;
2. base PnL is positive in at least 4/5 calendar months;
3. at least 30 positions close;
4. base PnL remains greater than zero after removing the single best
   base-scenario position;
5. zero shorts, kill-switch events, data gaps, invalid lineage, unexplained
   fills, or other review blockers;
6. fills, orders, positions, signal lineage, monthly results, concentration
   result, and gate conclusion reproduce exactly.

This deliberately applies the future gate to opened development data. Failure
on either fold closes this fingerprint and preserves all unseen 2026 data.

## Unseen validation and future blind protocol

Only if both opened-data folds pass may the already elapsed but locally unseen
2026-01..2026-05 data be imported and reviewed once under the same gates. That
window is validation evidence, not the final future blind.

Only if unseen validation also passes may the candidate wait for and consume
the locked 2026-08..2026-12 future blind window. Viewing either window never
permits tuning this model version. Any change requires a new model version and
a newly locked holdout.

Passing a backtest gate yields only `eligible_for_paper_shadow_review`; the
tool must not call `promotion_review.py` or mutate SourcePolicy automatically.
Until every required stage passes, keep `stop_before_testnet_resume`.

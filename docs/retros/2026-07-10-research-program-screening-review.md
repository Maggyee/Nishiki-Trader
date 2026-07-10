# Phase 2 Research Program Screening Review

- **Date**: 2026-07-10
- **Registry**: `docs/progress/phase-2-research-candidate-registry.json`
- **Schema**: `research.program.review.v1`
- **Strict candidates**: 16
- **Economic families**: 16
- **Development passers**: 0
- **Development watchlist**: 0
- **Decision**: Pause new candidate generation until independent evidence
- **Trading-state effect**: None

## Conclusion

The program has now tested sixteen distinct source/model fingerprints spanning
linear ML, breakout, trend/regime, pullback continuation, mean reversion,
volatility expansion, volume confirmation, absolute and cross-sectional
momentum, breadth, relative value, taker flow, flow exhaustion, funding
crowding, diversified momentum, and low-volatility rotation.

Every candidate is rejected under its pre-registered evidence protocol. No
candidate reaches `development_pass` or `development_watchlist`. The screened
set of good strategies is therefore empty. Selecting a "best" rejected model
would misrepresent the gate and violate the anti-overfit objective.

## Cumulative registry

| Family | Source/model shorthand | Base PnL | Stress PnL | Positions | Main failure |
|---|---|---:|---:|---:|---|
| Linear ML | ridge walk-forward | -1.129677 | -1.186094 | 1 | negative, inactive |
| Breakout | Donchian/ATR 15m | -39.313136 | -47.625248 | 184 | negative before costs |
| Trend regime | EMA/momentum/ATR | -21.238820 | -23.139897 | 31 | blind-window failure |
| Pullback continuation | daily regime/hourly pullback | -33.543655 | -41.495339 | 137 | turnover without edge |
| Mean reversion | z-score/RSI2 | -12.031668 | -16.365120 | 88 | cost-negative |
| Volatility breakout | squeeze breakout | +15.666855 | +14.340034 | 26 | 2/4 folds, concentrated |
| Volume breakout | price/OBV/volume | +13.266385 | +11.420167 | 37 | 2/4 folds, leave-best negative |
| Absolute momentum | dual 20/60-day | -0.773624 | -1.834220 | 21 | negative, sparse |
| Cross-sectional momentum | BTC/ETH/SOL 90-day | -32.210919 | -32.489414 | 8 | negative |
| Market breadth | 2-of-3 breadth | -10.027097 | -10.761071 | 21 | negative |
| Relative value | ETH/BTC z-score | +15.989241 | +15.380761 | 18 | 2/4 folds, leave-best negative |
| Taker flow | 7-day buy-share rotation | +23.505068 | +22.678201 | 23 | 2/4 folds, 7/20 months |
| Flow exhaustion | 4h capitulation reversal | -1.431597 | -1.623924 | 7 | negative, sparse |
| Funding crowding | funding-filtered momentum | -21.591179 | -22.124877 | 15 | negative |
| Diversified momentum | BNB/XRP/ADA basket | +44.064632 | +43.795051 | 27 | 2/4 folds, 4/20 months |
| Low-vol rotation | BNB/XRP/ADA low-vol | -25.725617 | -26.278526 | 17 | negative |

PnL scopes follow each candidate's own registered study and are not a common
leaderboard. The table exists to preserve outcomes, not to rank incompatible
windows. Exact gates and fold evidence remain in the linked source retros.

## What the near-positive candidates actually show

Five candidates have positive aggregate base/stress PnL: volatility squeeze,
volume breakout, relative value, taker flow, and diversified momentum. None is
a near-pass under the full protocol:

- every one wins only 2/4 folds;
- volatility/volume breakout and relative value fail leave-best concentration;
- taker flow has only 7/20 positive months and 23 positions;
- diversified momentum has only 4/20 positive months and 27 positions;
- their gains cluster in favorable 2024 directional regimes and do not repeat
  reliably in 2025.

Positive aggregate PnL is therefore not sufficient evidence of a durable
strategy.

## Stop rule

`apps.ops.research_program_review` validates unique identities, finite metrics,
classification values, and evidence-file existence. With 16/16 candidates
rejected, it emits:

```text
recommendation = pause_new_candidate_generation_until_independent_evidence
stop_rule.triggered = true
```

The stop rule prohibits:

- tuning parameters on opened samples;
- weighting an ensemble by observed PnL;
- consuming holdouts for rejected models;
- resuming testnet because one rejected aggregate is positive.

Research may resume only with independently justified evidence: a genuinely new
data-generating mechanism fixed before access, or a newly accrued future sample.
Merely adding indicators, changing lookbacks, swapping a few symbols, or testing
more combinations on the same opened periods does not qualify.

## Operational boundary

SourcePolicy remains unchanged, testnet continuity remains stopped, live remains
blocked, no credentials were loaded, and no upstream source was modified. The
correct current decision is `stop_before_testnet_resume` with an empty selected
strategy set.

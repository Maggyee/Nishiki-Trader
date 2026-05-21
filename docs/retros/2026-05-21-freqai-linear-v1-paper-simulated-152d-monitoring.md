# Paper simulated monitoring — 2026-05-21 (152d through May)

- **Date (UTC)**: 2026-05-21
- **Source / model**: `freqai_linear_v1 / linear-mom-train20240105`
- **Kind**: Monitoring evidence only — not a `SourcePolicy` decision.

## Scope

This extends the offline paper_simulated evidence window from 2024-04-30
through 2024-05-31 while preserving the original model boundary
`train_until=2024-01-05T23:59:00Z`.

No `promotion_review.py` command was run. The source is already authorized
at `testnet_canary` by
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`; this
record only adds offline monitoring evidence.

## Run Identity

- bundle: `data/paper/20260521-021418Z-e535b581`
- manifest sha256:
  `06d9300a3183a80cb8c3c7874034aad12985fee3c814dae48e2dd9881ab44095`
- git_commit: `7b048db8e72c46cd65b86180c27e96fafbdc0497`
- git_dirty: `false`
- signal store sha256:
  `dc096103628497d286872a8cb62737a8880549f6b04ca5d0e91c29a832cf840d`
- backtest_start: `2024-01-01T00:00:00.000Z`
- backtest_end: `2024-05-31T23:59:00.000Z`
- bars: 218880
- signal rows: 2107
- signal cutoff: `1717199940000000000`

The explicit signal cutoff excludes later 2026 wall-clock canary restamp
rows from this historical replay.

## Runtime Counters

| metric | value |
|---|---:|
| orders | 1987 |
| fills | 1987 |
| positions | 994 |
| heartbeat_count | 218880 |
| poll_count | 218880 |
| data_gap_count | 0 |
| restart_sequence | 0 |
| expired / unauthorized / signal_lag / kill_switch | 0 / 0 / 0 / 0 |
| review_blockers | none |
| promotion_blockers | none |

## Return Evidence

| metric | value |
|---|---:|
| PnL total | +4.8726 USDT |
| PnL percent | +0.004873% |
| Win Rate | 0.5358 |
| Expectancy | +0.00491 USDT/trade |
| Max Drawdown Pct | -0.003878% |
| Max Drawdown Abs | -3.8782 USDT |

## Month Split

| month | signals | target_long | target_short | closed positions | closed PnL USDT | win rate | expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-01 | 308 | 225 | 83 | 135 | +0.6463 | 0.5556 | +0.00479 |
| 2024-02 | 287 | 211 | 76 | 137 | +4.4086 | 0.5547 | +0.03218 |
| 2024-03 | 621 | 445 | 176 | 302 | +1.3731 | 0.5265 | +0.00455 |
| 2024-04 | 534 | 384 | 150 | 250 | -2.1081 | 0.5040 | -0.00843 |
| 2024-05 | 357 | 260 | 97 | 169 | +0.5535 | 0.5680 | +0.00328 |

## Reading

The mechanical path is still healthy: sidecars match, all signals are
accepted, and no risk or data quality blocker appears. The return evidence
does not justify higher risk. May is mildly positive, but overall expectancy
remains tiny and April stays a negative held-out month.

This record supports continuing to observe the source at its existing
`testnet_canary` authorization. It is not a promotion, demotion, or live-risk
approval.

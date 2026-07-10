# 2026-07-10 Cost-Sensitive Alpha Blind Review

- **Status**: Complete
- **Decision**: `stop_before_testnet_resume`
- **Scope**: BTCUSDT Binance Spot, 2024-08-01 through 2024-12-31 locked blind window
- **Code baseline**: `0aa37acdf7dc6e8c1d7ee09279213ff1c05d3a81`, all evidence bundles `git_dirty=false`
- **Policy effect**: None. This review does not mutate `SourcePolicy` or open a promotion stage.

## Data and cost assumptions

- Local catalog: 527040 BTCUSDT 1m bars covering 2024-01-01 00:00 through
  2024-12-31 23:59 UTC, zero duplicate timestamps and zero one-minute gaps.
- Every backtest uses NautilusTrader, `AccountType.CASH`, `OmsType.NETTING`,
  100000 USDT starting balance, 0.001 BTC trade size, min confidence 0.5, and
  the existing 5% daily drawdown stop.
- Cost scenarios are per fill: gross = 0/0 bps fee/slippage; base = 10/2 bps;
  stress = 10/5 bps.
- Recalculation is `recorded PnL + recorded commission - modeled fee - modeled
  slippage`, so bundles that already include commissions are not charged twice.

## Existing source early rejection

Before the locked blind comparison, `apps.ops.alpha_review` read the existing
152-day paper bundle `data/paper/20260521-021418Z-e535b581`:

| scenario | net PnL USDT |
|---|---:|
| gross | +4.873394 |
| base | -24.218490 |
| stress | -31.491462 |

The bundle also contains historical SHORT positions, incompatible with the
declared Spot-only/no-margin Phase 6 scope. The tool recommendation is
`demote_to_paper_simulated_recommended`; this is an audit recommendation only.
The currently signed policy remains unchanged until a human creates an actual
`promotion_review.py` decision.

## Locked blind results

| label | source / model | gross | base | stress | base-positive months | closed positions | reproducible | conclusion |
|---|---|---:|---:|---:|---:|---:|---|---|
| current reference | `freqai_linear_v1 / linear-mom-train20240105` | -0.291994 | -0.522843 | -0.580555 | 0/5 | 1 | reference only | `demote_to_paper_simulated_recommended` |
| EMA reference | `rule_baseline_v1 / ema5-20+rsi14` | -0.045589 | -0.278392 | -0.336592 | 0/5 | 1 | reference only | stop |
| walk-forward candidate | `freqai_linear_walkforward_v1 / ridge-wf60d-cost30bp-v1` | -0.904010 | -1.129677 | -1.186094 | 0/5 | 1 | yes | insufficient activity and negative net |
| breakout candidate | `rule_breakout_v1 / donchian20-10-atr14x0.25-15m` | -6.064690 | -39.313136 | -47.625248 | 1/5 | 184 | yes | negative before and after modeled costs |
| same-size buy-and-hold | `benchmark_buy_and_hold / same-size-spot-v1` | +28.941990 | +28.752138 | +28.704675 | 3/5 | 1 | deterministic reference | reference only |

Both new candidates remain long/flat with zero short positions. Neither meets
the conservative gate: base and stress must both be positive, at least 4/5
months must be positive under base costs, at least 30 positions must close, and
the evidence must be clean and reproducible.

### Candidate monthly modeled net PnL

| month | walk-forward base | breakout gross | breakout base | breakout stress |
|---|---:|---:|---:|---:|
| 2024-08 | 0.000000 | -3.645270 | -8.840987 | -10.139916 |
| 2024-09 | 0.000000 | +0.967090 | -3.765045 | -4.948078 |
| 2024-10 | 0.000000 | -4.365530 | -10.326043 | -11.816172 |
| 2024-11 | 0.000000 | +14.677270 | +7.272249 | +5.420994 |
| 2024-12 | -1.129677 | -13.698250 | -23.653310 | -26.142075 |

## Evidence bundles

- Current reference: `data/backtests/20260710-031506Z-7720e0ef`, manifest
  `db121c865da05e67866b5dff2703c1d60daf6c8e2c1cc2a09b55bf06bac194a0`.
- EMA reference: `data/backtests/20260710-031508Z-a9b64a88`, manifest
  `cf6fb8a8170ab46b6bba026fa616871e240cf1347813638473cedf7d8db84abb`.
- Walk-forward runs: `data/backtests/20260710-031510Z-94c0e7b4` and
  `data/backtests/20260710-031516Z-7705bbe8`; fills SHA-256
  `cd83fb90f6c7985b4b6503a6603610d7dd4900506d6a136d701ee5d377957fd6`.
- Breakout runs: `data/backtests/20260710-031522Z-241b8679` and
  `data/backtests/20260710-031529Z-ecffd143`; fills SHA-256
  `916d77757c7a303a82a8149150dd67e236684d833585fab752878205e121afc0`.
- Machine-readable local artifact: `data/alpha-review-2024.json` (gitignored).

For both candidates, `compare_backtests` returned `MATCH` across fills,
orders, positions, and signal_lineage sidecars.

## Decision and next entrypoint

Do not resume the 14-day testnet continuity campaign and do not tune these
model versions against the now-opened blind window. Neither candidate enters
paper_shadow. The next research task must start from a new economic hypothesis,
assign a new source/model fingerprint, and reserve a future untouched blind
period. Current SourcePolicy stays unchanged until the operator explicitly
reviews the demotion recommendation through `promotion_review.py`.

The review remained passive: it did not start Nautilus, place orders, load
credentials, write SignalEvent, mutate policy, or authorize live trading.

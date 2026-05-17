# Phase 2 Signal-Source Baselines

- **Phase**: 2 (research → bridge → backtest_runner)
- **Date**: 2026-05-17
- **Owner**: nishiki
- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/...parquet` (1440 1m bars, 2024-01-01 UTC)
- **Signal store**: `data/bridge/signals.db` (sha256 `76db252504ae34214808ebf2f7915679696f773591e56b57dd3cd37fc2208c46` at the time of recording)
- **Code baseline**: git `83b0910` (`feat(strategies_freqtrade): add rule-based baseline SignalEvent generator`)

## Purpose

Lock in the two signal sources currently living side-by-side in `signals.db`
as Phase 2 reproducibility anchors. Each future strategy or runner change
should rerun both CLIs and compare the manifest stats below — drift outside
the wall-clock fields (`run_id`, `started_at`, `finished_at`,
`elapsed_seconds`) is a regression to explain or a new baseline to record.

## Sources

| key | `source` | `model_version` | rows | nature |
|---|---|---|---:|---|
| demo | `manual_research` | `binance-fixture-v1` | 3 | hand-seeded buy / flat / sell scaffold from `apps.ops.backfill_bars --seed-demo-signals` |
| rule | `rule_baseline_v1` | `ema5-20+rsi14` | 71 | EMA(5)/EMA(20) cross with RSI(14) overbought / oversold filter from `apps.strategies_freqtrade.research.baseline_rule_signals` |

Both subsets share the same `signal_source.store_sha256` because they live in
the same `signals.db`; the runner selects between them via `--signal-source`
/ `--signal-model-version`. This is the ADR-002 §5 traceability contract in
action.

## Baseline bundle stats

Two bundles produced by `apps.strategies_nautilus.runners.backtest_runner`
with `--trade-size 0.001 --starting-balance 100000 --min-confidence 0.5`,
`BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL`, default kill-switch (5% daily
loss).

| metric | demo | rule |
|---|---:|---:|
| signal rows in run | 3 | 71 |
| iterations | 1440 | 1440 |
| total events | 8 | 284 |
| total orders | 4 | 142 |
| total positions | 2 | 71 |
| total fills | 4 | 142 |
| PnL (total, USDT) | -1.01904229 | -4.73745857 |
| PnL% (total) | -0.001019 | -0.004737 |
| Win Rate | 0.500 | 0.1267605633802817 |
| Expectancy (USDT) | -0.509521145 | -0.066724768591549274 |
| Sharpe Ratio (252d) | null | null |
| Sortino Ratio (252d) | null | null |
| Profit Factor | null | null |
| Lineage decisions | `target_long×1`, `target_flat×1`, `target_short×1` | `target_long×36`, `target_short×35` |

`Sharpe`, `Sortino`, and `Profit Factor` come back `null` because the
realised return series is degenerate on a 1-day, fee-dominated placeholder
run. They are pinned here so future runs can confirm "still null, still
placeholder-grade" rather than silently flipping to a numeric value that
nobody noticed.

## Reading the comparison

- **Same catalog, same store, identical `store_sha256`** → the bundles differ
  only because the runner selects a different subset of `signals.db`. This
  is exactly the ADR-002 §5 audit contract.
- **Demo emits `flat`; rule does not.** Demo deliberately tests position
  closing; rule only emits at EMA crossovers and relies on the next opposite
  cross to flip the position. Any new Phase 2 source that emits `flat`
  should add a new row in the lineage decisions column.
- **Rule churns ~35× more fills than demo for the same day** → kill-switch
  and fee accounting are exercised much more heavily on the rule path. If a
  future runner change drops rule `total_fills` below ~140 with no other
  parameter change, that is a regression in cross detection or the
  `signal_id` carry-through.
- **Both bundles are negative.** Neither source has alpha. This note grades
  fingerprints, not strategies.

## How to reproduce

```bash
# 1. Bars + demo signals (idempotent; download skipped if cached).
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.backfill_bars \
  --download --symbol BTCUSDT --interval 1m --date 2024-01-01 \
  --catalog-path data/catalog --seed-demo-signals \
  --signal-store-path data/bridge/signals.db

# 2. Rule signals.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.baseline_rule_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL'

# 3. Demo bundle.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.backtest_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source manual_research --signal-model-version binance-fixture-v1 \
  --allowed-source manual_research --allowed-model-version binance-fixture-v1 \
  --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5

# 4. Rule bundle.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.backtest_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source rule_baseline_v1 --signal-model-version 'ema5-20+rsi14' \
  --allowed-source rule_baseline_v1 --allowed-model-version 'ema5-20+rsi14' \
  --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5
```

Each bundle is written under `data/backtests/<run_id>/`. Compare each
manifest's `stats_pnls.USDT` and `totals` against the table above; absolute
drift greater than 0.01 on PnL / Expectancy or any count change is a
regression unless the change is intentional and recorded as a new dated
baseline below.

## Updating this baseline

When the baseline must move (intentional strategy / runner change), append a
new dated section below rather than rewriting this one. Older fingerprints
stay useful as forensic anchors.

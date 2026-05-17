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

Note that `signal_source.store_sha256` shifts every time `signals.db` gains
or drops rows — `signals.db` itself is gitignored, so reproducing an older
fingerprint exactly requires walking the same `backfill_bars` /
`baseline_rule_signals` sequence from an empty store. The numerical
fingerprints below are still the contract; the SHA is a fast staleness
detector, not a primary key.

---

## 2026-05-17 v2 — BTCUSDT 2024-01-01 ~ 2024-01-07 (7-day window)

- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/` covering 2024-01-01 through 2024-01-07 (10080 1m bars, backfilled day-by-day via `apps.ops.backfill_bars`).
- **Signal store**: `data/bridge/signals.db` sha256 `993b4689db35ced308718bc3ba2e55fca9b145439ffd1c36c9fe0fa206bd9155` (= original 3 demo + 71 rule@2024-01-01 from v1 + 564 new rule rows@2024-01-02..07).
- **Code baseline**: git `5fd5be9` (`feat(bridge): enforce ADR-005 source-family prefix on SignalEvent`).

| metric | demo (7d) | rule (7d) | demo Δ vs v1 | rule Δ vs v1 |
|---|---:|---:|---|---|
| signal rows in run | 3 | 635 | 0 | +564 |
| iterations | 10080 | 10080 | +8640 | +8640 |
| total events | 8 | 2532 | 0 | +2248 |
| total orders | 4 | 1266 | 0 | +1124 |
| total positions | 2 | 633 | 0 | +562 |
| total fills | 4 | 1266 | 0 | +1124 |
| PnL (total, USDT) | -0.76826176 | -57.153288 | +0.25078053 (BacktestEngine `on_stop` closes the demo short at 01-07 close, not 01-01 close — different mark) | -52.41582943 (linear-ish with fill count: ~6.4× more fills, ~12× more loss, ratio dominated by fee drag) |
| Win Rate | 0.500 | 0.10584518167456557 | 0 | -0.02091538 |
| Expectancy (USDT) | -0.38413088 | -0.0902895545023697 | +0.12538910 | -0.02356478 |
| Sharpe Ratio (252d) | null | null | — | — |
| Sortino Ratio (252d) | null | null | — | — |
| Profit Factor | null | null | — | — |
| Lineage decisions | `target_long×1`, `target_flat×1`, `target_short×1` | `target_long×318`, `target_short×317` | unchanged | +282 / +282 |

### Reading v2

- **Demo lineage unchanged.** Same 3 signals → same 4 fills decisions —
  demo signals only fire on 2024-01-01 and the engine's `on_stop` flat
  closes the leftover short. The PnL difference vs v1 is the close-mark
  drift, not strategy behaviour.
- **Rule scales close to linear.** 7-day rule signals = 635 vs 71 ≈ 8.9×;
  fills 1266 vs 142 ≈ 8.9×. Win Rate drops slightly (10.6% vs 12.7%) and
  Expectancy worsens slightly (-0.090 vs -0.067 USDT/trade) — fee drag
  dominates as fills accumulate, exactly what a no-alpha rule predicts.
- **`signal_source.store_sha256` matches across the demo and rule bundles**
  (`993b4689...`) because both filtered runs scan the same `signals.db`.
  The runner's `signal_filter` is the only thing that differs between the
  two bundles. ADR-002 §5 traceability holds.

### v1 → v2 reproduction note

To reproduce v1 from a clean state:

```bash
rm data/bridge/signals.db
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.backfill_bars \
  --download --symbol BTCUSDT --interval 1m --date 2024-01-01 \
  --catalog-path data/catalog --seed-demo-signals \
  --signal-store-path data/bridge/signals.db
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.baseline_rule_signals \
  --catalog-path data/catalog --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT --venue BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL'
```

To extend to v2, append the 2024-01-02 .. 2024-01-07 backfills, then rerun
`baseline_rule_signals` once more (duplicate rule signals from 01-01 will
be skipped by `DuplicateSignalError`).

---

## 2026-05-17 v3 — first `freqai_*` source, dry-run policy

- **Catalog input**: same 7-day `BTCUSDT.BINANCE` 1m catalog as v2, covering
  2024-01-01 through 2024-01-07 (10080 bars).
- **Signal source**: `freqai_linear_v1` /
  `linear-mom-train20240105`.
- **Signal store**: `data/bridge/signals.db` sha256
  `55e5a218d1d9213d145a4db1148f07e6a62b0a7676e6b8ce4eaf26d09420323a`
  (= existing v2 demo + rule rows plus 7 `freqai_linear_v1` rows).
- **Feature hash**:
  `sha256:885207acda6e307c4ac19a20c40e36b09619e3ed80f92f7c328a8dc36cff9b58`.
- **Policy**: `SourcePolicy(position_pct_multiplier=0.2, dry_run=True)`.
- **Code baseline**: this commit, which adds the first lightweight
  classic-ML export under the ADR-005 `freqai` family.

`freqai_linear_v1` is a Phase 2 bridge smoke source, not alpha. It fits a
deterministic ridge-linear momentum model on pre-2024-01-06 bars and exports
post-train predictions as `SignalEvent v1`. It does not import the freqtrade
runtime, touch upstream source, or submit orders.

| metric | freqai linear v3 |
|---|---:|
| signal rows in run | 7 |
| signal side split | `buy×7` |
| iterations | 10080 |
| total events | 0 |
| total orders | 0 |
| total positions | 0 |
| total fills | 0 |
| PnL (total, USDT) | 0 |
| PnL% (total) | 0 |
| Win Rate | null |
| Expectancy (USDT) | null |
| Lineage decisions | `target_long×7` |

### Reading v3

- **Dry-run is working.** The strategy produced 7 `target_long` lineage
  decisions, but `_apply_intent` submitted no orders because the applied
  policy has `dry_run=True`.
- **The 0.2 multiplier is still recorded.** Because dry-run suppresses order
  submission, the multiplier does not affect fills yet, but it is present in
  `run_manifest.json` under `strategies[0].params.policies` for ADR-004
  reproducibility.
- **This is out-of-sample relative to the configured train boundary.**
  Training rows end at `2024-01-05T23:59:00Z`; all emitted signals are on
  2024-01-06 or 2024-01-07.

### v3 reproduction

Starting from the v2 catalog and signal store:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT \
  --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --train-until '2024-01-05T23:59:00Z'

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.backtest_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2 \
  --policy-dry-run
```

---

## 2026-05-17 v4 — simulated paper bundle report evidence

- **Catalog input**: same 7-day `BTCUSDT.BINANCE` 1m catalog as v2/v3
  (10080 bars).
- **Signal store**: `data/bridge/signals.db` sha256
  `55e5a218d1d9213d145a4db1148f07e6a62b0a7676e6b8ce4eaf26d09420323a`.
- **Code baseline**: git `7e92564`
  (`feat(strategies_nautilus): add paper bundle report`).
- **Report reader**:
  `apps.strategies_nautilus.runners.report_paper_bundle`.

| metric | freqai paper shadow | rule paper simulated |
|---|---:|---:|
| bundle | `data/paper/20260517-034251Z-02c7d57d` | `data/paper/20260517-034308Z-feb4fcc4` |
| manifest sha256 | `251fc2a9d586a04892f10cd36893bdae9124d277c95949d775d3236f46133c90` | `5bab3411db34fa2b6d25601a6cd19883722d7ed4d14701a116676f91bb1d5bda` |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | `rule_baseline_v1 / ema5-20+rsi14` |
| `git_dirty` | false | false |
| runtime | `catalog_polling` / `simulated` | `catalog_polling` / `simulated` |
| signal rows | 7 | 635 |
| session days inclusive | 7 | 7 |
| policy | `dry_run=True`, multiplier `0.2` | `dry_run=False`, multiplier `0.2` |
| lineage decisions | `target_long×7` | `target_long×318`, `target_short×317` |
| lineage reasons | `dry_run×7` | empty reason×633, `already_target_long×1`, `already_target_short×1` |
| orders / fills / positions | 0 / 0 / 0 | 1265 / 1265 / 633 |
| PnL total (USDT) | 0 | -0.31674399999610614 |
| Win Rate | null | 0.27689873417721517 |
| Expectancy (USDT) | null | -0.0005475727848101619 |
| max drawdown pct | null (not yet emitted by paper runner) | null (not yet emitted by paper runner) |
| review blockers | none | none |
| promotion blockers | `manual_review_required_before_disabling_dry_run` | none |
| report recommendation | `manual_review_required_before_paper_simulated` | `review_simulated_paper_evidence` |

### Reading v4

- **The report reader is useful as a promotion-review gate.** Both paper
  bundles have no review blockers and no sidecar row-count mismatches. The
  dry-run FreqAI source still reports a promotion blocker because disabling
  dry-run requires a manual ADR-007 review.
- **Rule simulated is only a local execution-path control.** It proves that
  simulated orders/fills/positions carry `signal_id` under `kind="paper"`;
  it is not alpha evidence and does not justify testnet/live.
- **Max drawdown remains a missing metric.** The current paper runner writes a
  final account balance row, not a full equity curve. The report surfaces this
  as `missing_metrics=["max_drawdown_pct"]` instead of fabricating a value.

### v4 reproduction

Starting from the v3 catalog and signal store:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2 \
  --policy-dry-run

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_paper_bundle \
  --json data/paper/<freqai_run_id>

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source rule_baseline_v1 \
  --signal-model-version 'ema5-20+rsi14' \
  --allowed-source rule_baseline_v1 \
  --allowed-model-version 'ema5-20+rsi14' \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_paper_bundle \
  --json data/paper/<rule_run_id>
```

---

## 2026-05-17 v5 — paper equity curve and max drawdown

- **Catalog input**: same 7-day `BTCUSDT.BINANCE` 1m catalog as v2/v3/v4
  (10080 bars).
- **Signal store**: `data/bridge/signals.db` sha256
  `55e5a218d1d9213d145a4db1148f07e6a62b0a7676e6b8ce4eaf26d09420323a`.
- **Code baseline**: git `e4007ab`
  (`feat(strategies_nautilus): add paper drawdown metrics`).
- **Change vs v4**: `paper_runner.py` now writes one `account_balances.parquet`
  row per bar and records `Max Drawdown (Pct)` / `Max Drawdown (Abs)` in the
  paper manifest. The report reader no longer flags max drawdown as missing.

| metric | freqai paper shadow | rule paper simulated |
|---|---:|---:|
| bundle | `data/paper/20260517-035247Z-bea9a949` | `data/paper/20260517-035302Z-947fc297` |
| manifest sha256 | `fa580017c4ac86c3fb2af11178c292e023a923862a120ad70b032451218bfe0e` | `852df0355c3e55e8ac3896f7dbb69879202eac417b8ba58d126896012e4e1c31` |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | `rule_baseline_v1 / ema5-20+rsi14` |
| `git_dirty` | false | false |
| runtime | `catalog_polling` / `simulated` | `catalog_polling` / `simulated` |
| signal rows | 7 | 635 |
| account balance rows | 10080 | 10080 |
| policy | `dry_run=True`, multiplier `0.2` | `dry_run=False`, multiplier `0.2` |
| lineage decisions | `target_long×7` | `target_long×318`, `target_short×317` |
| orders / fills / positions | 0 / 0 / 0 | 1265 / 1265 / 633 |
| PnL total (USDT) | 0 | -0.31674399999610614 |
| Max Drawdown (Pct) | 0 | -1.4153560695447201e-05 |
| Max Drawdown (Abs, USDT) | 0 | -1.415370000016992 |
| Win Rate | null | 0.27689873417721517 |
| Expectancy (USDT) | null | -0.0005475727848101619 |
| report `missing_metrics` | none | none |
| review blockers | none | none |
| promotion blockers | `manual_review_required_before_disabling_dry_run` | none |
| report recommendation | `manual_review_required_before_paper_simulated` | `review_simulated_paper_evidence` |

### Reading v5

- **Paper drawdown evidence is now complete for local simulated bundles.**
  `account_balances.parquet` has one equity snapshot per catalog bar, so max
  drawdown is computed from the same event-time curve that drives the paper
  risk checks.
- **FreqAI remains shadow-only.** Its dry-run bundle has complete metrics and
  no review blockers, but ADR-007 still requires manual promotion review
  before disabling `dry_run`.
- **Rule simulated remains a control, not alpha.** It proves simulated
  fills/positions/equity/lineage are auditable; the negative PnL still says
  nothing has been promoted toward testnet/live.

### v5 reproduction

Starting from the v3 catalog and signal store:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2 \
  --policy-dry-run

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_paper_bundle \
  --json data/paper/<freqai_run_id>

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source rule_baseline_v1 \
  --signal-model-version 'ema5-20+rsi14' \
  --allowed-source rule_baseline_v1 \
  --allowed-model-version 'ema5-20+rsi14' \
  --trade-size 0.001 \
  --starting-balance 100000 \
  --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_paper_bundle \
  --json data/paper/<rule_run_id>
```

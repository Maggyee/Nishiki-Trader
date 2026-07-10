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


---

## 2026-05-17 v6 — first ADR-007 §2.6 promotion review (`hold` on freqai_linear_v1)

- **Catalog input**: same 7-day `BTCUSDT.BINANCE` 1m catalog as v2 .. v5
  (10080 bars).
- **Signal store**: `data/bridge/signals.db` sha256
  `55e5a218d1d9213d145a4db1148f07e6a62b0a7676e6b8ce4eaf26d09420323a`.
- **Code baseline**: git `3ee958c`
  (`feat(strategies_nautilus): add incremental paper runtime evidence`)
  plus `apps.strategies_nautilus.runners.promotion_review` (this entry).
- **Change vs v5**: `paper_runner.py` now records the incremental paper
  session metadata (heartbeat / poll cursor / restart sequence / data-gap
  events). The first ADR-007 §2.6 promotion review uses these fields to
  evidence "no manual intervention, no restart, no data gap" before a
  `hold` decision.

| metric | freqai paper shadow (v6) | Δ vs v5 |
|---|---:|---|
| bundle | `data/paper/20260517-050320Z-f5e13cda` | new |
| manifest sha256 | `88164be1024d96f706f27d53e22933a7cbab6eedd576bb0a7274307ccc95eebe` | new |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | unchanged |
| `git_dirty` | false | unchanged |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | unchanged |
| signal rows | 7 | unchanged |
| account balance rows | 10080 | unchanged |
| heartbeat_count | 10080 | new (was unset) |
| poll_count | 10080 | new (was unset) |
| processed_until_ns | 1704671940000000000 | new (was unset) |
| polling_mode | incremental | new (was unset) |
| restart_sequence | 0 | new (was unset) |
| data_gap_count | 0 | new (was unset) |
| policy | `dry_run=True`, multiplier `0.2` | unchanged |
| lineage decisions | `target_long×7` | unchanged |
| orders / fills / positions | 0 / 0 / 0 | unchanged |
| PnL total (USDT) | 0 | unchanged |
| Max Drawdown (Pct) | 0 | unchanged |
| Max Drawdown (Abs, USDT) | 0 | unchanged |
| review blockers | none | unchanged |
| promotion gate blockers (review tool) | none | new |
| review record | [`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md`](../retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md) | new |
| review decision | `hold @ paper_shadow` | new |
| review decision allowed | yes | new |

### Reading v6

- **The promotion-review tool is the new gate.** v4 introduced
  `report_paper_bundle` (passive evidence summary). v6 layers
  `promotion_review` on top: the operator must declare `current_stage`,
  `target_stage`, `current_policy`, `target_policy`, and a written
  rationale; the tool checks the ADR-007 §2.5 stage table, the
  `paper_shadow → paper_simulated` evidence threshold (≥ 50 signals
  OR ≥ 7 days), bundle/policy match, `git_dirty`, review blockers,
  Phase-2 stage cap, and decision-specific rules. A `hold` is now a
  signed audit record, not an implicit assumption.
- **freqai_linear_v1 remains at `paper_shadow`.** The bundle satisfies
  the days-half of the ADR-007 OR-gate (7 inclusive days) but is far
  below the signals-half (7 vs 50). The retro records this reasoning
  so future agents do not silently re-attempt promotion without first
  expanding the catalog or signal rate.
- **Incremental session evidence is now visible to the review.**
  `runtime.heartbeat_count=10080`, `poll_count=10080`,
  `processed_until_ns` set, `restart_sequence=0`, `data_gap_count=0`
  give the operator concrete numbers to weigh, instead of reading
  "no restart was reported" as "no restart happened".

### v6 reproduction

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

UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
  data/paper/<freqai_run_id> \
  --current-stage paper_shadow \
  --target-stage paper_shadow \
  --current-dry-run --current-position-pct-multiplier 0.2 \
  --target-dry-run --target-position-pct-multiplier 0.2 \
  --decision hold \
  --operator nishiki \
  --rationale "<evidence-grounded reason>" \
  --output-markdown docs/retros/<UTC>-freqai-linear-v1-hold-paper-shadow.md
```


---

## 2026-05-17 v7 — catalog extended to 31 days, freqai_linear_v1 crosses ≥50 signal gate

- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/`
  covering **2024-01-01 through 2024-01-31** (44640 1m bars, 0 ts gaps,
  backfilled day-by-day via `apps.ops.backfill_bars`).
- **Signal store**: `data/bridge/signals.db` sha256
  `48ec184b4f6e8d0472672bdea8da3abb9cda4f7ff00d55208828eb2364e89fd7`
  (= v6 store + 301 new `freqai_linear_v1` rows; old 7 rows from v3..v6
  were preserved via `DuplicateSignalError` dedupe).
- **Code baseline**: git `52a01ba`
  (`feat(strategies_nautilus): add ADR-007 §2.6 promotion-review tooling`).
- **Goal of v7**: cross the ADR-007 §2.5 paper_shadow → paper_simulated
  evidence threshold (≥ 50 signals OR ≥ 7 days) on the **signals half**,
  not just the days half. v6 satisfied days only; v7 satisfies both.

### Reproducibility anchor (must hold for any future v8+)

| field | v3 (7-day) | v6 (7-day) | v7 (31-day) |
|---|---|---|---|
| `signal_source.model_version` | `linear-mom-train20240105` | `linear-mom-train20240105` | `linear-mom-train20240105` |
| `features_hash` (in raw_json) | `sha256:885207ac…` | `sha256:885207ac…` | `sha256:885207ac…` |
| `metadata.train_rows` | 7181 | 7181 | 7181 |
| `metadata.train_start` | 2024-01-01T00:19:00+00:00 | 2024-01-01T00:19:00+00:00 | 2024-01-01T00:19:00+00:00 |
| `metadata.train_until` | 2024-01-05T23:59:00+00:00 | 2024-01-05T23:59:00+00:00 | 2024-01-05T23:59:00+00:00 |

The model fit is **identical across v3, v6, v7** because `train_until_ns`
did not change. Extending the catalog only enlarges the out-of-sample
prediction region; the existing 7 v3..v6 signals are unchanged and
deduped by `signal_id`. This is the ADR-002 §5 traceability contract
working: same `(source, model_version, features_hash)` ⇒ same model ⇒
deterministic predictions.

### v7 bundle fingerprint

| metric | freqai paper shadow (v7) | Δ vs v6 (7-day) |
|---|---:|---|
| bundle | `data/paper/20260517-051417Z-9afb2cd1` | new |
| manifest sha256 | `218e3b0c75db85b5c6a90f692ee270d9d1de5b1aed58bab0e2fbc8015b541035` | new |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | unchanged |
| `git_dirty` | false | unchanged |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | unchanged |
| backtest_start | 2024-01-01T00:00:00.000Z | unchanged |
| backtest_end | 2024-01-31T23:59:00.000Z | +24 days |
| session_days_inclusive | 31 | +24 |
| iterations | 44640 | +34560 |
| signal rows | **308** | **+301** |
| account balance rows | 44640 | +34560 |
| heartbeat_count | 44640 | +34560 |
| poll_count | 44640 | +34560 |
| processed_until_ns | 1706745540000000000 | extended through 2024-01-31 |
| restart_sequence | 0 | unchanged |
| data_gap_count | 0 | unchanged |
| policy | `dry_run=True`, multiplier `0.2` | unchanged |
| lineage decisions | `target_long×225`, `target_short×83` (new bias) | new |
| orders / fills / positions | 0 / 0 / 0 | unchanged (dry-run) |
| PnL total (USDT) | 0 | unchanged (dry-run) |
| Max Drawdown (Pct / Abs USDT) | 0 / 0 | unchanged (dry-run) |
| review blockers | none | unchanged |
| promotion gate blockers | none | unchanged |
| second retro | [`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md`](../retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md) | new |
| review decision | `hold @ paper_shadow` | unchanged decision; new rationale |
| review decision allowed | yes | unchanged |

### Reading v7

- **The signals half of the ADR-007 §2.5 OR-gate is now cleared.** v6
  passed only on days (7 days, 7 signals). v7 passes on both halves
  (31 days, 308 signals ≥ 50). The promotion-review tool now reports
  `promotion_gate_blockers=[]` for the paper-shadow → paper-simulated
  transition, which v6 also did, but v6 was satisfied trivially on
  days. v7 is the first bundle where freqai_linear_v1 has enough
  shadow signals to argue from.
- **The decision is still `hold`, on a different reason.** v6 held
  because the absolute sample size was tiny (7). v7 holds because the
  308-signal evidence is **in-sample on January 2024** — the model
  was trained on 2024-01-01 .. 2024-01-05, predictions on 2024-01-06
  .. 2024-01-31 are out-of-sample relative to *training* but still
  inside the *January regime*. ADR-007 §2.6 manual review is the place
  where this distinction must be argued, and the v7 retro records it
  explicitly.
- **Lineage now shows mixed long/short bias.** v6 emitted `target_long×7`
  only; v7 emits `target_long×225` and `target_short×83`. This is
  the first time both sides of the model are exercised through the
  paper bridge end to end.
- **Reproducibility is preserved.** Same model, same `features_hash`,
  same `train_*` metadata across v3 / v6 / v7; the only change is the
  size of the OOS region. Anyone reproducing the run from a clean
  signal store and a 31-day catalog must land on the same 308 signals
  and the same `model_version` / `features_hash`.

### v7 reproduction

Starting from the v3 catalog (7 days) and signal store:

```bash
# Backfill the additional 24 days (2024-01-08 .. 2024-01-31). Idempotent —
# already-downloaded zips are skipped. Use a small sleep for politeness.
for d in $(seq -w 8 31); do
  UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.backfill_bars \
    --download --symbol BTCUSDT --interval 1m --date 2024-01-$d \
    --catalog-path data/catalog
  sleep 0.5
done

# Re-run the freqai linear exporter. Old 7 signals are deduped via
# DuplicateSignalError; ~301 new ones are written for 2024-01-08 .. 31.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT \
  --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --train-until '2024-01-05T23:59:00Z'

# Generate the 31-day paper-shadow bundle.
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

# Run the promotion review against the new bundle.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
  data/paper/<freqai_31d_run_id> \
  --current-stage paper_shadow \
  --target-stage paper_shadow \
  --current-dry-run --current-position-pct-multiplier 0.2 \
  --target-dry-run --target-position-pct-multiplier 0.2 \
  --decision hold \
  --operator nishiki \
  --rationale "<in-sample-vs-hold-out reasoning>" \
  --output-markdown docs/retros/<UTC>-freqai-linear-v1-hold-paper-shadow-31d.md
```


---

## 2026-05-17 v8 — catalog extended to 60 days; first hold-out month evidence

- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/`
  covering **2024-01-01 through 2024-02-29** (86400 1m bars, 0 ts gaps,
  60 days; February is a leap-year 29-day month and is fully covered).
- **Signal store**: `data/bridge/signals.db` sha256
  `6c30373984f7e565c855adb3f946722c43c9253038956895b34233a386d02dfe`
  (= v7 store + 287 new `freqai_linear_v1` rows in February;
  308 January rows from v7 were preserved via `DuplicateSignalError`).
- **Code baseline**: git `35a35c2`
  (`docs(progress): extend catalog to 31 days; freqai_linear_v1 crosses ≥50 signal gate`).
- **Goal of v8**: produce a **held-out month** (February) where the
  trainer has never seen any data, then compare January-vs-February
  signal-side distributions to test whether the model survives a
  regime change. The trainer boundary `train_until=2024-01-05T23:59`
  is unchanged, so January `signal_id`s are unchanged from v7 and only
  February is new.

### Reproducibility anchor (still holds)

| field | v3 (7-day) | v6 (7-day) | v7 (31-day) | v8 (60-day) |
|---|---|---|---|---|
| `signal_source.model_version` | `linear-mom-train20240105` | same | same | same |
| `features_hash` (in raw_json) | `sha256:885207ac…` | same | same | same |
| `metadata.train_rows` | 7181 | 7181 | 7181 | 7181 |
| `metadata.train_start` | 2024-01-01T00:19:00+00:00 | same | same | same |
| `metadata.train_until` | 2024-01-05T23:59:00+00:00 | same | same | same |
| `freqai_linear_v1` rows in store | 7 | 7 | 308 | 595 |

### v8 bundle fingerprint

| metric | freqai paper shadow (v8) | Δ vs v7 (31-day) |
|---|---:|---|
| bundle | `data/paper/20260517-052512Z-36feef84` | new |
| manifest sha256 | `9d813db2a77adf39cb974f5e6b7b3e04b2f701f930757edf132d97fd3ddb13c0` | new |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | unchanged |
| `git_dirty` | false | unchanged |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | unchanged |
| backtest_start | 2024-01-01T00:00:00.000Z | unchanged |
| backtest_end | 2024-02-29T23:59:00.000Z | +29 days |
| session_days_inclusive | 60 | +29 |
| iterations | 86400 | +41760 |
| signal rows | **595** (308 Jan + 287 Feb) | **+287 (Feb hold-out)** |
| account balance rows | 86400 | +41760 |
| heartbeat_count | 86400 | +41760 |
| poll_count | 86400 | +41760 |
| processed_until_ns | 1709251140000000000 | extended through 2024-02-29 |
| restart_sequence | 0 | unchanged |
| data_gap_count | 0 | unchanged |
| policy | `dry_run=True`, multiplier `0.2` | unchanged |
| lineage decisions | `target_long×436`, `target_short×159` | new |
| orders / fills / positions | 0 / 0 / 0 | unchanged (dry-run) |
| PnL total (USDT) | 0 | unchanged (dry-run) |
| Max Drawdown (Pct / Abs USDT) | 0 / 0 | unchanged (dry-run) |
| review blockers | none | unchanged |
| promotion gate blockers | none | unchanged |
| third retro | [`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md`](../retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md) | new |
| review decision | `hold @ paper_shadow` | unchanged decision; new rationale |
| review decision allowed | yes | unchanged |

### Jan-vs-Feb hold-out distributional comparison

Computed ad-hoc by joining `signal_lineage.parquet` (from the v8 paper
bundle) with `signals.db` rows on `signal_id`, splitting on
`ts_event < 2024-02-01T00:00Z`. The script is intentionally not
committed to the repo; it is a one-shot research aid. The numbers
below are the contract.

| metric | Jan (in-sample month) | Feb (hold-out month) | drift |
|---|---:|---:|---|
| signal count | 308 | 287 | -6.8% (within fewer-days budget) |
| inclusive days | 31 | 29 | leap year |
| signals per day | 9.94 | 9.90 | -0.4% |
| `target_long` lineage | 225 | 211 | -6.2% |
| `target_short` lineage | 83 | 76 | -8.4% |
| long_share | 0.7305 | 0.7352 | +0.6% |
| score p50 (`buy`) | +0.2342 | +0.2342 | 0 |
| score p50 (`sell`) | -0.2438 | -0.2332 | +4.3% |
| score abs_mean (`buy`) | 0.2817 | 0.2785 | -1.1% |
| score abs_mean (`sell`) | 0.2967 | 0.2736 | -7.8% |
| confidence mean (`buy`) | 0.5647 | 0.5627 | -0.4% |
| confidence mean (`sell`) | 0.5737 | 0.5597 | -2.4% |

### Reading v8

- **Signal-side hold-out passes.** Density (9.94 vs 9.90 / day),
  long-share (0.7305 vs 0.7352), and score / confidence quantiles are
  near-identical between January (in-sample month) and February
  (held-out month). The model does not collapse under a one-month
  regime shift. This is the first piece of out-of-training evidence
  that `freqai_linear_v1 / linear-mom-train20240105` is at least
  *consistent* outside its training month.
- **Return-side hold-out is still missing.** Dry-run paper-shadow
  produces no fills, so Win Rate / Expectancy / max drawdown are not
  computable from the v8 bundle. ADR-007 §2.5 is explicit that this
  is exactly what the `paper_simulated` stage exists for: turn off
  `dry_run`, keep the multiplier at 0.2, and run the bundle to
  collect those numbers. The v8 retro records "promote to
  paper_simulated" as the next deliberate human action; this v8 retro
  itself is still `hold` because flipping `dry_run` is the kind of
  state change ADR-007 §2.6 reserves for an explicit, dedicated
  promote retro.
- **Reproducibility chain is intact across v3 → v6 → v7 → v8.** Same
  `model_version`, same `features_hash`, same `train_rows`, same
  `train_start` / `train_until`. Only the OOS region grows; only new
  `signal_id`s are added. Anyone reproducing v8 from v7 just adds
  February days to the catalog and reruns the exporter.

### v8 reproduction

Starting from the v7 catalog (31 days) and signal store (308 freqai rows):

```bash
# Backfill February 2024 (leap-year 29 days). Idempotent.
for d in $(seq -w 1 29); do
  UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.backfill_bars \
    --download --symbol BTCUSDT --interval 1m --date 2024-02-$d \
    --catalog-path data/catalog
  sleep 0.5
done

# Re-run the freqai linear exporter. Old 308 January rows are deduped
# via DuplicateSignalError; ~287 new February rows are written.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals \
  --catalog-path data/catalog \
  --signal-store-path data/bridge/signals.db \
  --symbol BTCUSDT --venue BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --train-until '2024-01-05T23:59:00Z'

# Generate the 60-day paper-shadow bundle.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2 --policy-dry-run

# Run the third promotion review.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
  data/paper/<v8_run_id> \
  --current-stage paper_shadow --target-stage paper_shadow \
  --current-dry-run --current-position-pct-multiplier 0.2 \
  --target-dry-run --target-position-pct-multiplier 0.2 \
  --decision hold --operator nishiki \
  --rationale "<hold-out distributional evidence summary>" \
  --output-markdown docs/retros/<UTC>-freqai-linear-v1-hold-paper-shadow-60d-holdout.md
```

The Jan-vs-Feb distributional comparison itself is reproducible by
joining `signal_lineage.parquet` from the v8 bundle with `signals.db`
on `signal_id` and grouping on `ts_event < 2024-02-01T00:00Z`. The
script is one-shot and intentionally not committed; rerunning it on
the v8 fingerprint above must produce the numbers in the table above
or the v8 fingerprint is no longer reproducible.


---

## 2026-05-17 v9 — first deliberate promote: paper_shadow → paper_simulated

- **Catalog input**: same 60-day catalog as v8 (2024-01-01..2024-02-29,
  86400 1m bars, 0 ts gaps).
- **Signal store**: same as v8, sha256
  `6c30373984f7e565c855adb3f946722c43c9253038956895b34233a386d02dfe`
  (595 freqai rows: 308 Jan + 287 Feb).
- **Code baseline**: git `a9a35d4`
  (`docs(progress): extend catalog to 60 days; first hold-out month evidence for freqai_linear_v1`).
- **Change vs v8**: this is the first time `freqai_linear_v1` is run
  with `SourcePolicy(dry_run=False, position_pct_multiplier=0.2)`. The
  flip is authorized by an explicit `promote` retro before the run; the
  resulting bundle is the first paper_simulated evidence for the
  source.

### What landed

1. **`promote` retro** (first ever for any source in this project):
   [`docs/retros/2026-05-17-freqai-linear-v1-promote-paper-simulated.md`](../retros/2026-05-17-freqai-linear-v1-promote-paper-simulated.md).
   Evidence bundle: v8 paper-shadow (`data/paper/20260517-052512Z-36feef84`).
   `decision_allowed=True`; `policy_diff={"dry_run": {"current": true, "target": false}}`;
   `bundle_policy_matches_current=True`; no review or promotion gate
   blockers. `decision_reasons=["promote_gates_passed"]`.
2. **v9 simulated bundle**: produced by re-running `paper_runner` with
   `--policy-position-pct-multiplier 0.2` and **without** `--policy-dry-run`.
3. **`hold @ paper_simulated` retro**:
   [`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md`](../retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md).
   Records the first paper_simulated state for this source. Decision
   is `hold` because the next stage (testnet_canary) is hard-blocked
   by `promotion_review`'s `phase_3_not_ready` gate and ADR-007 §2.5
   also requires a Phase 3 testnet runbook that does not exist yet.

### v9 simulated bundle fingerprint

| metric | freqai paper simulated (v9) | reference (v8 shadow) |
|---|---:|---:|
| bundle | `data/paper/20260517-053502Z-37b99b3f` | `data/paper/20260517-052512Z-36feef84` |
| manifest sha256 | `fa344a5534c220a0a0547f58f069394921399fd21def505faaf3c978d04e6efb` | `9d813db2a77adf39cb974f5e6b7b3e04b2f701f930757edf132d97fd3ddb13c0` |
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | same |
| `git_dirty` | false | same |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | same |
| backtest_start | 2024-01-01T00:00:00.000Z | same |
| backtest_end | 2024-02-29T23:59:00.000Z | same |
| session_days_inclusive | 60 | same |
| iterations | 86400 | same |
| signal rows | 595 | same |
| applied policy | **`dry_run=False`**, multiplier `0.2` | `dry_run=True`, multiplier `0.2` |
| heartbeat_count | 86400 | same |
| poll_count | 86400 | same |
| processed_until_ns | 1709251140000000000 | same |
| restart_sequence | 0 | same |
| data_gap_count | 0 | same |
| **orders** | **545** | 0 (dry-run) |
| **fills** | **545** | 0 (dry-run) |
| **positions** | **273** | 0 (dry-run) |
| account_balances rows | 86400 | same |
| lineage decisions | `target_long×436`, `target_short×159` | same totals; reasons differ |
| lineage reasons (top) | empty×273 (first-fill openings), `already_target_long×299`, `already_target_short×23` | `dry_run×595` |
| every order has signal_id | yes (0 missing) | n/a |
| every fill has signal_id | yes (0 missing) | n/a |
| positions.signal_ids set | yes | n/a |
| kill-switch fires | 0 | 0 |
| **PnL (total, USDT)** | **+5.0076** | 0 (dry-run) |
| PnL% (total) | +0.005008% | 0 |
| **Win Rate** | 0.5551 | null |
| **Expectancy (USDT/trade)** | **+0.01858** | null |
| **Max Drawdown (Pct)** | **-1.0035e-05 (-0.001003%)** | 0 |
| **Max Drawdown (Abs, USDT)** | **-1.0035** | 0 |
| review blockers | none | none |
| promotion gate blockers (target=paper_simulated, decision=hold) | none | n/a |

### Reading v9

- **First real return-side numbers for `freqai_linear_v1`.** v3..v8
  were dry-run; v9 is the first time orders/fills/positions are
  produced and the strategy and `RiskEngine` are exercised end to
  end. Win Rate 55.5%, expectancy +0.019 USDT/trade, max drawdown
  -0.001% on the 60-day window. Numerically the source is positive,
  but the magnitude is tiny relative to fees / slippage modelling —
  this is "consistent enough to keep running on paper_simulated", not
  "alpha".
- **ADR-002 §4.1 traceability holds.** 545 orders and 545 fills carry
  signal_id (0 missing); 273 positions reference signal_ids. The
  number of unique `signal_id`s in fills (273) matches positions
  exactly because each position is opened by the first fill of a
  signal-driven order; subsequent same-signal fills inside the same
  position reuse the position record.
- **Strategy "already-on-side" logic shows.** 595 signals → 273
  position openings + 299 already_target_long + 23 already_target_short
  = 595 lineage rows. The strategy correctly does not double-open
  when a long signal arrives while already long, and the lineage
  reason explicitly names this behaviour.
- **Phase 2 ceiling reached for this source.** paper_simulated is the
  highest stage allowed in Phase 2 by `promotion_review`'s
  `phase_3_not_ready` gate. Any further promote requires Phase 3
  ADRs to define testnet runtime, exchange credentials management,
  emergency flatten, restart recovery, and alerting.

### v9 reproduction

Starting from the v8 catalog (60 days) and signal store (595 freqai rows):

```bash
# 1. Authorize the promote with the v8 shadow bundle as evidence.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
  data/paper/<v8_run_id> \
  --current-stage paper_shadow --target-stage paper_simulated \
  --current-dry-run --current-position-pct-multiplier 0.2 \
  --target-no-dry-run --target-position-pct-multiplier 0.2 \
  --decision promote --operator nishiki \
  --rationale "<§2.5 / §2.6 evidence summary>" \
  --output-markdown docs/retros/<UTC>-freqai-linear-v1-promote-paper-simulated.md

# 2. Run the simulated bundle WITHOUT --policy-dry-run.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner \
  --instrument-id BTCUSDT.BINANCE \
  --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' \
  --signal-source freqai_linear_v1 \
  --signal-model-version linear-mom-train20240105 \
  --allowed-source freqai_linear_v1 \
  --allowed-model-version linear-mom-train20240105 \
  --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5 \
  --policy-position-pct-multiplier 0.2

# 3. Record the simulated state with a hold retro.
UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.promotion_review \
  data/paper/<v9_run_id> \
  --current-stage paper_simulated --target-stage paper_simulated \
  --current-no-dry-run --current-position-pct-multiplier 0.2 \
  --target-no-dry-run --target-position-pct-multiplier 0.2 \
  --decision hold --operator nishiki \
  --rationale "<v9 sanity + return-side metrics + Phase 3 gating>" \
  --output-markdown docs/retros/<UTC>-freqai-linear-v1-hold-paper-simulated.md
```

Re-running v9 from v8 produces a deterministic bundle: same model
fingerprint + same signal store sha256 + same catalog content + same
git commit must yield the same orders/fills/positions/PnL down to the
floating-point noise level recorded above.


---

## 2026-05-17 v10 — 121-day paper_simulated extension through April

- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/`
  covering **2024-01-01 through 2024-04-30** (174240 1m bars, 121
  calendar days). March and April were appended after v9 as additional
  out-of-sample market regimes while keeping the original
  `train_until=2024-01-05T23:59:00Z` boundary.
- **Signal store**: `data/bridge/signals.db` sha256
  `8c2176c2a67d6d9fdb2fc70ec6c0cf72ea14c04dbf272baf1519a7c49935ca4e`.
  The exporter generated 1750 total `freqai_linear_v1` rows and wrote
  1155 new rows; the prior 595 Jan/Feb rows were skipped as duplicates.
- **Code baseline recorded in bundle**: git `bfbb7e6`
  (`feat(strategies_nautilus): land ADR-008 §6.1 Phase 3a wall-clock paper`).
- **Bundle**: `data/paper/20260517-090217Z-c1214e6d`, manifest sha256
  `966fc8ac6010592b4f2af5b10d6deb3c63109083f2cfa7e70c83b175b26763a3`.
- **Review record**:
  [`docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated-121d.md`](../retros/2026-05-17-freqai-linear-v1-hold-paper-simulated-121d.md).

### v10 simulated bundle fingerprint

| metric | freqai paper simulated (v10) | reference (v9, 60d) |
|---|---:|---:|
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | same |
| `git_dirty` | false | false |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | same |
| backtest_start | 2024-01-01T00:00:00.000Z | same |
| backtest_end | 2024-04-30T23:59:00.000Z | 2024-02-29T23:59:00.000Z |
| session_days_inclusive | 121 | 60 |
| iterations | 174240 | 86400 |
| signal rows | 1750 | 595 |
| applied policy | `dry_run=False`, multiplier `0.2` | same |
| heartbeat_count / poll_count | 174240 / 174240 | 86400 / 86400 |
| data_gap_count / restart_sequence | 0 / 0 | 0 / 0 |
| orders / fills / positions | 1649 / 1649 / 825 | 545 / 545 / 273 |
| lineage decisions | `target_long×1265`, `target_short×485` | `target_long×436`, `target_short×159` |
| lineage reasons | empty×825, `already_target_long×852`, `already_target_short×73` | empty×273, `already_target_long×299`, `already_target_short×23` |
| kill-switch / expired / unauthorized / signal_lag | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| PnL (total, USDT) | +4.4126 | +5.0076 |
| PnL% (total) | +0.004413% | +0.005008% |
| Win Rate | 0.5291 | 0.5551 |
| Expectancy (USDT/trade) | +0.00524 | +0.01858 |
| Max Drawdown (Pct) | -3.8779e-05 (-0.003878%) | -1.0035e-05 (-0.001003%) |
| Max Drawdown (Abs, USDT) | -3.8782 | -1.0035 |
| review blockers / promotion blockers | none / none | none / none |

### Month split

The table below joins `signal_lineage.parquet` to `signals.db` on
`signal_id`, then splits by signal event month. PnL split uses closed
positions by `closed_ts`; the small gap between monthly closed PnL and total
PnL is the final open position's unrealized mark.

| month | signals | target_long | target_short | score_abs_mean | confidence_mean | closed positions | closed PnL USDT | win rate | expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-01 | 308 | 225 | 83 | 0.2857 | 0.5671 | 135 | +0.6463 | 0.5556 | +0.00479 |
| 2024-02 | 287 | 211 | 76 | 0.2772 | 0.5619 | 137 | +4.4086 | 0.5547 | +0.03218 |
| 2024-03 | 621 | 445 | 176 | 0.3168 | 0.5860 | 302 | +1.3731 | 0.5265 | +0.00455 |
| 2024-04 | 534 | 384 | 150 | 0.2845 | 0.5664 | 250 | -2.1081 | 0.5040 | -0.00843 |

### Reading v10

- **The source survives a longer replay mechanically.** Every signal is
  accepted, sidecars match manifest totals, every order/fill path remains
  simulated, `git_dirty=false`, and no data-gap, expiry, authorization,
  signal-lag, or kill-switch blocker appears.
- **The return-side evidence weakens as the window grows.** Total PnL stays
  slightly positive, but expectancy compresses from +0.01858 to +0.00524
  USDT/trade and April is negative. This is still monitoring evidence, not
  alpha evidence.
- **No promotion implication.** `paper_simulated` remains the ceiling for
  this source until ADR-008 Phase 3a's 24h wall-clock soak is recorded and
  Phase 3b-3e testnet credential, emergency, restart, and alert gates exist.


---

## 2026-05-21 v11 — 152-day paper_simulated monitoring extension through May

- **Catalog input**: `data/catalog/data/bar/BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL/`
  covering **2024-01-01 through 2024-05-31** (218880 1m bars, 152
  calendar days, no missing days). May was appended after v10 while keeping
  the original `train_until=2024-01-05T23:59:00Z` boundary.
- **Signal store**: `data/bridge/signals.db` sha256
  `dc096103628497d286872a8cb62737a8880549f6b04ca5d0e91c29a832cf840d`.
  The exporter generated 2107 total historical `freqai_linear_v1` rows,
  wrote 357 new May rows, and skipped the prior 1750 Jan-Apr rows as
  duplicates. The paper run explicitly used
  `--signal-until-ns 1717199940000000000` to exclude later wall-clock
  canary restamp rows from the offline historical window.
- **Code baseline recorded in bundle**: git `7b048db`
  (`docs(retros): record clean live telemetry canary`), `git_dirty=false`.
- **Bundle**: `data/paper/20260521-021418Z-e535b581`, manifest sha256
  `06d9300a3183a80cb8c3c7874034aad12985fee3c814dae48e2dd9881ab44095`.
- **Monitoring record**:
  [`docs/retros/2026-05-21-freqai-linear-v1-paper-simulated-152d-monitoring.md`](../retros/2026-05-21-freqai-linear-v1-paper-simulated-152d-monitoring.md).
  This is not a `SourcePolicy` decision and does not open
  `promotion_review.py`.

### v11 simulated bundle fingerprint

| metric | freqai paper simulated (v11) | reference (v10, 121d) |
|---|---:|---:|
| source / model | `freqai_linear_v1 / linear-mom-train20240105` | same |
| `git_dirty` | false | false |
| runtime mode / data_mode / order_mode | `paper` / `catalog_polling` / `simulated` | same |
| backtest_start | 2024-01-01T00:00:00.000Z | same |
| backtest_end | 2024-05-31T23:59:00.000Z | 2024-04-30T23:59:00.000Z |
| session_days_inclusive | 152 | 121 |
| iterations | 218880 | 174240 |
| signal rows | 2107 | 1750 |
| applied policy | `dry_run=False`, multiplier `0.2` | same |
| heartbeat_count / poll_count | 218880 / 218880 | 174240 / 174240 |
| data_gap_count / restart_sequence | 0 / 0 | 0 / 0 |
| orders / fills / positions | 1987 / 1987 / 994 | 1649 / 1649 / 825 |
| lineage decisions | `target_long×1525`, `target_short×582` | `target_long×1265`, `target_short×485` |
| kill-switch / expired / unauthorized / signal_lag | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| PnL (total, USDT) | +4.8726 | +4.4126 |
| PnL% (total) | +0.004873% | +0.004413% |
| Win Rate | 0.5358 | 0.5291 |
| Expectancy (USDT/trade) | +0.00491 | +0.00524 |
| Max Drawdown (Pct) | -3.8779e-05 (-0.003878%) | -3.8779e-05 (-0.003878%) |
| Max Drawdown (Abs, USDT) | -3.8782 | -3.8782 |
| review blockers / promotion blockers | none / none | none / none |

### Month split

| month | signals | target_long | target_short | score_abs_mean | confidence_mean | closed positions | closed PnL USDT | win rate | expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-01 | 308 | 225 | 83 | 0.2857 | 0.5671 | 135 | +0.6463 | 0.5556 | +0.00479 |
| 2024-02 | 287 | 211 | 76 | 0.2772 | 0.5619 | 137 | +4.4086 | 0.5547 | +0.03218 |
| 2024-03 | 621 | 445 | 176 | 0.3168 | 0.5860 | 302 | +1.3731 | 0.5265 | +0.00455 |
| 2024-04 | 534 | 384 | 150 | 0.2845 | 0.5664 | 250 | -2.1081 | 0.5040 | -0.00843 |
| 2024-05 | 357 | 260 | 97 | 0.2689 | 0.5569 | 169 | +0.5535 | 0.5680 | +0.00328 |

### Reading v11

- **The mechanical evidence still holds.** Every historical signal through
  May is accepted, sidecars match manifest totals, every order/fill path
  remains simulated, `git_dirty=false`, and no data-gap, expiry,
  authorization, signal-lag, or kill-switch blocker appears.
- **May is mildly positive but does not strengthen the alpha case.** The
  total PnL improves from v10's +4.4126 USDT to +4.8726 USDT and May alone
  adds +0.5535 USDT, but overall expectancy stays very small at
  +0.00491 USDT/trade. This remains monitoring evidence, not a reason to
  increase risk.
- **No policy implication.** The source is already authorized at
  `testnet_canary` with multiplier `0.1`; this v11 bundle is a
  paper_simulated monitoring extension at multiplier `0.2`. It should not be
  used as routine `hold @ testnet_canary` ratification.

---

## 2026-07-10 — cost-sensitive full-year blind review

The catalog now covers all of 2024 (527040 BTCUSDT 1m bars, zero duplicates,
zero timestamp gaps). Two fixed Spot-only long/flat candidates were evaluated
on the locked 2024-08-01..2024-12-31 window with 10 bps fees and 2/5 bps
slippage scenarios:

| source / model | signals in blind bundle | fills / positions | gross PnL | base PnL | stress PnL | base-positive months | result |
|---|---:|---:|---:|---:|---:|---:|---|
| `freqai_linear_walkforward_v1 / ridge-wf60d-cost30bp-v1` | 1 | 2 / 1 | -0.904010 | -1.129677 | -1.186094 | 0/5 | fail |
| `rule_breakout_v1 / donchian20-10-atr14x0.25-15m` | 368 | 368 / 184 | -6.064690 | -39.313136 | -47.625248 | 1/5 | fail |

Both candidates produced zero short positions and reproduced byte-for-byte
across fills, orders, positions, and signal lineage. Neither enters
paper_shadow. Same-size buy-and-hold returned +28.752138 USDT under the base
scenario. Full evidence and hashes:
[`2026-07-10-cost-sensitive-alpha-blind-review.md`](../retros/2026-07-10-cost-sensitive-alpha-blind-review.md).

---

## 2026-07-10 — pre-registered trend-regime 2025 blind review

`rule_trend_regime_v1 / ema24-96-1h-mom24-atr14x0.5-v1` was locked in commit
`b8c7ee2` before any 2025 market data was read. Its 2024-08..12 development
screen was aggregate-positive (gross/base/stress
`+16.191970/+10.844598/+9.507755` USDT), so the written protocol allowed the
future 2025-08..12 blind window to be consumed.

| fills / positions | gross PnL | base PnL | stress PnL | base-positive months | shorts | result |
|---:|---:|---:|---:|---:|---:|---|
| 62 / 31 | -13.634510 | -21.238820 | -23.139897 | 1/5 | 0 | `stop_before_testnet_resume` |

The two clean runs matched byte-for-byte across fills, orders, positions, and
signal lineage, but the candidate failed both profitability gates and the
4/5-month gate. It does not enter paper_shadow and must not be tuned against
the opened blind window under the same fingerprint. Full evidence and hashes:
[`2026-07-10-trend-regime-2025-blind-review.md`](../retros/2026-07-10-trend-regime-2025-blind-review.md).

# Project Status

- **Status file**: Active
- **Last updated**: 2026-05-17
- **Current phase**: Phase 2 entry
- **Current objective**: Stabilize model-driven `freqai_*` signal exports and simulated paper-session bundles while preserving the `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` boundary.
- **Source of truth**: This file for current state; ADRs for durable decisions; `docs/progress/` for detailed historical progress.

This file answers: "Where is the project now, and what should the next agent do?"

## Status File Discipline

`docs/project-status.md` is a current-state dashboard, not a changelog. Keep it short enough to read at every task start.

Rules for future agents:

- Keep only current phase, current objective, active focus, next steps, blockers, latest verification, and short milestone summaries here.
- Do not append long completed-work lists, command transcripts, or implementation narratives here.
- Move detailed historical progress to `docs/progress/` and link the archive if it remains useful.
- Put permanent architecture decisions in `docs/decisions/`, not this file.
- When updating this file, prefer replacing stale detail with current facts over adding more lines.

Detailed history archived so far:

- `docs/progress/phase-0-1-to-phase-2-entry.md`
- `docs/progress/phase-2-signal-source-baselines.md` — demo vs rule signal-source bundle fingerprints for BTCUSDT 2024-01-01.

## Progress Sync Protocol

At task start:

1. Read `docs/agent-reading-list.md`.
2. Read this file.
3. Run `git status --short --branch`.
4. If the working tree is clean, run `git fetch origin` and `git pull --ff-only`.
5. If the working tree is not clean, inspect local changes first; do not overwrite, rebase, stash, or reset without explicit user direction.
6. Run `git log --oneline --decorate -5`.
7. Inspect only files relevant to the task.

At task finish:

1. Update this file only if current phase, focus, blockers, next steps, or verification changed.
2. Archive detail in `docs/progress/` when the update would turn this file into a changelog.
3. Commit code and documentation changes unless the user explicitly says not to.
4. Report the commit hash, verification, upstream-source status, and live-path impact.

## Milestones

- Phase 0 skeleton and agent contracts are in place.
- ADR-001 through ADR-007 define the core tech stack, `SignalEvent v1`, project skeleton, backtest result format, signal-source taxonomy (`<family>_<variant>` with families = {manual, rule, freqai, llm}), gray-rollout / dry-run mechanics, and paper trading runtime / SourcePolicy promotion gates.
- Phase 1 bridge is implemented: `apps/bridge/` validates, persists, and replays `SignalEvent v1` through SQLite/WAL with CLI coverage.
- Placeholder strategy-side consumer is implemented: `apps/strategies_nautilus/signal_consumer.py` applies ADR-002 §4.1 checks without touching trading APIs.
- Baseline decision layer is implemented: `apps/strategies_nautilus/baseline_strategy.py` maps accepted signals to `OrderIntent` and enforces the 5%-day-loss kill-switch.
- Phase 2 Nautilus backtest path is catalog-driven: `backtest_runner.py` loads one instrument/bar type from `ParquetDataCatalog`, replays signals from `SignalStore.replay(**filter)`, validates ADR-004 sidecars, and exposes a `python -m` CLI entrypoint.
- Local real-data smoke path is in place: `apps.ops.backfill_bars` imports a BTCUSDT Binance public kline ZIP into `data/catalog/`, can seed demo `SignalEvent v1` rows, and `compare_backtests.py` compares replayed ADR-004 bundles while ignoring wall-clock run fields.
- Rule-based baseline signal generator is live: `apps/strategies_freqtrade/research/baseline_rule_signals.py` produces EMA(5)/EMA(20) + RSI(14) `SignalEvent v1` via CLI; the BTCUSDT 2024-01-01 fixture round-trips through `SignalStore` → `backtest_runner` end-to-end and writes a full ADR-004 bundle with `signal_id` traced through orders / fills / positions / signal_lineage.
- Upstream runtime is pinned: `nautilus-trader==1.226.0`; local `nautilus_trader/` source checkout is aligned to tag `v1.226.0`.
- First `freqai_*` source-family smoke is live: `apps/strategies_freqtrade/research/freqai_linear_signals.py` exports deterministic ridge-linear momentum predictions as `freqai_linear_v1 / linear-mom-train20240105`; the first baseline is dry-run only via `SourcePolicy(position_pct_multiplier=0.2, dry_run=True)`.
- First ADR-007 simulated paper bundle writer is live: `apps/strategies_nautilus/runners/paper_runner.py` writes `kind="paper"` bundles under `data/paper/<run_id>/` in `runtime.data_mode="catalog_polling"` / `runtime.order_mode="simulated"` mode only; it does not read exchange keys or submit live/testnet orders.
- Paper bundle review reader is live: `apps/strategies_nautilus/runners/report_paper_bundle.py` summarizes `kind="paper"` manifest + sidecars into ADR-007 review evidence without mutating `SourcePolicy` or touching exchange paths.

## Current Focus

Phase 2 entry: stabilize the real NautilusTrader backtest path and make it usable against project data.

Immediate focus:

1. Use the local `BTCUSDT.BINANCE` 1m fixture path as the required smoke test before changing runner behavior.
2. Treat the rule-based baseline (`rule_baseline_v1/ema5-20+rsi14`) as the reproducibility anchor; FreqAI/model-driven signals are a separate stream that must round-trip the same bridge.
3. Preserve reproducibility as catalog data grows: same git commit, signal-store SHA, catalog content, strategy params, risk params, and Nautilus version must produce identical stats and `fills.parquet`.
4. Keep LLM agents out of the live order path; Phase 2 remains research/backtest only.

## Next Steps

1. Use `freqai_linear_v1 / linear-mom-train20240105` as the first model-driven reproducibility anchor, and compare future full FreqAI exports against its dry-run fingerprint before replacing it.
2. Keep `freqai_linear_v1` in dry-run/shadow while collecting more model-source evidence; do not promote to paper simulated orders until there is a promotion review with bundle fingerprints.
3. Add true wall-clock paper session mechanics only after the local simulated bundle path is stable; no testnet/live credentials before that.
4. Decide Phase 2 SQLite -> Postgres / Redis Stream readiness only after backtest or paper volume exposes an actual bottleneck.

## Blocked / Deferred

- No live trading.
- No real exchange API keys in the repository.
- No Redis until cross-process signal transport is required.
- No Postgres/TimescaleDB/pgvector until schemas stabilize.
- No frontend implementation until backtest and risk result schemas are stable.
- No n8n workflows until Phase 3/4.
- No autonomous Agent trading. Agents may only research, review, summarize, and suggest.
- No edits to `freqtrade/` or `nautilus_trader/` unless explicitly requested.

## Latest Verification

On 2026-05-17, after the simulated paper runner landed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 264 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs` -> clean.
- `tests/strategies_nautilus/test_report_paper_bundle.py` covers paper bundle summary output, dry-run policy reporting, review blockers, sidecar count mismatches, CLI JSON/text output, and non-paper rejection.
- ADR-007 now explicitly allows Phase 2 `catalog_polling` simulated paper bundles while keeping true wall-clock paper/testnet/live gated; no runtime service was started and no real trading credentials were introduced.
- `tests/strategies_nautilus/test_paper_runner.py` covers dry-run no-order behavior, simulated orders/fills/positions carrying `signal_id`, signal lag, expired signals, unauthorized sources, kill-switch blocking, CLI entrypoint, and source-level guards against reading secret env vars or submitting live orders.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner --instrument-id BTCUSDT.BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' --signal-source freqai_linear_v1 --signal-model-version linear-mom-train20240105 --allowed-source freqai_linear_v1 --allowed-model-version linear-mom-train20240105 --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5 --policy-position-pct-multiplier 0.2 --policy-dry-run` -> 1 `data/paper/` bundle, signal rows=7, lineage=`target_long×7` with `reason=dry_run`, orders=0, fills=0, PnL=0.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals --catalog-path data/catalog --signal-store-path data/bridge/signals.db --symbol BTCUSDT --venue BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' --train-until '2024-01-05T23:59:00Z'` -> 7 `freqai_linear_v1` SignalEvents written.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.backtest_runner --instrument-id BTCUSDT.BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' --signal-source freqai_linear_v1 --signal-model-version linear-mom-train20240105 --allowed-source freqai_linear_v1 --allowed-model-version linear-mom-train20240105 --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5 --policy-position-pct-multiplier 0.2 --policy-dry-run` -> 1 dry-run bundle, signal rows=7, lineage=`target_long×7`, orders=0, fills=0, PnL=0; policy recorded in the manifest.
- v1/v2 demo and rule fingerprints remain archived in `docs/progress/phase-2-signal-source-baselines.md`; v3 records the first `freqai_linear_v1` fingerprint.

## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

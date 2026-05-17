# Project Status

- **Status file**: Active
- **Last updated**: 2026-05-17
- **Current phase**: Phase 2 entry
- **Current objective**: Replace the demo fixture signals with real FreqAI/research signal exports on the catalog-backed Nautilus backtest path while preserving the `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` boundary.
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
- ADR-001 through ADR-004 define the core tech stack, `SignalEvent v1`, project skeleton, and backtest result format.
- Phase 1 bridge is implemented: `apps/bridge/` validates, persists, and replays `SignalEvent v1` through SQLite/WAL with CLI coverage.
- Placeholder strategy-side consumer is implemented: `apps/strategies_nautilus/signal_consumer.py` applies ADR-002 §4.1 checks without touching trading APIs.
- Baseline decision layer is implemented: `apps/strategies_nautilus/baseline_strategy.py` maps accepted signals to `OrderIntent` and enforces the 5%-day-loss kill-switch.
- Phase 2 Nautilus backtest path is catalog-driven: `backtest_runner.py` loads one instrument/bar type from `ParquetDataCatalog`, replays signals from `SignalStore.replay(**filter)`, validates ADR-004 sidecars, and exposes a `python -m` CLI entrypoint.
- Local real-data smoke path is in place: `apps.ops.backfill_bars` imports a BTCUSDT Binance public kline ZIP into `data/catalog/`, can seed demo `SignalEvent v1` rows, and `compare_backtests.py` compares replayed ADR-004 bundles while ignoring wall-clock run fields.
- Rule-based baseline signal generator is live: `apps/strategies_freqtrade/research/baseline_rule_signals.py` produces EMA(5)/EMA(20) + RSI(14) `SignalEvent v1` via CLI; the BTCUSDT 2024-01-01 fixture round-trips through `SignalStore` → `backtest_runner` end-to-end and writes a full ADR-004 bundle with `signal_id` traced through orders / fills / positions / signal_lineage.
- Upstream runtime is pinned: `nautilus-trader==1.226.0`; local `nautilus_trader/` source checkout is aligned to tag `v1.226.0`.

## Current Focus

Phase 2 entry: stabilize the real NautilusTrader backtest path and make it usable against project data.

Immediate focus:

1. Use the local `BTCUSDT.BINANCE` 1m fixture path as the required smoke test before changing runner behavior.
2. Treat the rule-based baseline (`rule_baseline_v1/ema5-20+rsi14`) as the reproducibility anchor; FreqAI/model-driven signals are a separate stream that must round-trip the same bridge.
3. Preserve reproducibility as catalog data grows: same git commit, signal-store SHA, catalog content, strategy params, risk params, and Nautilus version must produce identical stats and `fills.parquet`.
4. Keep LLM agents out of the live order path; Phase 2 remains research/backtest only.

## Next Steps

1. Extend backfill beyond one BTCUSDT day; append a new dated section to `docs/progress/phase-2-signal-source-baselines.md` when the catalog window changes.
2. Plan ADR-005 (research-layer signal source taxonomy: how FreqAI / model-driven sources slot beside the rule baseline) before adding a second source family.
3. Decide Phase 2 SQLite -> Postgres / Redis Stream readiness only after backtest volume exposes an actual bottleneck.

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

On 2026-05-17, after the rule-based baseline signal generator landed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 183 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests` -> clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.baseline_rule_signals --catalog-path data/catalog --signal-store-path data/bridge/signals.db --symbol BTCUSDT --venue BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL'` -> 71 SignalEvents written for BTCUSDT 2024-01-01.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.backtest_runner --instrument-id BTCUSDT.BINANCE --bar-type 'BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL' --signal-source rule_baseline_v1 --signal-model-version 'ema5-20+rsi14' --allowed-source rule_baseline_v1 --allowed-model-version 'ema5-20+rsi14' --trade-size 0.001 --starting-balance 100000 --min-confidence 0.5` -> 1 bundle, totals fills=142, PnL (total)=-$4.74, Win Rate=12.7% (placeholder strategy, no alpha expected).
- Same CLI swapped to `--signal-source manual_research --signal-model-version binance-fixture-v1` (demo) -> 1 bundle, totals fills=4, PnL (total)=-$1.02, Win Rate=50%. Both fingerprints frozen in `docs/progress/phase-2-signal-source-baselines.md`.

## Recent Git Baseline

- `83b0910 feat(strategies_freqtrade): add rule-based baseline SignalEvent generator`

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

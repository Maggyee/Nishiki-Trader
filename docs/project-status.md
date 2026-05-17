# Project Status

- **Status file**: Active
- **Last updated**: 2026-05-17
- **Current phase**: Phase 2 entry
- **Current objective**: Stabilize model-driven `freqai_*` signal exports and incremental simulated paper-session evidence while preserving the `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` boundary.
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
- First ADR-007 simulated paper bundle writer is live: `apps/strategies_nautilus/runners/paper_runner.py` writes `kind="paper"` bundles under `data/paper/<run_id>/` in `runtime.data_mode="catalog_polling"` / `runtime.order_mode="simulated"` mode only, including per-bar account equity and max drawdown; it does not read exchange keys or submit live/testnet orders.
- Paper bundle review reader is live: `apps/strategies_nautilus/runners/report_paper_bundle.py` summarizes `kind="paper"` manifest + sidecars into ADR-007 review evidence without mutating `SourcePolicy` or touching exchange paths.
- Incremental paper-session mechanics are live: catalog polling now records event-time poll cursors, heartbeat/runtime logs, restart metadata from `previous_run_id`, and market-data gap blockers while keeping orders simulated and exchange credentials out of the path.
- ADR-007 §2.6 promotion-review tooling is live: `apps/strategies_nautilus/runners/promotion_review.py` packages a paper bundle, a declared `current_policy`/`target_policy`, and an operator decision (`promote|hold|demote|disable`) into the seven §2.6 sections plus a `decision_allowed` gate that enforces the §2.5 stage table, the `paper_shadow → paper_simulated` evidence threshold, bundle/policy match, `git_dirty`, review blockers, and the Phase-2 stage cap. Records land in `docs/retros/`.

## Current Focus

Phase 2 entry: stabilize the real NautilusTrader backtest path and make it usable against project data.

Immediate focus:

1. Use the local `BTCUSDT.BINANCE` 1m fixture path as the required smoke test before changing runner behavior.
2. Treat the rule-based baseline (`rule_baseline_v1/ema5-20+rsi14`) as the reproducibility anchor; FreqAI/model-driven signals are a separate stream that must round-trip the same bridge.
3. Preserve reproducibility as catalog data grows: same git commit, signal-store SHA, catalog content, strategy params, risk params, and Nautilus version must produce identical stats and `fills.parquet`.
4. Keep LLM agents out of the live order path; Phase 2 remains research/backtest only.

## Next Steps

1. Use `promotion_review.py` (not just `report_paper_bundle.py`) as the required ADR-007 §2.6 audit artifact for any `SourcePolicy` change. Records land in `docs/retros/<UTC>-<source>-<decision>-<target_stage>.md`.
2. Keep `freqai_linear_v1` in dry-run/shadow. The 2026-05-17 `hold` retro records that the source has 7 signals over 7 days — meets the days half of the ADR-007 §2.5 OR-gate but fails the ≥50 signals half. Next review needs ≥30-day catalog expansion or a higher-rate model variant.
3. Use the new incremental paper-session evidence (`processed_until_ns`, heartbeat log, restart metadata, and data-gap blockers) as the Phase 2 rehearsal before any persistent wall-clock service or testnet work.
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

On 2026-05-17, after ADR-007 §2.6 promotion-review tooling and the first `hold` retro landed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 295 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs` -> clean.
- `tests/strategies_nautilus/test_promotion_review.py` covers: hold passes on a clean dry-run bundle; hold rejects mismatched target policy; promote passes with ≥7-day evidence and explicit policy diff; promote rejects when evidence is below the ADR-007 §2.5 threshold; promote rejects empty policy diff, bundle/current_policy mismatch, stage-skipping, Phase-3 stages, `git_dirty`, and review blockers (kill-switch); demote passes when target is stricter; disable is always allowed; CLI returns nonzero on disallowed decisions; CLI rejects invalid decision names.
- `apps/strategies_nautilus/runners/promotion_review.py` integrates with `report_paper_bundle.load_paper_bundle_report` and never mutates `SourcePolicy`, starts a runtime, or talks to an exchange.
- First retro: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md` records `freqai_linear_v1 / linear-mom-train20240105` held at `paper_shadow`. Bundle `data/paper/20260517-050320Z-f5e13cda` (manifest sha256 `88164be1024d96f706f27d53e22933a7cbab6eedd576bb0a7274307ccc95eebe`) is the v6 paper-shadow fingerprint with `heartbeat_count=10080`, `poll_count=10080`, `processed_until_ns=1704671940000000000`, `restart_sequence=0`, `data_gap_count=0`, `git_dirty=false`, no review blockers, no promotion gate blockers.
- `tests/strategies_nautilus/test_paper_runner.py`, `test_report_paper_bundle.py` continue to cover paper drawdown, dry-run / simulated paths, lineage `signal_id` carry-through, lag / expiry / unauthorized / kill-switch rejection, incremental cursor metadata, restart cursor handling, market-data gap blockers, and source-level guards against reading secret env vars or submitting live orders.
- `docs/progress/phase-2-signal-source-baselines.md` v6 records the freqai paper-shadow fingerprint and links to the first retro; v1..v5 (demo, rule, freqai dry-run backtest, paper bundle reports, paper drawdown) remain archived.

## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

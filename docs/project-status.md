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
- Catalog is now 31 days of BTCUSDT 1m (2024-01-01..2024-01-31, 44640 bars, 0 ts gaps). With `train_until=2024-01-05T23:59`, `freqai_linear_v1 / linear-mom-train20240105` now produces 308 deterministic out-of-sample shadow `SignalEvent v1` rows. `features_hash` and training metadata are unchanged from v3/v6, so the model fingerprint remains stable while the paper-shadow evidence base grows from 7 to 308.
- Catalog now extends to 60 days (2024-01-01..2024-02-29, 86400 bars, 0 ts gaps). February is the first fully held-out month for `freqai_linear_v1 / linear-mom-train20240105` and adds 287 `SignalEvent v1` rows on top of January's 308 (total 595). `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) are unchanged across v3/v6/v7/v8; only the OOS region grows. Hold-out distributional comparison Jan vs Feb shows near-identical signal density (9.94 vs 9.90 per day), long-share (0.7305 vs 0.7352), and score / confidence quantiles — the model survives the one-month regime shift on signal generation.

## Current Focus

Phase 2 entry: stabilize the real NautilusTrader backtest path and make it usable against project data.

Immediate focus:

1. Use the local `BTCUSDT.BINANCE` 1m fixture path as the required smoke test before changing runner behavior.
2. Treat the rule-based baseline (`rule_baseline_v1/ema5-20+rsi14`) as the reproducibility anchor; FreqAI/model-driven signals are a separate stream that must round-trip the same bridge.
3. Preserve reproducibility as catalog data grows: same git commit, signal-store SHA, catalog content, strategy params, risk params, and Nautilus version must produce identical stats and `fills.parquet`.
4. Keep LLM agents out of the live order path; Phase 2 remains research/backtest only.

## Next Steps

1. Use `promotion_review.py` (not just `report_paper_bundle.py`) as the required ADR-007 §2.6 audit artifact for any `SourcePolicy` change. Records land in `docs/retros/<UTC>-<source>-<decision>-<target_stage>.md`.
2. Run a deliberate `promote` retro for `freqai_linear_v1 / linear-mom-train20240105` from `paper_shadow` to `paper_simulated` (`SourcePolicy(dry_run=False, position_pct_multiplier=0.2)`). Signal-side hold-out is already cleared by the v8 retro (Jan-vs-Feb distributions are stable). Return-side evidence (Win Rate / expectancy / max drawdown) is exactly what `paper_simulated` is for. Use the v8 catalog (60 days) so the simulated bundle covers the same in-sample + held-out window.
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

On 2026-05-17, after extending the catalog to 60 days and producing the first hold-out month evidence:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 295 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs` -> clean.
- BTCUSDT 1m catalog now spans 2024-01-01..2024-02-29 (86400 bars, 0 ts gaps); `data/bridge/signals.db` sha256 `6c30373984f7e565c855adb3f946722c43c9253038956895b34233a386d02dfe`; `freqai_linear_v1` row count went from 308 to 595 with old 308 deduped via `DuplicateSignalError` and `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) unchanged across v3/v6/v7/v8.
- `apps/strategies_nautilus/runners/promotion_review.py` integrates with `report_paper_bundle.load_paper_bundle_report` and never mutates `SourcePolicy`, starts a runtime, or talks to an exchange.
- First retro: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md` (7-day, 7 signals — days half met, signals half not). Bundle `data/paper/20260517-050320Z-f5e13cda` manifest `88164be1024d96f706f27d53e22933a7cbab6eedd576bb0a7274307ccc95eebe`.
- Second retro: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md` (31-day, 308 signals — both halves met but in-sample). Bundle `data/paper/20260517-051417Z-9afb2cd1` manifest `218e3b0c75db85b5c6a90f692ee270d9d1de5b1aed58bab0e2fbc8015b541035`.
- Third retro: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md` (60-day, 595 signals — first held-out month). Bundle `data/paper/20260517-052512Z-36feef84` manifest `9d813db2a77adf39cb974f5e6b7b3e04b2f701f930757edf132d97fd3ddb13c0`. v8 fingerprint: 86400 iterations, 595 dry-run signals (308 Jan + 287 Feb), lineage `target_long×436 + target_short×159`, `heartbeat_count=86400`, `poll_count=86400`, `processed_until_ns=1709251140000000000`, `restart_sequence=0`, `data_gap_count=0`, `git_dirty=false`, no review blockers, no promotion gate blockers. Decision is still `hold`. Hold-out distributional comparison Jan vs Feb (recorded in v8 progress entry): signal density 9.94 vs 9.90 per day; long-share 0.7305 vs 0.7352; score p50 buy +0.2342 / +0.2342, sell -0.2438 / -0.2332; confidence mean buy 0.5647 / 0.5627, sell 0.5737 / 0.5597 — signal-side distributions are near-identical across train and held-out month.
- The next deliberate human action is a separate `promote` retro that flips `dry_run=False` so the `paper_simulated` stage can produce the return-side evidence (Win Rate, expectancy, max drawdown) that dry-run paper-shadow cannot.
- `tests/strategies_nautilus/test_promotion_review.py` (18 cases) and the rest of the paper / report / runner suites continue to enforce dry-run vs simulated invariants, lineage `signal_id` carry-through, lag / expiry / unauthorized / kill-switch rejection, incremental cursor metadata, restart cursor handling, market-data gap blockers, and source-level guards against reading secret env vars or submitting live orders.
- `docs/progress/phase-2-signal-source-baselines.md` v8 records the 60-day fingerprint, the same-`features_hash` reproducibility table across v3/v6/v7/v8, the Jan-vs-Feb hold-out distributional comparison, and links to all three retros; v1..v7 remain archived.

## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

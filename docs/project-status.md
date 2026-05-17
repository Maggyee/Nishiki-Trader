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
- First `promote` retro in the project landed: `freqai_linear_v1 / linear-mom-train20240105` was deliberately moved from `paper_shadow` to `paper_simulated` via `promotion_review --decision promote`, authorizing `SourcePolicy(dry_run=False, position_pct_multiplier=0.2)`. The first paper_simulated bundle (v9, `data/paper/20260517-053502Z-37b99b3f`, manifest `fa344a55…`) produced 545 orders, 545 fills with every `signal_id` propagated, 273 positions, no kill-switch fires, no data gaps. Return-side metrics are now on record for the first time: PnL +5.0076 USDT (+0.005%), Win Rate 55.5%, expectancy +0.019 USDT/trade, max drawdown -0.001% / -$1.00 over 60 days. Source is now `hold @ paper_simulated`; further promotion to `testnet_canary` is hard-blocked by `phase_3_not_ready` and requires the Phase 3 risk/runbook ADR.
- ADR-008 (`docs/decisions/008-phase3-risk-runbook.md`) is drafted as the Phase 3 risk/runbook spec — it defines the `kind="testnet"` runtime, the wall-clock-paper precondition, real-exchange-credentials handling, emergency-flatten / kill-switch / restart / alerting workflows, the 6-phase implementation roadmap, and the 7-section validation checklist. It is **specification only**: no runtime is implemented yet, no credentials are added, and `promotion_review`'s `phase_3_not_ready` gate stays in place until each §6 sub-phase is built and tested. ADR-007 §4 has been renumbered to match: ADR-008 = this draft, ADR-009 = LLM dual-sign (was ADR-008), ADR-010 = Redis Stream (was ADR-009).
- ADR-008 **§6.1 Phase 3a (wall-clock paper) is implemented and smoke-passed**. `apps/strategies_nautilus/runners/paper_runner.py` now accepts `--data-mode wall_clock`; the new `apps/strategies_nautilus/runners/wall_clock_bar_feed.py` streams closed 1m klines from a Binance public WS endpoint via NautilusTrader's credential-free `BinanceWebSocketClient` (no `BINANCE_*` env vars are read; the test `test_wall_clock_sources_have_no_credential_or_live_tokens` grep-asserts this). The catalog-polling and wall-clock simulators share one `_step_one_bar` core so bundle fingerprints are comparable. Wall-clock bundles carry new `runtime` fields: `bar_source`, `ws_endpoint`, `ws_stream`, `ws_reconnect_count`, `duplicate_bars_dropped`, `max_duration_seconds`, `max_bars`, `signal_poll_interval_seconds`, `shutdown_reason`, and `credentials_loaded=false`. First real-WS smoke (5 min, `wss://data-stream.binance.vision:9443`, bundle `data/paper/20260517-075403Z-b76dcdb1`, manifest `f80bd450…`): 5 bars, 5 heartbeats, 0 data gaps, 0 reconnects, 0 duplicate drops. The `phase_3_not_ready` promotion gate stays closed — Phase 3b–3f are still pending.

## Current Focus

Phase 2 entry: stabilize the real NautilusTrader backtest path and make it usable against project data.

Immediate focus:

1. Use the local `BTCUSDT.BINANCE` 1m fixture path as the required smoke test before changing runner behavior.
2. Treat the rule-based baseline (`rule_baseline_v1/ema5-20+rsi14`) as the reproducibility anchor; FreqAI/model-driven signals are a separate stream that must round-trip the same bridge.
3. Preserve reproducibility as catalog data grows: same git commit, signal-store SHA, catalog content, strategy params, risk params, and Nautilus version must produce identical stats and `fills.parquet`.
4. Keep LLM agents out of the live order path; Phase 2 remains research/backtest only.

## Next Steps

1. Use `promotion_review.py` (not just `report_paper_bundle.py`) as the required ADR-007 §2.6 audit artifact for any `SourcePolicy` change. Records land in `docs/retros/<UTC>-<source>-<decision>-<target_stage>.md`.
2. Phase 3a (wall-clock paper) is in. Next is ADR-008 §6.1's deferred §7.2 item 4 — a real 24-hour wall-clock soak (heartbeat cadence, `data_gap_count`, `ws_reconnect_count`, `duplicate_bars_dropped`) — landed as its own retro before Phase 3b begins. Then move to ADR-008 §6.2 Phase 3b (`testnet_runner.py` with §4 credential-loading + `--allow-real-credentials` double-sign and §4.2 startup checks). The `phase_3_not_ready` gate stays closed through Phase 3e.
3. Continue collecting paper_simulated evidence on `freqai_linear_v1 / linear-mom-train20240105` as catalog windows extend (multi-month, multiple regime shifts). The v9 bundle's expectancy (+0.019 USDT/trade, 55.5% win rate, -0.001% max drawdown over 60 days) is barely above coin-flip; treat it as monitoring evidence, not alpha, until at least one substantially different market regime is in the test window.
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

On 2026-05-17, after Phase 3a wall-clock paper landed and passed its first real-WS smoke:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 290 passed (277 prior + 13 new wall-clock tests).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs` -> clean.
- BTCUSDT 1m catalog spans 2024-01-01..2024-02-29 (86400 bars, 0 ts gaps); `data/bridge/signals.db` sha256 `6c30373984f7e565c855adb3f946722c43c9253038956895b34233a386d02dfe`; `freqai_linear_v1` row count 595 (308 Jan + 287 Feb); `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) unchanged across v3/v6/v7/v8/v9.
- `apps/strategies_nautilus/runners/promotion_review.py` integrates with `report_paper_bundle.load_paper_bundle_report` and never mutates `SourcePolicy`, starts a runtime, or talks to an exchange.
- Five `docs/retros/` entries record the lifecycle of `freqai_linear_v1 / linear-mom-train20240105`:
  - 7-day shadow `hold` (sample size half met only): `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md`, bundle `data/paper/20260517-050320Z-f5e13cda` manifest `88164be1…`.
  - 31-day shadow `hold` (both halves met but in-sample): `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md`, bundle `data/paper/20260517-051417Z-9afb2cd1` manifest `218e3b0c…`.
  - 60-day shadow `hold` with first held-out month: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md`, bundle `data/paper/20260517-052512Z-36feef84` manifest `9d813db2…`.
  - First **`promote`** retro (paper_shadow → paper_simulated): `docs/retros/2026-05-17-freqai-linear-v1-promote-paper-simulated.md`. Evidence: same 60-day shadow bundle. `decision_allowed=True`, `policy_diff={"dry_run": {"current": true, "target": false}}`, no review or promotion blockers.
  - First `paper_simulated` `hold`: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md`, bundle `data/paper/20260517-053502Z-37b99b3f` manifest `fa344a55…`.
- v9 simulated bundle sanity: 86400 iterations, 595 signals, **545 orders / 545 fills (1:1, every row carrying `signal_id`)**, 273 positions, 86400 account balances, lineage `target_long×436 + target_short×159` with reasons split as 273 first-fill openings + 299 already_target_long + 23 already_target_short. Runtime: heartbeat=86400, poll=86400, processed_until_ns=1709251140000000000, restart_sequence=0, data_gap_count=0; risk: kill_switch=0, signal_lag=0, unauthorized=0, expired=0; manifest `git_dirty=false`. Applied policy: `dry_run=False`, multiplier 0.2.
- v9 return-side metrics: PnL +5.0076 USDT (+0.005% on 100000 USDT over 60 days), Win Rate 0.5551 (55.5%), expectancy +0.01858 USDT/trade, max drawdown -1.0035e-05 (-0.001003%) / -$1.0035. Treated as monitoring evidence, not alpha.
- `tests/strategies_nautilus/test_promotion_review.py` (18 cases) and the rest of the paper / report / runner suites continue to enforce dry-run vs simulated invariants, lineage `signal_id` carry-through, lag / expiry / unauthorized / kill-switch rejection, incremental cursor metadata, restart cursor handling, market-data gap blockers, and source-level guards against reading secret env vars or submitting live orders.
- `tests/strategies_nautilus/test_wall_clock_paper_runner.py` (13 cases) enforces the ADR-008 §7.2 invariants for Phase 3a: no `BINANCE_*` env reads in either `paper_runner.py` or `wall_clock_bar_feed.py`; closed-kline-only consumption with `ts_event_ns` dedup; non-kline payload rejection; manifest carry-through of `ws_reconnect_count` / `duplicate_bars_dropped` / `shutdown_reason`; SignalStore re-poll incremental cursor; SIGTERM and `max_duration` stop paths.
- Phase 3a real-WS smoke (5 min, `wss://data-stream.binance.vision:9443`, BTCUSDT 1m): bundle `data/paper/20260517-075403Z-b76dcdb1`, manifest sha256 `f80bd450fa6e47287316aba90498244fe467f341a3af54bb5b570e4babf3f56d`. `bar_count=5`, `heartbeat_count=5`, `data_gap_count=0`, `ws_reconnect_count=0`, `duplicate_bars_dropped=0`, `shutdown_reason=max_duration`, `credentials_loaded=false`. Manifest carries `git_dirty=true` because it ran before this commit; future wall-clock bundles will land with `git_dirty=false`. Retro: `docs/retros/2026-05-17-phase-3a-wall-clock-smoke.md`.
- `docs/progress/phase-2-signal-source-baselines.md` v9 records the promote event, the v9 simulated fingerprint diff vs v8, the strategy's already-on-side handling, and the Phase 2 ceiling at paper_simulated; v1..v8 remain archived.
- ADR-008 (`docs/decisions/008-phase3-risk-runbook.md`) is drafted and accepted as a Phase 3 specification only — it defines the testnet runtime, wall-clock paper precondition, real-credentials handling (no creds in repo, double-signed `--allow-real-credentials` flag, key-prefix-only audit), emergency flatten (7-step cancel-then-flatten with `emergency_flatten.json` audit), kill-switch (5% daily loss → auto-flatten), restart recovery (mandatory 3-way reconciliation with the exchange), the minimal alert set (`logs/alerts.log` + exit codes 0..5), and the testnet → live additional gates. ADR-007 §4 has been renumbered: ADR-008 (this), ADR-009 (LLM, was ADR-008), ADR-010 (Redis, was ADR-009). `promotion_review`'s `phase_3_not_ready` gate is unchanged and stays closed until ADR-008 §6.1–§6.5 sub-phases are built and tested.
- `docs/agent-reading-list.md` Phase 3 / testnet row now points at ADR-008 directly.

## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

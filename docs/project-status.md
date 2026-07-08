# Project Status

- **Status file**: Active
- **Last updated**: 2026-07-08 (dashboard passive bundle degradation handling)
- **Current phase**: Phase 5 entry (read-only frontend + monitoring; live trading still blocked)
- **Current objective**: Phase 5 remains the active implemented phase. ADR-013, `apps.ops.live_readiness`, and `apps.strategies_nautilus.runners.live_startup_guard` define passive Phase 6 live-readiness and startup-refusal gates, including spot-only/no-margin/no-leverage market-scope checks, exact live promotion-review field parsing, project-status / live-risk ADR / testnet continuity bundle manifest / promotion-review artifact SHA-256 capture in readiness reports, clean git evidence capture, and startup-guard cross-checks that saved readiness artifacts kept passive boundary flags closed, were generated from the same clean commit, referenced the same project-status / live-risk ADR / promotion-review artifact bytes, carried continuity bundle manifest fingerprints whose manifest paths still hash to the recorded bytes, and are fresh by `generated_at_ns` (default max age 24h). Startup guard reports record SHA-256 fingerprints for the saved readiness report, live-risk ADR, first-live-day runbook artifacts, readiness-vs-startup project-status SHA inputs, readiness-vs-startup live-risk ADR SHA inputs, readiness freshness-window evidence, readiness-vs-startup git commit/clean evidence, startup-side continuity manifest byte verification, and startup-side operator-document accepted states they consumed. `dashboard.snapshot.v1` can summarize saved `phase6.live_readiness.v1` / `phase6.live_startup_guard.v1` artifacts for read-only operator visibility, including required source/model identity, project-status, live-risk ADR, continuity bundle manifests, readiness continuity-summary / clean-git / capital-range / market-scope blocker checks, startup clean-git / capital-range / market-scope / SourcePolicy / continuity byte verification / runtime / credential-boundary blocker checks, accepted-and-fingerprinted readiness artifact evidence, readiness-vs-startup project-status SHA match, readiness-vs-startup ADR SHA match, readiness freshness window, readiness-vs-startup git commit match, attached readiness-report SHA matching against the startup-consumed readiness artifact, cross-report source/model matching, promotion-review artifact, promotion SHA-256 match, startup-side live-risk ADR / first-live-day runbook accepted-and-fingerprinted evidence, non-ok internal check statuses, open passive boundary flags, and missing/invalid/future report generation timestamps already present in those saved reports. Phase 6 is still closed: ADR-013 is Draft, strict testnet continuity remains `current_qualified_streak_days=0/14`, no live-canary promotion review exists, the first-live-day runbook is Draft, and no live runner is authorized or wired. ADR-012, `apps.ops.dashboard_snapshot`, `infra/grafana/dashboards/signals-overview.json`, and `apps/frontend` continue to define the read-only operations console consuming `dashboard.snapshot.v1` with runtime health, AgentAdvice, passive paper/testnet summaries, source/model Grafana drill-down links, snapshot freshness status with generator-configurable thresholds, snapshot source/input audit, signal/rejection/freshness/evidence summaries, observability, reference links, and Phase 6 blocker summaries. Agents and frontend still cannot write `SignalEvent`, mutate `SourcePolicy`, call exchange APIs, or enter the order path. Keep `freqai_linear_v1 / linear-mom-train20240105` at `hold @ testnet_canary` under `SourcePolicy(dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None)`. No live trading without ADR-013 acceptance, the ADR-001 capital ladder gate, and the ADR-008 14-day continuity gate.
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
- `docs/progress/phase-3-testnet-canary-evidence.md` — Phase 3 testnet canary evidence ledger and paused operating step.
- `docs/progress/phase-3-testnet-continuity-plan.md` — paused 14-day testnet continuity tracking plan and review command.

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
- Testnet bundle report reader is live: `apps/strategies_nautilus/runners/report_testnet_bundle.py` passively summarizes completed `kind="testnet"` bundles into retro evidence, including manifest identity, heartbeat gaps, alert message counts, live sidecar count agreement, fill lineage, final FLAT state, and review blockers without loading credentials or touching exchange paths. It also accepts multiple bundle directories and emits aggregate JSON or Markdown for the Phase 3 evidence ledger.
- Incremental paper-session mechanics are live: catalog polling now records event-time poll cursors, heartbeat/runtime logs, restart metadata from `previous_run_id`, and market-data gap blockers while keeping orders simulated and exchange credentials out of the path.
- ADR-007 §2.6 promotion-review tooling is live: `apps/strategies_nautilus/runners/promotion_review.py` packages a paper bundle, a declared `current_policy`/`target_policy`, and an operator decision (`promote|hold|demote|disable`) into the seven §2.6 sections plus a `decision_allowed` gate that enforces the §2.5 stage table, the `paper_shadow → paper_simulated` evidence threshold, bundle/policy match, `git_dirty`, review blockers, and the Phase-2 stage cap. Records land in `docs/retros/`.
- Catalog is now 31 days of BTCUSDT 1m (2024-01-01..2024-01-31, 44640 bars, 0 ts gaps). With `train_until=2024-01-05T23:59`, `freqai_linear_v1 / linear-mom-train20240105` now produces 308 deterministic out-of-sample shadow `SignalEvent v1` rows. `features_hash` and training metadata are unchanged from v3/v6, so the model fingerprint remains stable while the paper-shadow evidence base grows from 7 to 308.
- Catalog now extends to 60 days (2024-01-01..2024-02-29, 86400 bars, 0 ts gaps). February is the first fully held-out month for `freqai_linear_v1 / linear-mom-train20240105` and adds 287 `SignalEvent v1` rows on top of January's 308 (total 595). `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) are unchanged across v3/v6/v7/v8; only the OOS region grows. Hold-out distributional comparison Jan vs Feb shows near-identical signal density (9.94 vs 9.90 per day), long-share (0.7305 vs 0.7352), and score / confidence quantiles — the model survives the one-month regime shift on signal generation.
- First `promote` retro in the project landed: `freqai_linear_v1 / linear-mom-train20240105` was deliberately moved from `paper_shadow` to `paper_simulated` via `promotion_review --decision promote`, authorizing `SourcePolicy(dry_run=False, position_pct_multiplier=0.2)`. The first paper_simulated bundle (v9, `data/paper/20260517-053502Z-37b99b3f`, manifest `fa344a55…`) produced 545 orders, 545 fills with every `signal_id` propagated, 273 positions, no kill-switch fires, no data gaps. Return-side metrics are now on record for the first time: PnL +5.0076 USDT (+0.005%), Win Rate 55.5%, expectancy +0.019 USDT/trade, max drawdown -0.001% / -$1.00 over 60 days. Source is now `hold @ paper_simulated`; further promotion to `testnet_canary` is hard-blocked by `phase_3_not_ready` and requires the Phase 3 risk/runbook ADR.
- Paper_simulated monitoring evidence now extends through 2024-05-31: v11 bundle `data/paper/20260521-021418Z-e535b581` (manifest `06d9300a…`) replays 152 days / 218880 BTCUSDT 1m bars with 2107 `freqai_linear_v1` historical signals, 1987 orders/fills, 994 positions, no data gaps, no kill-switch, and `git_dirty=false`. Return-side evidence remains tiny: PnL +4.8726 USDT (+0.004873%), Win Rate 53.6%, expectancy +0.00491 USDT/trade, max drawdown -0.003878% / -$3.88. April is negative and May is only mildly positive; this remains monitoring evidence, not alpha.
- ADR-008 (`docs/decisions/008-phase3-risk-runbook.md`) is accepted as the Phase 3 risk/runbook spec — it defines the `kind="testnet"` runtime, the wall-clock-paper precondition, real-exchange-credentials handling, emergency-flatten / kill-switch / restart / alerting workflows, the 6-phase implementation roadmap, and the 7-section validation checklist. Phase 3a and the Phase 3b startup guard are now being implemented under that spec, but `promotion_review`'s `phase_3_not_ready` gate stays in place until each §6 sub-phase is built and tested. ADR-007 §4 has been renumbered to match: ADR-008 = this draft, ADR-009 = LLM dual-sign (was ADR-008), ADR-010 = Redis Stream (was ADR-009).
- ADR-008 **§6.1 Phase 3a (wall-clock paper) is implemented and accepted**. `apps/strategies_nautilus/runners/paper_runner.py` now accepts `--data-mode wall_clock`; the new `apps/strategies_nautilus/runners/wall_clock_bar_feed.py` streams closed 1m klines from a Binance public WS endpoint via NautilusTrader's credential-free `BinanceWebSocketClient` (no `BINANCE_*` env vars are read; the test `test_wall_clock_sources_have_no_credential_or_live_tokens` grep-asserts this). The catalog-polling and wall-clock simulators share one `_step_one_bar` core so bundle fingerprints are comparable. Wall-clock bundles carry new `runtime` fields: `bar_source`, `ws_endpoint`, `ws_stream`, `ws_reconnect_count`, `duplicate_bars_dropped`, `max_duration_seconds`, `max_bars`, `signal_poll_interval_seconds`, `shutdown_reason`, and `credentials_loaded=false`. First real-WS smoke (5 min, `wss://data-stream.binance.vision:9443`, bundle `data/paper/20260517-075403Z-b76dcdb1`, manifest `f80bd450…`) passed. The 24h soak (`data/paper/20260517-094345Z-ad69bd68`, manifest `98984bd1…`) also passed with `git_dirty=false`, 1440 bars, 24 heartbeats, 0 data gaps, 0 reconnects, 0 duplicate drops, `shutdown_reason=max_duration`, and `credentials_loaded=false`. The `phase_3_not_ready` promotion gate stays closed — Phase 3b–3f are still pending.
- ADR-008 **§6.2 Phase 3b startup guard, adapter configuration, and controlled connection probe are implemented, unit-tested, and live-verified end-to-end on Binance Spot testnet**: `apps/strategies_nautilus/runners/testnet_runner.py` validates `--mode testnet` + `--kind testnet`, `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET` presence and length, explicit `--allow-real-credentials`, clean git status, source/model stage evidence in `docs/retros/`, and testnet multiplier cap (`<=0.2`). After those gates pass, it builds a Nautilus `TradingNodeConfig` with Binance Spot `environment=TESTNET` data/exec client configs and real Binance factories. The audit/validation path keeps `api_key=None` / `api_secret=None` so JSON output never contains credentials. The `--connect-probe` path additionally injects the testnet key/secret into the in-memory `TradingNodeConfig` only, builds a `TradingNode` via an injectable `node_factory`, registers `BinanceLiveDataClientFactory` + `BinanceLiveExecClientFactory`, calls `node.build()` and `node.run()` with **no strategies and no actors registered** (so the node cannot submit orders even while connected), stops the node after `--max-connect-seconds` via a background timer that uses `loop.call_soon_threadsafe(node.stop)`, then disposes it. The probe writes `data/testnet/<run_id>/logs/runtime.log` (JSON Lines: `credentials_loaded` → `node_built` → `node_run_invoked` → `shutdown`) with `credentials_key_prefix` (8 chars) but never the full key/secret, plus `data/testnet/<run_id>/connection_probe.json` summary (`kind=testnet`, `runtime.mode=testnet`, `runtime.order_mode=exchange_testnet`, `stop_reason`, `node_built`, `node_run_invoked`, `strategies_registered=0`, `actors_registered=0`, no credentials).
- First live Phase 3b probe ran on 2026-05-18 against `https://testnet.binance.vision` + `wss://ws-api.testnet.binance.vision/ws-api/v3` with a locally-generated Ed25519 keypair (HMAC keys are rejected by Binance Spot WS `session.logon`; Nautilus's `BinanceExecClient._connect` unconditionally calls it). Bundle `data/testnet/20260518-122839Z-24bf3db2`. ExecClient `session.logon` succeeded under Ed25519, account `BINANCE-SPOT-master` registered in cache, ExecutionMassStatus reconciliation succeeded, startup reconciliation completed. No `ERROR` lines in the Nautilus log. Probe stopped at the 30s budget via the background timer, all engines disposed cleanly. Retro: `docs/retros/2026-05-18-phase-3b-testnet-connect-probe.md`.
- ADR-008 **§6.3 Phase 3c-a/b/c emergency-flatten orchestration, real Binance Spot testnet driver, and `testnet_runner.py` auto-trigger wiring are implemented and unit-tested**. `apps/strategies_nautilus/runners/emergency_flatten.py` still owns the exchange-agnostic seven-step path and audit files; `apps/strategies_nautilus/runners/binance_testnet_exchange.py` implements the default `--kind testnet` `ExchangeClient` with signed REST calls to `https://testnet.binance.vision`, Ed25519-only credential validation, open-order cancel, Spot account-balance inventory inference, market SELL close for long Spot inventory (no unsupported Spot `reduceOnly` parameter), order polling, and account snapshots. `apps/strategies_nautilus/runners/testnet_runner.py --long-run` now writes `data/testnet/<run_id>/run_manifest.json` + runtime/heartbeat/alert logs and auto-invokes the same emergency-flatten path when daily PnL reaches the 5% loss limit, exchange errors exceed 50/hour, or WS reconnects exceed 10/hour. Paper/live still require an injected factory.
- ADR-008 **§6.4 Phase 3d restart reconciliation + watchdog are implemented and unit-tested**. `testnet_runner.py --long-run --previous-run-id <id> --restart-reason <reason>` reads the previous `run_manifest.json`, computes `previous_manifest_sha256`, carries `previous_processed_until_ns` and `restart_sequence`, compares local open orders / positions from previous sidecars against exchange REST state, and refuses startup with exit code 3 plus `restart_drift_detected` alert on drift before building a node. `infra/watchdog/watchdog.py` is the minimal external watchdog: it reads only `data/testnet/<run_id>/logs/heartbeat.jsonl`, writes `infra/watchdog/state.json`, appends `heartbeat_lost` on stale/missing heartbeat, and invokes the existing emergency-flatten CLI without reading credentials itself.
- First **ADR-008 §6.6 testnet canary session is on record (30-min smoke)**: `docs/retros/2026-05-19-phase-3f-testnet-canary-session.md`. Bundle `data/testnet/20260519-023115Z-e6aeb688/` on `git_commit=13b12ca`, `elapsed_seconds=1805.21` against `max_run_seconds=1800`, `shutdown_reason=max_duration`. The runner registered one `BaselineNautilusStrategy` backed by `SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)` against Binance Spot testnet under `SourcePolicy(dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None)`. Lifecycle 5-tuple: `credentials_loaded` → `node_built` → `strategies_registered(strategies=1, actors=0)` → `node_run_invoked` → `shutdown`. Account `BINANCE-SPOT-master` registered at T+0.295s; `Reconciliation for BINANCE succeeded` at T+0.579s; `BaselineNautilusStrategy: RUNNING` + bar subscription succeeded at T+0.581s. 60 heartbeats at 30 s cadence with `ws_connected=true` throughout; `logs/alerts.log` does not exist (9/9 §5.4 paths silent). Nautilus stdout `grep ERROR=0`, stderr 22 bytes (`nohup` line only); only 2 WARN, both ADR-008 §5.4 catalog-external informationals identical to Phase 3f (`BinanceSpotInstrumentProvider: zero fees` at startup, `BinanceUserDataWebSocketClient: eventStreamTerminated` 0.114 s pre-shutdown). All engines (including `BaselineNautilusStrategy`) `DISPOSED` cleanly at `03:01:20.296Z-.297Z`. 0 orders / 0 fills / 0 positions — expected because the `freqai_linear_v1` SignalStore producer is offline (`rows_last_24h=0`, `latest_ts_event_ns=1714513500000000000`). The execution path is now proven; the bundle carries no sidecars (`orders.parquet` etc. are only written when there is data). Watchdog was deliberately not started for this 30 min smoke; a full 6 h canary must re-attach it per `docs/runbook-first-testnet-canary.md` §4.
- ADR-008 **§6.6 first-canary execution path is wired**. Three changes land together:
  - `apps/strategies_nautilus/baseline_nautilus_strategy.py` gains `SignalSource` protocol, `StaticSignalSource` (preserves backtest behaviour), and `SignalStorePollingSource` (testnet/live streaming poller against `apps/bridge/store.py`); `BaselineNautilusStrategyParams.signal_source` overrides the legacy `signals` list when set; `on_bar` now delegates signal popping to the source.
  - `apps/strategies_nautilus/runners/testnet_runner.py` gains `LongRunningTestnetSettings.enable_strategy_execution` (default `False`) plus a `register_strategies` callback injected through `run_long_running_testnet()` / `main()`. With the flag set the runner calls `register_strategies(node)` after `build()` and requires `strategies_registered >= 1`; without it the existing "refuses to run with registered strategies" gate stays in place. CLI exposes `--enable-strategy-execution`. The final manifest records `enable_strategy_execution`, `strategies_registered`, `actors_registered`.
  - `apps/strategies_nautilus/runners/first_testnet_canary.py` is the unit-tested glue: `FirstCanaryStrategySpec` validates `position_pct_multiplier` ∈ (0, 0.2], `trade_size > 0`, and source/model fields; `build_register_strategies(spec, lineage=…)` builds a `register_strategies(node)` callback that constructs `Authorization`+`SourcePolicy`+`BaselineStrategyConfig`+`SignalStorePollingSource`+`BaselineNautilusStrategy` and calls `node.trader.add_strategy(strategy)`. Operator launcher (kept out-of-repo at `infra/launchers/first-testnet-canary.py`) imports this and passes a fully-formed argv to `testnet_runner.main()`.
- The first **operating procedure for the first canary** is at `docs/runbook-first-testnet-canary.md` (preflight checklist; session parameter table; embedded operator-launcher template; watchdog + runner startup commands; monitoring jq snippets; emergency-stop sequence; clean-shutdown evidence collection). The matching post-run retro template lives at `docs/templates/testnet-canary-session-retro.md` — § 1 scope, § 2 run identity, § 3 runtime counters, § 4 heartbeat cadence, § 5 §5.4 alert outcome, § 6 runtime.log lifecycle, § 7 Nautilus log evidence, § 8 watchdog evidence, § 9 real order flow, § 10 signal flow, § 11 recommended next decision.
- The **testnet canary SignalStore restamp helper is live**: `apps/strategies_freqtrade/research/wall_clock_signal_replay.py` copies already-reviewed historical `freqai_linear_v1 / linear-mom-train20240105` rows, re-stamps `ts_event` into future wall-clock cadence, preserves source/model authorization, and records the original row under `metadata.wall_clock_replay`. It writes only `SignalEvent v1` rows to SQLite; no exchange, network, Nautilus, or order API is imported.
- First **ADR-008 §6.6 6 h canary with real order flow is on record**: `docs/retros/2026-05-19-phase-3f-testnet-canary-6h-order-flow.md`. Bundle `data/testnet/20260519-033558Z-e653c3e5/` consumed a restamped `freqai_linear_v1 / linear-mom-train20240105` row, filled `BUY MARKET 0.001 BTCUSDT` (`venue_order_id=4981384`, `trade_id=1676533`), and filled the scheduled shutdown `SELL MARKET 0.001 BTCUSDT` close (`venue_order_id=5070773`, `trade_id=1700032`, `realized_pnl=-0.02 USDT`). Runner shutdown was clean (`max_duration`, 720 heartbeats, 0 Nautilus ERROR, all engines disposed), but the watchdog loop kept running after completion and produced post-run `heartbeat_lost` false positives plus repeated emergency flatten calls. `infra/watchdog/watchdog.py` now treats completed manifests as terminal so the same bundle returns `status=run_completed`, `flatten_invoked=false`.
- **Live testnet sidecar writer is wired** for ADR-008 §6.6. `apps/strategies_nautilus/runners/sidecar_writer.py` introduces `SidecarRecording(venue_name, lineage)` and `write_live_sidecars(trader, venue_name, lineage, bundle_root, report_ts_event_ns)`, reusing `backtest_runner._prepare_reports` so backtest / paper / testnet bundles share one ADR-004 schema source. `testnet_runner.py --long-run` gains `--write-live-sidecars` (off by default; requires `--enable-strategy-execution`); the runner invokes the writer between `node.run()` returning and `node.dispose()`. Mismatched flag/recording is rejected at startup; writer exceptions are caught into `runtime["sidecar"]["error"]` and never change the exit code. `LongRunningTestnetResult` carries `sidecar_write_result` + `sidecar_error`; the manifest records `runtime.write_live_sidecars` and `runtime.sidecar.{success,error,result.{paths,*_count,lineage_rows}}`. `first_testnet_canary.build_sidecar_recording(spec, lineage=)` lets the launcher share one `lineage` list between the strategy and the post-run writer.
- Second **ADR-008 §6.6 6 h canary** is on record with the first parquet-backed evidence: `docs/retros/2026-05-19-phase-3f-testnet-canary-6h-sidecar-bundle.md`. Bundle `data/testnet/20260519-120037Z-f1b06fd3/` on commit `c2a4186`, 720 heartbeats, 0 alerts, all 8 engines DISPOSED cleanly. Sidecar write fired at 18:00:42.550Z (10 ms before shutdown), `success=true`, writes orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=3 parquet rows; manifest's `runtime.sidecar.result` agrees row-for-row. Real entry `BUY MARKET 0.001 BTCUSDT @76777.55` (venue_order_id 5112724, trade_id 1713055) with `signal_id` round-tripped through order/fill tags; scheduled close `SELL MARKET 0.001 BTCUSDT @76852.51` (venue_order_id 5224656, trade_id 1750207, `reduce_only=True`); position closed `realized_pnl=+0.07496 USDT`, 0 commissions. External watchdog ticked 1560 times for this run with 0 `flatten_invoked`, 716 healthy + 844 post-shutdown `run_completed`, confirming the `8e5fada` fix.
- **Live telemetry reader** is wired for ADR-008 §6.6. `apps/strategies_nautilus/runners/live_telemetry.py` introduces `LiveTelemetryReader(venue, bar_type, base_currency, starting_balance, signal_source=)` which reads `node.portfolio.equity(venue)` for `account_total_usdt`, `node.cache.orders_open(venue)` / `node.cache.positions_open(venue)` for the counters, `node.cache.bar(bar_type)` for `last_bar_ns`, and the launcher's `SignalStorePollingSource.last_popped_ns` for `last_signal_ns`. Daily PnL uses a UTC day anchor (`anchor=current_total` on day-rollover, `daily_pnl=current_total-anchor`). `testnet_runner.run_long_running_testnet` calls `reader.bind_node(node)` post-build when the injected reader exposes it; the hook is duck-typed so the default constant reader is unchanged. `first_testnet_canary.build_signal_source(spec)` + `build_live_telemetry_reader(spec, starting_balance=, signal_source=)` give the launcher one source object to share between the strategy and the reader. The launcher now wires this reader by default, so the 5.2 kill-switch (`daily_pnl < -5% × starting_balance`) and three 5.4 advisory alerts (`signal_lag_exceeded_threshold`, `data_gap_exceeded_tolerance`) observe live state instead of the prior all-zero canned values.
- **`ws_connected` and `ws_reconnect_count` are now read from the kernel engines.** `LiveTelemetryReader._read_ws_connected(node)` returns `node.kernel.data_engine.check_connected() and node.kernel.exec_engine.check_connected()` — both public `cpdef bint` methods on Nautilus's engines that walk each registered client's `is_connected` flag. The reader keeps `_ws_connected_prev` and increments `_ws_reconnect_count` on a `False → True` transition, so the §5.4 `ws_disconnected` advisory alert and the §5.2 `ws_reconnect_burst` auto-flatten trigger observe live state. Reads are wrapped in try/except and fall back to the previous value, so a transient kernel-attribute hiccup never crashes the monitor loop. `exchange_error_count` is still pinned at 0: the Binance live data/exec clients swallow errors into internal retry loops and don't publish a counter we can subscribe to without monkey-patching adapter internals; `data_gap_exceeded_tolerance` + `ws_disconnected` together cover the user-visible failure modes for now.
- Third **ADR-008 §6.6 6 h canary** is on record with live telemetry and no alerts: `docs/retros/2026-05-20-phase-3f-testnet-canary-6h-live-telemetry.md`. Bundle `data/testnet/20260520-095350Z-6414ef0d/` on commit `5f273b9`, `shutdown_reason=max_duration`, `elapsed_seconds=21605.289523`, `git_dirty=false`, 720 heartbeats, max heartbeat gap 30.043 s, `ws_connected=true` throughout, `ws_reconnect_count=0`, `exchange_error_count=0`, and no `logs/alerts.log`. Sidecars write orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=490; entry `BUY MARKET 0.001 BTCUSDT @77495.13` (`venue_order_id=5452942`, `trade_id=1807634`) and scheduled close `SELL MARKET 0.001 BTCUSDT @77516.50` (`venue_order_id=5551888`, `trade_id=1835995`) leave final sidecar position `FLAT`, `quantity=0`, `realized_pnl=+0.02137 USDT`. Watchdog evidence for this run: 1920 ticks, 713 healthy + 1207 run_completed, 0 `flatten_invoked`, 0 non-zero exit codes. This validates the startup WS suppression and the 120 s signal-lag threshold after the two 2026-05-20 aborts.
- First **`paper_simulated → testnet_canary` promote retro is signed**: `docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`. Evidence bundle: v9 `data/paper/20260517-053502Z-37b99b3f` (manifest `fa344a55…`, `git_dirty=false`, kind=paper, 60 day BTCUSDT 1m, 545 orders / 545 fills / 273 positions, kill_switch=0, data_gap=0). `current_policy=dry_run=False, multi=0.2, override=None` (matches v9 bundle); `target_policy=dry_run=False, multi=0.1, override=None` (halves canary position size). `policy_diff` is exactly `{"position_pct_multiplier": {"current": 0.2, "target": 0.1}}`. All gates passed: `bundle_policy_matches_current=True`, `review_blockers=none`, `promotion_gate_blockers=none`, `decision_reasons=[promote_gates_passed]`. Evidence paths recorded in §3a: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md` and `docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md`. This authorizes `SourcePolicy(dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None)` for `freqai_linear_v1 / linear-mom-train20240105` at `testnet_canary` going forward; running it on testnet still requires the operator to start `testnet_runner.py --long-run` with the strategy actually registered (the Phase 3f soak ran without strategies).
- ADR-008 **§8 promotion-review patch is landed**: `apps/strategies_nautilus/runners/promotion_review.py` now sets `PHASE_2_STAGE_LIMIT = STAGE_TESTNET_CANARY` (was `STAGE_PAPER_SIMULATED`), so the `phase_3_not_ready` blocker only fires for `live_canary` / `live_normal` from now on. A new gate `_testnet_canary_promote_blockers` only fires on the exact `paper_simulated → testnet_canary` promote transition and enforces: `current_policy.dry_run=False` and `target_policy.dry_run=False`; an operator-supplied `paper_simulated` retro path that exists and mentions `paper_simulated` + the bundle's source name; an operator-supplied testnet runbook signoff path that exists and mentions `ADR-008` + `§6.6`. The two paths are surfaced as `--paper-simulated-retro-path` and `--testnet-runbook-signoff-path` on the CLI, stored on `PromotionReview`, and rendered into a new `## 3a. Phase 3 evidence paths` Markdown subsection. `PolicyFields` schema and existing `paper_shadow → ...` gates are unchanged.
- ADR-008 **§6.6 Phase 3f testnet stability soak is complete** for commit `8f0e041`. `testnet_runner.py --long-run` ran 6 h on Binance Spot testnet against `https://testnet.binance.vision` with `freqai_linear_v1 / linear-mom-train20240105`, `position_pct_multiplier=0.2`, `dry_run=False`, no strategies registered. Bundle `data/testnet/20260518-150212Z-997bf080/` (`shutdown_reason=max_duration`, `elapsed_seconds=21605.193`, `git_dirty=false`, `restart_sequence=0`, `restart_drift_detected=false`, `exchange_error_count=0`, `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`, `daily_pnl=0.0`). 720 heartbeats at 30 s cadence with `ws_connected=true` throughout; `logs/alerts.log` does not exist (all 9 §5.4 alert paths silent). External `infra/watchdog/watchdog.py` recorded 714 healthy ticks, 0 `flatten_invoked`, `exit_code=0`. Nautilus `grep -c ERROR` = 0; stderr file 0 bytes; account `BINANCE-SPOT-master` registered at T+0.348 s, `Reconciliation for BINANCE succeeded` at T+0.694 s; all engines DISPOSED cleanly. Retro: `docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md`. This run is the ADR-008 §6.6 prerequisite stability evidence — it is **not** a `SourcePolicy` promotion; the `phase_3_not_ready` gate stays closed pending the §6.6/§8 follow-up patch to `promotion_review.py`.
- **2026-05-21 ADR-011 Draft landed**: `docs/decisions/011-bridge-postgres-mirror.md`. Defines bridge `SignalStore` (SQLite, default backend) → `PostgresSignalStore` (`signal_events` hypertable) **automatic** mirror. §2 triggers T1–T5 (dashboard freshness >1h lag unacceptable, cross-table SQL JOINs needed for Phase 4 agent work, SQLite size/latency thresholds (same as ADR-010 T4), concurrent-writer `database is locked` errors, backup strategy needing PG WAL). §5 design: **synchronous dual-write** with SQLite-primary / PG-secondary semantics (PG failure logs ERROR and continues, never blocks SQLite, never retries; bridge startup runs `apps.ops.sync_signals_to_postgres` for catch-up). §5.5 mandates test-isolation refactor (`pg_temp_*` schema or dedicated `trader_test` DB) so PG tests no longer TRUNCATE the live `signal_events` table — eliminating the current pytest→dashboard-empty friction. §7 migration steps A-G; §9 acceptance checklist. **Implementation is 0 lines** — ADR remains Draft until any of §2 triggers fires; current dashboard freshness is handled by manually running `python -m apps.ops.sync_signals_to_postgres`. Orthogonal to ADR-010: both can land independently or together. ADR-001 §6 / `docs/agent-reading-list.md` cross-references added; ADR-010 §7.5 reference to "ADR-011" updated since that number is now claimed.
- **2026-05-21 ADR-010 Draft landed**: `docs/decisions/010-redis-stream-signal-transport.md`. Defines the Redis Stream bypass for `SignalEvent v1` transport: §2 hard trigger conditions T1–T5 (signal-lag in canary, multi-consumer topology, multi-producer concurrency, SQLite size/latency thresholds, bridge↔nautilus host split), §5 per-`(source, model_version)` Stream key naming + consumer groups + dual-write (SQLite primary, Redis bypass) + dedup via `signal_id`, §6 docker-compose service block (loopback-only, AOF appendonly, MAXLEN ~100k), §7 step-by-step migration A–E (sink → source → testnet smoke → 6 h canary → optional default flip via future ADR-011), §9 acceptance checklist. **Implementation is 0 lines** — ADR remains Draft until any of §2 triggers fires; SQLite `SignalStore` stays the bridge's default backend. ADR-001 §6 / ADR-007 §4 / ADR-008 §2.2 cross-references updated to point at the new Draft. `docs/agent-reading-list.md` adds a "Signal transport / message bus / Redis" row.
- **2026-05-21 `signals-overview` Grafana dashboard wired on top of the new Postgres datasource**. `apps/ops/sync_signals_to_postgres.py` is an idempotent one-shot mirror from `apps/bridge/store.py::SignalStore` (SQLite, bridge default) into `apps/bridge/store.py::PostgresSignalStore` (`signal_events` hypertable). The current SQLite store carries **3745 rows** across `freqai_linear_v1 / linear-mom-train20240105` (3107), `rule_baseline_v1 / ema5-20+rsi14` (635), `manual_research / binance-fixture-v1` (3) — all mirrored. `infra/grafana/dashboards/signals-overview.json` is a new 13-panel dashboard (uid `signals-overview`, folder `trader`, 3 row headers + 6 stat + 4 timeseries + 2 table): signals-in-range, distinct sources, distinct models, mean confidence, buy/sell ratio, latest-signal age; signals-per-bucket-by-source / by-side; confidence-quantiles-over-time; score min/mean/max; source × model summary table; last-100-signals table. Template var `source` (multi-select + All) sourced from PG via the read-only `postgres-trader` datasource. Bridge default backend remains SQLite; PG is reload-from-source via the script. Side effect: pytest TRUNCATEs `signal_events`; re-run `python -m apps.ops.sync_signals_to_postgres` after pytest to keep dashboard data.
- **2026-05-21 First live validation of the 2026-05-21 observability stack via a 30 min testnet canary smoke**. `data/testnet/20260521-072730Z-2e4d2146/` on commit `98fc976`, `git_dirty=false`, `shutdown_reason=max_duration`, `elapsed_seconds=1805.349`. The new `infra/launchers/first-testnet-canary-30min-smoke.py` (gitignored sibling of the canonical 6 h launcher) trims `--max-run-seconds` to 1800; everything else (source, model_version, multiplier 0.1, sidecar writer, telemetry reader, watchdog) matches the canonical launcher. 60 heartbeats, `ws_connected=true` throughout, `ws_reconnect_count=0`, `exchange_error_count=0`, 0 Nautilus ERROR, stderr 0 bytes. Sidecars `orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=25`. Entry `BUY MARKET 0.001 BTCUSDT @77611.97` (`venue_order_id=5778771`, `trade_id=1881069`), scheduled close `SELL MARKET 0.001 BTCUSDT @77901.05` (`venue_order_id=5784503`, `trade_id=1881684`), final position FLAT, `realized_pnl=+0.28908 USDT`. One advisory alert `signal_lag_exceeded_threshold` fired at `07:55:34Z` because the wall-clock replay only staged 25 signals (covering ~25 min, vs the 30 min run); benign, warning-only, no flatten. Observability chain validated end-to-end under live traffic: `PrometheusTextfileWriter` → `data/observability/textfile/testnet-<run_id>.prom` → node_exporter → Prometheus, and `logs/{heartbeat,alerts}.jsonl` → Promtail → Loki → Grafana `canary-current` dashboard, with all 13 `trader_canary_*` series carrying `{kind="testnet", run_id="20260521-072730Z-2e4d2146"}` labels. Retro: `docs/retros/2026-05-21-phase-3f-testnet-canary-30min-smoke.md`.
- **2026-05-21 Postgres + TimescaleDB + pgvector landed at Phase 3 entry (service-only)**. ADR-001 §6 2026-05-21 修订（第二段）把 `postgres + TimescaleDB + pgvector` 从 Phase 2 提前到 Phase 3 entry **仅启服务、不迁移**。新容器 `trader-postgres` 用 `timescale/timescaledb-ha:pg16` 镜像（含 pgvector 0.8.2 + timescaledb 2.27.0），host 端口 `127.0.0.1:5433`（5432 被无关的 `nishiki-postgres` 占用）。`infra/postgres/init.sql` 在 fresh-init 时建 5 张占位表（`signal_events / orders / fills / positions` 用 hypertable，chunk = 1 day in ns；`embeddings` 用 `vector(1536)`）+ 只读角色 `trader_ro`。`apps/bridge/store.py` 加 `PostgresSignalStore` + `PostgresConnInfo` 作为**可选** backend，方法对齐 SQLite `SignalStore`（`write/mark/get/list_by_status/replay`），`DuplicateSignalError` 通过 `psycopg.errors.UniqueViolation` 映射；`SignalStore` (SQLite) 仍是 bridge 默认 backend，CLI / 工厂未改。Grafana provisioning 新增 read-only Postgres datasource (uid `postgres-trader`)，用 `trader_ro` 通过容器 DNS `postgres:5432` 接入，`jsonData.timescaledb=true`。`pyproject.toml` 加 `psycopg[binary]>=3.2`。新增 7 个 `tests/bridge/test_postgres_store.py` 用例（PG 不可达自动 skip）+ 修订 ADR-001 + 新 retro `docs/retros/2026-05-21-postgres-stack-phase3-entry.md`。**bundle 仍是 promotion source of truth**；本次不迁移历史数据，等真出瓶颈再开迁移 ADR。
- **2026-05-21 observability stack landed at Phase 3 entry**. ADR-001 §6 修订把 grafana + prometheus + loki（含 promtail / node_exporter）从 Phase 5 提前到 Phase 3 entry。`infra/docker-compose.yml` 拉起 5 个容器 (`prom/prometheus:v2.55.1`, `prom/node-exporter:v1.8.2`, `grafana/loki:3.2.1`, `grafana/promtail:3.2.1`, `grafana/grafana:11.3.1`)，全部绑 `127.0.0.1`（端口 9090 / 9100 / 3100 / 9080 / 3000）。新模块 `apps/strategies_nautilus/runners/textfile_metrics.py` 提供 `PrometheusTextfileWriter` + `render_textfile_metrics`：runner 每个 sample 写一份 `data/observability/textfile/testnet-<run_id>.prom`，shutdown 时 cleanup 删除；node_exporter 的 textfile collector 扫该目录后 Prometheus 抓 `:9100/metrics`。导出指标全部带 `{kind, run_id}` label：gauges `ws_connected / daily_pnl_usdt / account_total_usdt / open_orders / open_positions / last_bar_timestamp_seconds / last_signal_timestamp_seconds / heartbeat_timestamp_seconds / starting_balance_usdt / daily_loss_limit_pct / info`，counters `ws_reconnect_total / exchange_error_total / alert_total{alert=…}`。`LongRunningTestnetSettings.observability_textfile_dir` 默认 `data/observability/textfile`（CLI 可关），`run_long_running_testnet` 接受可注入 `textfile_writer`。Promtail 配置抓 4 个 jsonl job (`testnet_runtime` / `testnet_heartbeat` / `testnet_alerts` / `paper_runtime`)，按文件路径 regex 抽 `run_id` label；`infra/watchdog/state.json` 是 overwrite 模式不进 Loki，但 watchdog `heartbeat_lost` alert append 到 `data/testnet/<run_id>/logs/alerts.log` 已经被 `testnet_alerts` 覆盖。Grafana provisioning 自动加载 datasource (Prometheus + Loki) 和 dashboard `canary-current.json` (uid `canary-current`, folder `trader`, 14 panels: 6 stat + 4 timeseries + 2 logs panel + 2 row 标题, template var `run_id` 多选 + All)。**bundle (`run_manifest.json` + sidecar parquet) 仍是 promotion source of truth**，看板只做运行时观察。Retro: `docs/retros/2026-05-21-observability-stack-phase3-entry.md`。
- ADR-008 **§6.5 Phase 3e alert outlet is implemented and unit-tested**. The runner's monitor loop now also emits the three remaining §5.4 advisory alerts to `logs/alerts.log`: `ws_disconnected` (warning) on each `ws_connected=True→False` transition with re-arm on reconnect, `data_gap_exceeded_tolerance` (error) when `(sample.ts - last_bar)` exceeds `data_gap_tolerance_seconds` (CLI `--data-gap-tolerance-seconds`, default 120s), and `signal_lag_exceeded_threshold` (warning) when `(sample.ts - last_signal)` exceeds `signal_lag_threshold_seconds` (CLI `--signal-lag-threshold-seconds`, default 60s). These three are advisory-only — they never trigger auto-flatten and never change exit code. The §5.4 catalog is therefore fully covered: `kill_switch_fired`, `restart_drift_detected`, `exchange_error_burst`, `data_gap_exceeded_tolerance`, `signal_lag_exceeded_threshold`, `ws_disconnected` in `testnet_runner.py`; `heartbeat_lost` in `infra/watchdog/watchdog.py`; `emergency_flatten_started` / `emergency_flatten_completed` in `emergency_flatten.py`. Exit codes are pinned at 0 (clean stop), 1 (runtime error), 2 (startup validation), 3 (restart drift), 4 (kill-switch → flatten OK), 5 (kill-switch → flatten residual). `TestnetRuntimeTelemetry` gained `last_signal_ns`; `LongRunningTestnetSettings` gained `data_gap_tolerance_seconds` + `signal_lag_threshold_seconds` (both must be positive); `AdvisoryAlertState` owns dedup. `phase_3_not_ready` stays closed.
- ADR-009 **Phase 4 AgentAdvice audit foundation is implemented and unit-tested**. `apps.agents.advice.AgentAdvice` defines `schema_version="agent.advice.v1"` records for journals, reviews, analysis, and candidate parameter notes; `apps.agents.store.AgentAdviceStore` persists them in `data/agents/advice.db` with SQLite/WAL; `apps.agents.cli` writes JSON/JSONL, creates journal rows, replays JSONL, and records human review decisions. Payloads with structured execution fields are rejected, and AgentAdvice cannot parse as `SignalEvent`.
- Phase 4 MCP-facing AgentAdvice wrappers are implemented and unit-tested. `apps.mcp_server.agent_advice_tools` exposes only `query_agent_advice`, `write_agent_advice`, and `write_journal`, wraps `AgentAdviceStore`, appends local JSONL audit rows, rejects execution directives through the AgentAdvice schema, and does not import `SignalStore` outside tests.
- Phase 4 deterministic review agent is implemented and unit-tested. `apps.agents.review_agent` reads local status/evidence markdown, produces `advice_type="project_review"` AgentAdvice, and can dry-run or write to the AgentAdvice store without LLM calls, exchange access, `SignalEvent` writes, or `SourcePolicy` mutation.
- Phase 4 read-only dashboard snapshot surface is implemented and unit-tested. `apps.ops.dashboard_snapshot` emits `dashboard.snapshot.v1` JSON/Markdown from `docs/project-status.md`, the AgentAdvice SQLite store, and optional passive paper/testnet bundle report readers; it is a frontend/Grafana input surface only and does not touch the live order path.
- ADR-012 **Phase 5 read-only dashboard entry is implemented and verified**. `apps/frontend` is now a Next.js 15 + Tailwind operations console that reads `dashboard.snapshot.v1` server-side from `data/frontend/dashboard-snapshot.json` (or `TRADER_DASHBOARD_SNAPSHOT`) and renders operational posture, live gate, strict continuity, guardrail counts, order-path boundary flags, AgentAdvice rows, runtime health, read-only Signals & Rejections summaries, operator checklist, watchlist, latest verification, optional paper/testnet bundle summaries, and English / Simplified Chinese UI chrome selected by URL query. It has no API routes, no browser-side mutations, no trading controls, and no exchange access.

## Current Focus

Phase 5 entry: operate and harden the read-only dashboard as the current
operations console while ADR-013, `apps.ops.live_readiness`, and
`apps.strategies_nautilus.runners.live_startup_guard` track Phase 6 blockers
passively. Routine 14-day testnet continuity testing remains paused by operator
decision on 2026-06-04. The Phase 3 strict streak remains 0/14, so Phase 6 is
not open. ADR-008 §6.6 has fifteen clean 6 h sidecar-backed testnet canaries
summarized in `docs/progress/phase-3-testnet-canary-evidence.md`; the
continuity procedure is preserved but paused in
`docs/progress/phase-3-testnet-continuity-plan.md`.

Immediate focus:

1. Keep `freqai_linear_v1 / linear-mom-train20240105` at `hold @ testnet_canary` under the already-signed `SourcePolicy(dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None)`.
2. Treat `docs/progress/phase-3-testnet-canary-evidence.md`, `docs/progress/phase-3-testnet-continuity-plan.md`, the 2026-05-30 clean canary retro, the 2026-05-30 duplicate-entry abort retro, the 2026-05-30 post-fix clean retro, and the 2026-06-01 heartbeat-lost retro as the current operational evidence. Do not run more routine canaries unless the operator explicitly resumes live-readiness evidence collection. If canary evidence resumes, use `python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/<run_id>` before writing future manifest-backed canary retros, use `--markdown` with clean bundle directories before updating the clean evidence ledger, and use `--continuity --markdown --min-clean-hours-per-day 6 --required-consecutive-days 14` with every completed manifest-backed bundle in the candidate window before claiming continuity progress. Carry no-manifest aborts manually. Do not open a new `promotion_review` unless an actual policy/stage decision is being made.
3. Use `docs/decisions/009-agent-advice-audit.md` and `docs/decisions/012-phase5-readonly-dashboard.md` as the active agent/frontend boundaries. Agent/MCP work may write/replay/review `AgentAdvice`; dashboard work may read passive reports, observability textfiles, and AgentAdvice through `dashboard.snapshot.v1`. `TradingAgents/` is available as an ignored read-only upstream reference for future agent role/configuration ideas only; `docs/progress/tradingagents-reference-map.md` is the current safe adaptation map, and `apps.agents.role_profiles` is the first machine-readable AgentAdvice-only role seed. Neither path may write `SignalEvent`, mutate `SourcePolicy`, call exchange APIs, or encode structured execution directives.
4. ADR-008 §6.2 Phase 3b, §6.3 Phase 3c-a/b/c, §6.4 Phase 3d, §6.5 Phase 3e, §6.6 Phase 3f stability soak/canary, and the §8 promotion-review patch are all implemented and unit-tested. The `phase_3_not_ready` blocker now only hard-blocks `live_canary` / `live_normal`.
5. Keep LLM agents and FreqAI out of the order path; `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` remains the only bridge.

## Next Steps

1. Use `python -m apps.ops.live_readiness` as the passive Phase 6 blocker report before any live-risk discussion, feed a saved JSON report into `python -m apps.strategies_nautilus.runners.live_startup_guard` before any future live runner could load credentials, and attach saved JSON artifacts to `python -m apps.ops.dashboard_snapshot` with `--phase6-live-readiness-report` / `--phase6-live-startup-guard-report` for read-only dashboard visibility. Both gates should remain blocked until ADR-013 is Accepted, 14-day testnet continuity is proven, starting capital is declared within 100-500 USDT, a live-canary promotion review exists, and `docs/runbook-first-live-day.md` is Accepted.
2. Continue Phase 5 with only read-only dashboard improvements fed by `dashboard.snapshot.v1`; source/model drill-down links now land on Grafana `source` + `model_version` variables, and the frontend shows loaded snapshot age from the snapshot freshness policy. Keep the frontend free of API routes and mutation controls until a separate ADR opens a specific workflow.
3. Continue project development with targeted verification for the changed surface area; do not spend routine time rebuilding the 0/14 strict continuity streak unless live-readiness evidence is explicitly resumed.
4. If the operator explicitly resumes live-readiness evidence collection, use `docs/progress/phase-3-testnet-continuity-plan.md` and include every completed manifest-backed testnet bundle in the candidate window when running both `report_testnet_bundle --continuity` and `apps.ops.live_readiness`.
5. Use `promotion_review.py` (not just `report_paper_bundle.py`) as the required ADR-007 §2.6 audit artifact for any actual `SourcePolicy` change. Do **not** run `promotion_review.py hold @ testnet_canary` as a routine ratification of each canary — the canary retros plus the evidence and continuity progress files are the operational record.
6. Keep the `testnet_runner.py` startup guard + connection probe as the first line of defense for any subsequent testnet run: explicit `--allow-real-credentials`, clean git, source/model retro evidence, testnet multiplier cap, key-prefix-only audit, Ed25519-only credentials (HMAC fails Binance Spot WS `session.logon`), and Binance Spot TESTNET-only adapter config. The probe injects credentials into the in-memory `TradingNodeConfig` only and never writes the full key/secret to `logs/runtime.log` or `connection_probe.json`.
7. Collect additional testnet canary or paper_simulated evidence only when it directly supports a concrete development or promotion question. The v11 paper bundle's expectancy (+0.00491 USDT/trade, 53.6% win rate, -0.003878% max drawdown over 152 days) is weaker than v9, includes a negative April, and only mildly positive May; the parquet-backed canary fill set is still only a few trades. Treat both as operational/monitoring evidence, not alpha.
8. Decide SQLite -> Postgres / Redis Stream readiness only after backtest, paper, or testnet volume exposes an actual bottleneck.

## Blocked / Deferred

- No live trading.
- No Phase 6 entry: ADR-013 is Draft, strict continuity is 0/14, no live-canary promotion review exists, `docs/runbook-first-live-day.md` is Draft, and the live startup guard is not wired to any live runner.
- No real exchange API keys in the repository.
- No Redis until cross-process signal transport is required.
- No automatic SQLite -> Postgres mirror or PG-backed bridge default until an ADR-011 trigger fires; current Postgres/TimescaleDB/pgvector is service-only Phase 3 support.
- No frontend write actions, order controls, runner triggers, or browser-side mutations.
- No n8n workflows until a concrete Phase 4 orchestration need appears.
- No autonomous Agent trading. Agents may only research, review, summarize, and suggest.
- No edits to `freqtrade/` or `nautilus_trader/` unless explicitly requested.

## Latest Verification

On 2026-07-08, after tightening Phase 6 strict dashboard JSON output,
promotion-review artifact validation, UTF-8 operator-document blocker
handling, dashboard freshness threshold validation, strict JSON artifact
validation, dashboard report-shape validation, non-finite readiness/startup
numeric validation, live-readiness continuity configuration validation,
continuity proof validation, readiness-shape validation, source/model identity
gates, non-text identity/market-scope blocker handling, strict boolean control
blocker handling, credential env-name redaction, and dashboard cross-report
evidence handling, top-level report identity sanitization, generated-at
timestamp sanitization, git evidence sanitization, dashboard evidence
fingerprint sanitization, dashboard snapshot timestamp sanitization,
dashboard project-status UTF-8 handling, dashboard passive input degradation
handling, frontend degraded input visibility, and dashboard passive bundle
degradation handling:

- `dashboard.snapshot.v1` CLI JSON output now uses strict standard JSON and
  refuses to emit non-standard `NaN` / `Infinity` values if a future passive
  input or computed field becomes non-finite.
- `dashboard.snapshot.v1` now rejects malformed explicit
  `generated_at_ns` values before building the snapshot, requiring a
  non-negative integer nanosecond timestamp so freshness, report-age, and JSON
  output remain deterministic.
- `dashboard.snapshot.v1` now rejects non-finite snapshot freshness thresholds
  (`snapshot_warning_after_seconds` / `snapshot_stale_after_seconds`) before
  building the read-only snapshot, preventing `NaN` / `Infinity` thresholds from
  making dashboard freshness policy ambiguous.
- `dashboard.snapshot.v1` and
  `apps.strategies_nautilus.runners.live_startup_guard` now reject saved Phase
  6 report artifacts containing non-standard JSON constants such as `NaN` or
  `Infinity` while preserving artifact hashes and structured blockers.
- `dashboard.snapshot.v1` now converts attached Phase 6 report artifacts whose
  JSON top-level value is not an object into an invalid report summary with the
  artifact SHA-256 preserved, instead of crashing while building the read-only
  dashboard snapshot.
- `dashboard.snapshot.v1` now preserves invalid UTF-8 project-status input as
  a strict-JSON-safe degraded `project_status` row with `decode_error`, empty
  parsed sections, and `live_trading_blocked=false`, so the dashboard reports
  attention instead of crashing or treating malformed operator-document bytes as
  proof that live trading is blocked.
- `dashboard.snapshot.v1` now surfaces corrupt AgentAdvice SQLite input as
  `ops_status.state=attention` with the review queue marked unknown, and
  invalid UTF-8 Prometheus textfiles as observability parse errors with
  attention-state runs, instead of hiding the issue or aborting read-only
  snapshot generation.
- The read-only frontend now includes `agent_advice_error_count` and
  `observability_issue_count` in the first-viewport Blockers metric, and marks
  the AgentAdvice summary unknown when the snapshot says the advice database
  could not be read.
- `dashboard.snapshot.v1` now converts optional paper/testnet bundle report
  loader failures into invalid bundle rows with `review_blockers` instead of
  aborting snapshot generation, so attached passive evidence stays visible as
  blocked input.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now normalize
  non-finite live-canary numeric inputs (`starting_capital_usdt`,
  `max_leverage`, startup `position_pct_multiplier`, and readiness freshness
  windows) into structured blockers and standard JSON-safe `null` report
  fields instead of emitting `NaN` or `Infinity` artifacts.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now preserve SHA-256
  fingerprints and return structured blockers when required operator documents
  such as project status, the live-risk ADR, or the first-live-day runbook are
  not valid UTF-8, instead of aborting passive preflight report generation.
- Live promotion-review artifact parsing now preserves SHA-256 fingerprints
  and returns structured blockers for invalid UTF-8 or non-standard JSON
  constants, preventing malformed operator evidence from aborting Phase 6
  readiness/startup report generation or leaking non-standard numeric values
  into strict JSON output.
- `apps.ops.live_readiness` now rejects continuity review parameters that would
  weaken ADR-008 / ADR-013 proof requirements, including
  `required_consecutive_days < 14` and non-finite or non-positive
  `min_clean_hours_per_day`, before loading bundle continuity summaries.
- `apps.strategies_nautilus.runners.live_startup_guard` now rejects non-finite
  readiness freshness windows and non-finite saved continuity day/streak values
  with structured blockers instead of letting `NaN` disable stale-report checks
  or `Infinity` crash continuity parsing.
- `apps.strategies_nautilus.runners.live_startup_guard` now requires saved
  readiness artifacts to carry the concrete 14-day continuity proof fields
  before startup can pass: `required_consecutive_days >= 14`,
  `current_qualified_streak_days >= required`, zero kill-switch alerts, zero
  emergency-flatten-completed alerts, empty `restart_drift_days`, and no
  continuity blockers.
- `apps.strategies_nautilus.runners.live_startup_guard` now rejects valid JSON
  readiness artifacts whose top-level payload is not an object, or whose nested
  evidence sections are not JSON objects, with structured blockers instead of
  crashing before a future live runner can refuse startup cleanly.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now treat
  whitespace-only `source` / `model_version` values as undeclared before any
  passive Phase 6 readiness or startup gate can pass.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now treat non-string
  `source` / `model_version` values as undeclared and non-string `market_type`
  values as `market_type_must_be_text`, returning structured blockers instead
  of aborting passive preflight report generation.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now require live-canary
  boolean control fields to be real booleans: non-bool `margin_enabled`,
  startup `allow_live_credentials`, or startup `policy_dry_run` values return
  structured blockers instead of passing through Python truthiness.
- `apps.strategies_nautilus.runners.live_startup_guard` now only echoes the
  required live credential environment variable names in its credential-boundary
  report; unknown or non-text credential-name inputs are counted and blocked
  without writing their raw values into the passive report.
- `dashboard.snapshot.v1` now also blocks saved passing startup-guard reports
  with non-zero invalid or unknown credential env-name counts.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now emit top-level
  identity fields (`source`, `model_version`, startup `mode`, and startup
  `kind`) only as stripped text or `null`, so malformed programmatic inputs
  remain strict-JSON-safe blocked reports.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now emit top-level
  `generated_at_ns` only as a non-negative integer nanosecond timestamp or
  `null`; invalid explicit timestamps return `generated_at_ns_invalid` blockers
  instead of breaking strict JSON output.
- `apps.ops.live_readiness` and
  `apps.strategies_nautilus.runners.live_startup_guard` now emit git evidence
  only as text-or-`null` commit and boolean-or-`null` dirty state. Invalid
  injected git evidence returns `git_commit_invalid` /
  `git_dirty_state_invalid` blockers instead of passing through truthiness or
  writing non-JSON-safe values into passive reports.
- `dashboard.snapshot.v1` now treats saved Phase 6 artifact fingerprints and
  readiness-vs-startup git evidence as valid only when they are canonical
  SHA-256 hex strings and 40-character hex commits; malformed saved evidence
  blocks the read-only evidence row instead of being stringified into an
  apparently valid artifact.
- `dashboard.snapshot.v1` now records each attached Phase 6 report file's
  SHA-256 and, when a startup-guard report claims to pass, blocks the startup
  report if the attached readiness report's source/model or report bytes do
  not match the readiness artifact consumed by startup guard.
- `dashboard.snapshot.v1` now converts passing saved readiness or startup-guard
  reports with missing blank `source` / `model_version` identity fields into
  blockers.
- `dashboard.snapshot.v1` now requires startup-guard readiness-report artifact
  rows to be both accepted and fingerprinted before the evidence row is `ok`.
- `dashboard.snapshot.v1` now converts passing saved startup-guard reports with
  missing, invalid, dirty, or readiness-mismatched top-level git evidence into
  blockers.
- `dashboard.snapshot.v1` now converts passing saved startup-guard reports with
  missing/out-of-range 100-500 USDT capital plans or non-spot/margined/leveraged
  market scope into blockers.
- `dashboard.snapshot.v1` now converts passing saved startup-guard reports with
  missing or out-of-bounds `source_policy` evidence into blockers, including
  `dry_run=true`, a missing or above-0.1 `position_pct_multiplier`, a mismatched
  live-canary multiplier cap, or `within_live_canary_bounds=false`.
- `dashboard.snapshot.v1` now converts passing saved readiness reports with
  missing or failed `continuity_summary` evidence into blockers, including a
  missing required gate, fewer than 14 required days, a streak below the
  declared requirement, kill-switch alerts, emergency-flatten alerts, or
  restart-drift days.
- `dashboard.snapshot.v1` now converts passing saved readiness reports with
  missing, invalid, or dirty git evidence into blockers.
- `dashboard.snapshot.v1` now converts passing saved readiness reports with
  missing/out-of-range 100-500 USDT capital plans or non-spot/margined/leveraged
  market scope into blockers.
- `dashboard.snapshot.v1` now converts passing saved startup-guard reports with
  non-live runtime identity fields or credential-boundary leaks into blockers.
- `dashboard.snapshot.v1` now records attached Phase 6 report
  `generated_at_ns` / age and converts missing, invalid, or future
  `generated_at_ns` values in saved passing reports into blockers.
- `dashboard.snapshot.v1` now converts missing or open passive boundary flags
  in a saved passing `phase6.live_readiness.v1` or
  `phase6.live_startup_guard.v1` report into `boundary:<name>` blockers.
- `dashboard.snapshot.v1` now converts non-`ok` internal check statuses in a
  saved passing `phase6.live_readiness.v1` or `phase6.live_startup_guard.v1`
  report into `check:<name>` blockers.
- Startup-guard evidence still requires the startup-side live-risk ADR artifact
  and first-live-day runbook artifact to be both accepted and fingerprinted
  before those evidence rows are `ok`.
- Readiness-report source-document rows still distinguish fingerprint capture
  from acceptance; readiness blockers continue to carry the actual acceptance
  state.
- The frontend already renders Phase 6 evidence rows generically, so no
  frontend write/control surface changed.
- The change remains passive: it reads local dashboard input artifacts only; it
  does not run a live runner, load credentials, build or start Nautilus,
  connect to Binance, write `SignalEvent`, mutate `SourcePolicy`, place
  orders, or authorize live trading.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_live_readiness.py tests/strategies_nautilus/test_live_startup_guard.py tests/ops/test_dashboard_snapshot.py -q` -> **144 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix apps/frontend run typecheck` -> clean.
- `npm --prefix apps/frontend run build` -> clean Next.js production build.
- `npm --prefix apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.

On 2026-06-29, after making dashboard snapshot freshness thresholds configurable:

- `apps.ops.dashboard_snapshot` now accepts `--snapshot-warning-after-seconds` and `--snapshot-stale-after-seconds`, validates both thresholds are positive and `stale > warning`, and emits the selected values in `snapshot_freshness`; the frontend continues to only read and display snapshot age.
- The change is read-only: it only changes snapshot generation metadata, tests, and docs; it does not write `SignalEvent`, mutate `SourcePolicy`, call exchange APIs, start Nautilus, or affect live trading authorization.
- Custom snapshot JSON smoke with `--snapshot-warning-after-seconds 60 --snapshot-stale-after-seconds 300` -> `warning_after_seconds=60.0`, `stale_after_seconds=300.0`, `state_at_generation=fresh`, `evaluated_by=dashboard_reader`, and `live_path_allowed=false`.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **18 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- `curl -I --max-time 10 http://127.0.0.1:3001/?lang=zh-CN` -> HTTP 200 after restarting the local dev server on port 3001.
- `git diff --check` -> clean.

On 2026-06-29, after adding dashboard snapshot freshness status:

- `dashboard.snapshot.v1` now includes `snapshot_freshness` with generation-time freshness, 15 minute warning threshold, 60 minute stale threshold, and frontend-reader evaluation semantics; the frontend command band displays loaded snapshot age without refreshing or triggering any runner.
- The change is read-only: it only adds snapshot metadata and frontend rendering, does not write `SignalEvent`, does not mutate `SourcePolicy`, does not call exchange APIs, does not start Nautilus, and does not affect live trading authorization.
- Snapshot JSON smoke -> `snapshot_freshness.generated_at_ns` matches `generated_at_ns`, `state_at_generation=fresh`, `warning_after_seconds=900.0`, `stale_after_seconds=3600.0`, and `evaluated_by=dashboard_reader`.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **13 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- `git diff --check` -> clean.

On 2026-06-29, after adding source/model Grafana drill-down links:

- `dashboard.snapshot.v1` source/model evidence links now include `var-source` and `var-model_version`; `infra/grafana/dashboards/signals-overview.json` has an explicit `model_version` template variable and all `signal_events` panel queries apply the model filter.
- The change is read-only: it only changes dashboard links and Grafana SQL filters, does not write `SignalEvent`, does not mutate `SourcePolicy`, does not call exchange APIs, does not start Nautilus, and does not affect live trading authorization.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m json.tool infra/grafana/dashboards/signals-overview.json >/tmp/signals-overview.validated.json` -> valid JSON.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **13 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- Snapshot JSON smoke with the v11 paper bundle and 2026-05-30 testnet bundle -> first Grafana evidence href contains `var-source=freqai_linear_v1`, `var-model_version=linear-mom-train20240105`, `from=`, and `to=`.

On 2026-06-29, after adding read-only Phase 6 dashboard gate summaries:

- `dashboard.snapshot.v1` now includes a passive `phase6` summary for optional saved `phase6.live_readiness.v1` and `phase6.live_startup_guard.v1` artifacts; the frontend renders a read-only Phase 6 Gates panel and defaults missing artifacts to blocked.
- The dashboard path remains passive: it reads saved JSON only, does not run `live_readiness` or `live_startup_guard`, does not load credentials, does not start Nautilus, does not write `SignalEvent`, does not mutate `SourcePolicy`, does not place orders, and does not authorize live trading.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **12 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- Snapshot JSON smoke with missing Phase 6 artifact paths plus a `uv run python` assertion -> `phase6.state=blocked`, both reports `missing`, `missing_report_count=2`, `authorizes_live_trading=false`, and `places_orders=false`.
- `git diff --check` -> clean.

On 2026-06-29, after adding the passive Phase 6 live startup guard:

- Added `apps.strategies_nautilus.runners.live_startup_guard`, which emits `phase6.live_startup_guard.v1` JSON/Markdown and returns exit code 2 when a future live runner must refuse startup. It validates `--mode live`, `--kind live`, explicit `--allow-live-credentials`, clean git, accepted ADR-013, a saved passing `phase6.live_readiness.v1` report, exact source/model live-canary promotion review, 100-500 USDT starting capital, `SourcePolicy(dry_run=False, position_pct_multiplier<=0.1)`, and an accepted first-live-day runbook.
- Added Draft `docs/runbook-first-live-day.md`; it is a checklist and manual fallback draft only, not live authorization.
- The guard remains passive: it does not read live credential values, build a Nautilus node, connect to Binance, mutate `SourcePolicy`, write `SignalEvent`, place orders, or authorize live trading.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/strategies_nautilus/test_live_startup_guard.py tests/ops/test_live_readiness.py -q` -> **13 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Blocked current-repo smoke with the standard live guard CLI args -> exit 2, `startup_allowed=false`, `live_trading_authorized=false`, blockers include Draft ADR-013, missing readiness report, missing live promotion review, Draft first-live-day runbook, and dirty working tree.
- `git diff --check` -> clean.

On 2026-06-29, after adding the passive Phase 6 live-readiness gate:

- Added Draft ADR-013 (`docs/decisions/013-phase6-live-risk-gate.md`) and `apps.ops.live_readiness`, which emits `phase6.live_readiness.v1` JSON/Markdown from project status, ADR-013 status, optional passive testnet continuity bundles, optional live-canary promotion review evidence, and a declared starting capital. The tool is audit-only: it does not load credentials, start Nautilus, mutate `SourcePolicy`, write `SignalEvent`, place orders, or authorize live trading.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_live_readiness.py -q` -> **4 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/live_readiness.py tests/ops/test_live_readiness.py` -> clean.
- Blocked default smoke: `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.live_readiness --source freqai_linear_v1 --model-version linear-mom-train20240105 --starting-capital-usdt 100 --markdown` -> `readiness_gate_met=false`, `live_trading_allowed=false`, blockers = live-canary promotion review missing, ADR-013 not accepted, continuity evidence missing.
- Blocked current-window smoke with every completed manifest-backed testnet bundle in the paused candidate window -> `readiness_gate_met=false`, blockers include `testnet_continuity:current_qualified_streak_days=0<required=14` and `testnet_continuity:emergency_flatten_completed=2`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops -q` -> **14 passed, 5 skipped** (Postgres-backed sync tests skipped because `trader-postgres` was not reachable on `127.0.0.1:5433`).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.

On 2026-06-29, after adding read-only source/model evidence drill-down links:

- `dashboard.snapshot.v1` `signal_summary.by_source_model[*].evidence_links` now emits read-only Grafana source drill-down hrefs, attached passive paper/testnet bundle paths, and the testnet canary evidence ledger link when applicable; the frontend renders those links in the Signals & Rejections table without API routes or mutation controls.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **10 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py tests/ops/test_dashboard_snapshot.py` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- Snapshot JSON smoke with paper bundle `data/paper/20260521-021418Z-e535b581`, testnet bundle `data/testnet/20260530-141037Z-6e860b4f`, and repo browser base URL -> first source/model row emitted 4 evidence links: Grafana source drill-down, testnet bundle, paper bundle, and GitHub evidence ledger.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.

On 2026-06-14, after adding read-only source/model freshness to passive signal summaries:

- `PaperBundleReport` and `TestnetBundleReport` now expose first/last `signal_lineage.ts_event` bounds without changing sidecar schemas.
- `dashboard.snapshot.v1` `signal_summary` now emits global, per-run, and per-source/model latest signal freshness from attached passive paper/testnet bundle reports; the frontend renders a read-only Latest signal metric and source/model freshness column.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest -s tests/ops/test_dashboard_snapshot.py tests/strategies_nautilus/test_report_paper_bundle.py tests/strategies_nautilus/test_report_testnet_bundle.py -q` -> **39 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py apps/strategies_nautilus/runners/report_paper_bundle.py apps/strategies_nautilus/runners/report_testnet_bundle.py tests/ops/test_dashboard_snapshot.py tests/strategies_nautilus/test_report_paper_bundle.py tests/strategies_nautilus/test_report_testnet_bundle.py` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (same workspace-root inference warning as prior runs).
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- Snapshot JSON smoke with paper bundle `data/paper/20260521-021418Z-e535b581` and testnet bundle `data/testnet/20260530-141037Z-6e860b4f` -> `signal_summary.freshness.latest_signal_run_id=20260530-141037Z-6e860b4f`, `latest_signal_kind=testnet`, and 3003 signal rows.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest -s -q` -> **552 passed, 12 skipped** (Postgres-backed tests skipped because `trader-postgres` was not reachable on `127.0.0.1:5433`). Running full pytest without `TMPDIR=/tmp` hit an environment-specific `/mnt/c` file-mode assertion in two existing tests.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-11, after adding read-only signal-source and rejection summaries to the dashboard snapshot and frontend:

- Added `signal_summary` to `dashboard.snapshot.v1` from attached passive paper/testnet bundle report `signal_lineage` decision/reason counts; the frontend now renders a read-only Signals & Rejections panel.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **10 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py tests/ops/test_dashboard_snapshot.py` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build.
- `npm --prefix /home/nishiki/projects/trader/apps/frontend audit --audit-level=moderate` -> **0 vulnerabilities**.
- Snapshot JSON smoke with paper bundle `data/paper/20260521-021418Z-e535b581` and testnet bundle `data/testnet/20260530-141037Z-6e860b4f` -> `signal_summary` emitted 2 bundles, 3003 signal rows, 3003 accepted, 0 skipped, 0 true rejections.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **552 passed, 12 skipped** (Postgres-backed tests skipped because `trader-postgres` was not reachable on `127.0.0.1:5433`).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.

On 2026-06-11, after adding project-owned safe agent role profiles:

- Added `apps.agents.role_profiles.AgentRoleProfile` plus five default AgentAdvice-only profiles: `evidence_review`, `data_anomaly`, `macro_context`, `strategy_brainstorm`, and `parameter_review`.
- Added `python -m apps.agents.cli profiles` to list the safe role profile seed without touching the AgentAdvice DB, LLM providers, TradingAgents runtime code, or exchange paths.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.agents.cli profiles --profile-id evidence_review` -> emitted one `agent.role_profile.v1` JSON row with all execution boundaries in `disallowed_actions`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents/test_role_profiles.py tests/agents/test_cli.py -q` -> **11 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents -q` -> **42 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/agents tests/agents` -> clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **564 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.
- `rg -n "from TradingAgents|import TradingAgents|from tradingagents|import tradingagents" apps tests` -> no matches.

On 2026-06-11, after adding the TradingAgents safe adaptation map:

- Inspected `TradingAgents/tradingagents/default_config.py`, `tradingagents/graph/setup.py`, `tradingagents/graph/conditional_logic.py`, `tradingagents/graph/checkpointer.py`, `tradingagents/agents/utils/agent_states.py`, `tradingagents/agents/schemas.py`, and `cli/main.py`.
- Added `docs/progress/tradingagents-reference-map.md` to map borrowable patterns to AgentAdvice-only adaptations and list explicitly forbidden trader / portfolio-manager execution semantics.
- Updated `apps/agents/README.md`, `docs/agent-reading-list.md`, and `docs/progress/README.md` so future TradingAgents-inspired work starts from the safe adaptation map.
- `rg -n "from TradingAgents|import TradingAgents|from tradingagents|import tradingagents" apps tests` -> no matches.
- `git diff --check` -> clean.

On 2026-06-11, after adding the TradingAgents read-only upstream reference:

- `git clone https://github.com/TauricResearch/TradingAgents.git TradingAgents` -> checkout created at `04f434e86db88e7707bf16db8ed7183f9764fe26` on `main`.
- `TradingAgents/pyproject.toml` -> upstream version `0.2.5`; `TradingAgents/LICENSE` -> Apache-2.0.
- `git check-ignore -v TradingAgents/` -> `.gitignore:42:TradingAgents/`; root git does not track the upstream source tree.
- Boundary documented in `docs/upstream-versions.md` and `apps/agents/README.md`: TradingAgents is reference-only; no runtime dependency, no `SignalEvent` write, no `SourcePolicy` mutation, no exchange API access, and no live order path impact.
- `git diff --check` -> clean.

On 2026-06-11, after adding passive Prometheus textfile observability summaries to the dashboard snapshot and frontend runtime-health panel:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **10 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py tests/ops/test_dashboard_snapshot.py` -> clean.
- `cd apps/frontend && npm run typecheck` -> clean.
- `cd apps/frontend && npm run build` -> clean Next.js production build.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 2 --observability-textfile-dir data/observability/textfile --observability-limit 2 --grafana-base-url '' > /tmp/dashboard-observability-check.json` plus JSON smoke -> emitted `observability` with 2 textfiles, 2 stale runs, 0 alerts, and 1 open position from the passive textfile collector output.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **556 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `cd apps/frontend && npm audit --audit-level=moderate` -> **0 vulnerabilities**.
- `git diff --check` -> clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 2 --observability-textfile-dir data/observability/textfile --observability-limit 2 --grafana-base-url '' > data/frontend/dashboard-snapshot.json`; `cd apps/frontend && npm run dev -- --port 3003 --hostname 127.0.0.1`; `curl -I http://127.0.0.1:3003/?lang=zh-CN` -> **HTTP 200 OK**; content smoke found `运行健康`, `Textfile`, `数据延迟`, `未平状态`, and stale runtime rows.

On 2026-06-09, after adding Phase 5 read-only reference links:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **7 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py tests/ops/test_dashboard_snapshot.py` -> clean.
- `cd apps/frontend && npm run typecheck` -> clean.
- `cd apps/frontend && npm run build` -> clean Next.js production build.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 2 --grafana-base-url '' --repo-browser-base-url https://github.com/Maggyee/Nishiki-Trader/blob/main > /tmp/dashboard-snapshot-check.json` plus `json.tool` / `rg` smoke -> `reference_links` emitted GitHub doc hrefs and local-only Grafana source paths.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **541 passed, 12 skipped** (Postgres-backed tests skipped because `trader-postgres` was not reachable on `127.0.0.1:5433`).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `cd apps/frontend && npm audit --audit-level=moderate` -> not completed: npm registry audit endpoint DNS failed with `EAI_AGAIN`.
- home-frp follow-up after push: `npm --prefix /home/nishiki/projects/trader/apps/frontend ci` -> **0 vulnerabilities**; `npm --prefix /home/nishiki/projects/trader/apps/frontend run typecheck` -> clean; `npm --prefix /home/nishiki/projects/trader/apps/frontend run build` -> clean Next.js production build (with a non-fatal workspace-root inference warning from `/home/nishiki/package-lock.json`); `curl -I http://127.0.0.1:3002/?lang=zh-CN` -> **HTTP 200 OK**; content smoke found `参考链接`, `Signals overview`, `Current testnet canary`, and `边界账本`.

On 2026-06-06, after adding the read-only English / Simplified Chinese language switch:

- `cd apps/frontend && npm run typecheck` -> clean.
- `cd apps/frontend && npm run build` -> clean Next.js production build.
- `cd apps/frontend && npm audit --audit-level=moderate` -> **0 vulnerabilities**.
- `curl -I http://127.0.0.1:3002/?lang=zh-CN` -> **HTTP 200 OK** after restarting the dev server from a clean `.next`.
- `curl -s http://127.0.0.1:3002/?lang=zh-CN` -> content smoke found `运维观察台`, `语言`, `简体中文`, `操作员检查表`, `关注列表`, and `边界账本`.
- `ssh home-frp 'curl -s http://127.0.0.1:13002/?lang=zh-CN'` -> same Simplified Chinese content visible through the active tunnel.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **551 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.

On 2026-06-06, after upgrading the Phase 5 frontend into a read-only operations console:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ops/test_dashboard_snapshot.py -q` -> **5 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/ops/dashboard_snapshot.py tests/ops/test_dashboard_snapshot.py` -> clean.
- `cd apps/frontend && npm run typecheck` -> clean.
- `cd apps/frontend && npm run build` -> clean Next.js production build.
- `cd apps/frontend && npm audit --audit-level=moderate` -> **0 vulnerabilities**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 10 > data/frontend/dashboard-snapshot.json` -> emitted local gitignored snapshot with `ops_status`, parsed sections, and `operator_checklist`.
- `cd apps/frontend && npm run dev -- --port 3002`; `curl -I http://127.0.0.1:3002/` -> **HTTP 200 OK**; content smoke found `Operations Console`, `Operational posture`, `Operator Checklist`, `Watchlist`, `Verification`, and `Boundary Ledger`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **551 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.

On 2026-06-04, after opening Phase 5 read-only frontend entry:

- `cd apps/frontend && npm audit --audit-level=moderate` -> **0 vulnerabilities**.
- `cd apps/frontend && rm -rf .next && npm run typecheck` -> clean.
- `cd apps/frontend && npm run build` -> clean Next.js production build.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 10 > data/frontend/dashboard-snapshot.json` -> emitted local gitignored snapshot for frontend smoke.
- `cd apps/frontend && npm run dev -- --port 3001`; `curl -I http://127.0.0.1:3001/` -> **HTTP 200 OK**; content smoke found `Phase 5 Read-Only Operations`, `Trader Dashboard`, `Order Path`, and `AgentAdvice`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **551 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-04, after adding the deterministic review agent and read-only
dashboard snapshot surface:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents tests/ops/test_dashboard_snapshot.py -q` -> **39 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/agents apps/ops tests/agents tests/ops/test_dashboard_snapshot.py` -> clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.agents.review_agent --dry-run --project-status-path docs/project-status.md --evidence-path docs/progress/phase-3-testnet-canary-evidence.md --created-at-ns 1778760000000000000 --advice-id smoke-review` -> dry-run JSON only, `dashboard_snapshot_ready=true`, no store write.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.dashboard_snapshot --project-status-path docs/project-status.md --agent-advice-db data/agents/advice.db --advice-limit 5` -> emitted `dashboard.snapshot.v1` JSON with all live/order-path boundary flags false.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **551 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-04, after adding ADR-009 and the Phase 4 AgentAdvice audit store:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents -q` -> **27 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **520 passed, 12 skipped** (Postgres tests skipped because `trader-postgres` was not reachable on `127.0.0.1:5433`).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-04, after adding the Phase 4 MCP-facing AgentAdvice wrappers:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/mcp_server -q` -> **7 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **539 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/mcp_server tests/mcp_server` -> clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-04, after hardening live telemetry exchange-error log counting:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/strategies_nautilus/test_live_telemetry.py -q` -> **33 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **505 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-06-01, after the non-clean testnet canary
`20260601-013940Z-ffe1e00c`:

- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **504 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Replay preflight: `future_wall_clock_replay_rows=0`; replay wrote 480 rows immediately before runner launch, and runner reached `node_run_invoked` at `2026-06-01T01:39:40.702Z`.
- Runtime: 684 heartbeats, one runner entry order/fill (`BUY 0.001 BTCUSDT`), last heartbeat at `2026-06-01T07:21:42.443Z` with `open_positions=1`; no `run_manifest.json` or sidecar parquet files were written.
- Alerts: 50 `heartbeat_lost` rows plus one `emergency_flatten_completed` row. Emergency flatten closed `0.001 BTC` at `2026-06-01T07:49:12.965Z`, with `residual_orders=[]` and `residual_positions=[]`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260601-013940Z-ffe1e00c` -> failed because `run_manifest.json` is missing. This run is not clean evidence; clean aggregate remains unchanged.
- Retro: `docs/retros/2026-06-01-phase-3f-testnet-canary-runner-heartbeat-lost.md`.

On 2026-05-30, after running the post-fix 6 h testnet canary
`20260530-141037Z-6e860b4f`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.269135`, `git_dirty=false`, `git_commit=348ca5b3f79d0ba82dd3e7f732075571a01e7515`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.18 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=896. Entry `BUY 0.001 BTCUSDT @73981.85`, scheduled close `SELL 0.001 BTCUSDT @73971.30`, final position FLAT, realized PnL `-0.01055 USDT`.
- The run intentionally overlapped remaining future replay rows from the earlier aborted stream; lineage recorded the second same-bar buy intent as `suppressed_after_same_bar_order_submission`, and only one entry order was submitted.
- Watchdog: final `status=run_completed`, `exit_code=0`, `flatten_invoked=false`, `alert_path=null`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260530-141037Z-6e860b4f` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across the fifteen clean 6 h bundles -> `clean_run_count: 15/15`, `clean_elapsed_hours: 90.02`, `orders=30 / fills=30 / positions=15 / heartbeats=10787 / alerts=0`, `clean_realized_pnl=-0.21373 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest, the 2026-05-26 blocked bundle, the 2026-05-30 duplicate-entry abort, and this post-fix clean bundle -> `qualified_day_count: 7/10`, `current_qualified_streak_days: 0/14`, `longest_qualified_streak_days: 5`, 2026-05-30 clean hours `12.00`, blockers `current_qualified_streak_days=0<required=14` and `emergency_flatten_completed=2`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **504 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retros: `docs/retros/2026-05-30-phase-3f-testnet-canary-6h-control-run.md`, `docs/retros/2026-05-30-phase-3f-testnet-canary-duplicate-entry-abort.md`, and `docs/retros/2026-05-30-phase-3f-testnet-canary-post-fix-control-run.md`.

On 2026-05-25, after running the 6 h testnet canary
`20260525-000508Z-af7de22d`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.369265`, `git_dirty=false`, `git_commit=4be5a69`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.147 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @77194.71`, scheduled close `SELL 0.001 BTCUSDT @77365.44`, final position FLAT, realized PnL `+0.17073 USDT`.
- Watchdog: 717 healthy + 18 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260525-000508Z-af7de22d` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across ten clean 6 h bundles -> `clean_run_count: 10/10`, `clean_elapsed_hours: 60.01`, `orders=20 / fills=20 / positions=10 / heartbeats=7192 / alerts=0`, `clean_realized_pnl=-0.42502 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 6/7`, `current_qualified_streak_days: 5/14`, 2026-05-22 clean hours `12.00`, 2026-05-23 clean hours `12.00`, 2026-05-24 clean hours `12.00`, 2026-05-25 clean hours `6.00`, blockers `current_qualified_streak_days=5<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-25-phase-3f-testnet-canary-6h-control-run.md`.

On 2026-05-24, after running the second 6 h testnet canary
`20260524-072049Z-a49496ed`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.295099`, `git_dirty=false`, `git_commit=2d98efc`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.181 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=476. Entry `BUY 0.001 BTCUSDT @76880.41`, scheduled close `SELL 0.001 BTCUSDT @77110.68`, final position FLAT, realized PnL `+0.23027 USDT`.
- Watchdog: 717 healthy + 8 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260524-072049Z-a49496ed` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across nine clean 6 h bundles -> `clean_run_count: 9/9`, `clean_elapsed_hours: 54.01`, `orders=18 / fills=18 / positions=9 / heartbeats=6473 / alerts=0`, `clean_realized_pnl=-0.59575 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 5/6`, `current_qualified_streak_days: 4/14`, 2026-05-22 clean hours `12.00`, 2026-05-23 clean hours `12.00`, 2026-05-24 clean hours `12.00`, blockers `current_qualified_streak_days=4<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-24-phase-3f-testnet-canary-6h-second-control-run.md`.

On 2026-05-24, after running the 6 h testnet canary
`20260524-005423Z-24c8c34d`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.376894`, `git_dirty=false`, `git_commit=8e91489`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.176 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @76847.49`, scheduled close `SELL 0.001 BTCUSDT @77013.06`, final position FLAT, realized PnL `+0.16557 USDT`.
- Watchdog: 717 healthy + 2 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260524-005423Z-24c8c34d` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across eight clean 6 h bundles -> `clean_run_count: 8/8`, `clean_elapsed_hours: 48.01`, `orders=16 / fills=16 / positions=8 / heartbeats=5754 / alerts=0`, `clean_realized_pnl=-0.82602 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 5/6`, `current_qualified_streak_days: 4/14`, 2026-05-22 clean hours `12.00`, 2026-05-23 clean hours `12.00`, 2026-05-24 clean hours `6.00`, blockers `current_qualified_streak_days=4<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-24-phase-3f-testnet-canary-6h-control-run.md`.

On 2026-05-23, after running the afternoon 6 h testnet canary
`20260523-121618Z-ba5c4bfe`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.387502`, `git_dirty=false`, `git_commit=5ebb80c`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.16 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @74750.01`, scheduled close `SELL 0.001 BTCUSDT @75700.00`, final position FLAT, realized PnL `+0.94999 USDT`.
- Watchdog: 717 healthy + 8 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260523-121618Z-ba5c4bfe` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across seven clean 6 h bundles -> `clean_run_count: 7/7`, `clean_elapsed_hours: 42.01`, `orders=14 / fills=14 / positions=7 / heartbeats=5035 / alerts=0`, `clean_realized_pnl=-0.99159 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 4/5`, `current_qualified_streak_days: 3/14`, 2026-05-22 clean hours `12.00`, 2026-05-23 clean hours `12.00`, blockers `current_qualified_streak_days=3<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-23-phase-3f-testnet-canary-6h-afternoon-run.md`.

On 2026-05-23, after running the 6 h testnet canary
`20260523-014615Z-9ef29d55`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.291493`, `git_dirty=false`, `git_commit=9dccbd6`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.2 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @75412.90`, scheduled close `SELL 0.001 BTCUSDT @75259.45`, final position FLAT, realized PnL `-0.15345 USDT`.
- Watchdog: 715 healthy + 9 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260523-014615Z-9ef29d55` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across six clean 6 h bundles -> `clean_run_count: 6/6`, `clean_elapsed_hours: 36.01`, `orders=12 / fills=12 / positions=6 / heartbeats=4316 / alerts=0`, `clean_realized_pnl=-1.94158 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 4/5`, `current_qualified_streak_days: 3/14`, 2026-05-22 clean hours `12.00`, 2026-05-23 clean hours `6.00`, blockers `current_qualified_streak_days=3<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-23-phase-3f-testnet-canary-6h-control-run.md`.

On 2026-05-22, after running the evening 6 h testnet canary
`20260522-175232Z-83a9d87d`:

- `run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.422712`, `git_dirty=false`, `git_commit=a6f6cf3`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.18 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @76795.25`, scheduled close `SELL 0.001 BTCUSDT @75562.99`, final position FLAT, realized PnL `-1.23226 USDT`.
- Watchdog: 717 healthy + 5 run_completed ticks, 0 `flatten_invoked`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260522-175232Z-83a9d87d` -> `clean_for_retro: True`, `review_blockers: none`, `recommendation=ready_for_retro_evidence`.
- Clean aggregate command across five clean 6 h bundles -> `clean_run_count: 5/5`, `clean_elapsed_hours: 30.01`, `orders=10 / fills=10 / positions=5 / heartbeats=3597 / alerts=0`, `clean_realized_pnl=-1.78813 USDT`.
- Strict continuity command including the 2026-05-20 blocked manifest -> `qualified_day_count: 3/4`, `current_qualified_streak_days: 2/14`, 2026-05-22 clean hours `12.00`, blockers `current_qualified_streak_days=2<required=14` and `emergency_flatten_completed=1`.
- Pre-run baseline: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- Post-retro doc check: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Retro: `docs/retros/2026-05-22-phase-3f-testnet-canary-6h-evening-run.md`.

On 2026-05-22, after adding testnet continuity reporting:

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle --continuity --markdown --min-clean-hours-per-day 6 --required-consecutive-days 14 data/testnet/20260519-120037Z-f1b06fd3 data/testnet/20260520-035223Z-20061290 data/testnet/20260520-095350Z-6414ef0d data/testnet/20260521-102631Z-ea999625 data/testnet/20260522-030142Z-36922497` -> `qualified_day_count: 3/4`, `current_qualified_streak_days: 2/14`, `exchange_errors=0`, `ws_reconnects=1`, `restart_sequence=0`, `kill_switch=0`, `emergency_flatten_completed=1`, `required_gate_met=false`, blockers `current_qualified_streak_days=2<required=14` and `emergency_flatten_completed=1`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/strategies_nautilus/test_report_testnet_bundle.py -q` -> **20 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **503 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.

On 2026-05-22, after adding aggregate testnet bundle reporting:

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle data/testnet/20260522-030142Z-36922497` -> `clean_for_retro: True`, `review_blockers: none`, heartbeats=719, max gap 30.175 s, alerts=0, sidecars orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477, realized PnL `-0.46798 USDT`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_testnet_bundle --markdown data/testnet/20260519-120037Z-f1b06fd3 data/testnet/20260520-095350Z-6414ef0d data/testnet/20260521-102631Z-ea999625 data/testnet/20260522-030142Z-36922497` -> `clean_run_count: 4/4`, `clean_elapsed_hours: 24.01`, `orders=8 / fills=8 / positions=4 / heartbeats=2878 / alerts=0`, `clean_realized_pnl=-0.55587 USDT`, `recommendation=ready_for_progress_evidence`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/strategies_nautilus/test_report_testnet_bundle.py -q` -> **13 passed**; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **496 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- `data/testnet/20260522-030142Z-36922497/run_manifest.json` -> `shutdown_reason=max_duration`, `elapsed_seconds=21605.416622`, `git_dirty=false`, `git_commit=63ae0a1`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 719 heartbeats at 30 s cadence, max gap 30.175 s, `ws_connected=true` throughout, no `logs/alerts.log`.
- Live sidecars: orders=2 / fills=2 / positions=1 / account_balances=451 / signal_lineage=477. Entry `BUY 0.001 BTCUSDT @77719.74`, scheduled close `SELL 0.001 BTCUSDT @77251.76`, final position FLAT, realized PnL `-0.46798 USDT`.
- Watchdog: 717 healthy + 14 run_completed ticks, 0 `flatten_invoked`.
- Retro: `docs/retros/2026-05-22-phase-3f-testnet-canary-6h-control-run.md`; evidence summary updated in `docs/progress/phase-3-testnet-canary-evidence.md`.

On 2026-05-21, after landing the ADR-011 Draft for bridge → Postgres auto-mirror:

- `docs/decisions/011-bridge-postgres-mirror.md` created (Draft, ~290 lines).
- ADR-001 §6 (2026-05-21 修订第三段 + 新增第四段)、ADR-010 §7.5 + §10 交叉引用、`docs/agent-reading-list.md` 全部更新到 ADR-011 Draft。
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **483 passed** (baseline; no code changes — ADR is doc-only).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- Reality check: `apps/bridge/store.py::SignalStore.__init__` 仍然只接 `path` 参数；`SignalStore.write` 仍然只写 SQLite；PG 镜像继续靠 `apps/ops/sync_signals_to_postgres.py` 手动跑；测试隔离仍是 TRUNCATE 真实表（`tests/bridge/test_postgres_store.py` + `tests/ops/test_sync_signals_to_postgres.py`）。

On 2026-05-21, after landing the ADR-010 Draft for Redis Stream signal transport:

- `docs/decisions/010-redis-stream-signal-transport.md` created (Draft, ~250 lines).
- ADR-001 §6 (2026-05-21 修订第二段、第三段)、ADR-007 §4 后续 ADR 段、ADR-008 §2.2 不做段、`docs/agent-reading-list.md` 全部交叉引用到 ADR-010 Draft。
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **483 passed** (baseline; no code changes — ADR is doc-only).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- Reality check: 没有任何 Redis 容器被启动；`docker compose ps` 仍是 6 个服务 (prometheus / node_exporter / loki / promtail / grafana / postgres)；`apps/bridge/store.py` 没有 `RedisStreamSink` / `RedisStreamSource`，bridge 默认 backend 仍是 SQLite。

On 2026-05-21, after landing the `signals-overview` Grafana dashboard on the Postgres datasource:

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.ops.sync_signals_to_postgres` → `{read: 3745, written: 3745, skipped_duplicate: 0, skipped_filter: 0, errored: 0}`.
- `docker exec trader-postgres psql -U trader -d trader -c "SELECT source, COUNT(*) FROM signal_events GROUP BY source"` → `freqai_linear_v1: 3107`, `rule_baseline_v1: 635`, `manual_research: 3` (matches SQLite SignalStore).
- Grafana provisioning reload → `Dashboards config reloaded`. `/api/search?type=dash-db` lists 2 dashboards in folder `trader`: `canary-current` and `signals-overview`. New dashboard has 15 panels (12 data + 3 row headers).
- `/api/ds/query` against `grafana-postgresql-datasource uid=postgres-trader` for the source-summary panel returned `[('freqai_linear_v1', 3107), ('rule_baseline_v1', 635), ('manual_research', 3), ('freqai_v1', 1)]`. The `freqai_v1` row is the pre-existing fixture row from earlier PG test runs and is filtered out by the dashboard's default template var values.
- Template var `source` query (`SELECT DISTINCT source FROM signal_events ORDER BY source`) returned all 4 sources through `trader_ro`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **483 passed** (478 prior + 5 new `tests/ops/test_sync_signals_to_postgres.py` cases: dry_run no-op, full round-trip, idempotent rerun, source filter, since_ns filter).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- New files: `apps/ops/sync_signals_to_postgres.py`, `infra/grafana/dashboards/signals-overview.json`, `tests/ops/__init__.py`, `tests/ops/conftest.py`, `tests/ops/test_sync_signals_to_postgres.py`.
- Edits: `infra/README.md` (signals-overview note + sync hint), `docs/project-status.md`.

On 2026-05-21, after running the 30 min testnet canary smoke that validates the new observability stack end-to-end under live traffic:

- `data/testnet/20260521-072730Z-2e4d2146/run_manifest.json` → `shutdown_reason=max_duration`, `elapsed_seconds=1805.349`, `git_dirty=false`, `git_commit=98fc976`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`, `ws_reconnect_count=0`, `exchange_error_count=0`.
- 60 heartbeats at 30 s cadence, `ws_connected=true` throughout. `logs/alerts.log` contains 1 row: `signal_lag_exceeded_threshold` advisory (warning) — explained in retro §5 (wall-clock replay window shorter than the run window). No `kill_switch_fired`, no `data_gap_exceeded_tolerance`, no `ws_disconnected`, no `heartbeat_lost`, no `emergency_flatten_*`.
- Live sidecars under `data/testnet/20260521-072730Z-2e4d2146/`: `orders.parquet` (2 rows), `fills.parquet` (2 rows), `positions.parquet` (1 row), `account_balances.parquet` (451 rows), `signal_lineage.parquet` (25 rows). Entry `BUY 0.001 BTCUSDT @77611.97`, scheduled close `SELL 0.001 BTCUSDT @77901.05`, final position FLAT, realized PnL `+0.28908 USDT`, 0 commissions.
- Watchdog: 60 healthy ticks + 1 `run_completed` final tick, 0 `flatten_invoked`, `exit_code=0`. Append-only history at `infra/watchdog/history.jsonl` captured by Promtail `watchdog_history` job.
- `data/observability/textfile/testnet-20260521-072730Z-2e4d2146.prom` was written through the run (13 `trader_canary_*` series with `{kind="testnet", run_id="20260521-072730Z-2e4d2146"}`) and cleaned up at shutdown by `PrometheusTextfileWriter.cleanup()`. `curl :9100/metrics | grep '^trader_canary_'` returned all 13 series live. Prometheus query `trader_canary_heartbeat_timestamp_seconds` returned the new run_id labels under `instance=node_exporter:9100`, `job=node_exporter`.
- Loki `{job="testnet_heartbeat", run_id="20260521-072730Z-2e4d2146"}` returned the 60-row heartbeat stream; `{job="testnet_alerts", run_id=...}` returned the single advisory alert. `label_values(run_id)` over the last 7 d returned all 22 historical run_ids including the new one. Grafana `canary-current` dashboard template var `run_id` (LogQL `{job=~"testnet_.+|paper_.+"}`) lists the new run_id alongside the historical ones.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **478 passed** (baseline; no code changes).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean (baseline; no code changes).
- New files: `docs/retros/2026-05-21-phase-3f-testnet-canary-30min-smoke.md`.
- Edits: `docs/project-status.md` only.

On 2026-05-21, after bringing Postgres + TimescaleDB + pgvector forward to Phase 3 entry (service-only):

- `docker compose ps` → `trader-postgres` healthy on `127.0.0.1:5433` using `timescale/timescaledb-ha:pg16`.
- `docker exec trader-postgres psql -U trader -d trader -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb','vector')"` → `timescaledb 2.27.0` + `vector 0.8.2`.
- `\dt` → 5 tables (`embeddings`, `fills`, `orders`, `positions`, `signal_events`). `timescaledb_information.hypertables` → 4 hypertables (signal_events, orders, fills, positions, all `chunk_time_interval = 1 day in ns`). `embeddings.embedding` column = `vector(1536)`.
- `SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname='trader_ro'` → `trader_ro | t`.
- Grafana datasource provisioning → 3 datasources (`Loki uid=loki`, `Postgres uid=postgres-trader type=grafana-postgresql-datasource`, `Prometheus uid=prometheus`). End-to-end SQL via `/api/ds/query`: `SELECT current_database(), current_user, count(*) FROM information_schema.tables WHERE table_schema='public'` → `['trader', 'trader_ro', 5]`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **478 passed** (466 prior + 7 new `tests/bridge/test_postgres_store.py` cases + 5 textfile/test housekeeping uplift).
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/bridge -q` → **93 passed** (bridge SQLite + PG round-trip).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- New files: `infra/postgres/init.sql`, `docs/retros/2026-05-21-postgres-stack-phase3-entry.md`, `tests/bridge/test_postgres_store.py`.
- Edits: `infra/docker-compose.yml` (postgres 服务解注释 + volume), `infra/README.md` (Phase 3 entry 行更新), `infra/grafana/provisioning/datasources/datasources.yml` (Postgres ds + deleteDatasources), `apps/bridge/store.py` (新增 PostgresSignalStore + PostgresConnInfo), `pyproject.toml` (psycopg[binary]), `docs/decisions/001-tech-stack.md` (§6 2026-05-21 修订第二段), `docs/project-status.md`.

On 2026-05-21, after bringing the observability stack forward to Phase 3 entry:

- `infra/docker-compose.yml` brings up 5 containers (`trader-prometheus` / `trader-node-exporter` / `trader-loki` / `trader-promtail` / `trader-grafana`); all loopback ports. `curl :9090/-/ready` → `Prometheus Server is Ready.`, `:3100/ready` → `ready`, `:3000/api/health` → `{"database":"ok","version":"11.3.1"}`, `:9080/ready` → `Ready`, `:9100/metrics` → exposes textfile metrics. Prometheus active targets `prometheus` + `node_exporter` both `health=up`. Grafana provisioning auto-registered Prometheus + Loki datasources and loaded dashboard `canary-current` into folder `trader` (14 panels).
- End-to-end textfile smoke: hand-wrote `data/observability/textfile/testnet-smoke.prom` with `trader_canary_info{kind="testnet",run_id="smoke-test"} 1`, waited a Prometheus scrape interval, `PromQL trader_canary_info` returned the series with labels `{instance="node_exporter:9100", job="node_exporter", kind="testnet", run_id="smoke-test"}`. Cleanup removed the file; historical series remained queryable via TSDB.
- Loki end-to-end: Promtail bulk-tailed historical bundles. `label_values(run_id)` returned **20 distinct run_ids** spanning `20260517-050320Z-f5e13cda` through `20260521-021418Z-e535b581`. `testnet_heartbeat` job's most recent stream surfaced `run_id=20260520-040143Z-90c3c62b`'s heartbeat row including `account_total_usdt`, `daily_pnl`, `last_bar_ns`, `ws_connected`, etc.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **466 passed** (448 prior + 18 new `tests/strategies_nautilus/test_textfile_metrics.py` cases: `render_textfile_metrics` HELP/TYPE pairing, run identity labels, optional-field omit, alert_total cardinality, ws 0/1 mapping, label-value escaping, starting balance + daily loss limit emission; `write_textfile_atomic` replace-not-append + no `.tmp` left + mkdir; `PrometheusTextfileWriter` path naming, cumulative `record_alert`, cleanup idempotent + file-removed; `LongRunningTestnetSettings.observability_textfile_dir` default None + assignment; `run_long_running_testnet` with injected writer → `write_sample` ≥1 + `cleanup` ==1 + file removed + identity-label content; `observability_textfile_dir=None` → no `.prom` written; `ws_connected=False` sample → `ws_disconnected` counter recorded in textfile).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- New files: `apps/strategies_nautilus/runners/textfile_metrics.py`, `tests/strategies_nautilus/test_textfile_metrics.py`, `infra/prometheus/{prometheus.yml,README.md}`, `infra/loki/{loki-config.yml,README.md}`, `infra/promtail/{promtail.yml,README.md}`, `infra/grafana/{README.md,provisioning/datasources/datasources.yml,provisioning/dashboards/dashboards.yml,dashboards/canary-current.json}`, `docs/retros/2026-05-21-observability-stack-phase3-entry.md`.
- Edits: `infra/docker-compose.yml` (5 services解注释 + loopback port mapping), `infra/README.md` (Phase 3 entry 服务表), `apps/strategies_nautilus/runners/testnet_runner.py` (textfile writer 集成 + CLI flag), `docs/decisions/001-tech-stack.md` (§6 2026-05-21 修订).

On 2026-05-21, after extending `freqai_linear_v1` paper_simulated evidence through May:

- May 2024 Binance BTCUSDT 1m public klines imported: catalog now covers 2024-01-01..2024-05-31, 152 days, 218880 bars, no missing days.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_freqtrade.research.freqai_linear_signals ... --train-until 2024-01-05T23:59:00Z` -> generated 2107 historical signals, wrote 357 new May rows, skipped 1750 duplicates.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.paper_runner ... --signal-until-ns 1717199940000000000` -> `data/paper/20260521-021418Z-e535b581`, manifest sha256 `06d9300a3183a80cb8c3c7874034aad12985fee3c814dae48e2dd9881ab44095`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m apps.strategies_nautilus.runners.report_paper_bundle data/paper/20260521-021418Z-e535b581` -> review blockers none; promotion blockers none; recommendation `review_simulated_paper_evidence`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **448 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.

On 2026-05-21, after recording the clean 6 h live-telemetry canary and fixing final manifest open-state counters:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **448 passed**.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `tests/strategies_nautilus/test_testnet_sidecars.py::test_long_run_invokes_sidecar_writer_with_recording` now covers the live close-order timing issue: the monitor sample can still say `open_orders=1` / `open_positions=1`, but after sidecar write the manifest records `open_orders=0`, `open_positions=0`, and `open_state_source=live_sidecars` when the sidecar parquet files show filled orders and a flat position.
- New retro: `docs/retros/2026-05-20-phase-3f-testnet-canary-6h-live-telemetry.md`.

On 2026-05-20, after wiring `ws_connected` / `ws_reconnect_count` through the kernel engines:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **447 passed** (440 prior + 7 new `tests/strategies_nautilus/test_live_telemetry.py` cases: ws_connected true when both kernel engines connected; false when data_engine disconnected; false when exec_engine disconnected; ws_reconnect_count increments on False→True edge across both engines; no increment while staying connected; reader keeps prev value when kernel read raises; ws_connected falls back to prev when node has no kernel — preserves backwards compatibility for the existing `_FakeNode` tests).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- `apps/strategies_nautilus/runners/live_telemetry.py` gains `_ws_connected_prev` + `_ws_reconnect_count` private state and a `_read_ws_connected(node)` helper that reads `node.kernel.data_engine.check_connected() and node.kernel.exec_engine.check_connected()`, increments `_ws_reconnect_count` on the False→True edge, and stores the prev for next call.
- No changes to `testnet_runner.py`, `first_testnet_canary.py`, the operator launcher, or any sidecar/manifest schema — the bind_node contract is unchanged.

On 2026-05-20, after landing the live telemetry reader:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **440 passed** (420 prior + 20 new `tests/strategies_nautilus/test_live_telemetry.py` cases: `SignalStorePollingSource.last_popped_ns` starts None and tracks max popped ts then keeps the last value on empty pops; `LiveTelemetryReader` returns safe defaults when unbound; reads account total from `node.portfolio.equity`; falls back to `starting_balance` on empty portfolio; counts `orders_open` / `positions_open`; reads `last_bar_ns` from cache and returns None on cache errors; reads `last_signal_ns` from polling source; UTC day anchor returns 0 on first call then diff same day then resets on new UTC day; catches node-side exceptions; `bind_node` is idempotent; `build_signal_source` honours injected clock and explicit cursor; `build_register_strategies` uses supplied source or builds its own; `build_live_telemetry_reader` plumbs spec fields; `run_long_running_testnet` calls `reader.bind_node(node)` exactly once post-build).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- New module `apps/strategies_nautilus/runners/live_telemetry.py`; extended `apps/strategies_nautilus/baseline_nautilus_strategy.py` `SignalStorePollingSource` with `last_popped_ns`; extended `apps/strategies_nautilus/runners/first_testnet_canary.py` with `build_signal_source` + `build_live_telemetry_reader` and made `build_register_strategies` accept a pre-built `signal_source`; runner gained a duck-typed `reader.bind_node(node)` call after `node.build()`.
- Operator launcher (`infra/launchers/first-testnet-canary.py`, gitignored) updated to share one `SignalStorePollingSource` between the strategy and the live reader.

On 2026-05-20, after the second 6 h testnet canary (parquet-backed) completed on commit `c2a4186`:

- Bundle `data/testnet/20260519-120037Z-f1b06fd3/run_manifest.json`: `shutdown_reason=max_duration`, `elapsed_seconds=21605.389287`, `git_dirty=false`, `git_commit=c2a4186363094ac4a6f7db59fdad857e68dd5668`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `write_live_sidecars=true`, `open_orders=0`, `open_positions=0`, `daily_pnl=0`, `exchange_error_count=0`, `ws_reconnect_count=0`, `ws_connected=true`, `auto_flatten_trigger=null`, `emergency_flatten_success=null`, `credentials_key_prefix=yKtnt9cb`, full credentials never on disk.
- `runtime.sidecar`: `success=true`, `error=null`, `result.{orders_count=2, fills_count=2, positions_count=1, account_rows=451, lineage_rows=3}`; the five parquet files exist under the bundle root with sizes 22529 / 16889 / 17357 / 11920 / 7078 bytes.
- `logs/runtime.log`: 6 lifecycle rows — `credentials_loaded` 12:00:37.171Z → `node_built` 12:00:37.193Z → `strategies_registered(strategies=1, actors=0)` 12:00:37.200Z → `node_run_invoked(max=21600)` 12:00:37.201Z → `sidecar_write(success=true)` 18:00:42.550Z → `shutdown(stop_reason=max_duration)` 18:00:42.560Z. Sidecar write to shutdown latency 10 ms (writer-then-dispose ordering preserved).
- `logs/heartbeat.jsonl`: 720 rows; first 12:00:37.200Z, last 18:00:12.211Z; every row carries `ws_connected=true`, `exchange_error_count=0`, `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`, `account_total_usdt=10000.0`, `daily_pnl=0.0`.
- `logs/alerts.log` **does not exist** — authoritative record that none of the 9 ADR-008 §5.4 alert kinds fired.
- `/tmp/phase3f-canary/runner.stdout.log` (432 lines, kept out-of-bundle): `Account BINANCE-SPOT-master registered in cache` T+0.405 s; `Reconciliation for BINANCE succeeded` T+0.688 s; `BaselineNautilusStrategy: RUNNING` T+0.689 s; `Subscribed BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL bars` T+0.889 s. `grep -c ERROR` = 0. `grep -c WARN` = 10 — seven hourly `BinanceSpotInstrumentProvider: zero fees` informationals, two `RiskEngine: Cannot check MARKET order risk: no prices for BTCUSDT` on entry/exit, one `BinanceUserDataWebSocketClient: eventStreamTerminated` 0.3 s pre-shutdown. None fall into the §5.4 catalog. stderr file 0 bytes. All 8 engines DISPOSED between 18:00:42.551Z and 18:00:42.561Z.
- Live order flow: `BUY MARKET 0.001 BTCUSDT.BINANCE` filled 12:04:00.480Z (`venue_order_id=5112724`, `trade_id=1713055`, `avg_px=76777.55 USDT`, `client_order_id=O-20260519-120400-001-000-1`, tag `signal_id:freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779192191762184234:buy:b9b75c9cde48`); scheduled close `SELL MARKET 0.001 BTCUSDT.BINANCE` filled 18:00:37.244Z (`venue_order_id=5224656`, `trade_id=1750207`, `avg_px=76852.51 USDT`, `reduce_only=True`, no signal tag). `PositionClosed` `realized_pnl=+0.07496 USDT`, `realized_return=+0.00098 (+0.098 %)`, `commissions=[0 BTC, 0 USDT]`, `duration_ns=21396764000000`.
- Sidecar internal consistency: `orders.parquet`/`fills.parquet`/`positions.parquet`/`signal_lineage.parquet` row counts agree with `runtime.sidecar.result`. `signal_lineage.parquet` carries 3 rows (all `decision=target_long`); only the first carries `order_ids` / `fill_ids` / `position_id` because signals 2 and 3 were `already_target_long` no-ops. `signal_id` round-trips through the entry order's `tags`, the entry fill's `signal_id` column, and `signal_lineage.signal_id` / `positions.signal_ids`. `account_balances.parquet` has 447 unique currencies + 4 duplicates (BTC×3, USDT×3 — the two changed currencies' pre/mid/post-trade `AccountState` snapshots).
- External `infra/watchdog/watchdog.py` loop (`/tmp/phase3f-canary/watchdog.loop.log`, filtered by `active_run_id=20260519-120037Z-f1b06fd3`): 1560 ticks for this run — 716 `status=healthy` ticks during the 6 h window, 844 `status=run_completed` ticks after shutdown, 0 `flatten_invoked=true` ticks, 1560 / 1560 `exit_code=0`. Final `infra/watchdog/state.json` records `status=run_completed`, `exit_code=0`, `flatten_invoked=false`, `last_heartbeat_at=2026-05-19T18:00:12.211Z`. The post-completion fix `8e5fada` behaved as designed; the 19 historical `flatten_invoked=true` rows in the same loop file belong to the prior `e653c3e5` canary and are documented in its retro.
- Retro: `docs/retros/2026-05-19-phase-3f-testnet-canary-6h-sidecar-bundle.md`.

On 2026-05-19, after landing the live testnet sidecar writer:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **419 passed** (410 prior + 9 new `tests/strategies_nautilus/test_testnet_sidecars.py` cases: `LongRunningTestnetSettings.write_live_sidecars` default-false and strategy-execution prerequisite; `run_long_running_testnet` rejects flag-without-recording and recording-without-flag with `StartupValidationError`; happy path calls injected writer with `trader`/`venue_name`/`lineage`/`bundle_root`/`report_ts_event_ns` and populates `result.sidecar_write_result` + `runtime["sidecar"]` + manifest + runtime.log `sidecar_write` event + `to_dict()` payload; writer exception path records `runtime["sidecar"]["error"]` while keeping `exit_code=0`; flag-off path never invokes the writer; `write_live_sidecars` direct test materializes all five parquet files of the right schema and stamps account rows with the supplied `report_ts_event_ns`; `build_sidecar_recording` returns a recording whose `lineage` is the same list object passed in).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- New module `apps/strategies_nautilus/runners/sidecar_writer.py` reuses `backtest_runner._prepare_reports` / `_write_parquet` / `validate_sidecar_bundle`; no duplication of `_SIDECAR_SCHEMAS`.
- `testnet_runner.py` gains `LongRunningTestnetSettings.write_live_sidecars`, `LongRunningTestnetResult.sidecar_write_result` + `sidecar_error`, `--write-live-sidecars` CLI flag, and the `sidecar_recording` / `live_sidecar_writer` injection knobs on `run_long_running_testnet` / `main`.
- `first_testnet_canary.build_sidecar_recording` exposes a one-liner for the operator launcher to share the same `lineage` list between `build_register_strategies` and the runner.
- `docs/runbook-first-testnet-canary.md` updated: launcher template adds `--write-live-sidecars`, `build_sidecar_recording`, and `sidecar_recording=` plumbing; §6 / §8 spell out the post-shutdown parquet expectations; §9 requires sidecar/manifest cross-check.

On 2026-05-19, after adding the wall-clock SignalStore restamp helper:

- `uv run pytest -q` → **410 passed** (404 prior + 6 new tests for `wall_clock_signal_replay.py`: restamp selection/cadence, metadata lineage, duplicate/replay skip, dry-run no-write, CLI dry-run summary, and no network/trading API token checks).
- `uv run pytest tests/strategies_freqtrade/test_freqai_linear_signals.py tests/strategies_freqtrade/test_wall_clock_signal_replay.py tests/strategies_nautilus/test_signal_source.py -q` → 39 passed.
- `uv run ruff check apps tests docs infra` → clean.
- `docs/runbook-first-testnet-canary.md` §1.5 now includes the dry-run and write commands for generating future-time `freqai_linear_v1` rows before starting the canary.

On 2026-05-19, after the first 30-min testnet canary smoke completed on commit `13b12ca`:

- Bundle `data/testnet/20260519-023115Z-e6aeb688/run_manifest.json`: `shutdown_reason=max_duration`, `elapsed_seconds=1805.210493`, `git_dirty=false`, `git_commit=13b12ca96e66d1bfe1587bc6115607b48e583186`, `strategies_registered=1`, `actors_registered=0`, `enable_strategy_execution=true`, `open_orders=0`, `open_positions=0`, `daily_pnl=0`, `exchange_error_count=0`, `ws_reconnect_count=0`, `ws_connected=true`, `auto_flatten_trigger=null`, `emergency_flatten_success=null`.
- `logs/runtime.log`: 5 lifecycle rows — `credentials_loaded` 02:31:15.086Z → `node_built` 02:31:15.131Z → `strategies_registered(strategies=1, actors=0)` 02:31:15.137Z → `node_run_invoked(max=1800)` 02:31:15.138Z → `shutdown(stop_reason=max_duration)` 03:01:20.297Z. Build-to-register latency 6 ms; register-to-run 1 ms; run-to-shutdown 1805.16 s.
- `logs/heartbeat.jsonl`: 60 rows; first 02:31:15.138Z, last 03:00:45.585Z; every row carries `ws_connected=true`, `exchange_error_count=0`, `ws_reconnect_count=0`, `account_total_usdt=10000.0`, `daily_pnl=0.0`, `open_orders=0`, `open_positions=0`.
- `logs/alerts.log` **does not exist** — none of the 9 ADR-008 §5.4 alert kinds fired (watchdog `heartbeat_lost` is n/a because the external watchdog was not started for this 30 min smoke).
- No sidecars in bundle — `orders.parquet` / `fills.parquet` / `positions.parquet` / `account_balances.parquet` / `signal_lineage.parquet` are not written because there was 0 order flow.
- `/tmp/phase3f-canary/runner.stdout.log` (349 lines, kept out-of-bundle): `Account BINANCE-SPOT-master registered in cache` at T+0.295s; `Reconciliation for BINANCE succeeded` at T+0.579s; `BaselineNautilusStrategy: RUNNING` + `Subscribed BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL bars` at T+0.581-0.733s; `Connected to wss://stream.testnet.binance.vision` at T+0.763s. `grep -c ERROR` = 0. `grep -c WARN` = 2 (both ADR-008 §5.4 catalog-external informationals identical to Phase 3f).
- `/tmp/phase3f-canary/runner.stderr.log` = 22 bytes, only `nohup: ignoring input`.
- All engines `DISPOSED` cleanly at 03:01:20.296Z–.297Z, including `BaselineNautilusStrategy` — the first evidence that the strategy's `on_stop` handles a flat-portfolio `close_all_positions` call without exception.
- SignalStore snapshot at retro time: `rows_total=1750` for `(freqai_linear_v1, linear-mom-train20240105)`; `rows_last_24h=0`; `latest_ts_event_ns=1714513500000000000` (2024-04-30T23:45:00Z). The session window contained no matching rows by design.
- Retro: `docs/retros/2026-05-19-phase-3f-testnet-canary-session.md`.

On 2026-05-19, after wiring the ADR-008 §6.6 first-canary execution path:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **404 passed** (387 prior + 9 new `test_signal_source.py` for `StaticSignalSource` / `SignalStorePollingSource` + 6 new `test_testnet_runner_startup.py` cases for `enable_strategy_execution` default-rejects / requires-callback / rejects-zero / records-counts / settings default / CLI flag flow + 8 new `test_first_testnet_canary.py` for `FirstCanaryStrategySpec` validation, authorization construction, `build_register_strategies` clock/store/sink injection, explicit and default-clock cursor wiring, and default `node.trader.add_strategy` sink).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- The legacy `paper_runner.py` / `backtest_runner.py` / `wall_clock_paper_runner.py` paths continue to pass with **zero changes** — the `BaselineNautilusStrategyParams.signals` list-style constructor is preserved, defaulting through `StaticSignalSource`.

On 2026-05-19, after generating the first `paper_simulated → testnet_canary` promote retro from commit `44851f3`:

- Output: `docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md` (renders the seven ADR-007 §2.6 sections plus the new `## 3a. Phase 3 evidence paths`).
- CLI: `uv run python -m apps.strategies_nautilus.runners.promotion_review data/paper/20260517-053502Z-37b99b3f --current-stage paper_simulated --target-stage testnet_canary --current-no-dry-run --current-position-pct-multiplier 0.2 --current-min-confidence-override none --target-no-dry-run --target-position-pct-multiplier 0.1 --target-min-confidence-override none --decision promote --operator nishiki --rationale "…" --paper-simulated-retro-path docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md --testnet-runbook-signoff-path docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md --output-markdown docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.
- Stdout summary: `decision: promote (allowed=True)`, `bundle_policy_matches_current: True`, `review_blockers: none`, `promotion_gate_blockers: none`, `decision_reasons: promote_gates_passed`, `policy_diff: {"position_pct_multiplier": {"current": 0.2, "target": 0.1}}`. Exit code 0.
- Bundle fingerprint replayed in §3 of the retro: `run_id=20260517-053502Z-37b99b3f`, `manifest_sha256=fa344a5534c220a0a0547f58f069394921399fd21def505faaf3c978d04e6efb`, `git_commit=a9a35d46251b5452e83e6ed9a175f143a63b9bc0` (v9 baseline), `git_dirty=False`, runtime `mode=paper / data_mode=catalog_polling / order_mode=simulated`.
- Execution outcome on the v9 evidence: 545 orders / 545 fills (1:1, every row carries `signal_id`), 273 positions, PnL +5.0076 USDT, max_drawdown_pct ≈ -1.0035e-05, max_drawdown_abs ≈ -1.0035 USDT, kill_switch_fired=False, missing_metrics=none.

On 2026-05-19, after the ADR-008 §8 promotion-review patch landed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → **381 passed** (375 prior + 6 new tests for the `paper_simulated → testnet_canary` gate: happy-path with both evidence files, missing paths blocked, retro file not-found blocked, signoff missing `ADR-008` / `§6.6` markers blocked, CLI end-to-end with Markdown `## 3a. Phase 3 evidence paths` written, and `phase_3_not_ready` still hard-blocks `live_canary` promotion).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` → clean.
- `apps/strategies_nautilus/runners/promotion_review.py`: `PHASE_2_STAGE_LIMIT = STAGE_TESTNET_CANARY`; `PromotionReview` carries `paper_simulated_retro_path` and `testnet_runbook_signoff_path`; new `_testnet_canary_promote_blockers` only fires on the exact `paper_simulated → testnet_canary` promote transition; substring sanity checks (`paper_simulated` + source name; `ADR-008` + `§6.6`) prevent operators from passing any unrelated file. `PolicyFields` schema and existing `paper_shadow → paper_simulated` evidence/dry-run gates are unchanged.

On 2026-05-19, after the Phase 3f testnet stability soak completed on commit `8f0e041`:

- Bundle `data/testnet/20260518-150212Z-997bf080/run_manifest.json`: `shutdown_reason=max_duration`, `elapsed_seconds=21605.192657`, `git_dirty=false`, `restart_sequence=0`, `restart_drift_detected=false`, `exchange_error_count=0`, `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`, `daily_pnl=0.0`, `account_total_usdt=10000.0`, `credentials_key_prefix=yKtnt9cb`, full credentials never on disk.
- `logs/heartbeat.jsonl`: 720 rows at 30 s cadence; first `2026-05-18T15:02:12.858Z`, last `2026-05-18T21:01:48.192Z`; every row carries `ws_connected=true`, `exchange_error_count=0`, `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`.
- `logs/runtime.log`: four lifecycle rows — `credentials_loaded` 15:02:12.825Z → `node_built` 15:02:12.858Z → `node_run_invoked` 15:02:12.859Z → `shutdown` 21:02:18.018Z (`stop_reason=max_duration`, `auto_flatten_trigger=null`, `emergency_flatten_success=null`).
- `logs/alerts.log` **does not exist** — authoritative record that none of the 9 ADR-008 §5.4 alert kinds fired (`kill_switch_fired`, `restart_drift_detected`, `exchange_error_burst`, `data_gap_exceeded_tolerance`, `signal_lag_exceeded_threshold`, `ws_disconnected`, `heartbeat_lost`, `emergency_flatten_started`, `emergency_flatten_completed`).
- Nautilus stdout (`/tmp/phase3f/runner.stdout.log`, retained out-of-bundle): `Account BINANCE-SPOT-master registered in cache` at T+0.348 s, `Reconciliation for BINANCE succeeded` at T+0.694 s, `grep -c ERROR` = 0; stderr file 0 bytes. Eight `BinanceSpotInstrumentProvider: zero fees` informational warns (one + hourly) plus one `BinanceUserDataWebSocketClient: eventStreamTerminated, resubscribing...` 0.114 s before scheduled shutdown — neither fall into the §5.4 catalog, and engines (`DataClient-BINANCE`, `DataEngine`, `RiskEngine`, `ExecClient-BINANCE`, `ExecEngine`, `TESTNET_TRADER-001`, `TradingNode`) all DISPOSED at 21:02:18.017–.018Z.
- External `infra/watchdog/watchdog.py` loop (`/tmp/phase3f/watchdog.loop.log`): 714 `status=healthy` ticks, 0 `flatten_invoked=true` ticks; final `infra/watchdog/state.json` records `status=healthy`, `exit_code=0`, `flatten_invoked=false`, `heartbeat_age_seconds=0.235`, `alert_path=null`.
- Retro: `docs/retros/2026-05-18-phase-3f-testnet-long-run-6h.md`. The retro explicitly states it is a stability soak, not a `SourcePolicy` decision; the `phase_3_not_ready` gate stays closed.

On 2026-05-18, after the Phase 3e alert outlet implementation:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 375 passed (3 new advisory-alert path tests + 1 §5.4 source-wiring coverage assertion on top of Phase 3d coverage).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `tests/strategies_nautilus/test_testnet_runner_startup.py::test_adr_008_5_4_alert_kinds_have_runner_or_watchdog_wiring` grep-asserts each of the 9 §5.4 alert msgs is referenced in its expected source: `testnet_runner.py` for the 6 monitor-loop kinds (`kill_switch_fired`, `restart_drift_detected`, `exchange_error_burst`, `data_gap_exceeded_tolerance`, `signal_lag_exceeded_threshold`, `ws_disconnected`); `watchdog.py` for `heartbeat_lost`; `emergency_flatten.py` for `emergency_flatten_started` / `emergency_flatten_completed`. If a msg ever loses its wiring this test fails.
- `tests/strategies_nautilus/test_testnet_runner_startup.py::test_long_run_emits_ws_disconnected_on_transition` asserts the advisory `ws_disconnected` (warning) fires once per `True→False` WS transition, re-arms after reconnect, and lets the runner still exit 0 at `max_duration`. Two transitions in the sequence produce exactly two alerts.
- `tests/strategies_nautilus/test_testnet_runner_startup.py::test_long_run_emits_data_gap_exceeded_tolerance` asserts the advisory `data_gap_exceeded_tolerance` (error) fires exactly once per gap incident even though the stale sample is read for hundreds of polling ticks; runner still exits 0 at `max_duration` and no auto-flatten runs.
- `tests/strategies_nautilus/test_testnet_runner_startup.py::test_long_run_emits_signal_lag_exceeded_threshold` asserts the same dedup pattern for the advisory `signal_lag_exceeded_threshold` (warning) and confirms the new `last_signal_ns` field is what drives it.
- `tests/strategies_nautilus/test_testnet_runner_startup.py` now covers restart reconciliation: clean restart records `previous_manifest_sha256`, `previous_processed_until_ns`, `restart_sequence`, `restart_reason`, and zero drift; exchange-side drift exits 3, writes `restart_drift_detected`, and refuses to build the node; local sidecar open orders / positions compare equal against exchange REST snapshots after quantity normalization.
- `tests/strategies_nautilus/test_watchdog.py` covers the external watchdog: healthy heartbeat writes state without flattening; stale/missing heartbeat writes `heartbeat_lost`, invokes the injected flatten command, maps success to exit 4 and failure to exit 5, and the watchdog source contains no `BINANCE_TESTNET_*` credential reads.
- `tests/strategies_nautilus/test_testnet_runner_startup.py` now covers the `--long-run` shell: it writes `data/testnet/<run_id>/run_manifest.json`, `logs/runtime.log`, `logs/heartbeat.jsonl`, and `logs/alerts.log`; it redacts full credentials; it exits 4 when automatic emergency flatten succeeds and 5 when flatten reports residual risk; and it keeps the existing no-strategies/no-actors connection boundary.
- `apps/strategies_nautilus/runners/testnet_runner.py --long-run` tracks `runtime.daily_pnl`, `runtime.exchange_error_count`, and `runtime.ws_reconnect_count`, writes `kill_switch_fired` / `exchange_error_burst` / `ws_reconnect_burst` alerts, stops the node, and calls the same `run_emergency_flatten` path used by the operator CLI. The default emergency path is still `--kind testnet` only via the Binance Spot testnet `ExchangeClient`; paper/live require injection.
- `tests/strategies_nautilus/test_binance_testnet_exchange.py` covers: Ed25519-only credential validation; signed REST query construction with key header and no secret in URLs; open-order mapping; terminal vs non-terminal cancel responses; Spot inventory inference from `/api/v3/exchangeInfo` + `/api/v3/account`; market SELL close without unsupported Spot `reduceOnly`; rejection of Spot short-close attempts; order snapshot avg price mapping; account snapshot redaction; and emergency-flatten default factory dispatch for `--kind testnet`.
- `apps/strategies_nautilus/runners/emergency_flatten.py` remains exchange-agnostic orchestration; `apps/strategies_nautilus/runners/binance_testnet_exchange.py` is the only new network-capable driver and is restricted to Binance Spot testnet + Ed25519 credentials.
- `tests/strategies_nautilus/test_emergency_flatten.py` (21 cases) covers: settings validation (kind / run_id / operator / reason / instruments), full happy-path flatten with order ID and avg price recorded, `--cancel-only` short-circuit, cancel rejection + cancel exception → `residual_orders`, fill timeout + submit exception + REJECTED close → `residual_positions` with typed `reason`, FLAT position skip, no-orders-no-positions success, SIGTERM→SIGKILL bracket via injected signaller, SIGTERM failure short-circuits SIGKILL, `alerts.log` started/completed lines with severity `critical`, alerts.log append (never truncate) on pre-existing file, audit JSON contains every required ADR-008 §5.1 field plus the orchestration extensions (`cancel_only`, `elapsed_seconds`, `runner_sigterm_sent`, `runner_sigkill_sent`), CLI exit code 0 on success and 1 on residual.
- First live Phase 3b probe (`d9e542b`): bundle `data/testnet/20260518-122839Z-24bf3db2`, `elapsed_seconds=35.285`, `stop_reason=max_duration`, `error=null`, `node_built=true`, `node_run_invoked=true`, `strategies_registered=0`, `actors_registered=0`, `credentials_key_prefix=yKtnt9cb` (8 chars), zero `ERROR` lines in Nautilus log. ExecClient `session.logon` succeeded under Ed25519, account `BINANCE-SPOT-master` registered with full testnet faucet balances (10000 USDT / 1 BTC / 1 ETH / etc.), ExecutionMassStatus reconciliation succeeded at T+0.962s, timer fired `node.stop()` at T+30s, all engines DISPOSED cleanly. The probe artifacts contain only the 8-char key prefix (`yKtnt9cb`) — full API key, PEM private key, and historical HMAC secret are never written to `data/testnet/`. Retro: `docs/retros/2026-05-18-phase-3b-testnet-connect-probe.md`.
- `apps/strategies_nautilus/runners/testnet_runner.py` source contains no `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BinanceEnvironment.MAINNET`, or `BinanceEnvironment.US` references (grep-asserted in tests). Only `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET` are read, and only via the explicit `env` mapping or `os.environ` fallback.
- `run_connection_probe` writes `data/testnet/<run_id>/logs/runtime.log` as JSON Lines (`credentials_loaded` → `node_built` → `node_run_invoked` → `shutdown`) and `data/testnet/<run_id>/connection_probe.json` summary. Both files contain `credentials_key_prefix` (8 chars only) and never the full key or secret (asserted by tests).
- `_FakeNode`-driven unit tests assert: build/run/dispose called in order; `BinanceLiveDataClientFactory` + `BinanceLiveExecClientFactory` registered exactly once; trader has zero strategies and zero actors; in-memory `TradingNodeConfig` data/exec clients receive `api_key` + `api_secret` from env but environment stays `BinanceEnvironment.TESTNET` and account stays `BinanceAccountType.SPOT`; missing retro fails before any bundle directory is created; pre-existing run_id directory raises `FileExistsError`; a probe with a pre-registered strategy refuses to call `node.run()` and records the rejection in `connection_probe.json` (`stop_reason="exception"`, `node_run_invoked=false`).
- BTCUSDT 1m catalog spans 2024-01-01..2024-04-30 (174240 bars); `data/bridge/signals.db` sha256 `8c2176c2a67d6d9fdb2fc70ec6c0cf72ea14c04dbf272baf1519a7c49935ca4e`; `freqai_linear_v1` row count 1750 (308 Jan + 287 Feb + 621 Mar + 534 Apr); `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) unchanged across v3/v6/v7/v8/v9/v10.
- `apps/strategies_nautilus/runners/promotion_review.py` integrates with `report_paper_bundle.load_paper_bundle_report` and never mutates `SourcePolicy`, starts a runtime, or talks to an exchange.
- Six `docs/retros/` entries record the lifecycle of `freqai_linear_v1 / linear-mom-train20240105`:
  - 7-day shadow `hold` (sample size half met only): `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow.md`, bundle `data/paper/20260517-050320Z-f5e13cda` manifest `88164be1…`.
  - 31-day shadow `hold` (both halves met but in-sample): `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-31d.md`, bundle `data/paper/20260517-051417Z-9afb2cd1` manifest `218e3b0c…`.
  - 60-day shadow `hold` with first held-out month: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-shadow-60d-holdout.md`, bundle `data/paper/20260517-052512Z-36feef84` manifest `9d813db2…`.
  - First **`promote`** retro (paper_shadow → paper_simulated): `docs/retros/2026-05-17-freqai-linear-v1-promote-paper-simulated.md`. Evidence: same 60-day shadow bundle. `decision_allowed=True`, `policy_diff={"dry_run": {"current": true, "target": false}}`, no review or promotion blockers.
  - First `paper_simulated` `hold`: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated.md`, bundle `data/paper/20260517-053502Z-37b99b3f` manifest `fa344a55…`.
  - 121-day `paper_simulated` `hold`: `docs/retros/2026-05-17-freqai-linear-v1-hold-paper-simulated-121d.md`, bundle `data/paper/20260517-090217Z-c1214e6d` manifest `966fc8ac…`.
- v9 simulated bundle sanity: 86400 iterations, 595 signals, **545 orders / 545 fills (1:1, every row carrying `signal_id`)**, 273 positions, 86400 account balances, lineage `target_long×436 + target_short×159` with reasons split as 273 first-fill openings + 299 already_target_long + 23 already_target_short. Runtime: heartbeat=86400, poll=86400, processed_until_ns=1709251140000000000, restart_sequence=0, data_gap_count=0; risk: kill_switch=0, signal_lag=0, unauthorized=0, expired=0; manifest `git_dirty=false`. Applied policy: `dry_run=False`, multiplier 0.2.
- v9 return-side metrics: PnL +5.0076 USDT (+0.005% on 100000 USDT over 60 days), Win Rate 0.5551 (55.5%), expectancy +0.01858 USDT/trade, max drawdown -1.0035e-05 (-0.001003%) / -$1.0035. Treated as monitoring evidence, not alpha.
- v10 simulated bundle sanity: 174240 iterations, 1750 signals, **1649 orders / 1649 fills (1:1, every row carrying `signal_id`)**, 825 positions, 174240 account balances, lineage `target_long×1265 + target_short×485` with reasons split as 825 first-position actions + 852 already_target_long + 73 already_target_short. Runtime: heartbeat=174240, poll=174240, processed_until_ns=1714521540000000000, restart_sequence=0, data_gap_count=0; risk: kill_switch=0, signal_lag=0, unauthorized=0, expired=0; manifest `git_dirty=false`. Applied policy: `dry_run=False`, multiplier 0.2.
- v10 return-side metrics: PnL +4.4126 USDT (+0.0044% on 100000 USDT over 121 days), Win Rate 0.5291 (52.9%), expectancy +0.00524 USDT/trade, max drawdown -3.8779e-05 (-0.003878%) / -$3.8782. March/April extension weakens the case: April closed-position PnL is -2.1081 USDT.
- `tests/strategies_nautilus/test_promotion_review.py` (18 cases) and the rest of the paper / report / runner suites continue to enforce dry-run vs simulated invariants, lineage `signal_id` carry-through, lag / expiry / unauthorized / kill-switch rejection, incremental cursor metadata, restart cursor handling, market-data gap blockers, and source-level guards against reading secret env vars or submitting live orders.
- `tests/strategies_nautilus/test_wall_clock_paper_runner.py` (13 cases) enforces the ADR-008 §7.2 invariants for Phase 3a: no `BINANCE_*` env reads in either `paper_runner.py` or `wall_clock_bar_feed.py`; closed-kline-only consumption with `ts_event_ns` dedup; non-kline payload rejection; manifest carry-through of `ws_reconnect_count` / `duplicate_bars_dropped` / `shutdown_reason`; SignalStore re-poll incremental cursor; SIGTERM and `max_duration` stop paths.
- `tests/strategies_nautilus/test_testnet_runner_startup.py` (18 cases) enforces the Phase 3b startup boundary and the new connection probe: `--allow-real-credentials` required, credential lengths checked, dirty git rejected, paper_simulated/testnet retro evidence required, multiplier capped at 0.2, non-Binance / non-Spot configs rejected, Binance Spot TESTNET adapter config built without embedding credentials in the audit/validation path, JSON output redacts full key/secret, the runner source contains no live-mainnet credential references; for `--connect-probe`: bundle dir + runtime log + summary JSON are written without leaking key/secret, `BinanceLive*Factory` factories are registered, in-memory `TradingNodeConfig` carries credentials but the testnet environment is preserved, validation failure happens before bundle dir creation, pre-existing run_id raises, a node with a registered strategy is refused, and the CLI dispatches correctly under `--connect-probe`.
- Phase 3a real-WS smoke (5 min, `wss://data-stream.binance.vision:9443`, BTCUSDT 1m): bundle `data/paper/20260517-075403Z-b76dcdb1`, manifest sha256 `f80bd450fa6e47287316aba90498244fe467f341a3af54bb5b570e4babf3f56d`. `bar_count=5`, `heartbeat_count=5`, `data_gap_count=0`, `ws_reconnect_count=0`, `duplicate_bars_dropped=0`, `shutdown_reason=max_duration`, `credentials_loaded=false`. Manifest carries `git_dirty=true` because it ran before this commit; future wall-clock bundles will land with `git_dirty=false`. Retro: `docs/retros/2026-05-17-phase-3a-wall-clock-smoke.md`.
- Phase 3a 24h wall-clock soak accepted: bundle `data/paper/20260517-094345Z-ad69bd68`, manifest sha256 `98984bd15a37600b695716d072eb0688207d0154397e80d88a43ea7663aaca44`, `git_commit=d122ffda1011bdd5af9f9ae0db48b7bcd3d743cb`, `git_dirty=false`, `started_at=2026-05-17T09:43:45.246Z`, `finished_at=2026-05-18T09:43:45.429Z`, `elapsed_seconds=86400.183665`. Runtime: 1440 bars, 1440 polls, 24 heartbeats, `data_gap_count=0`, `ws_reconnect_count=0`, `duplicate_bars_dropped=0`, `shutdown_reason=max_duration`, `credentials_loaded=false`. Retro: `docs/retros/2026-05-18-phase-3a-wall-clock-24h-soak.md`.
- `docs/progress/phase-2-signal-source-baselines.md` v9 records the promote event, the v9 simulated fingerprint diff vs v8, the strategy's already-on-side handling, and the Phase 2 ceiling at paper_simulated; v1..v8 remain archived.
- ADR-008 (`docs/decisions/008-phase3-risk-runbook.md`) is accepted as the Phase 3 specification — it defines the testnet runtime, wall-clock paper precondition, real-credentials handling (no creds in repo, double-signed `--allow-real-credentials` flag, key-prefix-only audit), emergency flatten (7-step cancel-then-flatten with `emergency_flatten.json` audit), kill-switch (5% daily loss → auto-flatten), restart recovery (mandatory 3-way reconciliation with the exchange), the minimal alert set (`logs/alerts.log` + exit codes 0..5), and the testnet → live additional gates. ADR-007 §4 has been renumbered: ADR-008 (this), ADR-009 (LLM, was ADR-008), ADR-010 (Redis, was ADR-009). `promotion_review`'s `phase_3_not_ready` gate is unchanged and stays closed until ADR-008 §6.1–§6.5 sub-phases are built and tested.
- `docs/agent-reading-list.md` Phase 3 / testnet row now points at ADR-008 directly.

## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

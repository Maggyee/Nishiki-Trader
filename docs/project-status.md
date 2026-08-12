# Project Status

- **Status file**: Active
- **Last updated**: 2026-08-12 (Protocol v16 Treasury-yield volatility confirmation pre-registered; bodies unopened)
- **Current phase**: Phase 5 entry (read-only frontend + monitoring; live trading still blocked)
- **Current objective**: Phase 5 remains active and `stop_before_testnet_resume` remains in force. The original 16-candidate registry and Protocol v2-v5 research identities are frozen. Protocol v5 curve carry and BVOL relief are rejected and the 2026-08..12 blind remains sealed. The provider/timer review is complete: v5 and completed v2 timers are `inactive/disabled`, v5 collector status is `archived`, and a four-day post-window audit found zero new invocations. The retained v5 tree is 13 snapshots / 13 Parquets with zero conflicts; v2 `COMPLETE`, ledger, deployment identity and all recorded checksums remain unchanged. Dashboard renders the archive as a valid terminal state with no retry or operations issue. Independent Protocol v6 remains `blocked_provider_qualification` on the official 12-row grid, with historical development closed.
  The human-reviewed `freqai_linear_v1 / linear-mom-train20240105` decision is now `demote @ paper_simulated` under `SourcePolicy(dry_run=False, position_pct_multiplier=0.1, min_confidence_override=None)`. Its old testnet continuity evidence is archived and cannot authorize a restart. Phase 6 remains closed: ADR-013 is Draft, strict testnet continuity remains `current_qualified_streak_days=0/14`, no live-canary promotion review exists, the first-live-day runbook is Draft, and no live runner is authorized or wired.
  Research Protocol v7 is complete. VIX and OVX relief fail frozen gates; GVZ was retained as a provisional survivor after its official downtime sensitivity. Protocol v8 then independently confirmed the unchanged GVZ identity on 2023-2025: all 36 official archive checksums qualify, one REST-empty hour is classified as exchange unavailable with no synthetic bar, duplicate Nautilus replays match, and every fixed performance/evidence gate passes. GVZ is now `hold @ paper_shadow` under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`. Its first clean catalog-shadow bundle records 166/166 dry-run signals and zero orders/fills. Forward collection is active: Day 1 is qualified with fresh official GVZ, 167 contiguous closed BTCUSDT hourly bars, zero revisions/blockers, and 0 new forward signals; 38 pre-entry signals seed state but do not count. The weekday 02:30 UTC collector is installed in the `orca` crontab because this host has no user-systemd bus. `stop_before_testnet_resume` remains in force and the 2026-09..2027-01 future blind remains sealed.
  Protocol v9 then tested two pre-registered higher-order option-risk mechanisms. VIX9D-below-VIX and five-observation VVIX relief are both cost-positive and reproducible on 2020-2022, but both fail leave-best concentration; the curve rule also has only 12/36 positive months. Both are rejected, their 2023-2025 confirmation remains sealed, and neither affects the GVZ paper-shadow process.
  Protocol v10 opened the three pre-registered Coin Metrics responses once. Coverage passed, but none of 4,628 rows supplied status-time metadata, so v10 closed without factor values, signals, or PnL. Protocol v11 preserved the same rules and immutable bodies under a D+2 finalized-ledger reconstruction and completed duplicate 2020-2022 development replays. Hashrate recovery is cost-positive but fails breadth and leave-best concentration; BTC fee demand is negative after costs; stablecoin expansion is strongly positive but has only seven positions and is classified insufficient evidence. Zero candidates may open confirmation, and any future related study requires a new identity or genuinely forward immutable data.
  Protocol v12 now isolates the unchanged USDT+USDC 30-observation expansion rule as a `forward_data_candidate`. Day 0 pipeline qualification passed from clean pushed commit `70c53a2`: the 142-row stablecoin grid through 2026-08-10 and 167 closed BTC hours are complete with zero revisions/blockers. Because the latest factor predates the forward boundary, genuine evidence remains 0/180 days and 0/2 state changes. V12 creates no paper-shadow or promotion eligibility, and its recurring host schedule is not installed pending explicit operator approval.
  Protocol v13 completed three separate BTC network-mechanism development tests on a complete 1,157-day Coin Metrics grid with D+2 reconstruction semantics. Active-address expansion is cost-positive but fails monthly breadth and leave-best concentration; transfer-count expansion is negative; MVRV below one is cost-positive but has only seven positions and is classified insufficient evidence. All duplicate pairs reproduce and have no effective blockers or verified no-kline event hits. Zero candidates may open 2023-2025 confirmation. V13 does not change or schedule v12 and does not touch any trading path.
  Protocol v14 was pre-registered before opening a new Coin Metrics request, but the Community API returned HTTP 403 before metric rows because `CapRealUSD` is not publicly entitled. Community-scoped catalog metadata also excludes `CapRealUSD`, `NVTAdj`, and `SOPR`; catalog-all had described product coverage rather than free-plan availability. V14 is closed at `blocked_provider_qualification` with zero factor values, signals, or PnL opened. It cannot reopen or retune v13 and does not touch v12 or any trading path.
  Protocol v15 was pre-registered before opening one credential-free FRED CSV body, but its only GET timed out after 30 seconds before response headers or rows. It is closed at `blocked_provider_qualification`; no rate value, factor, signal, or PnL was received. An official U.S. Treasury annual-CSV recovery requires a separate frozen provider identity. Development and confirmation remain unopened; v12-v14 and all trading paths are unchanged.
  Protocol v16 completed development using 791 unfilled joint observations from eight official Treasury files. Real-yield relief and curve steepening are profitable but insufficient evidence. Treasury-yield volatility relief passed every development gate and its review is committed at `2e4edbf`. A separate confirmation contract now locks only that unchanged identity and the 2023-2025 nominal Treasury annual requests; bodies remain unopened until the contract is pushed. The final future blind stays sealed, v15 is not retried, and no trading path changes.
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
- `docs/progress/phase-2-research-protocol-v2.md` — independent-mechanism pre-registration, point-in-time contract, evidence partitions, and gates.
- `docs/progress/phase-2-research-protocol-v3.md` — macro/native mechanism pre-registration (hashrate, DXY, VIX) without reopening rejected families.
- `docs/progress/phase-2-research-protocol-v4.md` — separately identified FRED provider recovery for the two v3 macro routes blocked at Stooq.
- `docs/progress/phase-2-research-protocol-v5.md` — Binance-native BTC/ETH curve-carry and BVOL-relief pre-registration, immutable collection, dual-sleeve review, and future-blind gates.
- `docs/progress/phase-2-research-protocol-v6.md` — independent Binance-native
  availability discovery, book-depth mechanism review and one fixed pre-data
  identity; no archive body or PnL access yet.
- `docs/progress/phase-2-research-protocol-v7.md` — completed Cboe cross-asset
  volatility replication batch; all three candidates rejected and the future
  blind remains sealed.
- `docs/progress/phase-2-research-protocol-v9.md` — completed Cboe option-risk
  development batch; both candidates rejected and confirmation never opened.
- `docs/progress/phase-2-research-protocol-v10.md` — pre-registered
  crypto-native fundamental batch; v10 status-time route closed and v11
  completed development with zero confirmation-eligible candidates.
- `docs/progress/phase-2-research-protocol-v12.md` — stablecoin expansion
  forward-data contract; exact rule preserved and Day 0 pipeline qualified.
- `docs/progress/phase-2-research-protocol-v13.md` — completed BTC network
  mechanisms batch; zero candidates qualify to open confirmation.
- `docs/progress/phase-2-research-protocol-v14.md` — BTC valuation mechanisms
  blocked by Community entitlement before values; development remains unopened.
- `docs/progress/phase-2-research-protocol-v15.md` — U.S. rate mechanisms
  blocked by FRED read timeout before values; development remains unopened.
- `docs/progress/phase-2-research-protocol-v16.md` — Treasury-direct development
  complete; one candidate is eligible for independently frozen confirmation.
- `docs/progress/phase-3-testnet-canary-evidence.md` — archived Phase 3 testnet canary evidence ledger.
- `docs/progress/phase-3-testnet-continuity-plan.md` — archived 14-day testnet continuity procedure and review command.
- `docs/progress/phase-5-dashboard-history.md` — completed read-only dashboard, AgentAdvice input, passive Phase 6 gate, and dashboard hardening history.

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
- ADR-007 §2.6 promotion-review tooling is live: `apps/strategies_nautilus/runners/promotion_review.py` packages a paper or testnet bundle, a declared `current_policy`/`target_policy`, and an operator decision (`promote|hold|demote|disable`) into the seven §2.6 sections plus a `decision_allowed` gate that enforces the §2.5 stage table, the `paper_shadow → paper_simulated` evidence threshold, bundle/policy match, `git_dirty`, review blockers, and the Phase-2 stage cap. Testnet reviews resolve and hash the manifest-linked signed stage-policy artifact and fail closed if it is absent or inconsistent. Records land in `docs/retros/`.
- Catalog is now 31 days of BTCUSDT 1m (2024-01-01..2024-01-31, 44640 bars, 0 ts gaps). With `train_until=2024-01-05T23:59`, `freqai_linear_v1 / linear-mom-train20240105` now produces 308 deterministic out-of-sample shadow `SignalEvent v1` rows. `features_hash` and training metadata are unchanged from v3/v6, so the model fingerprint remains stable while the paper-shadow evidence base grows from 7 to 308.
- Catalog now extends to 60 days (2024-01-01..2024-02-29, 86400 bars, 0 ts gaps). February is the first fully held-out month for `freqai_linear_v1 / linear-mom-train20240105` and adds 287 `SignalEvent v1` rows on top of January's 308 (total 595). `model_version` / `features_hash` (`sha256:885207ac…`) / `train_rows` (7181) / `train_until` (2024-01-05T23:59) are unchanged across v3/v6/v7/v8; only the OOS region grows. Hold-out distributional comparison Jan vs Feb shows near-identical signal density (9.94 vs 9.90 per day), long-share (0.7305 vs 0.7352), and score / confidence quantiles — the model survives the one-month regime shift on signal generation.
- First `promote` retro in the project landed: `freqai_linear_v1 / linear-mom-train20240105` was deliberately moved from `paper_shadow` to `paper_simulated` via `promotion_review --decision promote`, authorizing `SourcePolicy(dry_run=False, position_pct_multiplier=0.2)`. The first paper_simulated bundle (v9, `data/paper/20260517-053502Z-37b99b3f`, manifest `fa344a55…`) produced 545 orders, 545 fills with every `signal_id` propagated, 273 positions, no kill-switch fires, no data gaps. Return-side metrics are now on record for the first time: PnL +5.0076 USDT (+0.005%), Win Rate 55.5%, expectancy +0.019 USDT/trade, max drawdown -0.001% / -$1.00 over 60 days. Source is now `hold @ paper_simulated`; further promotion to `testnet_canary` is hard-blocked by `phase_3_not_ready` and requires the Phase 3 risk/runbook ADR.
- Paper_simulated monitoring evidence now extends through 2024-05-31: v11 bundle `data/paper/20260521-021418Z-e535b581` (manifest `06d9300a…`) replays 152 days / 218880 BTCUSDT 1m bars with 2107 `freqai_linear_v1` historical signals, 1987 orders/fills, 994 positions, no data gaps, no kill-switch, and `git_dirty=false`. Return-side evidence remains tiny: PnL +4.8726 USDT (+0.004873%), Win Rate 53.6%, expectancy +0.00491 USDT/trade, max drawdown -0.003878% / -$3.88. April is negative and May is only mildly positive; this remains monitoring evidence, not alpha.
- Cost-aware research tooling is implemented: full-year range backfill, batched SignalStore export, cash/netting backtests, `alpha.review.v1`, `freqai_linear_walkforward_v1 / ridge-wf60d-cost30bp-v1`, and `rule_breakout_v1 / donchian20-10-atr14x0.25-15m`. The local BTCUSDT 1m catalog now covers all 2024 with 527040 rows, zero duplicates, and zero minute gaps; generated data remains gitignored.
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

All completed tournaments have empty rankings and the cumulative stop rule is
triggered for the original 16 families. Research Protocol v2 remains
data-blocked, although its fresh cloud coverage attempt completed at 7/7 paired
UTC days.
Research Protocol v3 is pre-registered for three independent macro/native
mechanisms. Hashrate's first real July schema/lineage snapshot is valid; DXY and
VIX are blocked at the frozen provider route because Stooq serves a JavaScript
verification page rather than CSV. Protocol v4 separately locked two new FRED
identities, but both direct July-only routes timed out from cloud and local
paths and wrote zero snapshots. Protocol v5's qualified Binance-only fast
tracks are now complete. Curve carry is rejected before signals/PnL because
both assets lack three official Spot execution days in the 2021 Aug-Dec fold.
BVOL completed 20 clean Nautilus runs and 10 reproducible pairs, but aggregate
base/stress PnL is -1.185170/-6.326371 USDT, only 3/5 folds and 13/25 months
pass, leave-best PnL is negative, and the ETH sleeve loses after costs. Both v5
candidates therefore resolve to `reject_v5_candidate`; no candidate advances
to the sealed future blind. The provider/timer review now resolves the durable
publication trigger as `stop_scheduled_collection`. Scheduled evidence through
data date 2026-07-21 retains 13 snapshots and 13 Parquets with zero conflicts;
the 2026-07-17 retry is the last complete batch, curves remained intermittent
or 404, and ETH BVOL repeatedly failed the unchanged every-second rule. Status
v2 and Dashboard archive compatibility are implemented. Both v5 and completed
v2 timers are now inactive/disabled; the four-day post-window audit found no
new journal rows or invocations and unchanged evidence. Independent Protocol v6 accepted one USD-M
book-depth mechanism as genuinely distinct and locked its source/model,
fields, parameters, evidence windows and gates before archive-body access. Its
v6-only immutable one-day collector opened the exact qualification date once
from a pushed clean commit. Both assets failed the exact grid gate because all
2,880 groups contain 12 rows including ±0.20; v6 is now
`blocked_provider_qualification` with raw evidence retained and historical
development closed. No factor, signal, return or PnL was opened. The
`freqai_linear_v1` 14-day testnet campaign is archived after demotion, and its
historical Phase 3 strict streak remains 0/14.
Protocol v7 is complete. The VIX/OVX/GVZ routes produced 171/175/162 isolated
signals and reproducible duplicate replays. VIX fails concentration, OVX fails
cost-adjusted return, monthly breadth, and concentration, and GVZ passes all
numeric gates but is rejected by the frozen execution-catalog continuity gate:
30 of 26,304 expected BTCUSDT hours are missing. The later operator-requested
downtime sensitivity verified that the official ZIP/checksum and REST sources
also contain no bars in those windows; 30 isolated zero-volume markers leave
all strategy results unchanged and receive no orders or fills. The diagnostic
does not reopen v7. Protocol v8 separately froze the unchanged GVZ survivor
before opening 2023-2025 PnL, passed every confirmation gate, and entered it at
`paper_shadow` dry-run. The future blind remains sealed and testnet stays
blocked.
Protocol v9 is also complete. The VIX9D-below-VIX curve and five-observation
VVIX-relief candidates pass provider, cost-sign, activity, lineage, verified
downtime, and reproducibility checks, but both fail leave-best concentration;
the curve candidate also fails monthly breadth. Both are rejected without
opening their 2023-2025 confirmation holdout.

Immediate focus:

1. Retain the completed Protocol v5/v2 archive without restarting either timer. Do not loosen validation, retry/backfill, open the 2026-08..12 PnL, retune either rule, fill data, hide an ETH loss with BTC, or resume testnet under those research identities. Any future related study requires a new pre-registered protocol and deployment identity.
2. Treat `docs/retros/2026-07-29-freqai-linear-v1-demote-paper-simulated.md` as the current policy decision. The Phase 3 progress files and canary retros are archived operational evidence only. They remain valid for connection, lifecycle, lineage, and emergency-path evidence, but not as alpha or as proof that `SourcePolicy.position_pct_multiplier` scaled the submitted quantity; that execution bug was fixed on 2026-07-16 and any future sizing claim needs post-fix evidence. Do not run another canary for this identity without a new allowed `paper_simulated -> testnet_canary` promotion review. After such a future promotion, use the passive bundle and continuity reports with every completed manifest-backed bundle in the candidate window, and carry no-manifest aborts manually.
3. Use `docs/decisions/009-agent-advice-audit.md` and `docs/decisions/012-phase5-readonly-dashboard.md` as the active agent/frontend boundaries. Agent/MCP work may write/replay/review `AgentAdvice`; dashboard work may read passive reports, observability textfiles, AgentAdvice, and `research.v5.collector_status.v1|v2` through `dashboard.snapshot.v1`. A valid v2 archive is terminal, not an operational fault. `TradingAgents/` is available as an ignored read-only upstream reference for future agent role/configuration ideas only; `docs/progress/tradingagents-reference-map.md` is the current safe adaptation map, and `apps.agents.role_profiles` is the first machine-readable AgentAdvice-only role seed. Neither path may write `SignalEvent`, mutate `SourcePolicy`, call exchange APIs, or encode structured execution directives.
4. ADR-008 §6.2 Phase 3b, §6.3 Phase 3c-a/b/c, §6.4 Phase 3d, §6.5 Phase 3e, §6.6 Phase 3f stability soak/canary, and the §8 promotion-review patch are all implemented and unit-tested. The `phase_3_not_ready` blocker now only hard-blocks `live_canary` / `live_normal`.
5. Keep LLM agents and FreqAI out of the order path; `SignalEvent v1 -> NautilusTrader Strategy -> RiskEngine` remains the only bridge.
6. Keep the confirmed GVZ identity at `paper_shadow` dry-run and collect genuinely forward official GVZ/BTC evidence. Do not change its parameters, disable dry-run, open the 2026-09..2027-01 blind early, or resume testnet.
7. Preserve both Protocol v9 rejects. Do not alter their thresholds/signs, combine them after seeing PnL, or open their sealed 2023-2025 confirmation results.
8. Preserve Protocol v11 results and keep 2023-2025 confirmation sealed. Hashrate and fee-demand identities are rejected; stablecoin expansion is an undersampled lead only and may be revisited solely through a new pre-registered forward immutable collection, without changing its 30-observation rule from these results.
9. Continue Protocol v12 manually or install its daily 12:30 UTC recurring schedule only after explicit operator approval. The first countable observation is 2026-08-12 at the 2026-08-14 decision; never count bootstrap rows or treat the 180-day continuation threshold as promotion evidence.
10. Preserve Protocol v13 results. Active-address and transfer-count expansion are rejected; MVRV below one is an undersampled lead only. Do not retune thresholds/signs, construct a PnL-selected ensemble, or open 2023-2025 confirmation.
11. Preserve v14's provider failure. Do not retry the exact request, delete the denied metric, load a paid credential, or substitute series under the same identity; its development and confirmation remain unopened.
12. Preserve v15's timeout result without retrying FRED. Any official Treasury-direct recovery must use a new frozen data contract before annual CSV values are opened.
13. Commit and push the v16 confirmation contract before opening the 2023-2025 annual Treasury bodies. Run only the unchanged Treasury-yield volatility relief identity twice; keep the final future blind sealed regardless of confirmation outcome.

## Next Steps

1. Keep the completed Protocol v5/v2 archive immutable. Do not restore either timer; only refresh the passive archived Dashboard artifact when an operator needs an audit view.
2. Keep the 2026-08..12 final blind unopened. Both v5 candidates are rejected and must not have blind PnL opened under this protocol. Do not tune after historical results, substitute providers, create a PnL-selected ensemble, or treat the BVOL diagnostic as promotion evidence.
3. Preserve the blocked Protocol v6 qualification evidence and stop. Do not delete the ±0.20 rows, reinterpret the grid, change the registered band/tolerance, retry Binance, or implement/open historical development, factors, signals or PnL under this identity.
4. Preserve the qualified v3 hashrate snapshot and the v4 timeout evidence. Do not retry macro providers automatically; any new route requires independent evidence and explicit review before a new protocol is registered.
5. Archive and retain the completed Protocol v2 7/7 option/basis evidence. Do not rebuild or restart the completed collector, open basis historical ZIPs, or invent option-method substitutes.
6. Continue the installed weekday 02:30 UTC Protocol v8 collector from its qualified Day 1 baseline. Accumulate 6 more distinct forward paper-shadow days or 50 new forward signals with clean schema, freshness, lineage, and verified-session behavior. Require a separate human review before any `paper_shadow -> paper_simulated` change.
7. Keep Protocol v9 closed with both candidates rejected. Do not open 2023-2025 confirmation, retune either rule, or create a PnL-selected ensemble.
8. Keep the signed `freqai_linear_v1` policy at `paper_simulated` with multiplier `0.1`; testnet/live remain blocked. Do not tune or revive this frozen model identity. New research candidates may enter `paper_shadow` only through a prospectively frozen confirmation protocol; GVZ is the current instance and its separate final future blind remains required before any testnet consideration.
9. Retain the 2026-07-29 demotion review and its linked testnet/policy fingerprints as the current audit chain; no follow-up runtime is required.
10. Continue Phase 5 with only read-only dashboard improvements fed by `dashboard.snapshot.v1`; keep the frontend free of API routes and mutation controls until a separate ADR opens a specific workflow.
11. If a future allowed promotion reopens live-readiness evidence collection, use `docs/progress/phase-3-testnet-continuity-plan.md` and include every completed manifest-backed testnet bundle in the candidate window when running both `report_testnet_bundle --continuity` and `apps.ops.live_readiness`.
12. Use `promotion_review.py` as the required ADR-007 §2.6 audit artifact for any actual `SourcePolicy` change. It now accepts paper evidence directly and testnet evidence through the manifest-linked signed policy record; linked policy absence or mismatch fails closed.
13. Only after a future allowed testnet promotion, keep the `testnet_runner.py` startup guard + connection probe as the first line of defense: explicit `--allow-real-credentials`, clean git, source/model retro evidence, testnet multiplier cap, key-prefix-only audit, Ed25519-only credentials, and Binance Spot TESTNET-only adapter config. The probe injects credentials into the in-memory `TradingNodeConfig` only and never writes the full key/secret to `logs/runtime.log` or `connection_probe.json`.
14. Do not collect additional testnet or paper evidence for the frozen `freqai_linear_v1` identity merely to improve its record. The v11 paper bundle's expectancy (+0.00491 USDT/trade, 53.6% win rate, -0.003878% max drawdown over 152 days) becomes negative under base/stress costs, contains incompatible historical shorts, and the parquet-backed canary fill set is only operational evidence.
14. Decide SQLite -> Postgres / Redis Stream readiness only after backtest, paper, or testnet volume exposes an actual bottleneck.
15. Any future alpha batch must use genuinely independent evidence and a new protocol frozen before data access; it may not reuse Protocol v7 to tune around its observed results.
16. Keep Protocol v13 confirmation sealed. Any MVRV follow-up must preserve the below-one identity and use prospectively collected immutable evidence rather than a threshold search on opened history.

## Blocked / Deferred

- No live trading.
- No Phase 6 entry: the reference source is demoted to `paper_simulated`, ADR-013 is Draft, strict continuity is 0/14, no live-canary promotion review exists, `docs/runbook-first-live-day.md` is Draft, and the live startup guard is not wired to any live runner.
- No real exchange API keys in the repository.
- No Redis until cross-process signal transport is required.
- No automatic SQLite -> Postgres mirror or PG-backed bridge default until an ADR-011 trigger fires; current Postgres/TimescaleDB/pgvector is service-only Phase 3 support.
- No frontend write actions, order controls, runner triggers, or browser-side mutations.
- No Protocol v5 research reopen: blind PnL, filling/interpolation, retuning,
  cross-asset result masking, testnet resume, and SourcePolicy changes are
  prohibited.
- No Protocol v5 timer restoration after the approved closeout. Any future
  related study requires a new protocol/provider identity; it may not loosen
  this identity's validation, retry/backfill its gaps, or rewrite its evidence.
- No Protocol v6 retry or historical development. The one allowed
  qualification download is retained and both assets failed the frozen exact
  grid on additional ±0.20 rows. Row deletion, grid reinterpretation, band or
  tolerance changes, another provider request, factor/signal implementation
  and PnL access are prohibited under this identity.
- No formal Protocol v7 reopen. The completed zero-volume downtime-marker
  sensitivity is diagnostic only. Further filling/interpolation, changing the
  execution interval, retuning after PnL, advancing GVZ, or opening the
  2026-09..2027-01 future blind is prohibited under this identity.
- No Protocol v9 confirmation opening. Both development candidates are
  rejected; their 2023-2025 strategy-specific PnL remains sealed.
- No GVZ `paper_simulated` entry yet. Protocol v8 confirmation authorizes only
  `paper_shadow` with `dry_run=True`; forward shadow evidence and a separate
  promotion review are still required.
- No n8n workflows until a concrete Phase 4 orchestration need appears.
- No autonomous Agent trading. Agents may only research, review, summarize, and suggest.
- No edits to `freqtrade/` or `nautilus_trader/` unless explicitly requested.

## Latest Verification

On 2026-08-12, after Protocol v16 Treasury-direct development:

- Pre-access code was pushed at `f77ad09`; eight annual payloads contain 791
  joint numeric observations with no fill and maximum four-day calendar gap.
- Real-yield relief and curve steepening are cost-positive but insufficient
  evidence. Treasury-yield volatility relief passes all gates with base/stress
  +55.211116/+53.821362 USDT, 20/36 positive months, 76 positions, and
  +35.236938 leave-best base PnL.
- All duplicate pairs reproduce with zero shorts, blockers, or verified
  no-kline event hits. Confirmation remains sealed until the development
  review is committed; SourcePolicy and trading paths are unchanged.

On 2026-08-12, after Protocol v15 provider qualification:

- The contract passed 12 focused tests and was pushed at `91a79e1` before the
  exact combined FRED body was requested.
- The only GET timed out after 30 seconds before response headers or body. No
  factor value, signal, PnL, confirmation, or future-blind evidence was opened.
- Direct U.S. Treasury nominal and real annual CSV routes both passed
  body-free HEAD qualification and require a new frozen provider identity.

On 2026-08-12, after Protocol v14 provider qualification:

- The zero-data contract and collectors passed 12 focused tests and were pushed
  at `0ec5333` before the exact time-series request was opened.
- The first and only request returned HTTP 403 before data rows; the immutable
  152-byte error body hashes to `79bcb4a2…0489` and identifies `CapRealUSD` as
  unavailable with Community credentials.
- Community-scoped catalog metadata includes none of the three registered
  metrics. Development, confirmation, factor values, signals, and PnL remain
  unopened; v12-v13 and every trading path are unchanged.

On 2026-08-12, after Protocol v13 BTC network-mechanism development:

- The pre-access contract was pushed at `e61cc0b`, and snapshot-integrity
  hardening was pushed at `70f0402` before the time-series body was opened.
- The immutable response contains 1,157 complete daily rows for all three
  metrics; snapshot hash is `2af15212…a016` and no row was filled.
- Active-address expansion base/stress PnL is +6.915612/+5.979135 USDT but it
  fails monthly breadth and leave-best concentration. Transfer expansion is
  -15.162113/-16.235711. MVRV below one is +1.918861/+1.848863 but has only
  seven positions and is insufficient evidence.
- All duplicate pairs reproduce, with zero shorts, effective blockers, or
  verified no-kline event hits. Zero candidates qualify for confirmation;
  v12, SourcePolicy, testnet, and live paths remain unchanged.
- Full verification: **1,076 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean.

On 2026-08-11, after Protocol v9 option-risk development:

- The two-candidate contract was pushed at `ca2bbf3` before VIX9D/VVIX body
  access; locked signal/review code was pushed at `0da8a49` before PnL access.
- Both new official Cboe snapshots contain 756 development observations and
  preserve raw hashes/vintages. No source refresh or forward fill was used.
- VIX9D-below-VIX base/stress PnL is +15.269651/+14.537709 USDT with 43
  positions, but only 12/36 positive months and leave-best -1.628722.
- VVIX relief base/stress PnL is +2.540920/+0.991650 USDT with 83 positions and
  21/36 positive months, but leave-best is -7.023792. Both duplicate replay
  pairs match and neither trades in a verified exchange no-kline hour.
- Both candidates are rejected. The 2023-2025 confirmation and shared future
  blind remain sealed; GVZ paper shadow, SourcePolicy, testnet, and live are
  unchanged.

On 2026-08-11, after Protocol v8 confirmation and paper-shadow entry:

- The pre-access contract was pushed at `138cf35`; confirmation code was clean
  and pushed at `20ec74d` before opening 2023-2025 execution/PnL.
- All 36 official Binance monthly archives match checksums. The catalog has
  26,303 official bars plus one exact REST-verified exchange-unavailable hour,
  zero synthetic bars, zero duplicates, and a passing session-aware audit.
- Two clean Nautilus replays return `MATCH`. Base/stress PnL is
  +25.180955/+21.737949 USDT, 2/3 years and 19/36 months are positive, 83
  positions close, and leave-best base PnL remains +12.855628 USDT.
- The first clean paper-shadow bundle records 166 accepted dry-run signals,
  zero orders/fills/positions, zero expired/unauthorized/kill-switch signals,
  and no signal in the verified unavailable hour.
- The prospectively locked forward collector ran on clean pushed commit
  `1b44e6e`. Day 1 is qualified: official GVZ ends 2026-08-10 (age 1 day),
  167 closed BTCUSDT hours are contiguous, historical revisions/blockers are
  zero, and 38 pre-entry signals are baseline-only. Gate progress is 1/7 days
  or 0/50 new forward signals; the weekday 02:30 UTC crontab is installed and
  `cron.service` is active.
- Current stage is `hold @ paper_shadow`; testnet/live remain blocked and the
  2026-09..2027-01 future blind remains sealed.
- The full Python suite reports 1027 passed / 12 Postgres-dependent skips.

On 2026-08-11, after the operator-requested Protocol v7 downtime sensitivity:

- All 36 local Binance monthly ZIPs match the current official SHA-256 files,
  and all 14 exact gap windows return zero rows from the official Spot REST
  kline endpoint. The gaps are exchange-side no-kline windows, not local import
  loss; archived notices identify the major multi-hour windows as maintenance.
- A separate catalog retained 26,274 official bars and added 30 zero-volume,
  previous-close downtime markers. It audits at 26,304 / 26,304 rows with zero
  duplicates, gaps, or irregular steps.
- Six clean-commit Nautilus replays completed, all three duplicate pairs return
  `MATCH`, and no order or fill occurred at a marker timestamp. VIX, OVX, and
  GVZ results are unchanged to reported precision; GVZ remains a diagnostic
  numeric pass only.
- Formal Protocol v7 selection remains zero, the future blind remains sealed,
  and no paper/testnet runtime, credential, SourcePolicy, or live path changed.
- The full Python suite reports 994 passed / 12 Postgres-dependent skips.

On 2026-08-11, after the Protocol v7 replication review:

- Official Cboe VIX/OVX/GVZ reserve snapshots qualified with 761/757/757 rows
  and produced 171/175/162 isolated long/flat signals.
- The BTCUSDT 1h reserve catalog has 26,274 / 26,304 expected bars, zero
  duplicates, and 30 missing intervals across 14 irregular steps. No fill or
  interpolation was applied.
- Six clean-commit Nautilus backtests completed; both runs for every candidate
  compare as `MATCH`. VIX base/stress PnL is +9.538828/+8.041265 USDT but fails
  leave-best concentration; OVX is -2.443604/-3.986020 and fails multiple
  gates; GVZ is +18.871408/+17.434647 and passes numeric gates but is rejected
  by the catalog hard blocker.
- Selected candidates are zero, recommendation is `stop_before_testnet_resume`,
  and no exchange credential, paper/testnet runtime, or trading policy was
  touched.
- The full Python suite reports 992 passed / 12 Postgres-dependent skips.

On 2026-07-29, after the human-approved `freqai_linear_v1` demotion:

- `promotion_review.py` accepted the exact
  `testnet_canary -> paper_simulated` decision with unchanged
  `SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
  min_confidence_override=None)`. Bundle/policy match is true and both review
  and transition blocker sets are empty.
- The review fingerprints clean testnet bundle
  `20260530-141037Z-6e860b4f` at manifest SHA-256
  `40c1a86106f3af1f9d02da6525db33d0958053135ef9739c1fd179cc45c347ad`
  and its linked signed policy artifact at SHA-256
  `bd86754b62bc1a7d2eedc9da30482360f4bb73709307a89b5622191fe15bccc3`.
  The bundle retains 719 heartbeats, zero alerts/blockers, two orders/fills,
  final FLAT state and -0.01055 USDT realized PnL as operational evidence.
- The testnet startup evidence scan now treats the newest allowed decision as
  authoritative. The repository scan returns no valid testnet stage evidence
  after the demotion, so it cannot fall back to the older promotion artifact.
- The full Python suite reports 973 passed / 12 Postgres-dependent skips;
  repository-wide Ruff passes. No exchange credential was loaded, no runtime
  was started, and no original paper/testnet evidence was modified.

On 2026-07-27, at the Protocol v5/v2 post-trigger-window closeout:

- Ten scheduled journal reports cover data dates 2026-07-17..21. The last
  complete batch is the 2026-07-17 retry; the latest date with any valid stream
  is 2026-07-21. First attempts were persistently 404, BTC curve never
  recovered after the complete batch, and ETH BVOL repeated the unchanged
  every-second validation failure on every later retry.
- The retained v5 tree is 13 snapshots / 13 Parquets / 0 vintage conflicts / 0
  comparison markers. Git/image identity matches clean commit `d37d227`.
  Protocol v2 still has `COMPLETE` and a 14-row qualification ledger.
- The decision is `stop_scheduled_collection`. Both timers have remained
  `inactive/disabled` with no next elapse since 2026-07-23 02:06:46 UTC; both
  services are `inactive/dead`, v5 failed state is cleared, and no collector
  container is running.
- Four days after both former trigger windows, v2 journal remains 70 rows / one
  recorded invocation and v5 remains 656 rows / ten invocations. Invocation
  sets, last timestamps and journal cursors are unchanged, proving zero new
  service invocations.
- The v5 tree remains 13 snapshots / 13 Parquets / zero conflicts and its
  manifest checksum is unchanged. v2 `COMPLETE`, its 14-row ledger and latest
  review checksums are unchanged. Archived collector and Dashboard smoke pass
  with zero blockers, no retry and collector issue count zero. Details are in
  `docs/progress/phase-2-research-v5-provider-timer-review.json` and
  `docs/retros/2026-07-23-research-v5-stop-scheduled-collection.md`.
- Collector/dashboard tests report 99 passed; the full suite reports 969
  passed / 12 Postgres-dependent skips when its temp root is on Linux storage.
  Repository-wide Ruff, strict JSON/diff checks, archived-v2 Dashboard snapshot
  smoke, frontend typecheck/build, and npm audit (0 vulnerabilities) pass.

On 2026-07-20, at Protocol v5's 08:20 retry observation:

- The 08:15:16..08:15:23 UTC batch for data date 2026-07-19 produced 2 valid
  and 2 failed streams: ETH curve and BTC BVOL succeeded; BTC curve returned
  HTTP 404; ETH BVOL repeated `must contain one observation in every UTC
  second`.
- The repeated ETH failure matches the baseline error and triggers a durable
  provider/timing review. The first 08:20 batch is recorded incomplete; later
  oracle observations stop while that trigger remains recorded.
- Storage is 11 snapshots / 11 Parquets / 0 conflicts / 0 comparison markers.
  Checkout and image revision match clean commit `d37d227`; the timer remains
  active/enabled and unchanged.
- Strict status and dashboard JSON parsing and consistency assertions passed.
  All mutation/trading boundaries remain false. Details are in
  `docs/retros/2026-07-20-research-v5-publication-observation.md`.

On 2026-07-19, after Protocol v6 provider qualification:

- Exact pushed commit `93e97cf` built the dedicated ARM64 image and passed a
  network-none empty-root dry-run before the single all-asset download. OCI
  revision, internal marker, environment and expected commit match; credential
  counts are zero and no v6 timer exists.
- Eight HTTP 200 responses retain four ZIPs and four official checksum bodies
  with zero conflicts/blockers. Both assets have 34,560 bookDepth rows in
  2,880 twelve-row groups; every group adds ±0.20 to the frozen ten-row grid,
  so zero groups qualify. Both mark-price files have 1,440 UTC minutes, but the
  audit stopped at the earlier hard grid blocker.
- Network-none/read-only cloud replay and a fetch-forbidden local replay
  reproduced `blocked_provider_qualification` without changing the evidence
  trees. Cloud/local evidence-package SHA-256 is
  `c627d6f2d246aad72334c28b1eecabd31fc7dd755739cae269352406c4845236`.
- No snapshot/Parquet, factor value, daily aggregation, state, signal, return,
  PnL, Nautilus run, credential, SourcePolicy, testnet or live path was opened.
  Full evidence is in
  `docs/retros/2026-07-19-research-v6-provider-qualification.md`.

On 2026-07-19, at Protocol v6 qualification-collector implementation:

- The separate v6 module locks the exact 2026-07-17 BTC/ETH bookDepth and
  mark-price requests, atomically caches each successful HTTP response,
  preserves permanent blockers/conflicts, and writes only one immutable raw
  envelope plus one audit-summary Parquet per qualified asset.
- Thirty-four v6 collector tests cover fixed URL/date, offline dry-run,
  request caching, retry/idempotency/conflict/tamper, exact schema/grid/UTC
  coverage, 1,440 mark minutes, same-minute matching and strict side/band
  boundaries. Sixty combined v2/v3/v5/v6 protocol/collector tests pass.
- The full suite reports **961 passed / 12 Postgres-dependent skips**; full
  Ruff and `git diff --check` pass. Docker is unavailable in the local
  workspace, so Compose rendering and the ARM64 image build remain mandatory
  parts of the same-SHA cloud preflight.
- No v6 Binance archive/checksum body, factor value, daily aggregation, state,
  signal, return, PnL, Nautilus run, credential, SourcePolicy, testnet or live
  path was opened.

On 2026-07-18, at Protocol v6 book-depth identity pre-registration:

- The mechanism review accepts resting limit-order liquidity-supply asymmetry
  for pre-registration only. The machine validator reports valid locked
  protocol/provider/fingerprint hashes with archive bodies, signals and PnL
  all false.
- Six new v6 drift tests and all 26 v2/v3/v5/v6 protocol tests pass. The full
  suite reports 927 passed / 12 skipped because local Postgres is unavailable;
  full Ruff, strict JSON parsing and `git diff --check` pass.
- No Binance archive/checksum body, factor value, return, SignalEvent,
  Nautilus run, credential, SourcePolicy, testnet or live path was opened.
- The live read-only v5 collector status remains `healthy` for data date
  2026-07-17 with four successful streams and 8 snapshots / 8 Parquets /
  0 conflicts.

On 2026-07-18, at Protocol v5's first scheduled data date:

- The 04:15 UTC attempt returned four HTTP 404s, retained all four streams
  flat, wrote no snapshot, and computed no signal/PnL. The scheduled 08:15 UTC
  retry completed all four streams with service exit 0.
- All four new snapshots passed offline checksum, raw/hash, audit, availability,
  normalized-value, and envelope verification in the network-disabled locked
  image. Each of the four Parquets has one row exactly matching its snapshot
  normalized envelope.
- Storage is 8 snapshots / 8 Parquets with 0 conflict artifacts and 0 comparison
  markers. Timer, checkout, commit, image ID and OCI revision checks are clean.
- Detailed evidence is in
  `docs/retros/2026-07-18-research-v5-first-scheduled-collection.md`.

On 2026-07-18, at Protocol v5 historical fast-track completion:

- Curve's 2021 Aug-Dec execution fold has 216,000/220,320 minutes per asset;
  the same three missing official days produce a validated pre-PnL rejection.
  No curve signals or Nautilus run were created.
- All five BVOL Spot folds are complete and aligned. Twenty clean-commit
  Nautilus runs form ten reproducible asset/fold pairs with strict sidecars,
  lineage, Spot-only, concurrency, and notional evidence.
- BVOL aggregate base/stress PnL is -1.185170/-6.326371 USDT, 13/25 months and
  3/5 folds pass, leave-best base is -16.799085 USDT, and ETH is negative under
  both modeled costs. The locked decision is `reject_v5_candidate`.
- Both candidate reviews return `stop_before_testnet_resume`. The future blind,
  credentials, SourcePolicy, promotion review, testnet, and live path remain
  untouched. Machine detail is in
  `docs/progress/phase-2-research-v5-fast-track-results.json`.

On 2026-07-18, at Protocol v5 future collector deployment:

- Fast-track report commit `d37d227` was pushed before deployment. The same
  clean SHA is checked out under an isolated cloud path and labels dedicated
  ARM64 image `sha256:7ad7f9614692...`.
- A network-disabled, read-only dry-run produced all four plans with no network,
  data write, signal, or PnL. Host and image credential-entry counts are zero.
- The separate v5 timer is active/enabled for 04:15 and 08:15 UTC; the v2 timer
  remains active/enabled and unchanged. Existing v5 qualification evidence
  remains at four snapshots/four Parquets with zero conflicts.
- Details are in
  `docs/retros/2026-07-18-research-v5-collector-deployment.md`.

On 2026-07-17, at Protocol v5 Spot execution lineage qualification:

- Before historical Spot access, commit `8bcdb46` added the missing immutable
  ZIP/checksum/HTTP/vintage envelope and exact 1,440-minute gate. Commit
  `d7a2022` then kept idempotent Nautilus catalog messages out of strict JSON.
- The clean-commit 2026-07-16 BTC/ETH qualification snapshots passed checksum
  and offline verification, matched the prior July ZIP bytes, and imported
  1,440 bars each. Catalog audit found zero gaps, duplicates, or irregular
  steps and complete cross-asset timestamp alignment.
- Before PnL, the v5 portfolio notional audit was corrected to use the first
  in-fold 1m Spot close rather than the first day's final close. A non-constant
  end-to-end raw-to-review fixture now locks the registered sizing formula.
- Before future collector deployment, daily collection was made four-stream
  fail-closed: one missing curve/BVOL archive no longer prevents the other
  streams from being preserved, while the batch remains incomplete and exits
  nonzero for monitoring.
- The bulk curve collector now checks the usually unavailable required next
  contract before downloading index/front bytes. Successful snapshots retain
  the locked envelope order and identical content identity; missing dates keep
  the same fail-closed ledger semantics.
- `research_v5_review` now accepts validated pre-PnL hard-data-blocker evidence,
  so an incomplete execution catalog produces an explicit candidate rejection
  without fabricated fold metrics or a Nautilus run.
- The full suite is **910 passed, 12 Postgres-dependent skips**; full-repository
  Ruff and `git diff --check` pass. No historical Spot body, signal, return,
  PnL, backtest, credential, policy/testnet/live action, or future-blind data
  was accessed. Details are in
  `docs/retros/2026-07-17-research-v5-spot-lineage-qualification.md`.

On 2026-07-17, at Protocol v5 historical fast-track opening:

- Qualification retro commit `e2955d3` was pushed before historical access.
  Curve requires two listed quarters and first becomes complete on 2021-06-18;
  BVOL launches with partial days and first becomes complete on 2023-06-22.
- Valid BTC/ETH snapshots for both first-complete dates passed. The 2023-08-01
  BVOL file has 86,398 rows and a real grid gap, so the whole day remains flat.
- Range download now logs a failed date, writes no snapshot for it, continues
  later dates, and returns nonzero if coverage is incomplete. No validation
  threshold was relaxed. The v5 signal CLI can now isolate one BTCUSDT or
  ETHUSDT sleeve into its own SignalStore so duplicated Nautilus fold runs do
  not mix symbols. Before historical Spot execution access, the Spot daily
  route now also preserves official checksum/HTTP/vintage evidence and imports
  only an offline-verified 1,440-minute snapshot into the Nautilus catalog.
  The full suite is **907 passed, 12
  Postgres-dependent skips**; full-repository Ruff and `git diff --check` pass.
- No historical return/PnL, signal, Nautilus run, policy/testnet/live action, or
  future-blind data was accessed. Details are in
  `docs/retros/2026-07-17-research-v5-fast-track-collection-start.md`.

On 2026-07-17, after Protocol v5 provider qualification:

- Exact image/collector commit `3d1687b` passed a network-disabled cloud
  preflight, the four-snapshot 2026-07-16 collection, independent offline
  verification, and an idempotent real rerun.
- Local/cloud content hashes match for both curve and both BVOL datasets. Cloud
  evidence has four snapshots, four normalized Parquets, zero vintage conflicts,
  zero comparison markers, zero credential environment entries, and tree hash
  `401d59902aef4f9c7e86d8fe8003dd092a49a04ff55a3e56e8bd844bfe361744`.
- Local Spot execution qualification has 1,440 BTCUSDT and 1,440 ETHUSDT 1m
  bars, zero gaps/duplicates/irregular steps, and aligned timestamps. No signal
  or PnL was produced.
- The v5 timer is disabled. Historical fast-track access is allowed only after
  this retro is pushed; the future blind, SourcePolicy, testnet, and live path
  remain untouched. Details are in
  `docs/retros/2026-07-17-research-v5-provider-qualification.md`.

On 2026-07-17, during Protocol v5 July-only schema qualification:

- Pre-access commit `f8437f5` was pushed before the first real body. Its locked
  daily dry-run covered all four BTC/ETH curve/BVOL plans with zero network and
  zero writes.
- The first real batch failed closed before snapshot creation because official
  Futures 1d files use `count`/`taker_buy_volume`; the July BVOL schema uses
  `BTCBVOL`/`ETHBVOL` and exactly one observation per UTC-second bucket.
- The correction changes only raw-schema validation and the provider-contract
  hash. Candidate identities, fingerprints, formulas, parameters, partitions,
  costs, and gates remain unchanged. Thirteen focused protocol/snapshot/full
  integration tests pass; the full suite is **901 passed, 12
  Postgres-dependent skips**, and full-repository Ruff and `git diff --check`
  pass.
- No historical replication body, return, PnL, credential, signal, Nautilus
  qualification run, SourcePolicy mutation, testnet resume, or live action
  occurred. Details are in
  `docs/retros/2026-07-17-research-v5-schema-qualification-fix.md`.
- Correction commit `4891346` subsequently produced four valid local snapshots;
  offline verification and an idempotent rerun passed with zero conflicts.
  BTC/ETH Spot catalogs each contain 1,440 aligned 1m rows with zero gaps. A
  network-disabled cloud preflight then stopped before requests because the old
  v2 image lacks pandas. The dedicated commit-labelled, read-only v5 image and
  container-backed systemd unit are now implemented; the full suite is **903
  passed, 12 Postgres-dependent skips**, and full-repository Ruff plus
  `git diff --check` pass. Cloud image build/qualification is the remaining
  action.

On 2026-07-17, before any Protocol v5 Binance response body access:

- Locked the curve-carry and BVOL-relief candidate identities, BTCUSDT/ETHUSDT
  universe, prior-UTC-day availability rules, explicit missing-to-flat behavior,
  partitions, execution assumptions, fingerprints, costs, and dual-sleeve gates.
- Implemented an offline dry-run/immutable public-archive collector, deterministic
  SignalEvent v1 generators, portfolio-level daily equity and concurrency audit,
  `research.v5.review.v1`, and disabled cloud timer templates. The dry-run
  reports `network_accessed=false` and `data_written=false`.
- Forty-five focused protocol, collector, signal, end-to-end Nautilus replay,
  review, multi-asset, alpha, and daily-orchestrator tests pass. The full suite
  is **900 passed, 12
  Postgres-dependent skips**; full-repository Ruff and `git diff --check` pass.
- No Binance response body, historical data, return, PnL, credential,
  SignalStore write, Nautilus run, SourcePolicy mutation, testnet resume, or live
  action occurred.

On 2026-07-17, after Protocol v4 provider qualification:

- Pre-access commit `62d926f` was pushed before direct CSV access. Its cloud
  archive hash, protocol fingerprint, 19 synthetic tests, and both
  network-disabled dry-runs verified successfully.
- Both credential-free FRED July GETs timed out while reading the HTTPS response
  on the cloud path; local execution also produced zero files, and a retained
  local VIX log records the same 30-second response-read timeout.
- Cloud and local v4 raw directories contain zero snapshots. No response was
  accepted as CSV, no factor or signal generator was implemented, and both
  candidates are `blocked_provider_response_timeout`.
- No credentials, returns, PnL, SignalStore, Nautilus, SourcePolicy, testnet, or
  live path was used. Details are in
  `docs/retros/2026-07-17-research-v4-provider-qualification.md`.

On 2026-07-17, before direct Protocol v4 CSV access:

- Locked new identities `rule_broad_usd_weakness_v1 /
  fred-dtwexbgs20obs-negative-1d-v1` and `rule_equity_vol_relief_v2 /
  fred-vixcls5obs-negative-1d-v1`; signs, observation counts, zero thresholds,
  cost gates, and evidence partitions remain inherited from v3.
- Locked two credential-free FRED graph CSV GETs to July 2026 only. The
  immutable collector retains exact bytes, rejects invalid dates/values/lineage,
  refuses overwrite, does not forward-fill `.`, and uses retrieval time as the
  earliest safe availability timestamp.
- Documentation search disclosed limited current rows after the routes were
  chosen; v4 records that disclosure and forbids using it for parameter or PnL
  selection. No direct CSV, return, factor, signal, PnL, credential, Nautilus,
  policy, testnet, or live path was accessed.
- Nineteen focused protocol/collector tests pass; both CLI dry-runs report
  `network_accessed=false` and `data_written=false`.

On 2026-07-17, after Protocol v2 coverage completion and the first real v3
provider qualification:

- Protocol v2 attempt `attempt-20260711-001` completed seven exact option/basis
  pairs for 2026-07-11..17: 14 ledger rows, no duplicates, gaps, unpaired dates,
  blockers, or `last-error`; `COMPLETE` now makes later timer triggers no-op.
- The first v3 hashrate snapshot on clean tracked commit `7afc61d` contains 30
  completed UTC-day rows through 2026-07-16 and passes offline raw/parsed/audit/
  envelope/vintage/filename verification.
- The frozen DXY and VIX GETs returned an HTTP 200 JavaScript verification page,
  not CSV. Both failed before snapshot creation; changing User-Agent did not
  bypass the provider response. An isolated cloud-server retry produced the
  same CSV-structure rejection and zero files; the unregistered verification
  POST was not executed.
- All three dry-runs remained no-network/no-write; 15 focused v3 tests passed.
  No credentials, factors, returns, signals, PnL, Nautilus run, SourcePolicy
  mutation, testnet resume, or live action occurred. Detailed evidence is in
  `docs/retros/2026-07-17-research-v3-provider-qualification.md`.

On 2026-07-16, after the full-code review follow-up:

- `BaselineNautilusStrategy` now scales its concrete order quantity by the
  accepted `OrderIntent.target_position_pct`; multiplier `0.5` submits half the
  configured trade size and multiplier `0.0` submits no order.
- `SignalStorePollingSource` replays from the current run's fixed lower bound
  and deduplicates by `signal_id`, so same-timestamp and older late inserts are
  consumed once instead of being skipped after the event-time high water moves.
- The real `python -m apps.bridge.cli ... write` entrypoint is covered, and a
  corrupt persisted `raw_json` row is rejected without stopping later signals.
- Targeted verification passed 34 tests. The full suite is **853 passed, 12
  Postgres-dependent skips**; Ruff and `git diff --check` pass. No credentials,
  exchange connection, SourcePolicy mutation, testnet resume, or live action
  occurred. Historical canary bundles remain operational evidence but are not
  sizing-multiplier evidence.

On 2026-07-16, before any real Research Protocol v3 provider response access:

- Repaired the shared SignalEvent test fixtures so implicit `flat` and `sell`
  payloads receive consistent zero/negative scores while explicit conflict tests
  remain unchanged. The previously failing 21 tests are green; the full suite is
  **847 passed, 12 Postgres-dependent skips**, and Ruff passes.
- Implemented `apps.ops.research_v3_snapshot` for the three frozen public
  requests. Exact JSON/CSV bytes, parsed payloads, provider audit, canonical
  envelope, vintage, and filename hashes are independently verified.
- Twenty-three focused v3 tests cover request-contract drift, no-network dry-run,
  hashrate UTC-day rules, Stooq OHLC/publication lag, duplicate/future/non-finite
  data, overwrite refusal, tampering, July bounds, and absence of trading imports.
- All three CLI dry-runs report `network_accessed=false` and
  `data_written=false`. No real v3 response body, credentials, factor values,
  returns, signals, Nautilus run, policy mutation, testnet, or live path was used.

On 2026-07-16, during the fresh Protocol v2 cloud window:

- Added the passive `apps.ops.research_v2_daily` orchestration path with a
  per-data-directory lock, same-day idempotency, partial-pair retry, operational
  gap reset, append-preserving ledger, offline hash verification, atomic
  transaction recovery, and a hard stop at seven paired UTC days.
- Added a minimal non-root/read-only Compose image and a host systemd timer with
  three UTC retry slots. The image carries no credentials, ports, Docker socket,
  trading dependencies, SignalStore, NautilusTrader, or SourcePolicy access.
- Targeted collector/provider coverage verification passed 24 tests. The ARM64
  server rendered the Compose configuration and built/deployed non-root image
  `5a8289c50f89fb1a2ae9e1aaf5b69a12d2287fcb` from a hash-verified Git archive.
- Six fresh pairs are committed for UTC 2026-07-11 through 2026-07-16 under
  `attempt-20260711-001`: twelve verified ledger rows, 6/7 paired days, no gaps,
  duplicates, unpaired dates, or review blockers. Every no-PnL/no-signal/no-
  Nautilus/no-policy boundary remains false.
- The systemd timer is enabled for 03:15/06:15/09:15 UTC. A manual unit replay
  previously exited 0 with `already_collected_today` and
  `network_accessed=false`, confirming same-day retries do not add ledger rows.
- The ARM64 build and runtime checks pass. No `last-error.json` or coverage
  blocker exists; the final paired day remains pending.

On 2026-07-12, before accessing any real Research Protocol v3 factor body:

- Pre-registered three independent research-only identities:
  miner hashrate recovery, USD weakness (DXY), and equity vol relief (VIX).
- Locked zero-threshold sign rules, structural lookbacks, shared cost gates,
  2023-2025 diagnostic exclusion, one-opening 2020-2022 reserve, July no-PnL
  qualification, and the 2026-08..12 final future blind.
- Explicitly forbade reuse of rejected price/volume/funding families and of
  blocked Protocol v2 routes; parameters cannot be tuned at runtime.
- Synthetic generator/protocol tests cover state-change emission, causal
  mutation safety, fail-closed anti-overfit guards, and identity fingerprinting.
- No credentials, SignalStore writes, Nautilus runs, SourcePolicy changes,
  testnet resume, or live-path touch occurred during pre-registration.

On 2026-07-11, before accessing any real Research Protocol v2 factor body:

- Locked exactly three independent research-only identities, immutable
  parameters/factor fields, 2023-2025 diagnostic exclusion, one-opening
  2020-2022 replication reserve, July 2026 no-PnL qualification, and the
  2026-08..12 final future blind.
- Point-in-time generators fail closed on publication lookahead, missing daily
  observations, duplicates, invalid snapshot/spec hashes, non-finite values,
  unexplained option-factor decomposition, and invalid futures maturities.
- Locked exact public provider requests and immutable snapshot hashes before
  response access. Fixture tests cover option schema/liquidity, current/next
  delivery mapping, stablecoin universe/metrics, July-only bounds, and
  no-overwrite behavior; six provider tests passed.
- First qualification requests computed no PnL and wrote no invalid snapshot.
  They exposed zero-mark Deribit rows, Binance `contractStatus`, and a Coin
  Metrics Community 403 for USDT `TxTfrValUSD`; the first two are schema-only
  corrections and the third is a fail-closed provider-entitlement blocker.
- The first successful option/basis draft files are explicitly ineligible
  because their exact HTTP bytes were hashed but not retained. The replacement
  envelope stores exact bytes as base64 and verifies raw/parsed/audit/envelope/
  vintage/filename hashes; tamper tests fail closed.
- Replacement option and basis snapshots both pass offline verification. The
  option snapshot contains 876 contracts across 12 expiries (797 two-sided
  positive-mark, 9 zero-mark retained); basis maps the current and next
  quarterly BTCUSD contracts. Stablecoin produced no snapshot and remains
  blocked on provider entitlement. Full detail is in
  `docs/retros/2026-07-11-research-v2-provider-qualification.md`.
- The verified basis snapshot produces one causal factor row at the next UTC
  boundary; qualification explicitly loaded no returns, generated no signals,
  computed no PnL, and wrote no factor CSV. Five transformer tests cover delay,
  duplicate days, tampering, safe boundaries, and no-overwrite output.
- Paired snapshot coverage review is `collecting_insufficient_days` at 1/7,
  with one exact option/basis pair, no gaps, duplicates, unpaired dates, or
  integrity blockers. Five coverage tests prove 7-day pass and fail-closed
  gap/duplicate/tamper behavior without prices, returns, signals, or PnL.
- Official Binance S3 metadata audit is
  `blocked_incomplete_historical_reserve`: index archives start 2020-06 and
  required 2020-01..05 ZIP/checksum objects are absent. Five metadata tests
  cover missing/full months, malformed versus non-quarterly prefixes,
  pagination, and non-positive object size without reading price bodies.
- Verification: 40 targeted tests and the full **794-test** suite passed, with
  12 Postgres-dependent skips; Ruff, `git diff --check`, and protocol
  fingerprint validation passed. No real factor value, return, credential,
  SignalStore, Nautilus run, policy, testnet, or live state was consumed or
  mutated.

On 2026-07-10, after independent-alt replication and cumulative screening:

- BNB/XRP/ADA daily and 1m audits passed exactly; 48 clean bundles cover 24
  source/fold/asset pairs twice, and all eight portfolios stayed within their
  registered one/three-asset concurrency limits.
- Diversified momentum base/stress was `+44.064632/+43.795051` USDT but only
  2/4 folds and 4/20 months were positive; low-vol rotation was aggregate-negative.
- The validated registry contains **16 candidates across 16 families**, all
  `reject`, with zero passers/watchlist entries. `research.program.review.v1`
  triggers `pause_new_candidate_generation_until_independent_evidence`.
- Final verification: **754 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean. No remaining holdout, policy, credential, testnet, or
  live state was consumed or mutated.

On 2026-07-10, before downloading or viewing BNB/XRP/ADA price bodies:

- Locked the three-asset universe, two portfolio fingerprints, 2023 warm-up-only
  boundary, four development folds, 16/50 USDT budgets, 1/3-asset concurrency,
  unchanged cost/robustness gates, 2020-2022 validation reserve, and 2026 blind.
- Synthetic tests verify independent multi-asset long/flat momentum, low-vol
  selection, concurrency-limit pass/fail behavior, alt instrument precision,
  and exact aligned daily archive audit.
- Full verification: **753 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean. Only HTTP HEAD availability checks were made; no alt
  price body, result, SourcePolicy mutation, credential, testnet, or live action occurred.

On 2026-07-10, after the clean flow/positioning tournament:

- All 72 official funding archives passed checksum; 2024/2025 feature audits
  passed at 366/365 aligned Spot days and 1098/1095 funding rows per asset.
- 72 clean Nautilus bundles cover 36 source/fold/asset pairs twice; all pairs
  reproduce, all 12 portfolio folds are exclusive, and no blockers/shorts exist.
- Aggregate base/stress PnL: taker-flow rotation
  `+23.505068/+22.678201`, flow exhaustion `-1.431597/-1.623924`, funding
  crowding `-21.591179/-22.124877` USDT. Taker flow still failed at 2/4 winning
  folds, 7/20 positive months, and 23 positions.
- Ranking is empty and recommendation is `no_candidate_progresses`; no
  2020-2023/2026 data or trading-state mutation occurred.
- Final verification: **746 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean.

On 2026-07-10, before computing any Spot taker-flow feature or downloading a
funding archive:

- Locked three new flow/positioning source/model fingerprints, causal windows,
  one-asset Spot state, four folds, existing mechanical quantities, costs,
  feature fail-closed rules, unchanged robustness gates, absent 2020-2023
  historical reserve, and 2026-08..12 future blind.
- Synthetic tests cover weekly aggressive-buy flow selection, 4h capitulation
  entry plus 12h/recovered-flow exit, crowded-funding exclusion, raw archive
  parsing, official checksum enforcement, feature audit, and long/flat output.
- Full verification: **745 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean. No real feature aggregate/result, funding download,
  SourcePolicy mutation, credential load, testnet resume, or live action occurred.

On 2026-07-10, after the clean multi-asset development tournament:

- 2024/2025 per-asset audits passed at 527040/525600 rows with zero duplicates,
  gaps, or irregular steps and exact BTC/ETH/SOL timestamp alignment.
- 48 post-guard Nautilus bundles cover 24 source/fold/asset pairs twice; all
  duplicate reviews reproduce exactly. Twelve portfolio fold reviews have zero
  shorts/blockers and exact one-asset-at-a-time lineage.
- Aggregate base/stress PnL: cross-sectional momentum
  `-32.210919/-32.489414`, market breadth `-10.027097/-10.761071`, ETH/BTC
  relative value `+15.989241/+15.380761` USDT. Relative value still failed at
  2/4 winning folds, 7/20 positive months, 18 positions, and -3.309221 USDT
  after removing its best position.
- `strategy.tournament.v1` ranking is empty and recommendation is
  `no_candidate_progresses`. No 2020-2023/2026 data, SourcePolicy mutation,
  credential load, testnet resume, or live-path action occurred.
- Final verification: **736 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean.

On 2026-07-10, after invalidating the first multi-asset bundle batch:

- Raw lineage proved the single-instrument runner replayed same-source events
  for other symbols; those 48 bundles and derived reviews are excluded from all
  scoring and cannot support a strategy conclusion.
- `BaselineNautilusStrategy` now records `instrument_mismatch` and skips any
  SignalEvent whose symbol/venue differs from its configured InstrumentId. An
  end-to-end test confirms the mismatched signal cannot create an order.
- Full verification: **734 passed, 12 Postgres-dependent skips**; Ruff and
  `git diff --check` clean. No strategy parameter, fold, cost, gate, SourcePolicy,
  credential, testnet, or live authorization changed.

On 2026-07-10, before importing or viewing any ETHUSDT/SOLUSDT bars:

- Locked the BTC/ETH/SOL universe, three source/model fingerprints, prior-day
  causality, fold-local state initialization, four opened-data folds, mechanical
  50 USDT sizing, cost scenarios, concentration/evidence gates, absent
  2020-2023 historical reserve, and 2026-08..12 future blind.
- Added complete-month Binance archive import, deterministic multi-asset signal
  tests, strict single-asset-to-portfolio cost aggregation, raw-lineage
  exclusivity checks, and exact catalog coverage/fingerprint/alignment audit.
- Full verification: **733 passed, 12 Postgres-dependent skips** with Linux
  `TMPDIR=/tmp`; Ruff and `git diff --check` clean. The default Windows-mounted
  pytest temp directory was separately confirmed unsuitable for two existing
  POSIX mode assertions and did not indicate a product failure.
- No new-symbol market data, credentials, exchange connection, SourcePolicy
  mutation, testnet resume, or live-path action occurred.

On 2026-07-10, after the four-type opened-data tournament:

- Pre-registration commit `bcee304`; 32 clean manifests across 16 source/fold pairs, all duplicate comparisons `MATCH`, zero shorts/blockers, and 16 strict `alpha.review.v1` files.
- Aggregate base/stress PnL: mean reversion `-12.031668/-16.365120`, volatility squeeze `+15.666855/+14.340034`, volume breakout `+13.266385/+11.420167`, dual momentum `-0.773624/-1.834220` USDT.
- Volatility squeeze and volume breakout still failed: only 2/4 profitable folds, 26/37 positions, and leave-best base `-1.037924/-8.082295`. `strategy.tournament.v1` ranking is empty and recommendation is `no_candidate_progresses`.
- Strict tournament/review/manifest validation passed; full verification remains **716 passed, 12 Postgres-dependent skips**, Ruff and `git diff --check` clean. No 2020-2023/2026 data or trading-state mutation occurred.

On 2026-07-10, before running any diverse-tournament candidate on real data:

- Locked four distinct source/model fingerprints plus four opened-data folds, absent 2020-2023 historical validation, and the 2026-08..12 future blind without parameter search.
- Synthetic tests cover deterministic long/flat entry/exit behavior for mean reversion, volatility squeeze, volume/OBV breakout, and dual momentum; tournament tests cover robust pass and concentration/stress rejection.
- Full verification -> **716 passed, 12 Postgres-dependent skips**; Ruff and `git diff --check` clean.
- No tournament candidate has read real catalog results; no 2020-2023/2026 data, SourcePolicy mutation, testnet resume, credential load, or live-path action occurred.

On 2026-07-10, after stopping pullback-regime before unseen validation:

- Fixed opened-data folds on clean preregistration commit `864bf44` -> 2024 gross/base/stress `-4.254450/-18.521015/-22.087657` USDT with 73 positions and 0/5 base-positive months; 2025 `+2.517530/-15.022640/-19.407682` with 64 positions and 1/5.
- Leave-best-position-out base results were `-23.465132` and `-19.843135`; both folds had zero shorts/blockers and exact duplicate-run `MATCH` across fills, orders, positions, and signal lineage.
- Strict `alpha.review.v1` validation and clean-manifest checks passed; full verification remains **709 passed, 12 Postgres-dependent skips**, Ruff and `git diff --check` clean.
- No 2026 data was imported or read, SourcePolicy was not changed, and testnet/live paths were not started.

On 2026-07-10, before reading any 2026 market data:

- Locked `rule_pullback_regime_v1 / daily50-200-1h24-pullback-giveback1.25-v1`, the unseen 2026-01..05 validation, and the future 2026-08..12 blind window.
- Synthetic tests verify deterministic previous-day regime use, pullback recovery, bounded-giveback exit, long/flat-only output, and the new leave-best-position-out cost gate.
- Full verification -> **709 passed, 12 Postgres-dependent skips**; Ruff and `git diff --check` clean.
- No 2026 bar/result was imported or read; no credentials, exchange connection, Nautilus run, signal-store write, SourcePolicy change, or testnet resume occurred.

On 2026-07-10, after the 2024-2025 market-regime failure attribution:

- Passive analysis covered 1052640 BTCUSDT 1m bars and 60 closed trend-regime positions across the clean development and blind bundles.
- Development vs blind market return was `+44.79%` vs `-24.29%`; strategy gross PnL was `+16.191970` vs `-13.634510` USDT. Removing the best development position makes development gross/base negative.
- All 25 blind gross losers had positive MFE; 20 cleared modeled base costs while open before closing negative. The diagnosis remains research-only and does not alter the prior gate conclusion.
- Two identical analysis runs produced JSON sha256 `b3fce9b52f8d0774029903b1ad7110f2a7752e3c5b72c99cb5c9b598fa1c85ad`.
- Full verification -> **706 passed, 12 Postgres-dependent skips**; Ruff, strict finite JSON parsing, and `git diff --check` clean.

On 2026-07-10, after completing the pre-registered trend-regime blind review:

- Local BTCUSDT catalog audit -> 1052640 1m rows for 2024-2025, including 525600 rows in 2025, with 0 duplicate timestamps and 0 minute gaps.
- 2024 development screen -> gross/base/stress `+16.191970/+10.844598/+9.507755` USDT, clean and reproducible; this passed only the written continuation screen.
- Locked 2025-08..12 blind -> gross/base/stress `-13.634510/-21.238820/-23.139897` USDT, 1/5 base-positive months, 31 closed positions, 0 shorts, no lineage/blocker failures; recommendation `stop_before_testnet_resume`.
- Bundles `20260710-053944Z-1a2d2376` and `20260710-054013Z-b92c0aa3` record `git_dirty=false` and pre-registration commit `b8c7ee2`; `compare_backtests` returned `MATCH` for fills, orders, positions, and signal lineage.
- SourcePolicy was not changed, `promotion_review.py` was not called, credentials were not loaded, and testnet/live paths were not started.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **704 passed, 12 skipped** (Postgres-dependent tests skipped because the local service was unavailable).
- Ruff, strict finite `alpha.review.v1` JSON parsing, and `git diff --check` -> clean.

On 2026-07-10, after implementing the cost-sensitive alpha research surface:

- Local BTCUSDT catalog audit -> 527040 1m rows for 2024, 0 duplicates, 0 timestamp gaps.
- Existing 152-day paper bundle passive review -> gross `+4.873394`, base `-24.218490`, stress `-31.491462` USDT; recommendation `demote_to_paper_simulated_recommended` without policy mutation.
- Clean blind bundles on git `0aa37ac` -> walk-forward base/stress `-1.129677/-1.186094` USDT with 1 position; breakout base/stress `-39.313136/-47.625248` with 184 positions and 1/5 positive months; same-size buy-and-hold base `+28.752138`.
- Candidate replay verification -> `compare_backtests` `MATCH` for fills, orders, positions, and signal_lineage on both pairs; every evidence manifest records `git_dirty=false`, `AccountType.CASH`, and commit `0aa37ac`.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> **701 passed, 12 skipped** (Postgres-dependent tests skipped because the local service was unavailable).
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean.
- `git diff --check` -> clean.
- The change is research/backtest/audit only: no upstream edits, credentials, exchange calls, testnet restart, live authorization, or order-path change.

On 2026-07-10, before reading any 2025 bars:

- Locked `rule_trend_regime_v1 / ema24-96-1h-mom24-atr14x0.5-v1` and the 2025-08..2025-12 future blind window in `docs/progress/phase-2-trend-regime-hypothesis.md`.
- Added Binance archive ms/us timestamp detection; Binance's official public-data documentation records the 2025-01-01 Spot switch to microseconds.
- Full verification -> 704 passed, 12 Postgres-dependent skips; ruff and `git diff --check` clean.
- No 2025 market data or result was read while choosing this fingerprint.

On 2026-07-10, after archiving completed dashboard / passive Phase 6 history out of this status file:

- `docs/progress/phase-5-dashboard-history.md` now carries older Phase 4/5 dashboard, AgentAdvice, observability, and passive Phase 6 validation details that were making this file too long.
- `docs/project-status.md` is back to current-state guidance plus latest verification instead of a dated changelog.
- This is a docs-only maintenance change; it does not write `SignalEvent`, mutate `SourcePolicy`, load credentials, start Nautilus, connect to Binance, place orders, or authorize live trading.
- Verification for this docs-only change: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` -> clean; `git diff --check` -> clean.
- Latest code-path verification remains the 2026-07-08 dashboard hardening sequence archived in `docs/progress/phase-5-dashboard-history.md`: 144 targeted tests passed, ruff clean, frontend typecheck/build clean, and npm audit reported 0 vulnerabilities.

On 2026-07-12, after the full-code review follow-up for bridge and testnet safety:

- `SignalEvent v1` now rejects `side`/`score` conflicts at parse time (`buy` with negative score, `sell` with positive score, `flat` with non-zero score).
- `bridge write` can optionally apply ADR-002 consumer checks via `--enforce-consumer-policy` with `--allowed-sources` and `--allowed-models`.
- Long-running testnet restarts now resume `SignalStorePollingSource` from `previous_processed_until_ns + 1` and record `resume_from_ns` in runtime metadata.
- Targeted verification -> `TMPDIR=.tmp .venv/bin/python -m pytest tests/bridge/test_signal_event.py tests/bridge/test_validators.py tests/bridge/test_cli.py::test_cli_write_enforces_consumer_policy tests/bridge/test_cli.py::test_cli_write_rejects_unauthorized_with_consumer_policy tests/strategies_nautilus/test_testnet_runner_startup.py::test_long_run_restart_sets_signal_cursor_from_previous_processed_until -q` -> **75 passed**.
- `.venv/bin/ruff check` on touched bridge/testnet files -> clean.
- No upstream `freqtrade/` or `nautilus_trader/` edits; live trading remains blocked. Testnet execution path behavior is safer on restart when strategy execution is enabled.


## Recent Git Baseline

- Current baseline includes the first `freqai_linear_v1` dry-run source; run `git log --oneline --decorate -5` for the exact latest commit hash.

Agents should run `git log --oneline --decorate -5` for the latest commits instead of assuming this section is exhaustive.

# Phase 3f testnet canary session — 2026-05-19 (30-min smoke)

- **Date (UTC)**: 2026-05-19T02:31:15Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — **not** a `SourcePolicy` decision.
  This is a 30-minute integration smoke: the first time
  `BaselineNautilusStrategy` was actually registered on a running
  `TradingNode` against Binance Spot testnet under the
  `--enable-strategy-execution` double-signoff. It is the
  smaller-scope alternative to the runbook's nominal 6 h session and
  exists to prove the execution path lights up end-to-end before
  spending six wall-clock hours on a longer canary.

## 1. Scope

First real testnet canary session under ADR-008 §6.6 with
`max_run_seconds=1800` (30 min smoke) instead of the 21600 (6 h)
production value.
`apps/strategies_nautilus/runners/testnet_runner.py --long-run
--enable-strategy-execution` registered one streaming
`BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`
against Binance Spot testnet (`https://testnet.binance.vision`,
`wss://stream.testnet.binance.vision`). Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This session was launched via `infra/launchers/first-testnet-canary.py`
(operator-owned, gitignored), and **no external watchdog loop** was
started — the agent polled the bundle directly because 30 minutes does
not need automated hang detection.

Expected outcome (and observed outcome): **0 orders / 0 fills / 0
positions** because the `freqai_linear_v1` SignalStore producer is
offline. The latest signal in `data/bridge/signals.db` is from
2024-04-30; `SignalStorePollingSource.cursor_ns` was initialised to
`time.time_ns()` at strategy start (~2026-05-19), so
`store.replay(since_ns=cursor, until_ns=bar_ts)` returned `[]` on every
poll. The execution path nonetheless ran cleanly for the full window.

## 2. Run identity

- bundle: `data/testnet/20260519-023115Z-e6aeb688/`
- run_id: `20260519-023115Z-e6aeb688`
- git_commit at launch: `13b12ca96e66d1bfe1587bc6115607b48e583186`
  (`chore: gitignore infra/launchers/`)
- git_dirty: `false`
- started_at: `2026-05-19T02:31:15.086Z`
- finished_at: `2026-05-19T03:01:20.297Z`
- elapsed_seconds: `1805.210493` (max_run_seconds = 1800, drift 5.21 s)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `yKtnt9cb` (8 chars; full key never on disk)

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| strategies_registered | 1 |
| actors_registered | 0 |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | 0.1 |
| starting_balance USDT | 10000 |
| daily_pnl USDT (final) | 0 |
| account_total_usdt (last heartbeat) | 10000.0 |
| open_orders (final) | 0 |
| open_positions (final) | 0 |
| restart_sequence | 0 |
| restart_drift_detected | `false` |
| exchange_error_count | 0 |
| ws_reconnect_count | 0 |
| ws_connected (final) | `true` |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger | `null` |
| emergency_flatten_success | `null` |

## 4. Heartbeat cadence

`logs/heartbeat.jsonl` carries 60 rows, one every 30 s, matching the
1800 s budget exactly (1800 / 30 = 60).

- first heartbeat: `2026-05-19T02:31:15.138Z`
- last heartbeat: `2026-05-19T03:00:45.585Z` (35 s before shutdown)
- every row carries `ws_connected=true`, `exchange_error_count=0`,
  `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`,
  `account_total_usdt=10000.0`, `daily_pnl=0.0`, `last_bar_ns=null`
  (the strategy was subscribed to bars but the heartbeat probe in this
  smoke path does not surface `last_bar_ns` from the running node — the
  Nautilus WS log confirms bars were flowing).

## 5. §5.4 alert outcome

`logs/alerts.log` **does not exist** in the bundle. That is the
authoritative record that none of the 9 ADR-008 §5.4 alert kinds fired:

| §5.4 kind | source | fired this session |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no (cold start, `restart_sequence=0`) |
| `exchange_error_burst` | `testnet_runner.py` | no (`exchange_error_count=0 < 50`) |
| `ws_disconnected` | `testnet_runner.py` | no (`ws_connected=true` on every heartbeat) |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | no |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | n/a (watchdog not started for this 30 min smoke) |
| `emergency_flatten_started` | `emergency_flatten.py` | no |
| `emergency_flatten_completed` | `emergency_flatten.py` | no |

The runtime.log `shutdown` event likewise records
`auto_flatten_trigger=null` and `emergency_flatten_success=null`.

## 6. Runtime.log lifecycle

`logs/runtime.log` carries exactly five lines, matching the new ADR-008
§6.6 lifecycle five-tuple (the four-tuple from Phase 3f plus the new
`strategies_registered` event):

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-19T02:31:15.086Z` |
| `node_built` | `2026-05-19T02:31:15.131Z` |
| `strategies_registered` (strategies=1, actors=0) | `2026-05-19T02:31:15.137Z` |
| `node_run_invoked` (max_run_seconds=1800.0) | `2026-05-19T02:31:15.138Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-19T03:01:20.297Z` |

Build-to-register latency: 6 ms. Register-to-run latency: 1 ms.
Run-to-shutdown: 1805.16 s.

## 7. Nautilus log evidence

`/tmp/phase3f-canary/runner.stdout.log` (349 lines) was captured
outside the bundle. Key markers:

- `Account BINANCE-SPOT-master registered in cache` at
  `2026-05-19T02:31:15.381Z` (T+0.295 s after `credentials_loaded`).
- `Reconciliation for BINANCE succeeded` at
  `2026-05-19T02:31:15.665Z` (T+0.579 s).
- `BaselineNautilusStrategy: RUNNING` at `02:31:15.666Z` plus
  `SubscribeBars(BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL)` and
  `Subscribed BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL bars` —
  confirms the strategy on_start path ran without error and the WS
  subscription completed.
- `BinanceWebSocketClient: ws-client 0: Connected to
  wss://stream.testnet.binance.vision` at `02:31:15.848Z`.
- `grep -c ERROR runner.stdout.log` → **0**.
- `grep -c WARN runner.stdout.log` → **2**:
  - `BinanceSpotInstrumentProvider: Not requesting actual trade fees
    for TESTNET; all instruments will have zero fees` at 02:31:15 —
    informational, not in the §5.4 catalog. Identical to Phase 3f.
  - `BinanceUserDataWebSocketClient: Received eventStreamTerminated,
    resubscribing...` at 03:01:20.182Z — 0.114 s before the scheduled
    shutdown completed. The user-data listen key was terminated as
    `node.stop()` was running; not in the §5.4 catalog. Identical to
    Phase 3f.
- `/tmp/phase3f-canary/runner.stderr.log` → **22 bytes**, containing
  only the `nohup: ignoring input` line.
- Engine teardown was clean: `DataClient-BINANCE`, `DataEngine`,
  `RiskEngine`, `ExecClient-BINANCE`, `ExecEngine`,
  **`BaselineNautilusStrategy`**, `TESTNET_TRADER-001`, `TradingNode`
  all log `DISPOSED` at `03:01:20.296Z`–`.297Z`. The strategy disposing
  cleanly is the first time we have evidence the new
  `BaselineNautilusStrategy.on_stop` path tolerates a `close_all_positions`
  call when the portfolio is flat — no exception was raised.

## 8. Watchdog evidence

`infra/watchdog/watchdog.py` was **not** started for this 30 min
smoke. The decision was deliberate: the watchdog is the external
hang/heartbeat-loss detector designed for multi-hour unattended runs;
a 30 min smoke can be polled directly. The agent did this — the
`infra/watchdog/state.json` at retro time is still the stale Phase 3f
snapshot from 2026-05-18. The next full 6 h canary session must
re-attach the watchdog loop per §4 of
`docs/runbook-first-testnet-canary.md`.

## 9. Real order flow

This is the first session where order flow was possible. **0 orders /
0 fills / 0 positions** were produced — as expected. The bundle
contains no `orders.parquet`, `fills.parquet`, `positions.parquet`,
`account_balances.parquet`, or `signal_lineage.parquet`; the runner
only writes those sidecars when there is data, and there was none.

- `orders.parquet` row count: not written (0 orders)
- `fills.parquet` row count: not written
- `positions.parquet` row count: not written
- `account_balances.parquet` row count: not written
- `signal_lineage.parquet` row count: not written
- First order client_order_id / first fill exchange order_id: n/a
- Net PnL on closed positions USDT: 0
- Max drawdown observed during session USDT: 0
- `signal_id` round-trip: vacuously true (no fills to carry it)

The 0-order outcome is **not** a failure of the canary. It is the
expected consequence of running the strategy against an offline
SignalStore producer. The execution path (testnet connect, account
reconciliation, bar subscription, on_bar tick, strategy DISPOSED) all
fired without error — that is the only thing this smoke was designed
to validate. Real order-flow evidence still needs to come from a
later session that runs against a live FreqAI signal producer (or a
backfill helper that re-stamps catalog signals into "now").

## 10. Signal flow

- `SignalStorePollingSource(cursor_ns).start` ≈
  `1747621875138000000` (initialised from `time.time_ns()` at
  strategy build, ≈ `2026-05-19T02:31:15.138Z`).
- `SignalStorePollingSource(cursor_ns).end` =
  unchanged from `.start` (no rows popped, no cursor advance).
- rows popped during the session: **0**
- rows rejected by Authorization or SourcePolicy: 0
- rows accepted into the strategy: 0
- SignalStore `data/bridge/signals.db` snapshot at retro time:
  `rows_total=1750` for `(freqai_linear_v1, linear-mom-train20240105)`;
  `rows_last_24h=0`; `latest_ts_event_ns=1714513500000000000`
  (`2024-04-30T23:45:00Z`). The session window
  `[2026-05-19T02:31:15Z, 2026-05-19T03:01:20Z]` contained no
  matching SignalStore rows.

## 11. Decision

This retro **does not** mutate `SourcePolicy`. It records that the
ADR-008 §6.6 execution path is now end-to-end live on Binance Spot
testnet, with the new `enable_strategy_execution` double-signoff and a
streaming `SignalStorePollingSource` correctly wired into the running
`BaselineNautilusStrategy`. No order, no fill, no §5.4 alert; clean
shutdown at `max_duration`.

Recommended next moves (each still requires its own `promotion_review`
artifact when it touches `SourcePolicy`):

- **hold @ testnet_canary** — keep `freqai_linear_v1 /
  linear-mom-train20240105` at the existing policy. This smoke does
  not produce return-side evidence either way; nothing has changed
  about the source itself.
- **Build the missing piece**: a small online producer (or a "shift
  catalog signals into now" helper) so the next canary session can
  pop ≥ 1 row, drive ≥ 1 MARKET order, and produce
  `orders.parquet` / `fills.parquet` / `positions.parquet`. Only
  after that session does the project have its first real testnet
  order-flow datapoint.
- **Then** schedule a full 6 h canary with the watchdog re-attached
  per `docs/runbook-first-testnet-canary.md` §4 and write a
  proper-length session retro using
  `docs/templates/testnet-canary-session-retro.md`.

The `phase_3_not_ready` blocker continues to hard-block `live_canary`
/ `live_normal` pending Phase 4 live-trading ADRs; the
`paper_simulated → testnet_canary` promote retro from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`
remains in force.

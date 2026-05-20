# Phase 3f testnet canary session — 2026-05-19 (6h sidecar bundle)

- **Date (UTC)**: 2026-05-19T12:00:37Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Second 6 h Binance Spot testnet canary under ADR-008 §6.6, this time on
commit `c2a4186` which wires the live testnet sidecar writer.
`testnet_runner.py --long-run --enable-strategy-execution
--write-live-sidecars` registered one streaming
`BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`.
Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This session proves three things on top of the prior 6 h order-flow
session (`20260519-033558Z-e653c3e5`):

- The runner now writes all five ADR-004 sidecars in the testnet bundle
  (`orders.parquet`, `fills.parquet`, `positions.parquet`,
  `account_balances.parquet`, `signal_lineage.parquet`) with internally
  consistent counts and `signal_id` round-trip.
- The watchdog post-completion fix (`8e5fada`) holds: the external loop
  ticked 844 times after the runner stopped and never invoked emergency
  flatten.
- The runner produced a real Binance Spot testnet entry + scheduled
  shutdown close round-trip with positive realized PnL (+0.07496 USDT).

## 2. Run identity

- bundle: `data/testnet/20260519-120037Z-f1b06fd3/`
- run_id: `20260519-120037Z-f1b06fd3`
- git_commit at launch: `c2a4186363094ac4a6f7db59fdad857e68dd5668`
  (`feat(strategies_nautilus): wire ADR-008 §6.6 live testnet sidecar writer`)
- git_dirty: `false`
- started_at: `2026-05-19T12:00:37.171Z`
- finished_at: `2026-05-19T18:00:42.560Z`
- elapsed_seconds: `21605.389287` (max_run_seconds = 21600, drift 5.39 s)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `yKtnt9cb` (8 chars only; full key never on disk)

## 3. Runtime counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| write_live_sidecars | `true` |
| strategies_registered | 1 |
| actors_registered | 0 |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | 0.1 |
| starting_balance USDT | 10000 |
| daily_pnl USDT (final manifest) | 0 |
| open_orders (final manifest) | 0 |
| open_positions (final manifest) | 0 |
| restart_sequence | 0 |
| restart_drift_detected | `false` |
| exchange_error_count | 0 |
| ws_reconnect_count | 0 |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger | `null` |
| emergency_flatten_success | `null` |

## 4. Heartbeat cadence

`logs/heartbeat.jsonl` carries 720 rows, matching the 6 h budget at
30 s cadence.

- first heartbeat: `2026-05-19T12:00:37.200Z`
- last heartbeat: `2026-05-19T18:00:12.211Z`
- every row carries `ws_connected=true`, `exchange_error_count=0`,
  `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`,
  `account_total_usdt=10000.0`, `daily_pnl=0.0`

The default `TelemetryReader` does not surface the strategy's transient
Nautilus position during the run (it returns canned values); the order
and position truth is in the sidecars and the Nautilus stdout in §7 / §9.

## 5. §5.4 alert outcome

`logs/alerts.log` **does not exist** — authoritative record that none
of the 9 ADR-008 §5.4 alert kinds fired this session.

| §5.4 kind | source | fired |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no |
| `exchange_error_burst` | `testnet_runner.py` | no |
| `ws_disconnected` | `testnet_runner.py` | no |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | no |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | no |
| `emergency_flatten_started` | `emergency_flatten.py` | no |
| `emergency_flatten_completed` | `emergency_flatten.py` | no |

## 6. Runtime.log lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-19T12:00:37.171Z` |
| `node_built` | `2026-05-19T12:00:37.193Z` |
| `strategies_registered` (strategies=1, actors=0) | `2026-05-19T12:00:37.200Z` |
| `node_run_invoked` (max=21600) | `2026-05-19T12:00:37.201Z` |
| `sidecar_write` (success=true) | `2026-05-19T18:00:42.550Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-19T18:00:42.560Z` |

Build-to-register latency: 7 ms. Register-to-run latency: 1 ms.
Run-to-sidecar-write latency: 21605.349 s. Sidecar-write to shutdown
latency: 10 ms (writer-then-dispose ordering preserved).

## 7. Nautilus log evidence

`/tmp/phase3f-canary/runner.stdout.log` (kept out-of-bundle).

- `grep -c ERROR runner.stdout.log` → 0.
- `grep -c WARN runner.stdout.log` → 10. Breakdown: seven hourly
  `BinanceSpotInstrumentProvider: zero fees` informationals (one + per
  hour), two `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT` warnings on entry/exit, and one
  `BinanceUserDataWebSocketClient: eventStreamTerminated, resubscribing`
  0.3 s before scheduled shutdown — none fall into the §5.4 catalog.
- `Account BINANCE-SPOT-master registered in cache` at T+0.405 s.
- `Reconciliation for BINANCE succeeded` at T+0.688 s.
- `BaselineNautilusStrategy: RUNNING` at T+0.689 s.
- `Subscribed BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL bars` at T+0.889 s.
- `/tmp/phase3f-canary/runner.stderr.log` is 0 bytes.
- Engine teardown: `DataClient-BINANCE`, `DataEngine`, `RiskEngine`,
  `ExecClient-BINANCE`, `ExecEngine`, `BaselineNautilusStrategy`,
  `TESTNET_TRADER-001`, `TradingNode` all logged `DISPOSED` between
  18:00:42.551Z and 18:00:42.561Z.

## 8. Watchdog evidence

`/tmp/phase3f-canary/watchdog.loop.log` accumulates state across
sessions (the operator never killed the loop between the prior
`e653c3e5` canary and this one). Filtering by
`active_run_id=20260519-120037Z-f1b06fd3` isolates this session's 1560
ticks:

- `status=healthy`: 716 ticks (≈ elapsed_seconds / 30 = 720; 4 fewer
  because the watchdog read state during the brief
  startup/teardown windows when the bundle was momentarily quiet).
- `status=run_completed`: 844 ticks (every post-shutdown tick).
- `flatten_invoked=true`: 0 ticks.
- `exit_code=0`: 1560 / 1560 ticks.

The 19 historical `flatten_invoked=true` rows in the same loop log
belong to the prior `e653c3e5` canary and are documented in
`docs/retros/2026-05-19-phase-3f-testnet-canary-6h-order-flow.md`.
The post-completion bundle fix (`8e5fada`, "fix(watchdog): ignore
completed testnet runs") behaved as designed for this session.

Final `infra/watchdog/state.json`: `status=run_completed`,
`exit_code=0`, `flatten_invoked=false`, `last_heartbeat_at=2026-05-19T18:00:12.211Z`,
`alert_path=null`.

## 9. Real order flow

All five ADR-004 sidecars are present and internally consistent. The
manifest carries the same counts under `runtime.sidecar.result`.

| sidecar | rows | notes |
|---|---:|---|
| `orders.parquet` | 2 | entry + scheduled-shutdown close |
| `fills.parquet` | 2 | 1:1 with orders |
| `positions.parquet` | 1 | single round-trip |
| `account_balances.parquet` | 451 | 447 unique currencies; BTC + USDT each appear 3× because their balance changed during the run and the live Trader cache retained pre-trade / mid-position / post-trade `AccountState` snapshots for the changed currencies |
| `signal_lineage.parquet` | 3 | one per restamped SignalEvent the strategy popped |

Entry leg:

- `client_order_id`: `O-20260519-120400-001-000-1`
- `venue_order_id`: `5112724` · `trade_id`: `1713055`
- side / type / qty: `BUY MARKET 0.001 BTCUSDT.BINANCE`
- fill price: `76777.55 USDT`
- `ts_event` fill: `1779192240480000000` (`2026-05-19T12:04:00.480Z`)
- order tag: `signal_id:freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779192191762184234:buy:b9b75c9cde48`

Exit leg (scheduled `on_stop` close, `reduce_only=True`, no tag):

- `client_order_id`: `O-20260519-180037-001-000-2`
- `venue_order_id`: `5224656` · `trade_id`: `1750207`
- side / type / qty: `SELL MARKET 0.001 BTCUSDT.BINANCE`
- fill price: `76852.51 USDT`
- `ts_event` fill: `1779213637244000000` (`2026-05-19T18:00:37.244Z`)

Position close:

- `position_id`: `position-84bfbc7b30f98abfbe8920c4` (sidecar id);
  Nautilus internal id `BTCUSDT.BINANCE-BaselineNautilusStrategy-000`
- `avg_px_open=76777.55` / `avg_px_close=76852.51`
- `realized_pnl=+0.07496 USDT` (`realized_return=0.00098`, +0.098 %)
- `commissions=['0.00000000 BTC', '0.00000000 USDT']` (testnet fee-free)
- `duration_ns=21396764000000` (5 h 56 min 36 s)
- `signal_ids` = entry leg's signal_id
- `unrealized_pnl=0.0` (FLAT after close)

`signal_id` round-trip: every fill row that originated from a
`BaselineNautilusStrategy` decision carries `signal_id`; the
scheduled-shutdown close fill carries an empty `signal_id` because
`on_stop()`'s `close_all_positions` is not triggered by a signal —
documented as expected behaviour in the prior session retro and
unchanged here.

Net session result: 2 orders / 2 fills / 1 closed position, PnL
+0.07496 USDT (`+0.00075 %` vs starting balance 10000 USDT), 0 rejects.
The starting balance 10000 USDT is the runner's policy reference, not
the testnet faucet's actual quote; the faucet wallet held ~86 774 USDT
during this run, which is also visible in `account_balances.parquet`.

## 10. Signal flow

The active signals were produced by
`apps.strategies_freqtrade.research.wall_clock_signal_replay`
2 min 40 s before runner start, preserving `source=freqai_linear_v1`,
`model_version=linear-mom-train20240105`, and recording the original
historical rows under `metadata.wall_clock_replay`.

- restamp generated_count: 3 (all `side=buy`, `ttl_seconds=900`)
- restamp first/last ts_event: `2026-05-19T12:03:11.762Z` /
  `2026-05-19T12:05:11.762Z`
- `signal_lineage.parquet`: 3 rows, all `decision=target_long`,
  `source=freqai_linear_v1`,
  `model_version=linear-mom-train20240105`
- rows that produced a real order: 1 (the first BUY; the strategy was
  flat at decision time)
- rows that became no-op `already_target_long`: 2 (signals 2 and 3
  arrived while the strategy was already long); these rows have empty
  `order_ids` / `fill_ids` / `position_id` in the sidecar, which is the
  expected lineage shape for already-on-side decisions
- rows rejected by Authorization or SourcePolicy: 0
- `signal_lag_exceeded_threshold` did not fire — the longest pop lag
  was ~48 s (signal `ts_event` → 1 min bar close at which the strategy
  evaluates), under the 60 s default

## 11. Decision

This retro **does not** mutate `SourcePolicy`. Recommended next
decision (must still go through `promotion_review.py`):
**hold @ testnet_canary**.

Reasons:

- Positive: real `SignalEvent v1` → Nautilus → Binance Spot testnet
  MARKET order/fill/position lifecycle is proven for a second
  consecutive session, this time with all ADR-004 sidecars on disk.
- Positive: scheduled `max_duration` shutdown submitted and filled the
  strategy close order, disposed all 8 engines cleanly, and the
  external watchdog cleanly transitioned to `status=run_completed`
  without any post-run false positives.
- Positive: closing PnL is positive (+0.07496 USDT) and the sidecar
  counts agree with `runtime.sidecar.result` in the manifest.
- Negative: nothing surfaced; sample size is still tiny
  (2 fills / 1 closed position) and cannot speak to alpha.

The follow-up `promotion_review` retro should use this session retro as
`--testnet-runbook-signoff-path` when staying at `testnet_canary`.

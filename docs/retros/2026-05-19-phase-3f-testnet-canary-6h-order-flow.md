# Phase 3f testnet canary session — 2026-05-19 (6h order flow)

- **Date (UTC)**: 2026-05-19T03:35:58Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Six-hour Binance Spot testnet canary with
`testnet_runner.py --long-run --enable-strategy-execution`, one
registered `BaselineNautilusStrategy`, and a
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`.
The signal input was produced by the wall-clock restamp helper from
already-reviewed historical `SignalEvent v1` rows. Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This session proves live testnet order flow for the bridge:
SignalStore row -> SourcePolicy-authorized Nautilus strategy ->
RiskEngine -> Binance Spot testnet MARKET order -> fill -> strategy
shutdown close. It also exposed a watchdog lifecycle bug: after the
runner completed normally, the still-running watchdog treated the final
heartbeat silence as `heartbeat_lost` and repeatedly invoked emergency
flatten. That post-run behavior was fixed after this retro by making
the watchdog treat a completed `run_manifest.json` as terminal.

## 2. Run identity

- bundle: `data/testnet/20260519-033558Z-e653c3e5/`
- run_id: `20260519-033558Z-e653c3e5`
- git_commit at launch: `f007f1ae370255450d7c384625fb26295781d836`
  (`feat(freqai): restamp signals for testnet canary`)
- git_dirty: `false`
- started_at: `2026-05-19T03:35:58.056Z`
- finished_at: `2026-05-19T09:36:03.260Z`
- elapsed_seconds: `21605.204385` (max_run_seconds = 21600, drift 5.20 s)
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

- first heartbeat: `2026-05-19T03:35:58.101Z`
- last heartbeat: `2026-05-19T09:35:33.227Z`
- every row carries `ws_connected=true`, `exchange_error_count=0`,
  `ws_reconnect_count=0`, `open_orders=0`, `open_positions=0`,
  `account_total_usdt=10000.0`, and `daily_pnl=0.0`

The heartbeat telemetry currently does not surface the strategy's
temporary Nautilus position during the run; the order/position truth is
in the Nautilus stdout events below.

## 5. §5.4 alert outcome

The runner itself completed with `shutdown_reason=max_duration` and no
auto-flatten trigger. `logs/alerts.log` was created only after the
runner had already stopped, because the external watchdog loop remained
active and repeatedly interpreted post-shutdown heartbeat silence as a
fault. The file has 57 lines:

| §5.4 kind | source | fired this session |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no |
| `exchange_error_burst` | `testnet_runner.py` | no |
| `ws_disconnected` | `testnet_runner.py` | no |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | no |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | yes (19, post-run false positives) |
| `emergency_flatten_started` | `emergency_flatten.py` | yes (19, watchdog-triggered) |
| `emergency_flatten_completed` | `emergency_flatten.py` | yes (19, all `success=true`) |

The first watchdog-triggered emergency flatten reported
`closed_positions=1`; subsequent calls reported `closed_positions=0`.
The final `emergency_flatten.json` records `success=true`,
`residual_orders=[]`, `residual_positions=[]`, and final BTC free
balance `0E-8`. This is testnet-only fallout from the watchdog lifecycle
bug, not a strategy-originated order.

## 6. Runtime.log lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-19T03:35:58.056Z` |
| `node_built` | `2026-05-19T03:35:58.094Z` |
| `strategies_registered` (strategies=1, actors=0) | `2026-05-19T03:35:58.100Z` |
| `node_run_invoked` (max_run_seconds=21600.0) | `2026-05-19T03:35:58.101Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-19T09:36:03.260Z` |

Build-to-register latency: 6 ms. Register-to-run latency: 1 ms.
Run-to-shutdown: 21605.16 s.

## 7. Nautilus log evidence

`/tmp/phase3f-canary/runner.stdout.log` was captured outside the
bundle.

- `grep -c ERROR runner.stdout.log` -> 0.
- `grep -c WARN runner.stdout.log` -> 10. These were the hourly
  testnet zero-fee informational warning, two `RiskEngine: Cannot check
  MARKET order risk: no prices for BTCUSDT.BINANCE` warnings for MARKET
  entry/exit, and the normal user-data `eventStreamTerminated` message
  during shutdown.
- `Account BINANCE-SPOT-master registered in cache` at
  `2026-05-19T03:35:58.464Z`.
- `Reconciliation for BINANCE succeeded` at
  `2026-05-19T03:35:58.833Z`.
- `/tmp/phase3f-canary/runner.stderr.log` is 0 bytes.
- Engine teardown was clean: `DataClient-BINANCE`, `DataEngine`,
  `RiskEngine`, `ExecClient-BINANCE`, `ExecEngine`,
  `BaselineNautilusStrategy`, `TESTNET_TRADER-001`, and `TradingNode`
  all logged `DISPOSED` by `2026-05-19T09:36:03.260Z`.

## 8. Watchdog evidence

`/tmp/phase3f-canary/watchdog.loop.log` recorded 719 healthy checks
while the runner was active, then 19 post-run `flatten_invoked=true`
checks after the final heartbeat aged past the 90 s timeout. The last
post-run state before the fix was `status=heartbeat_stale`,
`exit_code=4`, and `flatten_returncode=0`. After patching
`infra/watchdog/watchdog.py`, the same completed bundle returns:

```json
{
  "exit_code": 0,
  "flatten_invoked": false,
  "status": "run_completed"
}
```

## 9. Real order flow

The runner does not yet write live testnet `orders.parquet`,
`fills.parquet`, `positions.parquet`, `account_balances.parquet`, or
`signal_lineage.parquet`; the durable order evidence for this session
is the Nautilus stdout plus exchange order/trade IDs.

Strategy-originated flow:

- Entry:
  - `OrderInitialized`: `2026-05-19T03:37:00.306754878Z`
  - client_order_id: `O-20260519-033700-001-000-1`
  - side/type/quantity: `BUY MARKET 0.00100000 BTCUSDT.BINANCE`
  - signal tag:
    `signal_id:freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779161800131715782:buy:0513fbb10921`
  - venue_order_id: `4981384`
  - trade_id: `1676533`
  - fill price: `76778.75 USDT`
- Exit on scheduled shutdown:
  - `OrderInitialized`: `2026-05-19T09:35:58.102442145Z`
  - client_order_id: `O-20260519-093558-001-000-2`
  - side/type/quantity: `SELL MARKET 0.00100000 BTCUSDT.BINANCE`
  - venue_order_id: `5070773`
  - trade_id: `1700032`
  - fill price: `76758.75 USDT`
- `PositionClosed`: `2026-05-19T09:35:58.194195884Z`
  - position_id: `BTCUSDT.BINANCE-BaselineNautilusStrategy-000`
  - avg_px_open: `76778.75`
  - avg_px_close: `76758.75`
  - realized_pnl: `-0.02000000 USDT`

The strategy-originated order/fill count is therefore 2 orders, 2 fills,
1 opened position, and 1 closed position. `signal_id` round-tripped on
the entry order/fill; the scheduled close is an `on_stop()` flatten and
does not carry a signal tag.

## 10. Signal flow

The active signal was produced by
`apps.strategies_freqtrade.research.wall_clock_signal_replay` shortly
before runner start, preserving `source=freqai_linear_v1` and
`model_version=linear-mom-train20240105` with
`metadata.wall_clock_replay` linking back to the reviewed historical row.

- rows accepted into the strategy: 1 (the first restamped BUY)
- rows that became no-op due already-target-long: at least the remaining
  restamped BUY rows in the session window
- rows rejected by Authorization or SourcePolicy: 0 observed
- first accepted signal ts_event: `1779161800131715782`

Because live testnet sidecars are not written yet, exact
`SignalStorePollingSource(cursor_ns)` start/end and per-row lineage
counts are not persisted. Adding a live sidecar writer remains a
follow-up before relying on parquet-based promotion evidence.

## 11. Decision

This retro does not mutate `SourcePolicy`. Recommended next decision:
**hold @ testnet_canary**, but only after recording the watchdog issue
as an operational fix and continuing with another clean canary.

Reasons:

- Positive: real SignalEvent v1 -> Nautilus -> Binance Spot testnet
  MARKET order/fill/position lifecycle is proven.
- Positive: scheduled `max_duration` shutdown submitted and filled the
  strategy close order, then disposed all engines cleanly.
- Negative: the watchdog loop produced post-run false positives and
  repeated emergency flatten calls after a normal shutdown.
- Negative: live testnet parquet sidecars and durable signal lineage are
  still missing; current evidence depends on stdout and exchange IDs.


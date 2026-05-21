# Phase 3f testnet canary session — 2026-05-20 (6h live telemetry)

- **Date (UTC)**: 2026-05-20T09:53:50Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Six-hour Binance Spot testnet canary after the 2026-05-20 startup
`ws_connected` false-positive fix and the signal-lag threshold update
to 120 s. The operator ran from the control machine only. The launcher
registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`
and enabled live telemetry plus live sidecar writing.

Authorized policy:
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This session proves that the live telemetry reader can run a full 6 h
window without the two prior abort causes:

- startup `ws_connected=false` was suppressed until first real connect
- `signal_lag_exceeded_threshold` did not fire with a 120 s threshold

## 2. Run identity

- bundle: `data/testnet/20260520-095350Z-6414ef0d/`
- run_id: `20260520-095350Z-6414ef0d`
- git_commit at launch: `5f273b9a281560b03a7d0f02fd4e5af75dc33f42`
  (`docs(retros): record signal lag canary abort`)
- git_dirty: `false`
- started_at: `2026-05-20T09:53:50.478Z`
- finished_at: `2026-05-20T15:53:55.767Z`
- elapsed_seconds: `21605.289523` (max_run_seconds = 21600, drift 5.29 s)
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
| final account_total_usdt | 86775.49416 |
| daily_pnl USDT (telemetry) | 76775.49416 |
| exchange_error_count | 0 |
| ws_reconnect_count | 0 |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger | `null` |
| emergency_flatten_success | `null` |
| signal_lag_threshold_seconds | 120 |

Manifest nuance: `runtime.open_positions=1` is the last monitor-loop
sample before `BaselineNautilusStrategy.on_stop()` closed the testnet
position. The post-run sidecar is the final order/position authority and
records the position as `FLAT`. A follow-up code patch makes future
manifests use the post-run sidecars for final `open_orders` /
`open_positions`.

## 4. Heartbeat cadence

`logs/heartbeat.jsonl` carries 720 rows, matching the 6 h budget at
30 s cadence.

- first heartbeat: `2026-05-20T09:53:50.500Z`
- last heartbeat: `2026-05-20T15:53:38.443Z`
- max heartbeat gap: 30.043 s
- every row carries `ws_connected=true`
- every row carries `exchange_error_count=0`
- every row carries `ws_reconnect_count=0`

The final heartbeats still show `open_positions=1` for the same reason
as the manifest: they are emitted before the scheduled `on_stop` close.

## 5. §5.4 alert outcome

`logs/alerts.log` **does not exist** — authoritative record that none
of the 9 ADR-008 §5.4 alert kinds fired during this session.

| §5.4 kind | source | fired this session |
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
| `credentials_loaded` | `2026-05-20T09:53:50.478Z` |
| `node_built` | `2026-05-20T09:53:50.499Z` |
| `strategies_registered` (strategies=1, actors=0) | `2026-05-20T09:53:50.499Z` |
| `node_run_invoked` (max=21600) | `2026-05-20T09:53:50.501Z` |
| `sidecar_write` (success=true) | `2026-05-20T15:53:55.766Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-20T15:53:55.767Z` |

Sidecar write completed 1 ms before the shutdown record. Engine teardown
completed cleanly at `2026-05-20T15:53:55.767Z`.

## 7. Nautilus log evidence

`/tmp/phase3f-canary/runner.stdout.log` was kept out of the bundle.

- `grep -c ERROR runner.stdout.log` -> 0.
- `grep -c WARN runner.stdout.log` -> 10. Breakdown: seven testnet
  zero-fee informationals, two `RiskEngine: Cannot check MARKET order
  risk: no prices for BTCUSDT.BINANCE` warnings on entry/exit, and one
  `BinanceUserDataWebSocketClient: Received eventStreamTerminated`
  message 0.225 s before scheduled shutdown. None fall into the ADR-008
  §5.4 alert catalog.
- `Account BINANCE-SPOT-master registered in cache` at
  `2026-05-20T09:53:50.740Z`.
- `Reconciliation for BINANCE succeeded` at
  `2026-05-20T09:53:51.021Z`.
- `BaselineNautilusStrategy: RUNNING` at
  `2026-05-20T09:53:51.021Z`.
- `Subscribed BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL bars` at
  `2026-05-20T09:53:51.181Z`.
- `/tmp/phase3f-canary/runner.stderr.log` is 0 bytes.
- `DataClient-BINANCE`, `DataEngine`, `RiskEngine`, `ExecClient-BINANCE`,
  `ExecEngine`, `BaselineNautilusStrategy`, `TESTNET_TRADER-001`, and
  `TradingNode` all logged `DISPOSED`.

## 8. Watchdog evidence

The control-machine watchdog loop was attached after startup, at
`2026-05-20T09:56:24.454Z`, and stopped manually after result review on
2026-05-21.

Filtering `/tmp/phase3f-canary/watchdog.loop.log` by
`active_run_id=20260520-095350Z-6414ef0d`:

- total ticks: 1920
- `status=healthy`: 713
- `status=run_completed`: 1207
- `flatten_invoked=true`: 0
- non-zero exit codes: 0
- final state: `status=run_completed`, `exit_code=0`,
  `flatten_invoked=false`, `last_heartbeat_at=2026-05-20T15:53:38.443Z`

## 9. Real order flow

All five ADR-004 sidecars are present and internally consistent. The
manifest carries the same sidecar counts under `runtime.sidecar.result`.

| sidecar | rows | notes |
|---|---:|---|
| `orders.parquet` | 2 | entry + scheduled-shutdown close |
| `fills.parquet` | 2 | 1:1 with orders |
| `positions.parquet` | 1 | single round-trip, final side `FLAT` |
| `account_balances.parquet` | 451 | BTC and USDT appear multiple times because balances changed during the run |
| `signal_lineage.parquet` | 490 | one row per restamped `SignalEvent` popped |

Entry leg:

- `client_order_id`: `O-20260520-095400-001-000-1`
- `venue_order_id`: `5452942` · `trade_id`: `1807634`
- side / type / qty: `BUY MARKET 0.001 BTCUSDT.BINANCE`
- fill price: `77495.13 USDT`
- `ts_event` fill: `1779270840580999936`
- order tag:
  `signal_id:freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779270839458874869:buy:acb2a9f85c17`

Exit leg (scheduled `on_stop` close, `reduce_only=True`, no signal tag):

- `client_order_id`: `O-20260520-155350-001-000-2`
- `venue_order_id`: `5551888` · `trade_id`: `1835995`
- side / type / qty: `SELL MARKET 0.001 BTCUSDT.BINANCE`
- fill price: `77516.50 USDT`
- `ts_event` fill: `1779292430651000064`

Position close:

- sidecar `position_id`: `position-54725315ce5ca3b107741d28`
- `avg_px_open=77495.13` / `avg_px_close=77516.50`
- `realized_pnl=+0.02137 USDT`
- `realized_return=0.00028` (+0.028%)
- `commissions=['0.00000000 BTC', '0.00000000 USDT']`
- `duration_ns=21590070000128` (5 h 59 min 50 s)
- final `side=FLAT`, `quantity=0.0`, `unrealized_pnl=0.0`

Final account-balance sidecar rows for changed currencies include
`BTC=0`, `USDT=86775.47150`, confirming no residual BTC inventory in
the sidecar snapshot.

## 10. Signal flow

The active signals were produced by
`apps.strategies_freqtrade.research.wall_clock_signal_replay` shortly
before runner start:

- generated_count: 480
- interval_seconds: 45
- side: `buy`
- first_ts_event: `1779270997375927463`
- last_ts_event: `1779292552375927463`

`signal_lineage.parquet` records 490 rows for this run. All rows have
`decision=target_long`; one row carries `order_ids` / `fill_ids` /
`position_id` (the entry while flat), and the rest are no-op target-long
decisions while already long. Max observed lineage lag
(`ts_decision - ts_event`) was 52.623 s, below the 120 s advisory
threshold.

## 11. Decision

This retro does not mutate `SourcePolicy`. It records a clean operational
session and supports continuing to **hold @ testnet_canary** for
`freqai_linear_v1 / linear-mom-train20240105` under the already-signed
testnet policy.

Do not run `promotion_review.py hold @ testnet_canary` as routine
ratification for this session: the project status explicitly treats the
canary retro as the operational record, and `promotion_review.py` should
only be opened for an actual policy/stage decision.

Follow-up:

1. Keep collecting testnet canary sessions if more operational evidence
   is desired.
2. Do not proceed to live trading without a separate live-risk ADR and
   explicit `promotion_review` decision.
3. Keep the manifest final-open-state patch so future runs report final
   `open_orders/open_positions` from post-run sidecars.

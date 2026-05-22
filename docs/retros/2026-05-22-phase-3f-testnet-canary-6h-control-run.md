# Phase 3f testnet canary session — 2026-05-22 6 h control run

- **Date (UTC)**: 2026-05-22T03:01:42Z – 2026-05-22T09:01:48Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Real 6 h Binance Spot testnet canary under ADR-008 §6.6, run on the
control machine from a long-lived foreground Codex tool session. The runner
registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`,
with live telemetry, live sidecar writing, Prometheus textfile metrics, and
the external watchdog attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This session reuses the hardened launch flow from commit `0116b89`: no
one-shot `nohup ... &`, no pre-existing future wall-clock replay rows, and no
overlapping replay stream.

## 2. Run Identity

- bundle: `data/testnet/20260522-030142Z-36922497/`
- run_id: `20260522-030142Z-36922497`
- git_commit at launch: `63ae0a16b9d9247d6b3dde6c3b4f057f5b54f870`
- git_dirty: `false`
- started_at: `2026-05-22T03:01:42.865Z`
- finished_at: `2026-05-22T09:01:48.282Z`
- elapsed_seconds: `21605.416622` (max_run_seconds = `21600`)
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`
- credentials_key_prefix: `yKtnt9cb`

## 3. Runtime Counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| write_live_sidecars | `true` |
| strategies_registered | `1` |
| actors_registered | `0` |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | `0.1` |
| starting_balance USDT | `10000.0` |
| daily_pnl USDT (final telemetry) | `76775.09919` |
| account_total_usdt (final telemetry) | `86775.09919` |
| open_orders (final manifest) | `0` |
| open_positions (final manifest) | `0` |
| open_state_source | `live_sidecars` |
| restart_sequence | `0` |
| restart_drift_detected | `false` |
| exchange_error_count | `0` |
| ws_reconnect_count | `0` |
| shutdown_reason | `max_duration` |
| auto_flatten_trigger | `null` |
| emergency_flatten_success | `null` |

The `daily_pnl` value keeps the known testnet faucet-account caveat:
telemetry anchors from `starting_balance=10000`, while the testnet wallet
reports about `86775 USDT`.

## 4. Heartbeat Cadence

- first heartbeat: `2026-05-22T03:01:42.912Z`
- last heartbeat: `2026-05-22T09:01:14.648Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.175` s
- `ws_connected`: `true x 719`
- `ws_reconnect_count`: `0 x 719`
- `exchange_error_count`: `0 x 719`
- open_orders histogram: `0 x 719`
- open_positions histogram: `0 x 5`, `1 x 714`

The last heartbeat sampled before the scheduled close fill. The manifest's
final open state is therefore sourced from live sidecars and records
`open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`.

## 5. §5.4 Alert Outcome

`logs/alerts.log` does not exist. That is the authoritative record that none
of the 9 alert paths fired.

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

## 6. Runtime.log Lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-22T03:01:42.865Z` |
| `node_built` | `2026-05-22T03:01:42.911Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-22T03:01:42.912Z` |
| `node_run_invoked` | `2026-05-22T03:01:42.920Z` |
| `sidecar_write` (success=true) | `2026-05-22T09:01:48.279Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-22T09:01:48.282Z` |

Sidecar write completed 3 ms before the shutdown event.

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- `Account BINANCE-SPOT-master registered in cache` and exchange
  reconciliation completed during startup.
- All engines disposed cleanly at shutdown.

WARN classification:

- 7 x `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals.
- 2 x `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` on the entry and scheduled close market orders.
- 1 x `BinanceUserDataWebSocketClient: eventStreamTerminated` during teardown.

These match previously documented Phase 3 canary informationals and do not
map to ADR-008 §5.4 alert kinds.

## 8. Watchdog Evidence

The watchdog loop was attached after the bundle was created and stopped after
the completed manifest was written.

- `status=healthy`: `717`
- `status=run_completed`: `14`
- `flatten_invoked=true`: `0`
- final state before watchdog shutdown:
  `status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
  `alert_path=null`, `last_heartbeat_at=2026-05-22T09:01:14.648Z`

The final heartbeat age exceeded the normal timeout after shutdown, but the
completed manifest made the watchdog report `run_completed` instead of
`heartbeat_lost`.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `477`
- Net realized PnL on closed position: `-0.46798 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 77719.74 USDT`
- client_order_id `O-20260522-030400-001-000-1`
- venue_order_id `6058323`
- trade_id `1948557`
- fill ts_event `2026-05-22T03:04:00.296000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779419032044800168:buy:4fdee14d69db`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 77251.76 USDT`
- client_order_id `O-20260522-090142-001-000-2`
- venue_order_id `6128708`
- trade_id `1964943`
- fill ts_event `2026-05-22T09:01:43.006000Z`

Position close:

- sidecar position_id `position-d629f7e0ae9f3599ceec95fe`
- `avg_px_open=77719.74` / `avg_px_close=77251.76`
- `realized_pnl=-0.46798 USDT`
- `realized_return=-0.00602` (-0.602%)
- final `side=FLAT`, `quantity=0.0`, `unrealized_pnl=0.0`
- final sidecar account snapshots include `BTC=0` and `USDT=86775.10838`.

Traceability:

- entry order carries the `signal_id` tag;
- entry fill carries the same `signal_id`;
- the closed position carries the source `signal_id`;
- the scheduled close fill has no signal tag, as expected for a time-based
  reduce-only close.

## 10. Signal Flow

Before launch, the future replay check returned
`future_wall_clock_replay_rows=0`. The full replay command then wrote 480
future rows:

- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1779419032044800168` (`2026-05-22T03:03:52.044800Z`)
- last_ts_event:
  `1779440587044800168` (`2026-05-22T09:03:07.044800Z`)
- interval_seconds: `45`
- side: `buy`

The successful session consumed 477 rows before shutdown:

- lineage rows: `477`
- lineage `ts_event` range:
  `2026-05-22T03:03:52.044800Z` –
  `2026-05-22T09:00:52.044800Z`
- lineage decision counts: `target_long x 477`
- lineage rows with non-empty `order_ids` / `fill_ids` / `position_id`: `1`

Only the first signal opened the long position; all later target-long signals
were no-ops while already long. `logs/heartbeat.jsonl` did not persist a
`last_signal_ns` key on heartbeat rows, but the sidecar lineage is complete
and no `signal_lag_exceeded_threshold` alert fired.

## 11. Observability Evidence

During the run, node_exporter exposed the new run_id in all
`trader_canary_*` textfile metrics, including
`trader_canary_heartbeat_timestamp_seconds{run_id="20260522-030142Z-36922497"}`.
Prometheus returned the series while the run was active. After shutdown,
`PrometheusTextfileWriter.cleanup()` removed
`data/observability/textfile/testnet-20260522-030142Z-36922497.prom`, so an
instant Prometheus query no longer returns a current sample.

Loki query for `{job="testnet_heartbeat", run_id="20260522-030142Z-36922497"}`
returned the heartbeat stream; `{job="testnet_alerts", run_id=...}` returned
no streams.

## 12. Decision

This retro does not mutate `SourcePolicy`.

Recommended next decision:

- **hold @ testnet_canary** — clean 6 h session, real entry/exit order flow,
  no ADR-008 §5.4 alerts, no exchange/runtime errors, no WS reconnects, final
  sidecar state flat, and watchdog completed without emergency flatten.

Do not proceed to live trading without a separate live-risk ADR and the
ADR-001 capital ladder gate.


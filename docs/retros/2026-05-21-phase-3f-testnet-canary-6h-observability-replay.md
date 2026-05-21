# Phase 3f testnet canary session — 2026-05-21 6 h observability replay

- **Date (UTC)**: 2026-05-21T10:26:31Z – 2026-05-21T16:26:37Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Real 6 h Binance Spot testnet canary under ADR-008 §6.6, run on the
control machine. `testnet_runner.py --long-run --enable-strategy-execution
--write-live-sidecars` registered one streaming `BaselineNautilusStrategy`
backed by `SignalStorePollingSource(freqai_linear_v1 /
linear-mom-train20240105)`.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This run validates the full path requested after the observability hardening:
trading + observation + alerting + replay evidence. It does not move the
source beyond `hold @ testnet_canary`.

## 2. Run Identity

- bundle: `data/testnet/20260521-102631Z-ea999625/`
- run_id: `20260521-102631Z-ea999625`
- git_commit at launch: `10158665b3c4ce83cb9b0f1e0e5db5ba301acb4e`
- git_dirty: `false`
- started_at: `2026-05-21T10:26:31.876Z`
- finished_at: `2026-05-21T16:26:37.212Z`
- elapsed_seconds: `21605.3354` (max_run_seconds = `21600`)
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
| daily_pnl USDT (final telemetry) | `76775.55249` |
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

The `daily_pnl` value keeps the same known testnet faucet-account caveat as
the 2026-05-21 30 min smoke: live telemetry initializes the UTC-day anchor
from `starting_balance=10000`, while the testnet wallet reports about
`86775 USDT`.

## 4. Heartbeat Cadence

- first heartbeat: `2026-05-21T10:26:31.924Z`
- last heartbeat: `2026-05-21T16:26:03.877Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- ws_connected throughout: `true` (`719 true`)
- `ws_reconnect_count`: `0` in all heartbeat rows
- `exchange_error_count`: `0` in all heartbeat rows
- open_orders histogram: `0 x 719`
- open_positions histogram: `0 x 3`, `1 x 716`

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

The 480-signal replay window avoided the expected warning seen in the 30 min
smoke, where the shorter replay preset ended before the run window.

## 6. Runtime.log Lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-21T10:26:31.876Z` |
| `node_built` | `2026-05-21T10:26:31.923Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-21T10:26:31.923Z` |
| `node_run_invoked` | `2026-05-21T10:26:31.928Z` |
| `sidecar_write` (success=true) | `2026-05-21T16:26:37.210Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-21T16:26:37.212Z` |

Build-to-run latency: about `0.052` s from credentials load to
`node_run_invoked`. Sidecar write completed 2 ms before shutdown.

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- `Account BINANCE-SPOT-master registered in cache` at `10:26:32.319Z`
  (T+0.443 s).
- `Reconciliation for BINANCE succeeded` at `10:26:32.802Z` (T+0.926 s).
- All engines disposed cleanly between `16:26:37.211Z` and
  `16:26:37.212Z`.

WARN classification:

- 7 x `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals
  (startup plus hourly refreshes).
- 2 x `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` on the entry and scheduled close market orders.
- 1 x `BinanceUserDataWebSocketClient: eventStreamTerminated` during teardown,
  0.23 s before final disposal.

These match previously documented Phase 3 canary informationals and do not
map to ADR-008 §5.4 alert kinds.

## 8. Watchdog Evidence

The watchdog loop and append-only history both recorded 720 ticks for this
run:

- `status=healthy`: `717`
- `status=run_completed`: `3`
- `flatten_invoked=true`: `0`
- final `infra/watchdog/state.json`: `status=run_completed`, `exit_code=0`,
  `flatten_invoked=false`, `alert_path=null`,
  `last_heartbeat_at=2026-05-21T16:26:03.877Z`

The final heartbeat age exceeded the normal 90 s timeout after shutdown, but
the completed `run_manifest.json` terminal state correctly made the watchdog
report `run_completed` instead of `heartbeat_lost`.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `955`
- First fill ts_event: `2026-05-21T10:28:00.305000Z`
- Last fill ts_event: `2026-05-21T16:26:31.982000Z`
- Net realized PnL on closed position: `-0.18422 USDT`
- Account-total max drawdown observed after account initialization:
  approximately `2.36643 USDT` (`0.00273%`)

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 77326.10 USDT`
- client_order_id `O-20260521-102800-001-000-1`
- venue_order_id `5820973`
- trade_id `1889152`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779359245017939454:buy:85f1cbfc4307`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 77141.88 USDT`
- client_order_id `O-20260521-162631-001-000-2`
- venue_order_id `5917339`
- trade_id `1912144`
- final position `FLAT`

Traceability:

- entry order carries the `signal_id` tag;
- entry fill carries the same `signal_id`;
- the closed position carries the source `signal_id` in `positions.signal_ids`;
- the scheduled close fill has no signal tag, as expected for a time-based
  reduce-only close.

## 10. Signal Flow

- lineage rows: `955`
- lineage `ts_event` range:
  `2026-05-21T10:27:25.017940Z` –
  `2026-05-21T16:25:55.017940Z`
- lineage decision counts: `target_long x 955`
- lineage rows with non-empty `order_ids` / `fill_ids` / `position_id`: `1`

There was one operator false start before this foreground run: an initial
one-shot shell `nohup ... &` launch was cleaned up by the tool environment
after it connected, before the first signal was due. It wrote no orders,
fills, sidecars, or alerts (`data/testnet/20260521-102449Z-114b7c91/` has
one heartbeat only). A second 480-row future replay was then written
immediately before this foreground run. As a result, the successful session
consumed an overlapped buy-only replay stream and produced `955` lineage
rows. This did not create repeated exposure: only the first signal opened
the long position; the remaining target-long signals were no-ops while
already long, and no signal-lag alert fired.

## 11. Observability Evidence

- node_exporter exposed
  `trader_canary_info{kind="testnet",run_id="20260521-102631Z-ea999625"} 1`
  while the run was active.
- Promtail/Loki query for
  `{job="testnet_heartbeat", run_id="20260521-102631Z-ea999625"}` returned
  `719` heartbeat rows over the 7 h query window.
- Promtail/Loki query for
  `{job="testnet_alerts", run_id="20260521-102631Z-ea999625"}` returned no
  streams.
- Textfile metrics were cleaned up at shutdown by
  `PrometheusTextfileWriter.cleanup()`, so an instant Prometheus query after
  shutdown has no current `trader_canary_*` series for this run. Runtime
  observation remains supplementary; the bundle is still the promotion source
  of truth.

## 12. Decision

This retro does not mutate `SourcePolicy`.

Recommended next decision:

- **hold @ testnet_canary** — clean 6 h session, real entry/exit order flow,
  no ADR-008 §5.4 alerts, no exchange/runtime errors, no WS reconnects, final
  sidecar state flat, and watchdog completed without emergency flatten.

Do not run a routine `promotion_review.py hold @ testnet_canary` unless an
actual policy decision is needed. Do not proceed to live trading without a
separate live-risk ADR and the ADR-001 capital ladder gates.

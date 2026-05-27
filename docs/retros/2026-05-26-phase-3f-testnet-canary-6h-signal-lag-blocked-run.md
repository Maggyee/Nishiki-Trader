# Phase 3f testnet canary session - 2026-05-26 signal-lag blocked run

- **Date (UTC)**: 2026-05-26T09:19:17Z - 2026-05-26T15:19:23Z
- **Operator**: nishiki
- **ADR**: [ADR-008 Section 6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro - not a `SourcePolicy` decision.

## 1. Scope

Real 6 h Binance Spot testnet canary under ADR-008 Section 6.6, run on the
control machine from long-lived foreground Codex tool sessions. The runner
registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`,
with live telemetry, live sidecar writing, and the external watchdog
attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This run completed `max_duration`, closed the testnet position, and wrote
matching sidecars. It is **not** accepted as clean canary evidence because one
ADR-008 advisory alert fired:

```text
signal_lag_exceeded_threshold
```

The alert root cause was operational timing: the wall-clock replay stream was
written too far before the runner reached `node_run_invoked`, so the 480-row
stream ended before the 6 h session shutdown. This reset the strict continuity
streak to `0/14` for the reviewed window.

## 2. Run Identity

- bundle: `data/testnet/20260526-091917Z-1acd81fc/`
- run_id: `20260526-091917Z-1acd81fc`
- git_commit at launch: `2e37a2a8b1eeaa88ceb8d4777083dc4812ac489b`
- git_dirty: `false`
- manifest_sha256:
  `545d3b40ba8ae04de84d4c7c47454dd2dc07558ba74f0dbd314ad89e67c8be06`
- started_at: `2026-05-26T09:19:17.640Z`
- finished_at: `2026-05-26T15:19:23.028Z`
- elapsed_seconds: `21605.387683` (max_run_seconds = `21600`)
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
| daily_pnl USDT (final telemetry) | `76775.32867` |
| account_total_usdt (final sidecar) | `86775.32668` |
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

The `daily_pnl` value keeps the known testnet faucet-account caveat: telemetry
anchors from `starting_balance=10000`, while the testnet wallet reports about
`86775 USDT`.

## 4. Heartbeat Cadence

- first heartbeat: `2026-05-26T09:19:17.699Z`
- last heartbeat: `2026-05-26T15:18:48.898Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.182` s
- `ws_connected`: `true` throughout
- `ws_reconnect_count`: `0`
- `exchange_error_count`: `0`

The final manifest open state is sourced from live sidecars and records
`open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`.

## 5. Section 5.4 Alert Outcome

`logs/alerts.log` has one row:

```json
{"context": {"lag_seconds": 120.53014969825745, "last_signal_ns": 1779808160617938293, "threshold_seconds": 120.0}, "kind": "testnet", "msg": "signal_lag_exceeded_threshold", "run_id": "20260526-091917Z-1acd81fc", "severity": "warning", "ts": "2026-05-26T15:11:21.148Z"}
```

| Section 5.4 kind | source | fired this session |
|---|---|---|
| `kill_switch_fired` | `testnet_runner.py` | no |
| `restart_drift_detected` | `testnet_runner.py` | no |
| `exchange_error_burst` | `testnet_runner.py` | no |
| `ws_disconnected` | `testnet_runner.py` | no |
| `data_gap_exceeded_tolerance` | `testnet_runner.py` | no |
| `signal_lag_exceeded_threshold` | `testnet_runner.py` | yes, 1 warning |
| `heartbeat_lost` | `infra/watchdog/watchdog.py` | no |
| `emergency_flatten_started` | `emergency_flatten.py` | no |
| `emergency_flatten_completed` | `emergency_flatten.py` | no |

## 6. Runtime.log Lifecycle

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-26T09:19:17.640Z` |
| `node_built` | `2026-05-26T09:19:17.698Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-26T09:19:17.698Z` |
| `node_run_invoked` | `2026-05-26T09:19:17.704Z` |
| `sidecar_write` (success=true) | `2026-05-26T15:19:23.017Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-26T15:19:23.028Z` |

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- `Reconciliation for BINANCE succeeded` at `2026-05-26T09:19:18.520Z`.
- `BaselineNautilusStrategy: RUNNING` at `2026-05-26T09:19:18.521Z`.
- All engines disposed cleanly at shutdown.

WARN classification:

- 7 x `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals.
- 2 x `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` on the entry and scheduled close market orders.
- 1 x user-data websocket teardown informational:
  `eventStreamTerminated`.

These match the established testnet informational pattern and do not explain
the blocked result. The blocker is the structured `alerts.log` row.

## 8. Watchdog Evidence

The watchdog loop was attached after the bundle was created and stopped after
the completed manifest was written.

- `status=healthy`: `711`
- `status=run_completed`: `15`
- `flatten_invoked=true`: `0`
- `alert_path`: `null` for every watchdog sample
- final state before watchdog shutdown:
  `status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
  `alert_path=null`, `last_heartbeat_at=2026-05-26T15:18:48.898Z`

The watchdog did not fire `heartbeat_lost` and did not invoke emergency
flatten.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `467`
- Net realized PnL on closed position: `+0.09846 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 76799.54 USDT`
- client_order_id `O-20260526-092000-001-000-1`
- venue_order_id `7468405`
- trade_id `2312762`
- fill ts_event `2026-05-26T09:20:00.252000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779787190617938293:buy:630341ec204c`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 76898.00 USDT`
- client_order_id `O-20260526-151917-001-000-2`
- venue_order_id `7561988`
- trade_id `2346658`
- fill ts_event `2026-05-26T15:19:17.783000Z`

Position close:

- `realized_pnl=+0.09846 USDT`
- final `side=FLAT`
- final sidecar account snapshot includes `USDT=86775.32668`.

## 10. Signal Flow And Blocker

Before launch, the future replay check returned
`future_wall_clock_replay_rows=0`. The full replay command then wrote 480
future rows:

- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1779786605617938293` (`2026-05-26T09:10:05.617938Z`)
- last_ts_event:
  `1779808160617938293` (`2026-05-26T15:09:20.617938Z`)
- interval_seconds: `45`
- side: `buy`

The runner reached `node_run_invoked` at `2026-05-26T09:19:17.704Z`, after
the early replay rows were already in the past. The session consumed 467 rows
before shutdown. The last replayed signal was at `2026-05-26T15:09:20.617938Z`,
about 10 minutes before the scheduled close at `2026-05-26T15:19:17.783Z`.
At `2026-05-26T15:11:21.148Z`, the signal lag reached `120.53` seconds and
triggered `signal_lag_exceeded_threshold`.

Only the first consumed signal opened the long position; all later target-long
signals were no-ops while already long.

## 11. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260526-091917Z-1acd81fc` returned:

- `clean_for_retro: False`
- `review_blockers: alerts=1`
- `recommendation: review_blockers_before_retro`
- `sidecar_mismatches: none`
- `final_position_sides: {"FLAT": 1}`

Clean aggregate across the twelve clean 6 h canary bundles remains unchanged:

- `clean_run_count: 12/12`
- `clean_elapsed_hours: 72.02`
- `orders=24 / fills=24 / positions=12 / heartbeats=8630 / alerts=0`
- `clean_realized_pnl=-0.43603 USDT`

Strict continuity review, including this blocked run and the 2026-05-20
blocked manifest-backed bundle, now reports:

- `qualified_day_count: 6/8`
- `current_qualified_streak_days: 0/14`
- `longest_qualified_streak_days: 5`
- 2026-05-26 clean hours: `0.00`
- `required_gate_met: false`
- blockers:
  `current_qualified_streak_days=0<required=14`,
  `emergency_flatten_completed=1`

## 12. Decision

This run is **not** accepted as clean Phase 3f operational evidence because
`signal_lag_exceeded_threshold` fired. It does not change `SourcePolicy`, does
not authorize live trading, and does not satisfy the 14-day live-readiness
continuity gate.

Before the next canary, use the hardened runbook update: after writing a
wall-clock replay stream, start the runner promptly; if more than two minutes
elapse before `node_run_invoked`, discard that launch attempt and write a new
non-overlapping stream with enough coverage for the full 6 h run.

# Phase 3f testnet canary session - 2026-05-25 6 h second control run

- **Date (UTC)**: 2026-05-25T07:48:53Z - 2026-05-25T13:48:58Z
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

Before launch, `git status --short --branch` was clean, `git fetch origin`
and `git pull --ff-only` were up to date, full tests passed, ruff was clean,
and there were no pre-existing future wall-clock replay rows. The runner used
the existing control-machine launcher `infra/launchers/first-testnet-canary.py`.

Because this was the second clean 6 h run on 2026-05-25 UTC, it increases
that day's clean testnet hours to 12.00. It does not increase the strict
current qualified-day streak, which remains `5/14` until a clean 2026-05-26
UTC day is completed.

## 2. Run Identity

- bundle: `data/testnet/20260525-074853Z-592ff1f1/`
- run_id: `20260525-074853Z-592ff1f1`
- git_commit at launch: `d1ce519b7dffc3ecb776815252767c0c58fbaf08`
- git_dirty: `false`
- manifest_sha256:
  `4212b8a417b4557214109aa9ff215f5224963ee0aef156b82c859e1a9ca87ee5`
- started_at: `2026-05-25T07:48:53.585Z`
- finished_at: `2026-05-25T13:48:58.990Z`
- elapsed_seconds: `21605.405117` (max_run_seconds = `21600`)
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
| daily_pnl USDT (final telemetry) | `76775.26923` |
| account_total_usdt (final telemetry) | `86775.26923` |
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

- first heartbeat: `2026-05-25T07:48:53.608Z`
- last heartbeat: `2026-05-25T13:48:26.303Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.188` s
- `ws_connected`: `true` throughout
- `ws_reconnect_count`: `0`
- `exchange_error_count`: `0`

The final manifest open state is sourced from live sidecars and records
`open_orders=0`, `open_positions=0`, `open_state_source=live_sidecars`.

## 5. Section 5.4 Alert Outcome

`logs/alerts.log` does not exist. That is the authoritative record that none
of the alert paths fired.

| Section 5.4 kind | source | fired this session |
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
| `credentials_loaded` | `2026-05-25T07:48:53.585Z` |
| `node_built` | `2026-05-25T07:48:53.607Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-25T07:48:53.607Z` |
| `node_run_invoked` | `2026-05-25T07:48:53.608Z` |
| `sidecar_write` (success=true) | `2026-05-25T13:48:58.988Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-25T13:48:58.990Z` |

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- Account `BINANCE-SPOT-master` registered at `2026-05-25T07:48:53.987Z`.
- `Reconciliation for BINANCE succeeded` at `2026-05-25T07:48:54.361Z`.
- `BaselineNautilusStrategy: RUNNING` at `2026-05-25T07:48:54.361Z`.
- All engines disposed cleanly at shutdown.

WARN classification:

- 7 x `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals.
- 2 x `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` on the entry and scheduled close market orders.
- 1 x user-data websocket teardown informational:
  `eventStreamTerminated`.

These match the scheduled shutdown window and do not map to ADR-008 Section
5.4 alert kinds.

## 8. Watchdog Evidence

The watchdog loop was attached after the bundle was created and stopped after
the completed manifest was written.

- `status=healthy`: `717`
- `status=run_completed`: `11`
- `flatten_invoked=true`: `0`
- `alert_path`: `null` for every watchdog sample
- final state before watchdog shutdown:
  `status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
  `alert_path=null`, `last_heartbeat_at=2026-05-25T13:48:26.303Z`

The completed manifest made the watchdog report `run_completed` instead of
`heartbeat_lost` after the runner's scheduled shutdown.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `476`
- Net realized PnL on closed position: `+0.02838 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 77300.01 USDT`
- client_order_id `O-20260525-075200-001-000-1`
- venue_order_id `7122415`
- trade_id `2231287`
- fill ts_event `2026-05-25T07:52:00.890000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779695496824123566:buy:9dba18bb0ed8`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 77328.39 USDT`
- client_order_id `O-20260525-134853-001-000-2`
- venue_order_id `7187477`
- trade_id `2247397`
- fill ts_event `2026-05-25T13:48:53.856000Z`

Position close:

- `realized_pnl=+0.02838 USDT`
- final `side=FLAT`
- final sidecar account snapshot includes `USDT=86775.26761`.

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
  `1779695496824123566` (`2026-05-25T07:51:36.824124Z`)
- last_ts_event:
  `1779717051824123566` (`2026-05-25T13:50:51.824124Z`)
- interval_seconds: `45`
- side: `buy`

The successful session consumed 476 rows before shutdown:

- lineage rows: `476`
- lineage `ts_event` range:
  `2026-05-25T07:51:36.824124Z` -
  `2026-05-25T13:47:51.824124Z`
- lineage decision counts: `target_long x 476`
- lineage rows with non-empty `order_ids` / `fill_ids` / `position_id`: `1`

Only the first signal opened the long position; all later target-long signals
were no-ops while already long. No `signal_lag_exceeded_threshold` alert
fired.

## 11. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260525-074853Z-592ff1f1` returned:

- `clean_for_retro: True`
- `review_blockers: none`
- `recommendation: ready_for_retro_evidence`
- `sidecar_mismatches: none`
- `final_position_sides: {"FLAT": 1}`

Clean aggregate across the eleven clean 6 h canary bundles now reports:

- `clean_run_count: 11/11`
- `clean_elapsed_hours: 66.02`
- `orders=22 / fills=22 / positions=11 / heartbeats=7911 / alerts=0`
- `clean_realized_pnl=-0.39664 USDT`

Strict continuity review, including the 2026-05-20 blocked manifest-backed
bundle, now reports:

- `qualified_day_count: 6/7`
- `current_qualified_streak_days: 5/14`
- `longest_qualified_streak_days: 5`
- 2026-05-25 clean hours: `12.00`
- `required_gate_met: false`
- blockers:
  `current_qualified_streak_days=5<required=14`,
  `emergency_flatten_completed=1`

## 12. Decision

This run is accepted as clean Phase 3f operational evidence. It does not
promote the source, does not authorize live trading, and does not change
`SourcePolicy`.

Next operating step: continue the hardened control-machine canary routine.
The next run that can advance the strict day streak must complete on
2026-05-26 UTC or later.

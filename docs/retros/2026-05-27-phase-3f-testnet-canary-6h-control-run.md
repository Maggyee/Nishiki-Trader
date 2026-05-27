# Phase 3f testnet canary session - 2026-05-27 6 h control run

- **Date (UTC)**: 2026-05-27T05:47:00Z - 2026-05-27T11:47:05Z
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

This is the first clean canary after the 2026-05-26 signal-lag blocked run. It
restarts the strict current continuity streak at `1/14`.

## 2. Run Identity

- bundle: `data/testnet/20260527-054700Z-cacef82e/`
- run_id: `20260527-054700Z-cacef82e`
- git_commit at launch: `1771e74ae232484d83023262392af5511caa39c6`
- git_dirty: `false`
- manifest_sha256:
  `81a035d9fdabbf27dd5873e1cccb3d0a3c4085884eaaa193971100938175648c`
- started_at: `2026-05-27T05:47:00.255Z`
- finished_at: `2026-05-27T11:47:05.675Z`
- elapsed_seconds: `21605.420727` (max_run_seconds = `21600`)
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
| daily_pnl USDT (final telemetry) | `76775.51102` |
| account_total_usdt (final sidecar) | `86775.49487` |
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

- first heartbeat: `2026-05-27T05:47:00.289Z`
- last heartbeat: `2026-05-27T11:46:32.098Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.296` s
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
| `credentials_loaded` | `2026-05-27T05:47:00.255Z` |
| `node_built` | `2026-05-27T05:47:00.287Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-27T05:47:00.288Z` |
| `node_run_invoked` | `2026-05-27T05:47:00.291Z` |
| `sidecar_write` (success=true) | `2026-05-27T11:47:05.674Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-27T11:47:05.675Z` |

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- Account `BINANCE-SPOT-master` registered at `2026-05-27T05:47:00.606Z`.
- `Reconciliation for BINANCE succeeded` at `2026-05-27T05:47:00.996Z`.
- `BaselineNautilusStrategy: RUNNING` at `2026-05-27T05:47:00.996Z`.
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
- `status=run_completed`: `15`
- `flatten_invoked=true`: `0`
- `alert_path`: `null` for every watchdog sample
- final state before watchdog shutdown:
  `status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
  `alert_path=null`, `last_heartbeat_at=2026-05-27T11:46:32.098Z`

The completed manifest made the watchdog report `run_completed` instead of
`heartbeat_lost` after the runner's scheduled shutdown.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `475`
- Net realized PnL on closed position: `+0.16819 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 75642.00 USDT`
- client_order_id `O-20260527-055000-001-000-1`
- venue_order_id `7762395`
- trade_id `2410737`
- fill ts_event `2026-05-27T05:50:00.892000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779860995982314827:buy:3cd7d7c90485`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 75810.19 USDT`
- client_order_id `O-20260527-114700-001-000-2`
- venue_order_id `7839103`
- trade_id `2425284`
- fill ts_event `2026-05-27T11:47:00.426000Z`

Position close:

- `realized_pnl=+0.16819 USDT`
- final `side=FLAT`
- final sidecar account snapshot includes `USDT=86775.49487`.

Traceability:

- entry order carries the `signal_id` tag;
- entry fill carries the same `signal_id`;
- the closed position carries the source `signal_id`;
- the scheduled close fill has no signal tag, as expected for a time-based
  reduce-only close.

## 10. Signal Flow

Before launch, the future replay check returned
`future_wall_clock_replay_rows=0`. The full replay command was then written as
the final pre-launch action and the runner was immediately executed:

- pre_replay_utc: `2026-05-27T05:46:55Z`
- post_replay_utc: `2026-05-27T05:46:59Z`
- pre_runner_exec_utc: `2026-05-27T05:46:59Z`
- node_run_invoked: `2026-05-27T05:47:00.291Z`

The full replay command wrote 480 future rows:

- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1779860995982314827` (`2026-05-27T05:49:55.982315Z`)
- last_ts_event:
  `1779882550982314827` (`2026-05-27T11:49:10.982315Z`)
- interval_seconds: `45`
- side: `buy`

The first replayed signal was about 176 s after `node_run_invoked`. The final
replayed signal was about 125 s after runner shutdown, so the stream covered
the full 6 h session and avoided the 2026-05-26 replay-expiry failure mode.

The successful session consumed 475 rows before shutdown:

- lineage rows: `475`
- lineage `ts_event` range:
  `2026-05-27T05:49:55.982315Z` -
  `2026-05-27T11:45:25.982315Z`
- lineage decision counts: `target_long x 475`
- lineage rows with non-empty `order_ids` / `fill_ids` / `position_id`: `1`

Only the first signal opened the long position; all later target-long signals
were no-ops while already long. No `signal_lag_exceeded_threshold` alert
fired.

## 11. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260527-054700Z-cacef82e` returned:

- `clean_for_retro: True`
- `review_blockers: none`
- `recommendation: ready_for_retro_evidence`
- `sidecar_mismatches: none`
- `final_position_sides: {"FLAT": 1}`

Clean aggregate across the thirteen clean 6 h canary bundles now reports:

- `clean_run_count: 13/13`
- `clean_elapsed_hours: 78.02`
- `orders=26 / fills=26 / positions=13 / heartbeats=9349 / alerts=0`
- `clean_realized_pnl=-0.26784 USDT`

Strict continuity review, including the 2026-05-20 and 2026-05-26 blocked
manifest-backed bundles, now reports:

- `qualified_day_count: 7/9`
- `current_qualified_streak_days: 1/14`
- `longest_qualified_streak_days: 5`
- 2026-05-27 clean hours: `6.00`
- `required_gate_met: false`
- blockers:
  `current_qualified_streak_days=1<required=14`,
  `emergency_flatten_completed=1`

## 12. Decision

This run is accepted as clean Phase 3f operational evidence. It does not
change `SourcePolicy`, does not authorize live trading, and does not satisfy
the 14-day live-readiness continuity gate.

Continue the hardened 6 h/day control-machine canary routine. The next strict
continuity advancement requires a clean 2026-05-28 UTC day.

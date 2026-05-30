# Phase 3f testnet canary session - 2026-05-30 6 h control run

- **Date (UTC)**: 2026-05-30T06:23:56Z - 2026-05-30T12:24:01Z
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
there were no stale runner/watchdog processes, and there were no pre-existing
future wall-clock replay rows.

## 2. Run Identity

- bundle: `data/testnet/20260530-062356Z-f47c4a93/`
- run_id: `20260530-062356Z-f47c4a93`
- git_commit at launch: `f9bf7836d7662305808c1241862c23576d33faa6`
- git_dirty: `false`
- manifest_sha256:
  `d1d13e7e62e38ede1e119840a88034c0d0a908852cf2685a3c55afa12222f147`
- started_at: `2026-05-30T06:23:56.215Z`
- finished_at: `2026-05-30T12:24:01.665Z`
- elapsed_seconds: `21605.450064` (max_run_seconds = `21600`)
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
| policy_position_pct_multiplier | `0.1` |
| starting_balance USDT | `10000.0` |
| daily_pnl USDT (final telemetry) | `76775.55907` |
| account_total_usdt (final sidecar) | `86775.55953` |
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

## 4. Heartbeat And Alerts

- first heartbeat: `2026-05-30T06:23:56.261Z`
- last heartbeat: `2026-05-30T12:23:27.635Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.18` s
- `ws_connected`: `true` throughout
- `ws_reconnect_count`: `0`
- `exchange_error_count`: `0`
- `logs/alerts.log`: absent

No ADR-008 Section 5.4 alert fired: no kill switch, restart drift, exchange
error burst, WS disconnect, data gap, signal lag, heartbeat loss, or emergency
flatten event.

## 5. Lifecycle And Watchdog

| event | ts |
|---|---|
| `credentials_loaded` | `2026-05-30T06:23:56.215Z` |
| `node_built` | `2026-05-30T06:23:56.260Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-30T06:23:56.261Z` |
| `node_run_invoked` | `2026-05-30T06:23:56.261Z` |
| `sidecar_write` (success=true) | `2026-05-30T12:24:01.662Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-30T12:24:01.665Z` |

The watchdog final state before shutdown was
`status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
`alert_path=null`, and `last_heartbeat_at=2026-05-30T12:23:27.635Z`.
The watchdog process was stopped after the completed manifest was written.

## 6. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.

WARN classification:

- 7 x `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals.
- 2 x `RiskEngine: Cannot check MARKET order risk: no prices for
  BTCUSDT.BINANCE` on the entry and scheduled close market orders.
- 1 x user-data websocket teardown informational:
  `eventStreamTerminated`.

These match known clean-canary shutdown and Binance Spot testnet behavior and
do not map to ADR-008 Section 5.4 alert kinds.

## 7. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `475`
- Net realized PnL on closed position: `+0.06466 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 73597.34 USDT`
- client_order_id `O-20260530-062700-001-000-1`
- venue_order_id `8798317`
- trade_id `2705433`
- fill ts_event `2026-05-30T06:27:00.460999Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1780122411540936433:buy:c20717805499`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 73662.00 USDT`
- client_order_id `O-20260530-122356-001-000-2`
- venue_order_id `8847224`
- trade_id `2716391`
- fill ts_event `2026-05-30T12:23:56.392000Z`

Position close:

- `realized_pnl=+0.06466 USDT`
- final `side=FLAT`
- final sidecar account snapshot includes `USDT=86775.55953`.

## 8. Signal Flow

Before launch, the future replay check returned
`future_wall_clock_replay_rows=0`. The full replay command was written as the
final pre-launch action and the runner was immediately executed:

- pre_replay_utc: `2026-05-30T06:23:50Z`
- post_replay_utc: `2026-05-30T06:23:54Z`
- pre_runner_exec_utc: `2026-05-30T06:23:54Z`
- node_run_invoked: `2026-05-30T06:23:56.261Z`

The full replay command wrote 480 future rows:

- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1780122411540936433` (`2026-05-30T06:26:51.540936Z`)
- last_ts_event:
  `1780143966540936433` (`2026-05-30T12:26:06.540936Z`)
- interval_seconds: `45`
- side: `buy`

The first replayed signal was about 175 s after `node_run_invoked`. The final
replayed signal was about 125 s after runner shutdown, so the stream covered
the full 6 h session. The successful session consumed 475 rows before
shutdown, all with `decision=target_long`; only the first opened the long
position and all later target-long signals were no-ops while already long.

## 9. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260530-062356Z-f47c4a93` returned:

- `clean_for_retro: True`
- `review_blockers: none`
- `recommendation: ready_for_retro_evidence`
- `sidecar_mismatches: none`
- `final_position_sides: {"FLAT": 1}`

Clean aggregate across the fourteen clean 6 h canary bundles now reports:

- `clean_run_count: 14/14`
- `clean_elapsed_hours: 84.02`
- `orders=28 / fills=28 / positions=14 / heartbeats=10068 / alerts=0`
- `clean_realized_pnl=-0.20318 USDT`

Strict continuity review, including the 2026-05-20 and 2026-05-26 blocked
manifest-backed bundles, now reports:

- `qualified_day_count: 8/10`
- `current_qualified_streak_days: 1/14`
- `longest_qualified_streak_days: 5`
- 2026-05-30 clean hours: `6.00`
- `required_gate_met: false`
- blockers:
  `current_qualified_streak_days=1<required=14`,
  `emergency_flatten_completed=1`

## 10. Decision

This run is accepted as clean Phase 3f operational evidence. It does not
change `SourcePolicy`, does not authorize live trading, and does not satisfy
the 14-day live-readiness continuity gate.

Continue the hardened 6 h/day control-machine canary routine. The next strict
continuity advancement requires a clean 2026-05-31 UTC day.

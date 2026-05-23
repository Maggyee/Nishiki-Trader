# Phase 3f testnet canary session — 2026-05-22 6 h evening run

- **Date (UTC)**: 2026-05-22T17:52:32Z – 2026-05-22T23:52:38Z
- **Operator**: nishiki
- **ADR**: [ADR-008 §6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro — not a `SourcePolicy` decision.

## 1. Scope

Real 6 h Binance Spot testnet canary under ADR-008 §6.6, run on the
control machine from a long-lived foreground Codex tool session. The runner
registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`,
with live telemetry, live sidecar writing, and the external watchdog
attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

Before launch, `git status --short --branch` was clean, `git fetch origin &&
git pull --ff-only` returned up to date, full tests passed, ruff was clean,
and there were no pre-existing future wall-clock replay rows.

## 2. Run Identity

- bundle: `data/testnet/20260522-175232Z-83a9d87d/`
- run_id: `20260522-175232Z-83a9d87d`
- git_commit at launch: `a6f6cf3d8effeb51e163786f7e36db7594457c6d`
- git_dirty: `false`
- started_at: `2026-05-22T17:52:32.682Z`
- finished_at: `2026-05-22T23:52:38.104Z`
- elapsed_seconds: `21605.422712` (max_run_seconds = `21600`)
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
| daily_pnl USDT (final telemetry) | `76773.87613` |
| account_total_usdt (final telemetry) | `86773.87613` |
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
reports about `86774 USDT`.

## 4. Heartbeat Cadence

- first heartbeat: `2026-05-22T17:52:32.714Z`
- last heartbeat: `2026-05-22T23:52:05.229Z`
- count: `719` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.18` s
- `ws_connected`: `true` throughout
- `ws_reconnect_count`: `0`
- `exchange_error_count`: `0`

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
| `credentials_loaded` | `2026-05-22T17:52:32.682Z` |
| `node_built` | `2026-05-22T17:52:32.712Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-22T17:52:32.713Z` |
| `node_run_invoked` | `2026-05-22T17:52:32.716Z` |
| `sidecar_write` (success=true) | `2026-05-22T23:52:38.102Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-22T23:52:38.104Z` |

## 7. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.
- `Account BINANCE-SPOT-master registered in cache` at
  `2026-05-22T17:52:33.128Z`.
- `Reconciliation for BINANCE succeeded` at `2026-05-22T17:52:33.486Z`.
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
- `status=run_completed`: `5`
- `flatten_invoked=true`: `0`
- final state before watchdog shutdown:
  `status=run_completed`, `exit_code=0`, `flatten_invoked=false`,
  `alert_path=null`, `last_heartbeat_at=2026-05-22T23:52:05.229Z`

The final heartbeat age exceeded the normal timeout after shutdown, but the
completed manifest made the watchdog report `run_completed` instead of
`heartbeat_lost`.

## 9. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `477`
- Net realized PnL on closed position: `-1.23226 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 76795.25 USDT`
- client_order_id `O-20260522-175500-001-000-1`
- venue_order_id `6250274`
- trade_id `1997610`
- fill ts_event `2026-05-22T17:55:00.700000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1779472499214895321:buy:0e4f1edec5db`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 75562.99 USDT`
- client_order_id `O-20260522-235232-001-000-2`
- venue_order_id `6344857`
- trade_id `2024125`
- fill ts_event `2026-05-22T23:52:32.815000Z`

Position close:

- sidecar position_id `position-ba2b8763350603b6831cdc11`
- `avg_px_open=76795.25` / `avg_px_close=75562.99`
- `realized_pnl=-1.23226 USDT`
- `realized_return=-0.01605` (-1.605%)
- final `side=FLAT`, `quantity=0.0`, `unrealized_pnl=0.0`
- final sidecar account snapshot includes `USDT=86773.87612`.

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
  `1779472499214895321` (`2026-05-22T17:54:59.214895Z`)
- last_ts_event:
  `1779494054214895321` (`2026-05-22T23:54:14.214895Z`)
- interval_seconds: `45`
- side: `buy`

The successful session consumed 477 rows before shutdown:

- lineage rows: `477`
- lineage `ts_event` range:
  `2026-05-22T17:54:59.214895Z` –
  `2026-05-22T23:51:59.214895Z`
- lineage decision counts: `target_long x 477`
- lineage rows with non-empty `order_ids` / `fill_ids` / `position_id`: `1`

Only the first signal opened the long position; all later target-long signals
were no-ops while already long. No `signal_lag_exceeded_threshold` alert
fired.

## 11. Evidence Reports

Passive bundle report:

- `clean_for_retro=True`
- `review_blockers=none`
- `recommendation=ready_for_retro_evidence`
- manifest sha256:
  `bcc9c75c933b8c29dfa0bc7e665c3e3293a8b5f836be29188c59937b0347f942`

Clean aggregate after this run:

- `clean_run_count: 5/5`
- `clean_elapsed_hours: 30.01`
- `orders=10 / fills=10 / positions=5 / heartbeats=3597 / alerts=0`
- `clean_realized_pnl=-1.78813 USDT`

Strict continuity after this run:

- `qualified_day_count: 3/4`
- `current_qualified_streak_days: 2/14`
- 2026-05-22 now has `12.00` clean hours.
- blockers remain `current_qualified_streak_days=2<required=14` and
  `emergency_flatten_completed=1` from the 2026-05-20 blocked bundle.

## 12. Decision

This retro does not mutate `SourcePolicy`.

Recommended next decision:

- **hold @ testnet_canary** — clean 6 h session, real entry/exit order flow,
  no ADR-008 §5.4 alerts, no exchange/runtime errors, no WS reconnects, final
  sidecar state flat, and watchdog completed without emergency flatten.

Do not proceed to live trading without a separate live-risk ADR and the
ADR-001 capital ladder gate.

# Phase 3f testnet canary session - 2026-05-30 post-fix control run

- **Date (UTC)**: 2026-05-30T14:10:37Z - 2026-05-30T20:10:43Z
- **Operator**: nishiki
- **ADR**: [ADR-008 Section 6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro - not a `SourcePolicy` decision.

## 1. Scope

Real 6 h Binance Spot testnet canary under ADR-008 Section 6.6, run on the
control machine from long-lived foreground Codex tool sessions after commit
`348ca5b` added same-bar executable intent suppression to
`BaselineNautilusStrategy`.

The runner registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`, with
live telemetry, live sidecar writing, and the external watchdog attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This run is accepted as clean Phase 3f operational evidence. It proves the
same-bar guard over the failure shape observed in
`20260530-132316Z-9b5e2230`: two due buy signals were present on the first
execution bar, but only one entry order was submitted. The suppressed same-bar
intent was retained in `signal_lineage.parquet` with reason
`suppressed_after_same_bar_order_submission`.

## 2. Run Identity

- bundle: `data/testnet/20260530-141037Z-6e860b4f/`
- run_id: `20260530-141037Z-6e860b4f`
- git_commit at launch: `348ca5b3f79d0ba82dd3e7f732075571a01e7515`
- git_dirty: `false`
- manifest_sha256:
  `40c1a86106f3af1f9d02da6525db33d0958053135ef9739c1fd179cc45c347ad`
- started_at: `2026-05-30T14:10:37.784Z`
- finished_at: `2026-05-30T20:10:43.053Z`
- elapsed_seconds: `21605.269135` (max_run_seconds = `21600`)
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
| account_total_usdt (final sidecar) | `86775.52382` |
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

## 4. Heartbeat And Alerts

- first heartbeat: `2026-05-30T14:10:37.805Z`
- last heartbeat: `2026-05-30T20:10:09.046Z`
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
| `credentials_loaded` | `2026-05-30T14:10:37.784Z` |
| `node_built` | `2026-05-30T14:10:37.804Z` |
| `strategies_registered` (strategies = `1`, actors = `0`) | `2026-05-30T14:10:37.804Z` |
| `node_run_invoked` | `2026-05-30T14:10:37.806Z` |
| `sidecar_write` (success=true) | `2026-05-30T20:10:43.052Z` |
| `shutdown` (stop_reason=`max_duration`) | `2026-05-30T20:10:43.053Z` |

The watchdog reached `status=run_completed`, `exit_code=0`,
`flatten_invoked=false`, `alert_path=null`, and
`last_heartbeat_at=2026-05-30T20:10:09.046Z`. The watchdog process was stopped
after the completed manifest was written.

## 6. Nautilus Log Evidence

- `grep -c ERROR /tmp/phase3f-canary/runner.stdout.log` -> `0`.
- `grep -c WARN /tmp/phase3f-canary/runner.stdout.log` -> `10`.
- stderr file: `0` bytes.

WARN classification matches the established clean-canary pattern:

- `BinanceSpotInstrumentProvider: zero fees for TESTNET` informationals.
- `RiskEngine: Cannot check MARKET order risk: no prices for BTCUSDT.BINANCE`
  on the entry and scheduled close market orders.
- user-data websocket teardown informational:
  `eventStreamTerminated`.

These do not map to ADR-008 Section 5.4 alert kinds.

## 7. Real Order Flow

- `orders.parquet` row count: `2`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `451`
- `signal_lineage.parquet` row count: `896`
- Net realized PnL on closed position: `-0.01055 USDT`
- Final position side: `FLAT`

Entry:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 73981.85 USDT`
- client_order_id `O-20260530-141200-001-000-1`
- venue_order_id `8864831`
- trade_id `2721073`
- fill ts_event `2026-05-30T14:12:00.715000Z`
- signal tag
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1780150271504158816:buy:79296192fb5d`

Scheduled close:

- `SELL MARKET 0.001 BTCUSDT.BINANCE @ 73971.30 USDT`
- client_order_id `O-20260530-201037-001-000-2`
- venue_order_id `8924421`
- trade_id `2734133`
- fill ts_event `2026-05-30T20:10:37.900000Z`

Position close:

- `realized_pnl=-0.01055 USDT`
- final `side=FLAT`
- final sidecar account snapshot includes `USDT=86775.52382`.

## 8. Signal Flow

Before launch, the future replay check found 422 rows from the earlier aborted
bundle's stream, spanning `2026-05-30T14:09:41.504159Z` to
`2026-05-30T19:25:26.504159Z`. Because that stream no longer covered a full
6 h canary by itself, a new 480-row stream was intentionally written with
overlap and recorded here as part of the evidence.

The new full replay command was written as the final pre-launch action:

- pre_replay_utc: `2026-05-30T14:10:32Z`
- post_replay_utc: `2026-05-30T14:10:36Z`
- pre_runner_exec_utc: `2026-05-30T14:10:36Z`
- node_run_invoked: `2026-05-30T14:10:37.806Z`
- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1780150413898471470` (`2026-05-30T14:13:33.898471Z`)
- last_ts_event:
  `1780171968898471470` (`2026-05-30T20:12:48.898471Z`)
- interval_seconds: `45`
- side: `buy`

The runner consumed 896 lineage rows across the overlapping streams. Only one
row has an order/fill/position id. The second due buy signal on the first
execution bar was recorded with reason
`suppressed_after_same_bar_order_submission`, proving the same-bar order guard
prevented the duplicate-entry failure from the preceding aborted bundle.

## 9. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260530-141037Z-6e860b4f` returned:

- `clean_for_retro: True`
- `review_blockers: none`
- `recommendation: ready_for_retro_evidence`
- `sidecar_mismatches: none`
- `final_position_sides: {"FLAT": 1}`

Clean aggregate across the fifteen clean 6 h canary bundles now reports:

- `clean_run_count: 15/15`
- `clean_elapsed_hours: 90.02`
- `orders=30 / fills=30 / positions=15 / heartbeats=10787 / alerts=0`
- `clean_realized_pnl=-0.21373 USDT`

Strict continuity review, including the manifest-backed blocked bundles, now
reports:

- `qualified_day_count: 7/10`
- `current_qualified_streak_days: 0/14`
- `longest_qualified_streak_days: 5`
- 2026-05-30 clean hours: `12.00`
- `required_gate_met: false`
- blockers:
  `current_qualified_streak_days=0<required=14`,
  `emergency_flatten_completed=2`

The 2026-05-30 UTC day remains unqualified because it also contains the
blocked `20260530-132316Z-9b5e2230` bundle. This clean run adds operational
evidence but does not repair same-day continuity.

## 10. Decision

This run is accepted as clean Phase 3f operational evidence. It does not
change `SourcePolicy`, does not authorize live trading, and does not satisfy
the 14-day live-readiness continuity gate.

Continue the hardened 6 h/day control-machine canary routine. The next strict
continuity advancement requires a clean 2026-05-31 UTC day with no blocked
bundle on that UTC day.

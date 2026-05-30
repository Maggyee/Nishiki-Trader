# Phase 3f testnet canary session - 2026-05-30 duplicate-entry abort

- **Date (UTC)**: 2026-05-30T13:23:16Z - 2026-05-30T13:29:34Z
- **Operator**: nishiki
- **ADR**: [ADR-008 Section 6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro - not a `SourcePolicy` decision.

## 1. Scope

Real Binance Spot testnet canary under ADR-008 Section 6.6, run on the control
machine from long-lived foreground Codex tool sessions. The runner registered
one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`, with
live telemetry, live sidecar writing, and the external watchdog attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This run is **not** accepted as clean canary evidence. It was operator-aborted
after the first execution bar submitted two same-side entry orders before the
portfolio cache observed the first fill. External emergency flatten succeeded
and left no residual testnet orders or positions.

## 2. Run Identity

- bundle: `data/testnet/20260530-132316Z-9b5e2230/`
- run_id: `20260530-132316Z-9b5e2230`
- git_commit at launch: `4093b5a3ee1d1072976e3e05ad78c03a0cb05298`
- git_dirty: `false`
- manifest_sha256:
  `52d61b0591640f28a7e86708cf586fe157d57a38014a76b60a71bd61adb8c76d`
- started_at: `2026-05-30T13:23:16.383Z`
- finished_at: `2026-05-30T13:29:34.342Z`
- elapsed_seconds: `377.958197`
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`

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
| account_total_usdt after external flatten | `86775.53437` |
| restart_sequence | `0` |
| ws_reconnect_count | `0` |
| exchange_error_count | `1` |
| shutdown_reason | `node_stopped` |
| auto_flatten_trigger | `null` |
| external emergency_flatten success | `true` |

The `exchange_error_count=1` came from the runner shutdown close attempt being
rejected after the external flatten had already sold the testnet BTC. It did
not leave residual exposure.

## 4. Heartbeat And Alert Outcome

- first heartbeat: `2026-05-30T13:23:16.406Z`
- last heartbeat: `2026-05-30T13:29:16.930Z`
- count: `13` rows in `logs/heartbeat.jsonl`
- max heartbeat gap: `30.052` s
- `ws_connected`: `true` throughout
- `ws_reconnect_count`: `0`

`logs/alerts.log` has two critical rows:

- `emergency_flatten_started` at `2026-05-30T13:29:28.094Z`
- `emergency_flatten_completed` at `2026-05-30T13:29:28.805Z`

Emergency flatten closed one LONG position:

- side before: `LONG`
- quantity before: `0.00200000 BTC`
- close side: `SELL`
- filled quantity: `0.00200000 BTC`
- average close price: `73773.43 USDT`
- reduce order id: `8856769`
- closed_at: `2026-05-30T13:29:28.700Z`
- residual_orders: `[]`
- residual_positions: `[]`
- elapsed_seconds: `0.7114089408423752`

## 5. Real Order Flow

- `orders.parquet` row count: `3`
- `fills.parquet` row count: `2`
- `positions.parquet` row count: `1`
- `account_balances.parquet` row count: `453`
- `signal_lineage.parquet` row count: `4`

Duplicate entry orders:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 73786.01 USDT`
  - client_order_id `O-20260530-132700-001-000-1`
  - venue_order_id `8856426`
  - trade_id `2718657`
  - signal id
    `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1780147571504158816:buy:4b5130b30fb7`
- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 73786.01 USDT`
  - client_order_id `O-20260530-132700-001-000-2`
  - venue_order_id `8856427`
  - trade_id `2718658`
  - signal id
    `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1780147616504158816:buy:e96602a4dd58`

The position sidecar recorded one LONG position with quantity `0.002`. The
external flatten close is recorded in `emergency_flatten.json`, not in
`fills.parquet`, because it was executed outside the runner.

During runner shutdown, `BaselineNautilusStrategy.on_stop()` attempted a
reduce-only SELL for `0.002` from its local Nautilus cache. Binance rejected it
because the external flatten had already closed the testnet balance. This
explains the third `orders.parquet` row:

- client_order_id `O-20260530-132929-001-000-3`
- side `SELL`
- quantity `0.002`
- status `REJECTED`

## 6. Signal Flow And Root Cause

Before launch, `future_wall_clock_replay_rows=0`. The replay command wrote
480 future rows:

- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event:
  `1780147571504158816` (`2026-05-30T13:26:11.504159Z`)
- last_ts_event:
  `1780169126504158816` (`2026-05-30T19:25:26.504159Z`)
- interval_seconds: `45`
- side: `buy`

The runner reached `node_run_invoked` at `2026-05-30T13:23:16.406Z`. On the
first execution bar at about `2026-05-30T13:27:00Z`, two due buy signals were
popped together and both produced `target_long` intents. The strategy submitted
both BUY market orders before the first fill/position update propagated through
the Nautilus portfolio cache. Both market orders filled at the same exchange
timestamp.

Root cause: the Nautilus wrapper relied on portfolio state idempotence, but did
not have a same-bar in-flight order guard. When multiple due entry signals are
processed in one `on_bar` call, the local portfolio may still look flat between
submissions. The fix added after this run suppresses later executable same-bar
intents while preserving their lineage rows for audit.

## 7. Bundle Report Output

`UV_CACHE_DIR=/tmp/uv-cache uv run python -m
apps.strategies_nautilus.runners.report_testnet_bundle
data/testnet/20260530-132316Z-9b5e2230` returned:

- `clean_for_retro: False`
- `review_blockers: shutdown_reason=node_stopped, open_positions=1, alerts=2,
  orders_fills_mismatch orders=3 fills=2, positions_not_flat`
- `recommendation: review_blockers_before_retro`
- `sidecar_mismatches: none`
- `alerts: emergency_flatten_started=1, emergency_flatten_completed=1`

Clean aggregate across the fourteen clean 6 h canary bundles remains
unchanged:

- `clean_run_count: 14/14`
- `clean_elapsed_hours: 84.02`
- `orders=28 / fills=28 / positions=14 / heartbeats=10068 / alerts=0`
- `clean_realized_pnl=-0.20318 USDT`

Strict continuity review, including this blocked run plus the earlier
manifest-backed blocked bundles, now reports:

- `qualified_day_count: 7/10`
- `current_qualified_streak_days: 0/14`
- `longest_qualified_streak_days: 5`
- 2026-05-30 clean hours: `6.00`
- 2026-05-30 blockers:
  `blocked_runs=20260530-132316Z-9b5e2230`, `alerts=2`,
  `emergency_flatten_completed=1`
- summary blockers:
  `current_qualified_streak_days=0<required=14`,
  `emergency_flatten_completed=2`

## 8. Decision

This run is **not** accepted as clean Phase 3f operational evidence. It does
not change `SourcePolicy`, does not authorize live trading, and does not
satisfy the 14-day live-readiness continuity gate.

The next canary must start from code that includes the same-bar executable
intent suppression guard, and the first post-fix run should be treated as a
new canary, not as a continuation of this aborted bundle.

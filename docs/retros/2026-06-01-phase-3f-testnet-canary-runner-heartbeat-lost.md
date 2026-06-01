# Phase 3f testnet canary session - 2026-06-01 runner heartbeat lost

- **Date (UTC)**: 2026-06-01T01:39:40Z - 2026-06-01T07:49:13Z
- **Operator**: nishiki
- **ADR**: [ADR-008 Section 6.6](../decisions/008-phase3-risk-runbook.md) Phase 3f
- **Kind**: Operational session retro - not a `SourcePolicy` decision.

## 1. Scope

Real Binance Spot testnet canary under ADR-008 Section 6.6. The runner
registered one streaming `BaselineNautilusStrategy` backed by
`SignalStorePollingSource(freqai_linear_v1 / linear-mom-train20240105)`, with
live telemetry enabled and an external watchdog attached.

Authorized policy remains
`SourcePolicy(dry_run=False, position_pct_multiplier=0.1,
min_confidence_override=None)` from
`docs/retros/2026-05-19-freqai-linear-v1-promote-testnet-canary.md`.

This run is **not** accepted as clean canary evidence. The runner process
disappeared before `max_duration`, stopped writing heartbeats, did not write a
`run_manifest.json`, and left one open testnet LONG position. The external
watchdog appended repeated `heartbeat_lost` alerts. Operator emergency flatten
closed the position and left no residual testnet orders or positions.

## 2. Run Identity

- bundle directory: `data/testnet/20260601-013940Z-ffe1e00c/`
- run_id: `20260601-013940Z-ffe1e00c`
- runner pid: `1187042`
- started_at: `2026-06-01T01:39:40.670Z`
- last heartbeat: `2026-06-01T07:21:42.443Z`
- emergency flatten completed: `2026-06-01T07:49:13.087Z`
- `run_manifest.json`: missing
- credentials_source: `env:BINANCE_TESTNET_API_KEY,BINANCE_TESTNET_API_SECRET`

Pre-run checks passed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` -> 504 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps tests docs infra` ->
  clean.
- `future_wall_clock_replay_rows=0` before writing the replay stream.

The wall-clock replay write happened immediately before runner launch:

- pre_replay_utc: `2026-06-01T01:39:35Z`
- post_replay_utc: `2026-06-01T01:39:39Z`
- runner `node_run_invoked`: `2026-06-01T01:39:40.702Z`
- generated_count: `480`
- skipped_duplicates: `0`
- first_ts_event: `1780278156230457738`
- last_ts_event: `1780299711230457738`
- interval_seconds: `45`
- side: `buy`

## 3. Runtime Counters

| metric | value |
|---|---:|
| kind | `testnet` |
| runtime.mode | `testnet` |
| runtime.data_mode | `exchange_ws` |
| runtime.order_mode | `exchange_testnet` |
| enable_strategy_execution | `true` |
| strategies_registered | `1` |
| actors_registered | `0` |
| source | `freqai_linear_v1` |
| model_version | `linear-mom-train20240105` |
| policy_position_pct_multiplier | `0.1` |
| starting_balance USDT | `10000.0` |
| heartbeat rows | `684` |
| alert rows | `51` |
| runner stdout `ERROR` count | `0` |
| runner stderr bytes | `0` |
| orders initialized by runner | `1` |
| orders filled by runner | `1` |
| positions opened by runner | `1` |
| positions closed by runner | `0` |
| emergency flatten closed positions | `1` |

The runner initialized and filled one entry order:

- `BUY MARKET 0.001 BTCUSDT.BINANCE @ 73570.01 USDT`
- client_order_id `O-20260601-014300-001-000-1`
- venue_order_id `9250745`
- trade_id `2807643`
- signal id
  `freqai_linear_v1:linear-mom-train20240105:wall_clock_replay:BTCUSDT:BINANCE:1780278156230457738:buy:55e9709be1ad`

The runner did not submit a close order before it disappeared.

## 4. Heartbeat And Alert Outcome

- first heartbeat: `2026-06-01T01:39:40.700Z`
- last heartbeat: `2026-06-01T07:21:42.443Z`
- count: `684` rows in `logs/heartbeat.jsonl`
- last heartbeat state: `open_orders=0`, `open_positions=1`,
  `ws_connected=true`, `ws_reconnect_count=0`, `exchange_error_count=0`

`logs/alerts.log` has `51` rows:

- `heartbeat_lost`: 50 rows from `2026-06-01T07:23:24.833Z` through
  `2026-06-01T07:48:54.418Z`.
- `emergency_flatten_completed`: 1 row at `2026-06-01T07:49:13.087Z`.

The watchdog itself was not continuously attached for the full run. The first
watchdog session stopped after `2026-06-01T04:02:47.610Z`; a detached
replacement was started at `2026-06-01T05:41:30.628Z` and caught the final
heartbeat stall. That monitoring gap is an additional reason this run cannot
be clean evidence.

## 5. Emergency Flatten Outcome

Emergency flatten command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m \
  apps.strategies_nautilus.runners.emergency_flatten \
  --kind testnet \
  --run-id 20260601-013940Z-ffe1e00c \
  --operator nishiki \
  --reason "operator-aborted canary after runner heartbeat_lost and open position" \
  --instrument-id BTCUSDT.BINANCE
```

Result:

- success: `true`
- closed_positions: `1`
- side before: `LONG`
- quantity before: `0.00100000 BTC`
- close side: `SELL`
- filled quantity: `0.00100000 BTC`
- average close price: `72751 USDT`
- reduce order id: `9334223`
- closed_at: `2026-06-01T07:49:12.965Z`
- residual_orders: `[]`
- residual_positions: `[]`
- elapsed_seconds: `0.7630749379750341`

## 6. Bundle Report Output

`report_testnet_bundle` could not produce a normal report because the runner did
not write `run_manifest.json`:

```text
report_testnet_bundle.py: error: [Errno 2] No such file or directory:
'data/testnet/20260601-013940Z-ffe1e00c/run_manifest.json'
```

Only these bundle files were present after flatten:

- `data/testnet/20260601-013940Z-ffe1e00c/emergency_flatten.json`
- `data/testnet/20260601-013940Z-ffe1e00c/logs/alerts.log`
- `data/testnet/20260601-013940Z-ffe1e00c/logs/heartbeat.jsonl`
- `data/testnet/20260601-013940Z-ffe1e00c/logs/runtime.log`

## 7. Decision

This run is **not** accepted as clean Phase 3f operational evidence. It does
not change `SourcePolicy`, does not authorize live trading, and does not
satisfy the 14-day live-readiness continuity gate.

Clean aggregate evidence remains unchanged at fifteen clean 6 h runs,
90.02 h, 30 orders, 30 fills, 15 closed positions, 10787 heartbeats, and
-0.21373 USDT realized PnL. From the manual continuity ledger, 2026-06-01 is a
blocked canary day because the runner heartbeat stopped, the bundle has no
manifest, and operator emergency flatten was required.

The next canary should launch the runner and watchdog from a process supervisor
that is independent of the Codex tool-session lifecycle, then verify both
processes remain alive before the first signal is due.

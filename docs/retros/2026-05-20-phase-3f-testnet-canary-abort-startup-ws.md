# Phase 3f testnet canary abort — startup WS telemetry

- **Date**: 2026-05-20 UTC
- **ADR**: ADR-008 §6.6
- **Run ID**: `20260520-035223Z-20061290`
- **Bundle**: `data/testnet/20260520-035223Z-20061290/`
- **Commit**: `ea18d9ad198deca3d0d8d1ceda9562e83717d16f`
- **Decision**: abort; not a SourcePolicy promotion / demotion record.

## Scope

This was a control-machine rerun of the 6 h testnet canary after
`ws_connected` was wired to live Nautilus kernel engines. It was stopped
early because `logs/alerts.log` appeared at startup, invalidating the
"clean canary" condition before the 6 h window could continue.

## Timeline

- `2026-05-20T03:52:23.177Z`: runner started with `git_dirty=false`.
- `2026-05-20T03:52:23.197Z`: `strategies_registered=1`.
- `2026-05-20T03:52:23.198Z`: first heartbeat wrote
  `ws_connected=false`; `alerts.log` emitted `ws_disconnected`.
- `2026-05-20T03:52:53.216Z`: next heartbeat showed
  `ws_connected=true`, `ws_reconnect_count=1`.
- `2026-05-20T03:54:20.702Z`: operator emergency flatten was started.
- `2026-05-20T03:54:21.038Z`: emergency flatten completed successfully.
- `2026-05-20T03:55:58.852Z`: runner shutdown completed with
  `shutdown_reason=node_stopped`.

The first emergency-flatten attempt was run inside the control sandbox and
failed DNS resolution. The same command was rerun outside the sandbox and
succeeded.

## Runtime Evidence

`run_manifest.json`:

- `elapsed_seconds=215.675842`
- `git_dirty=false`
- `strategies_registered=1`
- `enable_strategy_execution=true`
- `write_live_sidecars=true`
- `shutdown_reason=node_stopped`
- `exchange_error_count=0`
- `ws_reconnect_count=1`
- `runtime.sidecar.success=true`

Sidecars:

- `orders.parquet`: 2 rows
  - BUY `0.001 BTCUSDT`, filled at `76731.86`
  - SELL `0.001 BTCUSDT`, rejected during shutdown with Binance
    `insufficient balance`
- `fills.parquet`: 1 BUY fill
- `positions.parquet`: 1 LONG position row from the runner's pre-flatten
  sidecar view
- `signal_lineage.parquet`: 2 restamped wall-clock signal rows
- `account_balances.parquet`: 451 rows

Emergency flatten:

- `success=true`
- `closed_positions=1`
- closed `LONG 0.001 BTCUSDT` with market SELL order `5368618`
- `avg_price=76731.85`
- `residual_orders=[]`
- `residual_positions=[]`
- `elapsed_seconds=0.3360901319538243`

## Alert Outcome

`logs/alerts.log` contains:

- `ws_disconnected` at startup (`severity=warning`)
- `emergency_flatten_started`
- `signal_lag_exceeded_threshold`
- `emergency_flatten_started` from the successful sandbox-external retry
- `emergency_flatten_completed`

The startup `ws_disconnected` was an implementation artifact: the live
telemetry reader sampled Nautilus kernel connection state before the data
and execution engines had completed their first connection. That initial
pre-connect `False` should not count as a disconnect or reconnect.

## Follow-Up

Patch `LiveTelemetryReader` so startup `False` readings are suppressed until
the first observed connected state. After that first connection, real
`True -> False -> True` transitions must still emit `ws_disconnected` and
increment `ws_reconnect_count`.

After the patch, rerun the control-machine unit suite and only then schedule
another 6 h testnet canary.

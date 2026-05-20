# Phase 3f testnet canary abort — signal lag threshold

- **Date**: 2026-05-20 UTC
- **ADR**: ADR-008 §6.6
- **Run ID**: `20260520-040143Z-90c3c62b`
- **Bundle**: `data/testnet/20260520-040143Z-90c3c62b/`
- **Commit**: `087d8f0f6818bc73aa1e33f2f423d6eb50d10990`
- **Decision**: abort; not a SourcePolicy promotion / demotion record.

## Scope

This control-machine canary reran after the startup `ws_connected=false`
suppression patch. Startup telemetry was clean: the first heartbeat reported
`ws_connected=true` and `ws_reconnect_count=0`, with no startup
`ws_disconnected` alert.

The session was later invalidated by repeated
`signal_lag_exceeded_threshold` warnings. The underlying issue was
operational configuration: `signal_lag_threshold_seconds=60` is too tight
for a 1m bar-driven strategy when `last_signal_ns` is the source
`SignalEvent.ts_event`, not the wall-clock time at which the strategy pops
the signal.

## Runtime Evidence

- Runner started: `2026-05-20T04:01:43Z`
- Runner stopped: after operator `TERM` at `2026-05-20T09:50Z`
- No `run_manifest.json` or live sidecars were written because the runner
  was terminated after emergency flatten.
- Heartbeats: 698 rows
- Watchdog: healthy through the final observed heartbeat; no watchdog
  flatten invocation.
- Nautilus stdout: `ERROR=0`, `WARN=8`
- Real order path:
  - `2026-05-20T04:05:00.348Z`: BUY `0.001 BTCUSDT` filled at
    `76787.75 USDT`, venue order `5371356`, trade `1787552`.
  - `2026-05-20T09:50:10.121Z`: emergency flatten closed the LONG with
    market SELL order `5452063`, avg price `77492.93`.

## Alert Outcome

`logs/alerts.log` contains 336 alert rows:

- `signal_lag_exceeded_threshold` repeated throughout the session with
  `lag_seconds` just over 60 seconds.
- `emergency_flatten_started`.
- `emergency_flatten_completed`.

No `ws_disconnected` alert fired in this rerun, confirming the startup
WS telemetry fix worked.

## Emergency Flatten

`emergency_flatten.json`:

- `success=true`
- `closed_positions=1`
- `closed LONG 0.001 BTCUSDT`
- `cancelled_orders=[]`
- `residual_orders=[]`
- `residual_positions=[]`
- `elapsed_seconds=0.43506124801933765`

Exchange-side BTC was flat after the flatten (`BTC free=0`, `locked=0`).

## Follow-Up

For the restamp-based first canary, configure the runner with
`--signal-lag-threshold-seconds 120.0`. That preserves the advisory alert
for real producer stalls while allowing one closed-1m-bar polling cadence
plus telemetry jitter.

The runbook and local operator launcher were updated accordingly. The next
attempt should restamp fresh signals and rerun the 6 h canary on the control
machine.

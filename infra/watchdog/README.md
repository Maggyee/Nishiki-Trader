# Phase 3 Testnet Watchdog

- **Purpose**: Minimal external heartbeat watchdog for ADR-008 §5.5 / §6.4.
- **Current phase**: Phase 3d implementation.
- **Boundary**: This directory owns only watchdog state/history and the script that checks `data/testnet/<run_id>/logs/heartbeat.jsonl`; it does not read exchange credentials or place orders directly.
- **Next entrypoint**: `python -m infra.watchdog.watchdog --active-run-id <run_id> --instrument-id BTCUSDT.BINANCE`.

The watchdog is intentionally small: it reads the most recent heartbeat, writes
`infra/watchdog/state.json`, appends one tick to
`infra/watchdog/history.jsonl`, and invokes the existing
`apps.strategies_nautilus.runners.emergency_flatten` CLI when the heartbeat is
stale. Emergency flatten owns credential loading and exchange calls.

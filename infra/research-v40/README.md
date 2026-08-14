# infra/research-v40

## Purpose
Contains automated daily shadow execution infrastructure for Phase 2 Alpha Research Protocol v40 (`VXN` NASDAQ Volatility Relief Strategy).

## Current Phase
Phase 2 (Alpha Research Paper Shadow Forward Tracking).

## Boundaries
- Executes point-in-time snapshot collection for `VXN` daily index.
- Appends `SignalEvent v1` into `data/research-v40/shadow/signals.db`.
- Does not touch live execution orders or manage capital.
- Does not load secrets or private trading credentials.

## Next Implementation Entrypoint
`run-daily-shadow.sh` — executed daily via system crontab (`0 3 * * 1-5`).

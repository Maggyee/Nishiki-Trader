# Research Protocol v48 Infrastructure

## Purpose
Automated daily shadow data collection and signal generation for Protocol v48 (`rule_crypto_basis_relief_v1 / crypto-btc-basis-below-ma10-lag1d-v1`).

## Cadence
Daily at 04:15 UTC.

## Command
```bash
uv run python -m apps.ops.research_v48_shadow_daily --run-once
```

## Storage
- `data/research-v48/shadow/raw/`: Daily raw snapshots
- `data/research-v48/shadow/factors/`: Shadow factor CSVs
- `data/research-v48/shadow/signals.db`: Shadow `SignalEvent v1` SQLite store
- `data/research-v48/shadow/state.json`: Execution run history
- `docs/progress/phase-2-research-v48-paper-shadow-status.json`: Stage health status

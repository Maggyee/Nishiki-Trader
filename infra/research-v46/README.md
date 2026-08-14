# Research Protocol v46 Infrastructure

## Purpose
Houses daily prospective paper shadow automation for Protocol v46 Binance Perpetual Premium Index Standard Basis Relief (`rule_crypto_prem_relief_v1 / crypto-btc-prem-diff5-negative-lag1d-v1`).

## Current Phase
Phase 2 Alpha Research Protocol v46 (`hold @ paper_shadow`).

## Boundaries
- Executes daily prospective data collection via `apps.ops.research_v46_shadow_daily`.
- Emits `SignalEvent v1` into SQLite store at `data/research-v46/shadow/signals.db`.
- Strictly read-only dry-run signals; does not load credentials, mutate `SourcePolicy`, or touch live/testnet order execution paths.

## Next Implementation Entrypoint
`apps.ops.research_v46_shadow_daily --run-once`

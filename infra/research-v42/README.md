# Research Protocol v42 Infrastructure

## Purpose
Automated daily collection and signal generation for Phase 2 Alpha Research Protocol v42 (`rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1`).

## Phase and Boundaries
- Current Phase: Phase 2 Alpha Research (Paper Shadow).
- Boundaries: Forward paper shadow only; no live order execution, no testnet execution, no exchange credentials loaded.

## Daily Runner Entrypoint
- Command: `python -m apps.ops.research_v42_shadow_daily`
- Crontab entry: `45 3 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v42_shadow_daily >> /home/orca/orca/projects/trader/data/research-v42/shadow/cron.log 2>&1`
- Output status: `docs/progress/phase-2-research-v42-paper-shadow-status.json`
- SQLite store: `data/research-v42/shadow/signals.db`

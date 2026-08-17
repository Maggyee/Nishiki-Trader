# 2026-08-17 Protocol v48 Shadow Scheduler Installation

- **Scheduler target**: `apps.ops.research_v48_shadow_daily`.
- **Cadence**: Daily at 04:15 UTC (`15 4 * * *`).
- **Cron configuration**:
  ```bash
  15 4 * * * cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v48_shadow_daily >> /home/orca/orca/projects/trader/data/research-v48/shadow/cron.log 2>&1
  ```
- **Operator status**: Installed in user crontab (`orca`).
- **Boundaries**:
  - `loads_credentials`: False.
  - `mutates_source_policy`: False.
  - `touches_live_path`: False.
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

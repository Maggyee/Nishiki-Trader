# 2026-08-24 Protocol v22 Shadow Scheduler Installation

- **Status**: installed and active.
- **Candidate**: `rule_cboe_implied_correlation_relief_v1 / cboe-cor1m-diff5-negative-lag1d-v1`.
- **Mechanism**: user crontab (`orca`).
- **Schedule**: weekdays at 04:30 UTC (`30 4 * * 1-5`).
- **Command**:
  ```bash
  30 4 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v22_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v22-forward >> /home/orca/orca/projects/trader/data/research-v22-forward/cron.log 2>&1
  ```
- **Boundaries**:
  - `dry_run=True`, multiplier 0.2, no exchange keys.
  - Fail closed on any historical revision or data anomaly.
  - Future blind (2026-09..2027-01) remains sealed.

# 2026-08-14 Protocol v34 Shadow Scheduler Installation

- **Status**: installed and active.
- **Candidate**: `rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1`.
- **Mechanism**: user crontab (`orca`).
- **Schedule**: weekdays at 02:45 UTC (`45 2 * * 1-5`).
- **Command**:
  ```bash
  45 2 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v34_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v34-forward >> /home/orca/orca/projects/trader/data/research-v34-forward/cron.log 2>&1
  ```
- **Boundaries**:
  - `dry_run=True`, multiplier 0.2, no exchange keys.
  - Fail closed on any historical revision or data anomaly.
  - Future blind (2026-09..2027-01) remains sealed.

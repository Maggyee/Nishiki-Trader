# 2026-08-14 Protocol v36 Shadow Scheduler Installation

- **Status**: installed and active.
- **Candidate**: `rule_cboe_vpn_expansion_v1 / cboe-vpn-diff5-positive-lag1d-v1`.
- **Mechanism**: user crontab (`orca`).
- **Schedule**: weekdays at 03:00 UTC (`00 3 * * 1-5`).
- **Command**:
  ```bash
  00 3 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v36_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v36-forward >> /home/orca/orca/projects/trader/data/research-v36-forward/cron.log 2>&1
  ```
- **Boundaries**:
  - `dry_run=True`, multiplier 0.2, no exchange keys.
  - Fail closed on any historical revision or data anomaly.
  - Future blind (2026-09..2027-01) remains sealed.

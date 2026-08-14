# 2026-08-14 Protocol v42 Shadow Scheduler Installation

- **Status**: INSTALLED & VERIFIED.
- **Strategy**: `rule_cboe_vix6m_relief_v1 / cboe-vix6m-diff5-negative-lag1d-v1` (Cboe 6-Month Volatility Index Relief).
- **Schedule**: `45 3 * * 1-5` (Mon-Fri 03:45 UTC).
- **Crontab command**: `cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v42_shadow_daily >> /home/orca/orca/projects/trader/data/research-v42/shadow/cron.log 2>&1`
- **Verification**: `infra/research-v42/run-daily-shadow.sh` executed cleanly and updated status to `HEALTHY`.
- **Trading effect**: None; forward paper shadow signals only; live trading remains blocked by the Phase 6 gate.

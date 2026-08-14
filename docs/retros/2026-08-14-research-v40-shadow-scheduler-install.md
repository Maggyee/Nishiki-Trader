# 2026-08-14 Protocol v40 Shadow Scheduler Installation

- **Status**: INSTALLED & VERIFIED.
- **Strategy**: `rule_cboe_vxn_relief_v1 / cboe-vxn-diff5-negative-lag1d-v1` (Cboe NASDAQ Volatility Index Relief).
- **Schedule**: `15 3 * * 1-5` (Mon-Fri 03:15 UTC).
- **Crontab command**: `cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v40_shadow_daily >> /home/orca/orca/projects/trader/data/research-v40/shadow/cron.log 2>&1`
- **Verification**: `infra/research-v40/run-daily-shadow.sh` executed cleanly and updated status to `HEALTHY`.
- **Trading effect**: None; forward paper shadow signals only; live trading remains blocked by the Phase 6 gate.

# 2026-08-14 Protocol v46 Shadow Scheduler Installation

- **Status**: PASSED.
- **Strategy**: `btc_prem_diff5_negative` (`rule_crypto_prem_relief_v1 / crypto-btc-prem-diff5-negative-lag1d-v1`).
- **Cron entry**: `00 4 * * * cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v46_shadow_daily >> /home/orca/orca/projects/trader/data/research-v46/shadow/cron.log 2>&1`
- **Cadence**: Daily at 04:00 UTC (7 days/week for 24/7 crypto perpetuals).
- **Target log**: `data/research-v46/shadow/cron.log`
- **Trading effect**: None; live trading remains blocked by the Phase 6 gate.

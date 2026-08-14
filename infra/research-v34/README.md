# Research Protocol v34 Forward Paper-Shadow Infrastructure

## Purpose

Automated prospective collection and verification for Protocol v34 Cboe 5-Year Treasury Note Yield Relief (`rule_cboe_fvx_relief_v1 / cboe-fvx-diff5-negative-lag1d-v1`) under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`.

## Schedule

Weekdays at 02:45 UTC (`45 2 * * 1-5`) via the `orca` user crontab:

```bash
45 2 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v34_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v34-forward >> /home/orca/orca/projects/trader/data/research-v34-forward/cron.log 2>&1
```

## Boundaries

- Dry-run only; no orders, no live credentials, no `SourcePolicy` mutation.
- Collects official FVX from Cboe and 168h BTCUSDT klines from Binance public REST API.
- Evidence threshold: $\ge 7$ distinct qualified UTC collection days OR $\ge 50$ new forward signal events before `paper_simulated` review can be requested.

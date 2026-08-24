# Research Protocol v22 Forward Paper-Shadow Infrastructure

## Purpose

Automated prospective collection and verification for Protocol v22 Cboe 1-Month Implied Correlation Relief (`rule_cboe_implied_correlation_relief_v1 / cboe-cor1m-diff5-negative-lag1d-v1`) under `SourcePolicy(dry_run=True, position_pct_multiplier=0.2, min_confidence_override=None)`.

## Schedule

Weekdays at 03:00 UTC (`00 3 * * 1-5`) via the `orca` user crontab:

```bash
00 3 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v22_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v22-forward >> /home/orca/orca/projects/trader/data/research-v22-forward/cron.log 2>&1
```

## Boundaries

- Dry-run only; no orders, no live credentials, no `SourcePolicy` mutation.
- Collects official COR1M from Cboe and 168h BTCUSDT klines from Binance public REST API.
- Evidence threshold: $\ge 7$ distinct qualified UTC collection days OR $\ge 50$ new forward signal events before `paper_simulated` review can be requested.

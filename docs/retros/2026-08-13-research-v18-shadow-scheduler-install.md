# 2026-08-13 Research v18 paper-shadow scheduler installation

- **Identity**: `rule_nasdaq_vol_relief_v2 / cboe-vxn-ohlc5obs-negative-1d-v1`
- **Stage**: `hold @ paper_shadow`
- **Policy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`
- **Installed at**: 2026-08-13T03:18:16Z
- **Mechanism**: user crontab
- **Calendar**: `30 3 * * 1-5` (UTC host timezone)

## Installation result

The operator explicitly approved recurring collection. Day 1 had already
qualified from pushed commit `e90799e`. This host has no usable user-systemd
bus, so the collector was installed through the existing `orca` user crontab.
`cron.service` is the operational mechanism, matching v8 and v16.

The installed command is:

```text
30 3 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v18_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v18-forward >> /home/orca/orca/projects/trader/data/research-v18-forward/cron.log 2>&1
```

Post-install inspection found the v18 entry exactly once. The pre-existing v8
02:30 UTC and v16 12:30 UTC entries remain present exactly once each. The
complete installed crontab fingerprint is
`sha256:3f4d6a1c32dd56cd2277eee8a23ecf94823c41a0eaead502a9607335fe19eb21`.

## Boundaries

The schedule runs only the credential-free collector. Each attempt must still
pass clean-git/on-origin provenance, VXN D+1 freshness and revision checks,
and BTC closed-bar continuity/revision checks. Failed attempts remain
journaled and do not count as qualified days.

Installation does not alter the frozen collection contract, strategy
parameters, or `SourcePolicy`; does not authorize `paper_simulated`; and does
not start Nautilus, testnet, live trading, orders, or fills. Reaching 7 days or
50 new forward signals creates a separate human review opportunity only.

# 2026-08-12 Research v16 paper-shadow scheduler installation

- **Identity**: `rule_us_treasury_volatility_relief_v2 / treasury-nominal10-absdiff5-20-negative-lag2d-v1`
- **Stage**: `hold @ paper_shadow`
- **Policy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`
- **Installed at**: 2026-08-12T11:49:24Z
- **Mechanism**: user crontab
- **Calendar**: `30 12 * * 1-5` (UTC host timezone)

## Installation result

The operator explicitly approved recurring collection after the manual Day 1
qualification. This host has no usable user-systemd bus, so the collector was
installed through the existing `orca` user crontab mechanism. `cron.service`
is active.

The installed command is:

```text
30 12 * * 1-5 cd /home/orca/orca/projects/trader && /home/orca/orca/projects/trader/.venv/bin/python -m apps.ops.research_v16_shadow_daily --repo-root /home/orca/orca/projects/trader --data-root /home/orca/orca/projects/trader/data/research-v16-forward >> /home/orca/orca/projects/trader/data/research-v16-forward/cron.log 2>&1
```

Post-install inspection found the v16 entry exactly once. The pre-existing v8
02:30 UTC entry remains present exactly once. The complete installed crontab
fingerprint is
`sha256:d22697d8fa6d981eb1173ad17f58211d4bafcbc817c37ff4f3a3dbb793f115ad`.

## Boundaries

The schedule runs only the credential-free collector. Each attempt must still
pass clean-git/on-origin provenance, Treasury D+2 freshness and revision
checks, and BTC closed-bar continuity/revision checks. Failed attempts remain
journaled and do not count as qualified days.

Installation does not alter the frozen collection contract, strategy
parameters, or `SourcePolicy`; does not authorize `paper_simulated`; and does
not start Nautilus, testnet, live trading, orders, or fills. Reaching 7 days or
50 new forward signals creates a separate human review opportunity only.

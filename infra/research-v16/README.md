# Research Protocol v16 paper shadow

This directory documents the optional deployment boundary for the
credential-free v16 Treasury-volatility paper-shadow collector. The collector
writes only to the gitignored `data/research-v16-forward/` tree. It never
loads credentials, places orders, changes `SourcePolicy`, starts a Nautilus
runtime, touches testnet/live, or opens the sealed future blind.

Current phase: collector implementation and manual first-attempt
qualification. No timer, cron entry, service, or recurring process is
installed by this directory. Scheduling remains a separate operator decision.

The implementation entrypoint is:

```bash
uv run python -m apps.ops.research_v16_shadow_daily \
  --repo-root /home/orca/orca/projects/trader \
  --data-root /home/orca/orca/projects/trader/data/research-v16-forward
```

The frozen prospective cadence is weekdays at 12:30 UTC. Each attempt fetches
the previous and current official U.S. Treasury nominal-yield annual CSVs,
uses only observations eligible under D+2, captures 167 contiguous closed
public BTCUSDT hourly bars, detects revisions against accepted local state,
and writes dry-run `SignalEvent v1` lineage state. Multiple attempts on one UTC
date count as at most one qualified day.

Only an explicit future operator instruction may add a scheduler. Reaching
7 qualified days or 50 new forward signals creates human review eligibility;
it never automatically authorizes `paper_simulated`.

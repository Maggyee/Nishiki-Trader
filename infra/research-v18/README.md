# Research Protocol v18 paper shadow

This directory documents the optional deployment boundary for the
credential-free v18 VXN-volatility paper-shadow collector. The collector
writes only to the gitignored `data/research-v18-forward/` tree. It never
loads credentials, places orders, changes `SourcePolicy`, starts a Nautilus
runtime, touches testnet/live, or opens the sealed future blind.

Current phase: recurring paper-shadow collection after a qualified manual Day
1. The operator approved a user-crontab deployment on 2026-08-13 because this
host has no usable user-systemd bus. No service or timer file is enabled by
this directory; the repository remains declarative and the host crontab is the
operational deployment.

The implementation entrypoint is:

```bash
uv run python -m apps.ops.research_v18_shadow_daily \
  --repo-root /home/orca/orca/projects/trader \
  --data-root /home/orca/orca/projects/trader/data/research-v18-forward
```

The frozen prospective cadence is weekdays at 03:30 UTC, after the v8 02:30
UTC GVZ collector. Each attempt fetches the official Cboe VXN OHLC history,
uses only D+1 eligible closes, captures 167 contiguous closed public BTCUSDT
hourly bars, detects revisions against accepted local state, and writes
dry-run `SignalEvent v1` lineage. Multiple attempts on one UTC date count as
at most one qualified day.

The installed host entry is `30 3 * * 1-5` and appends output to
`data/research-v18-forward/cron.log`. Reaching 7 qualified days or 50 new
forward signals creates human review eligibility; it never automatically
authorizes `paper_simulated`.

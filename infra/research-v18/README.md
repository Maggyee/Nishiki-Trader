# Research Protocol v18 paper shadow

This directory documents the optional deployment boundary for the
credential-free v18 VXN-volatility paper-shadow collector. The collector
writes only to the gitignored `data/research-v18-forward/` tree. It never
loads credentials, places orders, changes `SourcePolicy`, starts a Nautilus
runtime, touches testnet/live, or opens the sealed future blind.

Current phase: prospective collection after the identity-specific ADR-007
`hold @ paper_shadow` review. Recurring host scheduling requires the already
recorded operator approval plus a clean pushed collector commit and a
qualified Day 1. This directory does not mutate the host crontab by itself.

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

Reaching 7 qualified days or 50 new forward signals creates human review
eligibility; it never automatically authorizes `paper_simulated`.

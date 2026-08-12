# Research Protocol v12 forward data candidate

This directory contains optional scheduling templates for the credential-free
Protocol v12 stablecoin forward collector. The collector writes only to the
gitignored `data/research-v12-forward/` tree and never opens orders, fills,
SourcePolicy, paper-shadow, testnet, live trading, v11 confirmation, or the
shared future blind.

Current phase: implementation and manual Day 0 qualification. The schedule is
intentionally **not installed** by repository changes. Enabling a recurring
host job is an operational action and requires explicit operator approval.

The next implementation entrypoint is:

```bash
python -m apps.ops.research_v12_forward_daily \
  --repo-root /home/orca/orca/projects/trader \
  --data-root /home/orca/orca/projects/trader/data/research-v12-forward
```

The frozen cadence is daily at 12:30 UTC. A systemd user timer template can be
added when the operator authorizes recurring collection; this host currently
has no usable user-systemd bus, so an approved deployment would likely use the
existing user crontab mechanism.

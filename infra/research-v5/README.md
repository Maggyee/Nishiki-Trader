# Research Protocol v5 cloud collector

- **Purpose**: run the four credential-free BTC/ETH curve/BVOL snapshot jobs
  once per UTC day from one locked clean commit.
- **Current phase**: templates only; do not enable before local July
  schema/lineage qualification passes and its retro is committed.
- **Boundaries**: collection only. No signals, PnL, Nautilus runtime,
  SourcePolicy mutation, testnet, credentials, or live-order access.
- **Next implementation entrypoint**:
  `python -m apps.ops.research_v5_daily --dry-run ...` on the intended cloud
  checkout, followed by a single explicitly dated qualification run.

The timer is independent of the completed Protocol v2 collector. It does not
modify, stop, or reuse the v2 unit, volume, image, or ledger. The data root is
append-preserving: identical content is idempotent, while an upstream revision
creates a new vintage and blocks result comparison.

Install only after replacing `TRADER_GIT_SHA` with the clean 40-character
commit that contains the pre-registration:

```bash
sudo install -d -m 0700 /var/lib/nishiki-trader/research-v5
sudo install -d -m 0755 /etc/nishiki-trader
sudo install -m 0600 infra/research-v5/research-v5.env.example \
  /etc/nishiki-trader/research-v5.env
sudo install -m 0644 infra/research-v5/systemd/nishiki-research-v5-collector.service \
  /etc/systemd/system/
sudo install -m 0644 infra/research-v5/systemd/nishiki-research-v5-collector.timer \
  /etc/systemd/system/
```

Run the network-disabled preflight first:

```bash
set -a
. /etc/nishiki-trader/research-v5.env
set +a
/opt/nishiki-trader/.venv/bin/python -m apps.ops.research_v5_daily \
  --date 2026-07-16 \
  --data-root "$RESEARCH_V5_DATA_ROOT" \
  --expected-git-commit "$TRADER_GIT_SHA" \
  --repo-root /opt/nishiki-trader \
  --dry-run
```

The service/timer remain disabled until the qualification retro authorizes
forward collection. Enabling the timer does not authorize signal generation or
opening the 2026-08..12 blind PnL.

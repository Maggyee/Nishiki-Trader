# Research Protocol v5 cloud collector

- **Purpose**: run the four credential-free BTC/ETH curve/BVOL snapshot jobs
  once per UTC day from one locked clean commit and commit-labelled image.
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

Each daily batch attempts all four asset/dataset streams even when one archive
is unavailable or invalid. It preserves successful immutable snapshots,
records every failed stream with `desired_state=flat`, marks the batch
incomplete, and exits nonzero so systemd monitoring still sees the failure.

Install only after replacing `TRADER_GIT_SHA` with the clean 40-character
commit that contains the pre-registration:

```bash
sudo install -d -m 0700 -o 1002 -g 1002 /var/lib/nishiki-trader/research-v5
sudo install -d -m 0755 /etc/nishiki-trader
sudo install -m 0600 infra/research-v5/research-v5.env.example \
  /etc/nishiki-trader/research-v5.env
sudo install -m 0644 infra/research-v5/systemd/nishiki-research-v5-collector.service \
  /etc/systemd/system/
sudo install -m 0644 infra/research-v5/systemd/nishiki-research-v5-collector.timer \
  /etc/systemd/system/
docker compose --env-file /etc/nishiki-trader/research-v5.env \
  -f infra/research-v5/compose.yml build collector
```

Run the network-disabled preflight first:

```bash
docker compose --env-file /etc/nishiki-trader/research-v5.env \
  -f infra/research-v5/compose.yml run --rm --no-deps collector \
  --date 2026-07-16 \
  --data-root /data/research-v5 \
  --expected-git-commit "$(git rev-parse HEAD)" \
  --repo-root /app \
  --dry-run
```

The image copies only the two collector modules and the provider contract. Its
read-only `.collector-git-sha` must match both `TRADER_GIT_SHA` and the CLI
argument before any request. It contains pandas/pyarrow for normalized Parquet
but no Nautilus runtime, signal generator, exchange credential, or order path.

The service/timer remain disabled until the fast-track reports authorize
forward collection. Enabling the timer does not authorize signal generation or
opening the 2026-08..12 blind PnL.

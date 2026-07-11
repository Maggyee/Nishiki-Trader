# Research Protocol v2 cloud collector

- **Purpose**: collect one immutable Deribit options snapshot and one Binance
  quarterly-basis snapshot per UTC day, then stop after seven consecutive paired
  days.
- **Current phase**: provider schema/freshness qualification only.
- **Boundaries**: no credentials, prices/returns/PnL summaries, SignalStore,
  NautilusTrader, SourcePolicy, testnet, or live-order access.
- **Next implementation entrypoint**:
  `python -m apps.ops.research_v2_daily --data-dir PATH`.

The deployment is intentionally separate from `infra/docker-compose.yml`. It is
a one-shot container started by a host systemd timer, not a resident trading
service. The image is locked to one 40-character Git SHA for the entire attempt.

## Host paths

- repository: `/opt/nishiki-trader`
- evidence: `/var/lib/nishiki-trader/research-v2`
- environment: `/etc/nishiki-trader/research-v2.env`
- unit files: `/etc/systemd/system/nishiki-research-v2-collector.{service,timer}`

The evidence directory is append-preserving. Operational gaps close the current
attempt and start a new one; prior evidence is retained and never selected by
PnL. Duplicate days, hash drift, ledger drift, or malformed snapshots fail
closed.

## Build and preflight

From a clean checkout at the intended commit:

```bash
sudo install -d -m 0700 -o 1002 -g 1002 /var/lib/nishiki-trader/research-v2
sudo install -d -m 0755 /etc/nishiki-trader
sudo install -m 0600 infra/research-v2/research-v2.env.example \
  /etc/nishiki-trader/research-v2.env
sudo sed -i "s/^TRADER_GIT_SHA=.*/TRADER_GIT_SHA=$(git rev-parse HEAD)/" \
  /etc/nishiki-trader/research-v2.env
docker compose --env-file /etc/nishiki-trader/research-v2.env \
  -f infra/research-v2/compose.yml build collector
docker compose --env-file /etc/nishiki-trader/research-v2.env \
  -f infra/research-v2/compose.yml run --rm --no-deps collector --preflight
```

Preflight performs no network requests and writes no evidence. Do not rebuild,
pull, or change `TRADER_GIT_SHA` during an active seven-day attempt.

## Schedule and monitoring

```bash
sudo install -m 0644 infra/research-v2/systemd/nishiki-research-v2-collector.service \
  /etc/systemd/system/
sudo install -m 0644 infra/research-v2/systemd/nishiki-research-v2-collector.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nishiki-research-v2-collector.timer
systemctl list-timers nishiki-research-v2-collector.timer
journalctl -u nishiki-research-v2-collector.service -n 100 --no-pager
```

The timer tries at 03:15, 06:15, and 09:15 UTC. A completed day is idempotent,
so retries do not call providers again. Exit code `75` is a transient network
failure; exit code `2` is a fail-closed configuration or integrity error.

After `COMPLETE` exists, the unit's `ExecCondition` skips all future container
and network work. Final review is read-only:

```bash
docker compose --env-file /etc/nishiki-trader/research-v2.env \
  -f infra/research-v2/compose.yml run --rm --no-deps collector --review-only
sha256sum /var/lib/nishiki-trader/research-v2/qualification-ledger.jsonl
```

Archive the whole evidence directory and its SHA-256 off-host. Completion does
not authorize factors, signals, backtests, Protocol v3 access, paper/testnet, or
live trading.

# Research Protocol v6 one-time qualification

- **Purpose**: collect and verify only the BTCUSDT/ETHUSDT USD-M `bookDepth`
  and 1m mark-price qualification evidence for UTC date 2026-07-17.
- **Current phase**: collector/image implementation. The qualification archive
  bodies remain unopened until this exact implementation commit is pushed and
  deployed from a clean detached checkout.
- **Boundaries**: credential-free provider qualification only. No historical
  range, factor output, signal generator, PnL, NautilusTrader, SourcePolicy,
  testnet, timer, daemon, or live-order path is present.
- **Next implementation entrypoint**: build
  `nishiki-research-v6:<full-sha>`, run the network-disabled dry-run against an
  empty data root, then run the `download` service exactly once.

The image contains only the v6 qualification module and its locked provider
contract. The OCI revision label, `TRADER_GIT_SHA`, internal
`/app/.collector-git-sha`, and required `--expected-git-commit` must all refer
to the same full 40-character commit before any request can run.

Each successful HTTP 200 response is published atomically as one immutable
directory containing the exact bytes and HTTP metadata. A rerun reads those
bytes first and never requests them again. Timeout/5xx failures leave only the
missing response eligible for a later retry. HTTP 4xx, checksum, schema, UTC
coverage, side/band, tamper, or content-conflict failures stop qualification
without deleting or rewriting retained evidence.

## Build and network-disabled preflight

Create the empty append-preserving host root and a local env file containing
the exact pushed commit:

```bash
sudo install -d -m 0700 -o 1002 -g 1002 /var/lib/nishiki-trader/research-v6
cp infra/research-v6/research-v6.env.example /tmp/research-v6.env
# Replace TRADER_GIT_SHA with the full clean pushed commit before continuing.
docker compose --env-file /tmp/research-v6.env \
  -f infra/research-v6/compose.yml build download
docker compose --env-file /tmp/research-v6.env \
  -f infra/research-v6/compose.yml run --rm --no-deps offline
```

The `offline` service has `network_mode: none` and a read-only data mount. Its
dry-run must report an empty data root, four ZIP plans, four checksum siblings,
`network_accessed=false`, and `data_written=false`.

## One qualification download

Only after the preflight passes:

```bash
docker compose --env-file /tmp/research-v6.env \
  -f infra/research-v6/compose.yml run --rm --no-deps download
```

The all-asset success condition is exactly two immutable snapshots, two
single-row audit Parquets, four raw ZIPs, four checksums, eight cached HTTP 200
responses, and zero blocker/conflict markers. Nothing in this command computes
or saves a factor value, daily aggregation, state, signal, return, or PnL.

## Read-only offline verification

Use the same image with no network and the evidence root mounted read-only:

```bash
docker compose --env-file /tmp/research-v6.env \
  -f infra/research-v6/compose.yml run --rm --no-deps offline \
  --asset all \
  --date 2026-07-17 \
  --verify /data/research-v6 \
  --data-root /data/research-v6 \
  --expected-git-commit "$(git rev-parse HEAD)"
```

Copying an existing evidence root for a second offline review is allowed;
re-accessing Binance to recreate the evidence is not. No systemd unit or timer
belongs in this directory because v6 qualification is a one-time gate.

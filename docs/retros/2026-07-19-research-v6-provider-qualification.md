# 2026-07-19 Research Protocol v6 provider qualification

- **Decision**: `blocked_provider_qualification`.
- **Qualification date**: 2026-07-17 only.
- **Assets**: BTCUSDT and ETHUSDT.
- **Collector commit**:
  `93e97cfc34a628a12b20e73c3a3ee9ae35f0796b`.
- **Historical development/factor/signal/PnL**: not opened / not computed.
- **Trading-state effect**: none.

## Sequence and deployment identity

The independent collector, 34 synthetic tests, isolated image/Compose files
and status update were committed and pushed before the first v6 archive or
checksum body was opened. The full pre-access suite was 961 passed with 12
Postgres-dependent skips; Ruff and `git diff --check` passed.

The pushed commit was transferred as a Git bundle with SHA-256
`ae80b6975bf4e5d331a1478ad2955e6b3cbacc01ef3df85f36b4a190e8485851`
and checked out clean and detached at
`/opt/nishiki-trader-v6-93e97cf` on the ARM64 `oracle` host. The dedicated image
is
`nishiki-research-v6:93e97cfc34a628a12b20e73c3a3ee9ae35f0796b`, image ID
`sha256:efc0ffd2ed47e6b891fd66668255b5eba2934165928e920bf6d5b8a8ff364c4e`.
Its OCI revision, internal `/app/.collector-git-sha`, image environment and CLI
expected commit all match the collector commit. The image and host env contain
zero Binance/key/secret/token/password variable names.

No v6 systemd unit or timer was created. The independent v5 collector timer
remained active and enabled. The v6 checkout, image, volume and evidence root
are separate from v5.

## Network-disabled preflight

The `offline` Compose service rendered successfully with `network_mode: none`,
a read-only data mount, non-root user, dropped capabilities and
`no-new-privileges`. Its dry-run validated the commit marker and locked provider
hash, reported four ZIP plans plus four checksum siblings, and left the empty
data root unchanged:

```text
archive_request_count=4
checksum_request_count=4
http_request_count=8
data_root_empty=true
network_accessed=false
data_written=false
```

The dry-run report SHA-256 is
`92eec8efa7b27486063b3fec74782c4c8103c0de3b71a19235d1b1e5826a9dde`.

## Single qualification download

Exactly one network-enabled all-asset invocation was made. It retained all
eight successful HTTP 200 responses between `2026-07-19T01:56:05.441379Z` and
`2026-07-19T01:56:07.976463Z`: four ZIP bodies, four official checksum bodies
and their HTTP metadata. All four official archive checksums match. Storage has
zero content conflicts and zero permanent HTTP blockers.

The immutable raw hashes are:

| Asset | File | SHA-256 |
|---|---|---|
| BTCUSDT | `BTCUSDT-bookDepth-2026-07-17.zip` | `b887dbc734f2ebbc42138f5bfcce14b8fb73d16bebd6db90d48420c0482323d9` |
| BTCUSDT | bookDepth checksum | `257b9006bfa2f87cd49df03aa685eadff3cc6303d13960ed7d584832039f600e` |
| BTCUSDT | `BTCUSDT-1m-2026-07-17.zip` | `d0101ba959bebffe4c740350252fdb66be09acac849cf64bcf85f1050b2487e7` |
| BTCUSDT | mark-price checksum | `bfc91e4a904c5382da95836fee2d990a3ea91f54333a36b1969e03851cab6c4a` |
| ETHUSDT | `ETHUSDT-bookDepth-2026-07-17.zip` | `c43af2caa78b4902221f5eee49fa2c4e8fb40c36cfc2dcd00dd7732f4c5c3233` |
| ETHUSDT | bookDepth checksum | `b2d8e491baf64fdc5c9da8bd0a7430ffc157be31fb38f288c67d9fcdbb124205` |
| ETHUSDT | `ETHUSDT-1m-2026-07-17.zip` | `b5607317a4eeb147bd32653a6f60d6f46baf2f1c5510da4949ddfe6d25b5496e` |
| ETHUSDT | mark-price checksum | `6627e7cf83df6a1338178325bd292b56e3e234ac92f5a6e20d072953dc5a0d95` |

No snapshot or audit Parquet was written because both assets failed before an
asset could qualify. The machine download report is
`blocked_provider_qualification` and has SHA-256
`8c7ebe06d4ebed8282bf1e1601b401be19867c507f2df9e0199695d11ca9b1c1`.

## Hard grid blocker

Both official bookDepth CSVs have the exact locked header
`timestamp,percentage,depth,notional`, finite positive depth/notional values and
34,560 rows across 2,880 strictly increasing timestamp groups. Coverage spans
`2026-07-17 00:00:03` through `2026-07-17 23:59:31`, with maximum adjacent gap
34 seconds. Both mark-price ZIPs contain the complete 1,440 UTC-minute grid.

However, every BTC and ETH timestamp group contains 12 rows with the official
numeric grid:

```text
[-5, -4, -3, -2, -1, -0.20, +0.20, +1, +2, +3, +4, +5]
```

The pre-registered v6 contract requires exactly ten rows and exactly
`[-5…-1,+1…+5]`. All 2,880 groups per asset therefore fail the frozen grid;
zero groups match it. Removing the two ±0.20 rows would be post-data row
deletion and is explicitly forbidden.

The collector's first machine error was the stricter textual diagnostic
`percentage[0] must be an integer`, because the official CSV spells locked
values as `-5.00`, `-4.00`, and so on. That diagnostic is not the substantive
decision evidence. A separate read-only numeric audit of the retained bytes
proved the material 12-row/±0.20 mismatch above. Its SHA-256 is
`0e736c3ce65aad7129ef8b77efd612ea1a731ebf4bba576c7e6736636dbae554`.
The validator rule, provider interpretation, tolerance and candidate identity
were not changed after access.

Because the exact-grid gate already fails, qualification stopped before the
weighted-price side/band audit. No row was deleted, interpolated or re-labelled,
and no alternate grid, percentage band or tolerance was evaluated.

## Offline reproduction and evidence transfer

The same image replayed the saved response cache with `network_mode: none` and
a read-only data mount. It returned the same two permanent failures and the
same report SHA, while the remote evidence tree hash remained unchanged. The
evidence package was copied without another Binance request; its cloud and
local SHA-256 both equal:

```text
c627d6f2d246aad72334c28b1eecabd31fc7dd755739cae269352406c4845236
```

Local replay injected a fetch function that raises on any attempted network
request. The function was never called, both cached failures reproduced, and
the local raw-evidence tree hash was unchanged before/after. A second local
numeric audit independently matched both official checksums, 34,560 rows,
2,880 twelve-row groups, the ±0.20 additions and zero groups matching the
locked grid.

The ignored local evidence copy is under
`data/research-v6/provider-qualification-2026-07-17/`. Raw data, ZIPs,
checksums, HTTP metadata and generated evidence reports remain outside Git.

## Decision and boundaries

The only allowed recommendation is `blocked_provider_qualification`. Protocol
v6 stops here: no historical 2023–2025 body, registered factor, daily median,
buy/flat state, SignalEvent, Spot return, Nautilus run or PnL may be opened or
implemented under this identity. The 2026-08..12 blind remains sealed.

No credential was loaded, no SourcePolicy or promotion review was touched, no
testnet work resumed, and no live order path changed. The original registry,
Protocols v2-v5, v5 rejected candidates and v5 collection schedule remain
unchanged.

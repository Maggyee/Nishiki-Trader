# 2026-07-17 Research Protocol v3 Provider Qualification

- **Status**: Partial pass; hashrate qualified, DXY and VIX provider routes
  blocked.
- **Scope**: July schema, publication lag, and immutable lineage only.
- **Code baseline**: clean tracked commit `7afc61d`, aligned with `origin/main`.
- **PnL accessed**: no.
- **Trading effect**: none.

## Preconditions

The three identities, parameters, partitions, gates, URLs, and query parameters
were frozen before real provider access. All three CLI dry-runs reported
`network_accessed=false`, `data_written=false`, and every no-trading boundary
false. The focused collector suite passed 15 tests before collection.

## Hashrate qualification pass

The Blockchain.com request returned the locked JSON schema and produced:

```text
path=data/research-v3/raw/hashrate-20260717T095630Z-3fd819633239.json
snapshot_sha256=sha256:3fd8196332393d5f06ea4ec96ac7d37de76374f7a731c91b52a2bf5f2480a20d
vintage_id=hashrate:2026-07-17T09:56:30.186191Z:3fd819633239
row_count=30
first_observation_day=2026-06-17
last_observation_day=2026-07-16
completed_utc_day_count=30
unit=Hash Rate TH/s
period=day
offline_valid=true
```

The gitignored snapshot retains exact response bytes, raw-byte SHA-256, parsed
payload, audit summary, canonical envelope hash, vintage, and filename hash
prefix. Offline verification recomputed all lineage successfully.

## DXY and VIX fail-closed result

Both frozen Stooq GETs returned HTTP 200 but identified their bodies as
`text/html; charset=utf-8`. The body was a JavaScript browser-verification page,
not a CSV with the locked `Date,Open,High,Low,Close` fields. The collector
rejected both responses during CSV structure validation and wrote no DXY or VIX
snapshot. Repeating the same GET and parameters with a browser-style
User-Agent did not change the response class.

The page proposed an additional verification POST. It was not executed because
v3 locks exactly one unauthenticated GET per provider kind. No cookie workflow,
browser bypass, alternate Stooq host, symbol, provider, or metric was introduced
after access. Therefore:

- `miner_hashrate_recovery`: current provider schema/lineage qualified;
- `usd_weakness_impulse`: `blocked_provider_direct_csv_unavailable`;
- `equity_vol_relief`: `blocked_provider_direct_csv_unavailable`.

## Boundary audit and decision

No credentials were loaded. No factor CSV, return, SignalEvent, SignalStore row,
Nautilus run, PnL, SourcePolicy change, testnet resume, or live-path action
occurred. The 2020-2022 reserve and 2026-08..12 final blind remain unopened.

Do not solve the browser challenge inside v3 or replace the frozen provider in
place. Retain the valid hashrate snapshot as qualification evidence. DXY and VIX
may be retried only if the exact frozen GET again serves direct CSV; otherwise a
new provider route requires a new pre-registered protocol and identity review.
Protocol-level historical replication remains closed because all v3 data paths
have not passed qualification.

# 2026-07-17 Research Protocol v5 fast-track collection start

- **Status**: Historical collection opened after provider qualification; bulk
  collection not yet complete.
- **Qualification gate commit**: `e2955d3` pushed to `origin/main` before
  historical access.
- **Returns/PnL accessed**: no.
- **Trading effect**: none.

## First historical availability observations

The first locked curve date, 2021-06-01, failed closed because the next-quarter
`BTCUSDT_210924` archive and checksum returned 404. The index and front-quarter
archives existed. Credential-free HEAD checks found 2021-06-18 as the first day
where both required BTC quarterly contracts existed; BTC and ETH curve
snapshots for that day then passed all checksum and offline validation.

The first locked BVOL date, 2023-06-01, also returned 404 because the archive
product had not launched. Both BTC and ETH first appeared on 2023-06-20, but
that launch-day file starts at 01:31:40 UTC and is intentionally rejected as a
partial day. The 2023-06-21 file starts at 00:05:30 and contains an additional
four-second gap. The first complete BTC and ETH day is 2023-06-22; both contain
exactly 86,400 UTC-second buckets and passed immutable snapshot validation.

These gaps occur before the first August scoring folds. Protocol v5 already
fixes fold initial state to flat, forbids forward fill, and requires a missing
day to remain/return flat. No data source, date partition, candidate identity,
parameter, or threshold is changed.

An inspected 2023-08-01 BVOL file contains 86,398 observations and a genuine
two-second grid gap. That day must be rejected and represented as flat, while
later valid days must still be collected. The original range CLI stopped at
the first bad day, so it now records a per-day failure ledger, writes no
snapshot for the failed date, continues to later dates, and returns nonzero if
any day failed. This is stricter coverage accounting, not gap tolerance.

## Boundary audit and next action

No return, PnL, SignalEvent, SignalStore row, Nautilus run, SourcePolicy
mutation, testnet resume, credential, or live path was used. The future blind
remains unopened and the v5 timer remains disabled.

After the range-continuation change is committed and pushed, collect the two
locked historical ranges once. Preserve the JSON failure ledgers and treat
every failed date as flat. Only complete scoring-fold catalog and lineage may
enter the duplicated Nautilus fast-track review.

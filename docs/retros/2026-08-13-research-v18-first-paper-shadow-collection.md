# 2026-08-13 Research v18 first paper-shadow collection

- **Identity**: `rule_nasdaq_vol_relief_v2 / cboe-vxn-ohlc5obs-negative-1d-v1`
- **Stage**: `hold @ paper_shadow`
- **Policy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`
- **Attempt**: `20260813T031755Z-2d86f76f3b64`
- **Decision**: qualified Day 1; continue collection
- **Scheduler at attempt time**: not yet installed

## Provenance

The collector implementation and prospective contract were committed and
pushed at `e90799e` before the first request. The attempt ran from clean
`main` commit `e90799e01e6c7d38302fd7a06905576e44553044`, already contained
by `origin/main`.

The append-only local journal is
`data/research-v18-forward/journal/20260813T031755Z-2d86f76f3b64.json`, with
file SHA-256
`4d827c149a86ad22953012b3d6ed903b74b3822eef7f77a26555a3c2200e0a4c`.
All local data remains gitignored.

## VXN qualification

The attempt opened the official Cboe VXN OHLC history. Under the frozen D+1
rule, a collection at `2026-08-13T03:17:55.346991Z` could use observations
only through 2026-08-12.

- 4256 official rows from 2009-09-14 through 2026-08-12; 758 unfilled
  2020-2022 reserve rows remain in the same body.
- Age: one calendar day, below the frozen four-day cap.
- Forward fill: none.
- Historical revisions: none.
- Snapshot semantic fingerprint:
  `sha256:60ba1d0fe8a3621b3b8c6a8fe28ce8e9a276bd4162a74ee8d2302d86f76f3b64`.
- Snapshot file SHA-256:
  `6d8f5792ea534feaf920ca978193d8f07ac248968d9c6617181edab10489ae35`.

Independent `--verify` rebuilt the request identity, payload hash, parsed
audit, snapshot fingerprint, and vintage successfully.

## BTC qualification

The public Binance response contributed 167 closed BTCUSDT hourly bars. The
accepted range is contiguous, with no duplicate timestamp, gap, or historical
revision. Raw file SHA-256 is
`65f263e547ff80e8a936e0b4efc24287dc76de921b0ff180fd364e556a3d0020`.

## Signal accounting

The collector wrote 41 deterministic historical state-seeding
`SignalEvent v1` rows for the exact source/model. They all precede the
paper-shadow forward boundary and therefore count as zero new forward signals.
The local signal-store SHA-256 after the attempt is
`58aedab48fee894fb9775dad5051f3de62affadf129f89962ef632cab2cbd710`.

Current gate progress is 1/7 distinct qualified UTC collection days and 0/50
new forward signals. The OR threshold is not met and no
`paper_shadow -> paper_simulated` review is eligible.

## Boundaries

The attempt loaded no credentials, submitted no order, created no fill,
changed no `SourcePolicy`, started no paper/testnet/live runtime, and did not
open the 2026-09 through 2027-01 future blind.

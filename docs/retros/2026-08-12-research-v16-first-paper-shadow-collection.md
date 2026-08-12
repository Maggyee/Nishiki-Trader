# 2026-08-12 Research v16 first paper-shadow collection

- **Identity**: `rule_us_treasury_volatility_relief_v2 / treasury-nominal10-absdiff5-20-negative-lag2d-v1`
- **Stage**: `hold @ paper_shadow`
- **Policy**: `dry_run=True`, `position_pct_multiplier=0.2`, `min_confidence_override=None`
- **Attempt**: `20260812T104309Z-a3a1f27bf08b`
- **Decision**: qualified Day 1; continue collection
- **Scheduler**: not installed

## Provenance

The collector implementation and prospective contract were committed and
pushed before the first request. The attempt ran from clean `main` commit
`8bb03fd34e004829b8bb6f49a220d323dfc3c94f`, and that commit was already
contained by `origin/main`.

The append-only local journal is
`data/research-v16-forward/journal/20260812T104309Z-a3a1f27bf08b.json`, with
file SHA-256
`3774faa0d8c50d2fec7fabfacaaa91d641b7a825525e739510eb401240d4f940`.
All local data remains gitignored.

## Treasury qualification

The attempt opened the official U.S. Treasury nominal-yield CSVs for 2025 and
2026. Under the frozen D+2 rule, a collection at
`2026-08-12T10:43:09.049022Z` could use observations only through 2026-08-10.

- 401 numeric 10-year observations: 249 in 2025 and 152 in 2026.
- First/last usable observations: 2025-01-02 / 2026-08-10.
- Maximum calendar gap: four days, below the frozen five-day cap.
- Forward fill: none.
- Historical revisions: none.
- Snapshot semantic fingerprint:
  `sha256:d664075202a8539007197a1be78478909cc0465b6f5414b2b45ea3a1f27bf08b`.
- Snapshot file SHA-256:
  `83754ea2aae6b8bd0c95754e7586b87c125aba02f4a004fe485e4e0b85add1b9`.

The independent `--verify` path rebuilt the request identities, raw payload
hashes, parsed audit, snapshot fingerprint, and vintage successfully.

## BTC qualification

The public Binance response contributed 167 closed BTCUSDT hourly bars. The
accepted range is contiguous, with no duplicate timestamp, gap, or historical
revision. Raw file SHA-256 is
`de2e4d83d07213170501227fe8c5181f8cceabe229d8e54e7a6367b73fef7925`.

## Signal accounting

The collector wrote 92 deterministic historical state-seeding
`SignalEvent v1` rows for the exact source/model. They all precede or equal the
paper-shadow forward boundary and therefore count as zero new forward signals.
The local signal-store SHA-256 after the attempt is
`abec640c2a8b75a00c4f27d14ff1b6d0f3b7e0296554bcde3b25ce58f5cd49f7`.

Current gate progress is 1/7 distinct qualified UTC collection days and 0/50
new forward signals. The OR threshold is not met and no
`paper_shadow -> paper_simulated` review is eligible.

## Boundaries

The attempt loaded no credentials, submitted no order, created no fill,
changed no `SourcePolicy`, started no paper/testnet/live runtime, and did not
open the 2026-09 through 2027-01 future blind. No cron entry, systemd timer, or
other recurring schedule was installed. Repeating the collection requires a
separate operator decision about scheduling or another explicit manual run.

# Research Protocol v5 July schema qualification fix

## Scope

This retro records the first local, July-only schema qualification attempt for
Research Protocol v5. It contains no return or PnL analysis and does not open
the locked historical replication partitions.

## Provenance and sequence

- Pre-registration commit `f8437f5e5f4cb942c50656ac3f466bf563fc90b3` was
  pushed to `origin/main` before any real Binance response body was opened.
- The commit-locked 2026-07-16 dry-run produced four BTC/ETH curve/BVOL plans
  with `network_accessed=false`, `data_written=false`,
  `signals_generated=false`, and `pnl_computed=false`.
- The first real local batch failed closed on the BTC index-price file before
  creating a snapshot: the official Futures header names are `count` and
  `taker_buy_volume`, not the generic kline aliases used by the synthetic
  preregistration fixture.

## July-only schema observations

Inspection remained limited to the already-authorized 2026-07-16 qualification
files needed to diagnose that failure:

- Futures index-price and delivery-contract 1d files contain one header plus
  one valid UTC-day row and use `count`, `taker_buy_volume`, and
  `taker_buy_quote_volume`.
- BTC BVOL uses `BTCBVOL` as `base_asset`; ETH is therefore locked to the same
  official naming rule, `ETHBVOL`.
- The BTC BVOL file contains 86,400 strictly increasing observations, exactly
  one in every UTC-second bucket. Millisecond jitter within a bucket is allowed;
  a missing or duplicate second is rejected.

No v5 snapshot or normalized Parquet was written by the failed batch. No
credential, SignalStore write, signal generation, Nautilus run, return, PnL,
SourcePolicy mutation, testnet resume, or live path was used.

## Correction and boundaries

The collector and provider contract now match those official raw names and
fail closed on BVOL second-bucket gaps. Candidate source/model identities,
features hashes, formulas, parameters, dates, partitions, cost assumptions,
portfolio limits, and review gates are unchanged. The provider-contract hash
changes because the raw schema is now exact; the protocol and candidate
fingerprint hashes do not change.

The correction is covered by millisecond/microsecond/nanosecond archive tests,
an explicit BVOL intraday-gap test, and the existing duplicated Nautilus
integration chain. The next action is to push this correction, then rerun all
four 2026-07-16 qualification snapshots from that new clean commit. Historical
replication bodies remain forbidden until the four-snapshot qualification and
offline verification succeed.

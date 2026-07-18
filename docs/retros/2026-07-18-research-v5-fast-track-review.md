# 2026-07-18 Research Protocol v5 fast-track review

- **Decision**: `stop_before_testnet_resume`
- **Curve carry**: `reject_v5_candidate` before signals or PnL.
- **BVOL relief**: `reject_v5_candidate` after the locked diagnostic.
- **Future blind accessed**: no.
- **Trading effect**: none.
- **Machine result**:
  `docs/progress/phase-2-research-v5-fast-track-results.json`

## Collection and data gates

The frozen Binance-only collection completed without a vintage conflict.
Curve collection requested 579 days per asset and retained 37 valid daily
factor snapshots per asset; missing official quarterly archives remained
explicit flat failures. BVOL collection requested 945 days per asset and
retained 437 BTC and 406 ETH valid daily snapshots. All retained factor
snapshots passed offline checksum/envelope verification.

All five BVOL Spot scoring folds are exact, aligned one-minute catalogs. The
first curve fold is not: both assets lack 2021-08-13 and 2021-09-29 because the
official daily ZIP has fewer than 1,440 rows, and lack 2021-12-24 because its
minute grid is incomplete. Each asset therefore has 216,000 of 220,320
required bars and 4,320 missing intervals in that fold.

The missing curve execution bars are a hard pre-PnL gate, not a value to fill
or interpolate. Six source-ledger observations were frozen as
`research.v5.data_blocker.v1`. The review returned
`incomplete_spot_execution_catalog`, `pnl_evaluated=false`, and
`reject_v5_candidate`. No curve SignalEvent, SignalStore, Nautilus run, return,
or PnL was generated.

## BVOL diagnostic

The five complete BVOL folds generated independent BTC and ETH SignalStores.
Each asset/fold ran twice from clean detached commit
`d664df9fd996fb018a42892d92948a9b2ff1d000`. All 20 Nautilus manifests report
`git_dirty=false`; all 10 duplicate pairs reproduce, and strict sidecar,
lineage, Spot-long/flat, two-sleeve concurrency, and 100 USDT notional gates
are clean.

The locked cost result is nevertheless negative and unstable:

| fold | base PnL | stress PnL | base-positive months | closed positions |
|---|---:|---:|---:|---:|
| 2023 Aug-Dec | 18.584852 | 17.333998 | 4/5 | 40 |
| 2024 Jan-May | -19.167649 | -20.554966 | 2/5 | 35 |
| 2024 Aug-Dec | 4.704579 | 3.892737 | 3/5 | 27 |
| 2025 Jan-May | 6.319055 | 5.551972 | 3/5 | 28 |
| 2025 Aug-Dec | -11.626008 | -12.550112 | 1/5 | 30 |
| **aggregate** | **-1.185170** | **-6.326371** | **13/25** | **160** |

Only 3/5 folds have positive base and stress, below the required 4/5. Only
13/25 months are base-positive, below 15/25. Removing the best position leaves
-16.799085 USDT. BTC is positive after base/stress costs, but ETH is negative
at -9.310547/-11.633231 USDT, so one sleeve would be subsidizing the other.
These independently fail the aggregate-cost, fold-count, month-count,
concentration, and each-asset gates.

## Decision and boundaries

Both pre-registered v5 candidates are rejected. There is no selected candidate,
no parameter change, no replacement data provider, and no PnL-selected
ensemble. The 2026-08-01 through 2026-12-31 blind remains sealed; rejected
candidates will not have their blind PnL opened under this protocol.

The future collector may now be deployed only as the already-qualified,
credential-free, idempotent archive collector required by the registered
workflow. It collects raw evidence only and must not generate signals, run
Nautilus, modify SourcePolicy, resume testnet, or touch the live order path.
